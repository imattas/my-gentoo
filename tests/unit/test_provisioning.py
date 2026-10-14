import unittest
import json
from pathlib import Path
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
from installer.provisioning.packages import validate_boot_assets


class ProvisioningConfigurationTests(unittest.TestCase):
    def test_make_conf_uses_conservative_zen4_flags_and_memory_bounded_jobs(self):
        config = {
            "compiler_flags_candidate": "-O2 -pipe -march=znver4",
            "global_use": ["X", "wayland", "vulkan"],
            "video_cards": ["amdgpu", "radeonsi"],
        }

        result = render_make_conf(config, cpu_threads=16, memory_gib=64)

        self.assertIn('CFLAGS="-O2 -pipe -march=znver4"', result)
        self.assertIn('MAKEOPTS="-j8"', result)
        self.assertIn('--jobs=4', result)
        self.assertNotIn("-Ofast", result)
        self.assertNotIn("-flto", result)

    def test_fstab_mounts_expected_subvolumes_and_efi(self):
        result = render_fstab(
            "12345678-1234-1234-1234-123456789abc",
            "12345678-1234-1234-1234-123456789abd",
        )

        self.assertIn("UUID=12345678-1234-1234-1234-123456789abc /efi vfat", result)
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
  [2] default/linux/amd64/23.0/desktop/kde/systemd
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
            efi_uuid="12345678-1234-1234-1234-123456789abc",
            btrfs_uuid="12345678-1234-1234-1234-123456789abd",
            luks_uuid="12345678-1234-1234-1234-123456789abe",
            cpu_threads=16,
            memory_gib=64,
            timezone="America/New_York",
            hostname="gentoo-workstation",
        )

        self.assertIn("etc/kernel/cmdline", files)
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

        self.assertTrue(all(isinstance(command, list) for command in base + desktop))
        self.assertTrue(any("@world" in command for command in base))
        self.assertFalse(any("@world" in command for command in desktop))
        self.assertIn("kde-plasma/plasma-meta", desktop[0])
        with self.assertRaises(ValueError):
            render_emerge_commands(packages, "wipe", "/mnt/gentoo")

    def test_boot_validation_requires_systemd_boot_and_a_production_uki(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            efi = root / "efi" / "EFI"
            (efi / "systemd").mkdir(parents=True)
            (efi / "systemd" / "systemd-bootx64.efi").write_bytes(b"bootloader")
            with self.assertRaises(RuntimeError):
                validate_boot_assets(root)
            (efi / "Linux").mkdir()
            (efi / "Linux" / "gentoo-production.efi").write_bytes(b"uki")

            self.assertEqual(validate_boot_assets(root), ["gentoo-production.efi"])


if __name__ == "__main__":
    unittest.main()
