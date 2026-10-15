import unittest
import json
from pathlib import Path
import struct
import tempfile

from installer.provisioning.configuration import (
    build_target_files,
    render_fstab,
    render_kernel_cmdline,
    render_make_conf,
    select_kde_systemd_profile,
    write_target_files,
)
from installer.provisioning.packages import render_emerge_commands
from installer.provisioning.packages import (
    _is_unified_kernel_image,
    _uki_has_command_line,
    validate_boot_assets,
)


_UKI_CMDLINE = "rd.luks.name=12345678-1234-1234-1234-123456789abc=gentoo-root root=/dev/mapper/gentoo-root rootflags=subvol=@ rw"


def efi_application_image(subsystem=10, sections=(".linux", ".initrd", ".cmdline")):
    payloads = {".linux": b"kernel", ".initrd": b"initrd", ".cmdline": _UKI_CMDLINE.encode() + b"\0"}
    data = bytearray(0x400)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x40)
    data[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<H", data, 0x46, len(sections))
    struct.pack_into("<H", data, 0x54, 0xE0)
    struct.pack_into("<H", data, 0x58, 0x20B)
    struct.pack_into("<H", data, 0x9C, subsystem)
    for index, name in enumerate(sections):
        offset = 0x138 + index * 40
        data[offset : offset + 8] = name.encode("ascii")[:8].ljust(8, b"\0")
        payload = payloads.get(name, b"payload")
        raw_offset = 0x200 + index * 0x100
        struct.pack_into("<I", data, offset + 16, len(payload))
        struct.pack_into("<I", data, offset + 20, raw_offset)
        data[raw_offset : raw_offset + len(payload)] = payload
    return bytes(data)


class ProvisioningConfigurationTests(unittest.TestCase):
    @staticmethod
    def _prepare_boot_root(root):
        cmdline = root / "etc" / "kernel" / "cmdline"
        cmdline.parent.mkdir(parents=True, exist_ok=True)
        cmdline.write_text(_UKI_CMDLINE, encoding="utf-8")

    def test_make_conf_uses_conservative_zen4_flags_and_memory_bounded_jobs(self):
        config = {
            "compiler_flags_candidate": "-O2 -pipe -march=znver4",
            "global_use": ["X", "wayland", "vulkan"],
            "video_cards": ["amdgpu", "radeonsi"],
        }

        result = render_make_conf(config, cpu_threads=16, memory_gib=64)

        self.assertIn('CFLAGS="-O2 -pipe -march=znver4"', result)
        self.assertIn("getbinpkg", result)
        self.assertIn("binpkg-request-signature", result)
        self.assertIn('MAKEOPTS="-j8"', result)
        self.assertIn('--jobs=4', result)
        self.assertNotIn("-Ofast", result)
        self.assertNotIn("-flto", result)

    def test_fstab_mounts_expected_subvolumes_and_efi(self):
        result = render_fstab(
            "ABCD-1234",
            "12345678-1234-1234-1234-123456789abd",
        )

        self.assertIn("UUID=ABCD-1234 /efi vfat", result)
        for path, subvol in (("/", "@"), ("/home", "@home"), ("/.snapshots", "@snapshots"), ("/var/log", "@log")):
            self.assertIn(f"UUID=12345678-1234-1234-1234-123456789abd {path} btrfs", result)
            self.assertIn(f"subvol={subvol}", result)

    def test_kernel_cmdline_uses_actual_luks_uuid_and_btrfs_root_subvolume(self):
        result = render_kernel_cmdline("12345678-1234-1234-1234-123456789abc")

        self.assertEqual(
            result,
            "rd.luks.name=12345678-1234-1234-1234-123456789abc=gentoo-root "
            "root=/dev/mapper/gentoo-root rootflags=subvol=@ rw",
        )
        with self.assertRaises(ValueError):
            render_kernel_cmdline("guess-me")

    def test_profile_selection_requires_one_exact_current_kde_systemd_profile(self):
        output = """
Available profile symlink targets:
  [1] default/linux/amd64/23.0/systemd *
  [2] default/linux/amd64/23.0/desktop/plasma/systemd
"""

        self.assertEqual(
            select_kde_systemd_profile(output, "23.0"),
            "2",
        )
        with self.assertRaises(ValueError):
            select_kde_systemd_profile(output, "24.0")

    def test_generated_target_files_use_real_ids_and_contain_no_secrets(self):
        root = Path(__file__).resolve().parents[2]
        workstation = json.loads((root / "config" / "workstation.yaml").read_text())
        packages = json.loads((root / "config" / "packages.yaml").read_text())
        kernel = json.loads((root / "config" / "kernel.yaml").read_text())

        files = build_target_files(
            workstation,
            packages,
            kernel,
            efi_uuid="ABCD-1234",
            btrfs_uuid="12345678-1234-1234-1234-123456789abd",
            luks_uuid="12345678-1234-1234-1234-123456789abe",
            cpu_threads=16,
            memory_gib=64,
            timezone="America/New_York",
            hostname="gentoo-workstation",
        )

        self.assertIn("etc/kernel/cmdline", files)
        self.assertIn("etc/portage/binrepos.conf/gentoobinhost.conf", files)
        self.assertIn("sync-type = rsync", files["etc/portage/repos.conf/gentoo.conf"])
        self.assertIn("x86-64-v3", files["etc/portage/binrepos.conf/gentoobinhost.conf"])
        self.assertIn("sys-libs/ncurses -gpm", files["etc/portage/package.use/gentoo-workstation"])
        self.assertEqual(
            files["etc/portage/package.accept_keywords/gentoo-workstation"],
            "sys-kernel/linux-firmware ~amd64\n",
        )
        self.assertEqual(
            files["etc/portage/package.license/gentoo-workstation"],
            "sys-kernel/linux-firmware linux-fw-redistributable\n",
        )
        self.assertIn(
            "sys-kernel/installkernel systemd dracut systemd-boot ukify uki",
            files["etc/portage/package.use/gentoo-workstation"],
        )
        self.assertIn("rd.luks.name=12345678-1234-1234-1234-123456789abe=gentoo-root", files["etc/kernel/cmdline"])
        self.assertIn("/home", files["etc/fstab"])
        self.assertNotIn("password", "\n".join(files.values()).lower())

    def test_target_writer_only_accepts_declared_relative_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_target_files(root, {"etc/hostname": "gentoo\n"})
            self.assertEqual((root / "etc/hostname").read_text(), "gentoo\n")
            with self.assertRaises(ValueError):
                write_target_files(root, {"../../outside": "no\n"})

    def test_package_commands_are_argv_and_gate_world_update_to_base_stage(self):
        root = Path(__file__).resolve().parents[2]
        packages = json.loads((root / "config" / "packages.yaml").read_text())

        base = render_emerge_commands(packages, "base", "/mnt/gentoo")
        desktop = render_emerge_commands(packages, "desktop", "/mnt/gentoo")
        gaming = render_emerge_commands(packages, "gaming", "/mnt/gentoo")

        self.assertTrue(all(isinstance(command, list) for command in base + desktop + gaming))
        self.assertTrue(any("@world" in command for command in base))
        self.assertNotIn("sys-kernel/gentoo-kernel-bin", base[1])
        self.assertIn("sys-kernel/gentoo-kernel-bin", base[2])
        self.assertLess(base.index(next(command for command in base if "sys-fs/btrfs-progs" in command)), 2)
        self.assertFalse(any("@world" in command for command in desktop))
        self.assertIn("kde-plasma/plasma-meta", desktop[0])
        self.assertEqual(gaming[1][-2:], ["enable", "steam-overlay"])
        self.assertEqual(gaming[2][-3:], ["sync", "-r", "steam-overlay"])
        self.assertIn("games-util/steam-launcher::steam-overlay", gaming[-1])
        scripted = render_emerge_commands(packages, "desktop", non_interactive=True)
        self.assertTrue(all("--ask=n" in command for command in scripted[:1]))
        self.assertTrue(all("--ask" not in command for command in scripted))
        self.assertFalse(any("--sync" in command for command in base))
        with self.assertRaises(ValueError):
            render_emerge_commands(packages, "wipe", "/mnt/gentoo")

    def test_versioned_portage_uki_is_promoted_to_production_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_boot_root(root)
            efi = root / "efi" / "EFI"
            (efi / "systemd").mkdir(parents=True)
            (efi / "Linux").mkdir()
            (efi / "systemd" / "systemd-bootx64.efi").write_bytes(efi_application_image())
            generated = efi / "Linux" / "gentoo-6.18.54.efi"
            generated.write_bytes(efi_application_image())
            self.assertTrue(_is_unified_kernel_image(generated))
            self.assertTrue(_uki_has_command_line(generated, _UKI_CMDLINE.split()))

            self.assertEqual(validate_boot_assets(root), ["gentoo-production.efi"])
            self.assertEqual(
                (efi / "Linux" / "gentoo-production.efi").read_bytes(), generated.read_bytes()
            )

    def test_boot_validation_requires_systemd_boot_and_a_production_uki(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_boot_root(root)
            efi = root / "efi" / "EFI"
            (efi / "systemd").mkdir(parents=True)
            (efi / "systemd" / "systemd-bootx64.efi").write_bytes(efi_application_image())
            with self.assertRaises(RuntimeError):
                validate_boot_assets(root)
            (efi / "Linux").mkdir()
            production = efi / "Linux" / "gentoo-production.efi"
            production.write_bytes(efi_application_image())
            self.assertTrue(_is_unified_kernel_image(production))
            self.assertTrue(_uki_has_command_line(production, _UKI_CMDLINE.split()))

            self.assertEqual(validate_boot_assets(root), ["gentoo-production.efi"])

    def test_boot_validation_rejects_non_pe_or_non_efi_production_images(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_boot_root(root)
            efi = root / "efi" / "EFI"
            (efi / "systemd").mkdir(parents=True)
            (efi / "Linux").mkdir()
            (efi / "systemd" / "systemd-bootx64.efi").write_bytes(efi_application_image())
            production = efi / "Linux" / "gentoo-production.efi"
            production.write_bytes(b"not a PE/COFF image")

            with self.assertRaisesRegex(RuntimeError, "valid EFI application"):
                validate_boot_assets(root)

            production.write_bytes(efi_application_image(3))
            with self.assertRaisesRegex(RuntimeError, "valid EFI application"):
                validate_boot_assets(root)

            production.write_bytes(efi_application_image(sections=(".linux",)))
            with self.assertRaisesRegex(RuntimeError, "valid EFI application"):
                validate_boot_assets(root)

    def test_boot_validation_rejects_a_uki_with_a_stale_luks_command_line(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_boot_root(root)
            efi = root / "efi" / "EFI"
            (efi / "systemd").mkdir(parents=True)
            (efi / "Linux").mkdir()
            (efi / "systemd" / "systemd-bootx64.efi").write_bytes(efi_application_image())
            stale = _UKI_CMDLINE.replace("12345678", "aaaaaaaa")
            image = bytearray(efi_application_image())
            offset = 0x200 + 2 * 0x100
            payload = stale.encode() + b"\0"
            image[offset : offset + len(payload)] = payload
            section = 0x138 + 2 * 40
            struct.pack_into("<I", image, section + 16, len(payload))
            (efi / "Linux" / "gentoo-production.efi").write_bytes(image)

            with self.assertRaisesRegex(RuntimeError, "valid EFI application"):
                validate_boot_assets(root)


if __name__ == "__main__":
    unittest.main()
