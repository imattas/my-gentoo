import io
from pathlib import Path
import struct
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from installer.cli import main


CMDLINE = (
    "rd.luks.name=12345678-1234-1234-1234-123456789abc=gentoo-root "
    "root=/dev/mapper/gentoo-root rootflags=subvol=@ rw"
)


def make_uki(kernel_payload: bytes = b"kernel") -> bytes:
    sections = (".linux", ".initrd", ".cmdline")
    payloads = {
        ".linux": kernel_payload,
        ".initrd": b"initrd",
        ".cmdline": CMDLINE.encode() + b"\0",
    }
    image = bytearray(0x500)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x40)
    image[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<H", image, 0x46, len(sections))
    struct.pack_into("<H", image, 0x54, 0xE0)
    struct.pack_into("<H", image, 0x58, 0x20B)
    struct.pack_into("<H", image, 0x9C, 10)
    for index, name in enumerate(sections):
        section = 0x138 + index * 40
        image[section : section + 8] = name.encode().ljust(8, b"\0")
        payload = payloads[name]
        raw_offset = 0x200 + index * 0x100
        struct.pack_into("<I", image, section + 16, len(payload))
        struct.pack_into("<I", image, section + 20, raw_offset)
        image[raw_offset : raw_offset + len(payload)] = payload
    return bytes(image)


class KernelRollbackIntegrationTests(unittest.TestCase):
    def _root(self, directory: Path) -> tuple[Path, Path]:
        root = directory / "target"
        linux = root / "efi/EFI/Linux"
        systemd = root / "efi/EFI/systemd"
        linux.mkdir(parents=True)
        systemd.mkdir(parents=True)
        (root / "etc/kernel").mkdir(parents=True)
        (root / "etc/kernel/cmdline").write_text(CMDLINE, encoding="utf-8")
        (systemd / "systemd-bootx64.efi").write_bytes(make_uki())
        return root, linux

    @staticmethod
    def _run_rollback(
        root: Path,
        *,
        efi_mounted: bool = True,
        expected_esp: str = "/dev/loop7p1",
        disk_serial: str = "GQ-BOOT-261015",
        root_source: str = "/dev/mapper/gentoo-root[/@] btrfs",
        command: str = "kernel-rollback",
        image: Path | None = None,
    ) -> int:
        def fake_run(argv, **_kwargs):
            if argv[0] == "findmnt":
                mountpoint = argv[argv.index("--mountpoint") + 1]
                if mountpoint == str(root / "efi"):
                    return SimpleNamespace(stdout="/dev/loop7p1 vfat\n", returncode=0)
                return SimpleNamespace(stdout=root_source + "\n", returncode=0)
            if argv[-1] == "/dev/disk/by-partlabel/GENTOO-ESP":
                return SimpleNamespace(stdout=f"{expected_esp}\n", returncode=0)
            if argv[0] == "lsblk" and "PKNAME" in argv:
                return SimpleNamespace(stdout="loop7\n", returncode=0)
            if argv[0] == "lsblk" and "SERIAL" in argv:
                return SimpleNamespace(stdout=f"{disk_serial}\n", returncode=0)
            if argv[0] == "readlink":
                return SimpleNamespace(stdout=f"{argv[-1]}\n", returncode=0)
            return SimpleNamespace(stdout="/dev/loop7\n", returncode=0)

        workstation = {"storage": {"system_target": {"serial": "GQ-BOOT-261015"}}}

        def fake_load_config(path):
            if Path(path).name == "kernel.yaml":
                return {"experimental_entry": "gentoo-experimental"}
            return workstation

        with (
            patch("installer.cli.platform.system", return_value="Linux"),
            patch("installer.cli.os.path.ismount", return_value=efi_mounted),
            patch("installer.cli.os.geteuid", return_value=0, create=True),
            patch("installer.cli.load_config", side_effect=fake_load_config),
            patch("installer.cli.subprocess.run", side_effect=fake_run),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            args = [command, "--root", str(root)]
            if image is not None:
                args.extend(["--image", str(image)])
            return main(args)

    def _experimental_target(self, directory: Path) -> tuple[Path, Path, bytes]:
        root, linux = self._root(directory)
        production = make_uki(b"production")
        (linux / "gentoo-production.efi").write_bytes(production)
        loader = root / "efi/loader"
        entries = loader / "entries"
        entries.mkdir(parents=True)
        (loader / "loader.conf").write_text("default gentoo-production\ntimeout 5\n")
        (entries / "gentoo-production.conf").write_text(
            "title Gentoo Workstation (production)\n"
            "efi /EFI/Linux/gentoo-production.efi\n"
        )
        candidate = directory / "experimental-candidate.efi"
        candidate.write_bytes(make_uki(b"experimental"))
        return root, candidate, production

    def test_cli_stages_experimental_uki_without_changing_production_or_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root, candidate, production_before = self._experimental_target(directory)

            result = self._run_rollback(
                root,
                command="kernel-stage-experimental",
                image=candidate,
            )

            efi = root / "efi"
            self.assertEqual(result, 0)
            self.assertEqual(
                (efi / "EFI/Linux/gentoo-production.efi").read_bytes(), production_before
            )
            self.assertEqual(
                (efi / "EFI/Linux/gentoo-experimental.efi").read_bytes(), candidate.read_bytes()
            )
            self.assertEqual(
                (efi / "loader/loader.conf").read_text(),
                "default gentoo-production\ntimeout 5\n",
            )
            self.assertIn(
                "efi /EFI/Linux/gentoo-experimental.efi",
                (efi / "loader/entries/gentoo-experimental.conf").read_text(),
            )

    def test_cli_refuses_experimental_staging_for_wrong_disk_serial(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root, candidate, production_before = self._experimental_target(directory)

            result = self._run_rollback(
                root,
                disk_serial="UNAUTHORIZED-DISK",
                command="kernel-stage-experimental",
                image=candidate,
            )

            self.assertEqual(result, 2)
            self.assertFalse((root / "efi/EFI/Linux/gentoo-experimental.efi").exists())
            self.assertEqual(
                (root / "efi/EFI/Linux/gentoo-production.efi").read_bytes(), production_before
            )

    def test_cli_restores_previous_uki_after_simulated_failed_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, linux = self._root(Path(temporary))
            previous = make_uki(b"known-good")
            (linux / "gentoo-fallback.efi").write_bytes(previous)
            production = linux / "gentoo-production.efi"
            production.write_bytes(b"incomplete update artifact")

            result = self._run_rollback(root)

            self.assertEqual(result, 0)
            self.assertEqual(production.read_bytes(), previous)

    def test_cli_refuses_corrupt_fallback_and_keeps_current_image_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, linux = self._root(Path(temporary))
            production = linux / "gentoo-production.efi"
            current = make_uki(b"current")
            production.write_bytes(current)
            (linux / "gentoo-fallback.efi").write_bytes(b"corrupt fallback")

            result = self._run_rollback(root)

            self.assertEqual(result, 2)
            self.assertEqual(production.read_bytes(), current)

    def test_cli_refuses_to_write_when_the_efi_mount_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, linux = self._root(Path(temporary))
            production = linux / "gentoo-production.efi"
            current = make_uki(b"current")
            production.write_bytes(current)
            (linux / "gentoo-fallback.efi").write_bytes(make_uki(b"previous"))

            result = self._run_rollback(root, efi_mounted=False)

            self.assertEqual(result, 2)
            self.assertEqual(production.read_bytes(), current)

    def test_cli_refuses_an_efi_mount_with_the_wrong_partition_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, linux = self._root(Path(temporary))
            production = linux / "gentoo-production.efi"
            current = make_uki(b"current")
            production.write_bytes(current)
            (linux / "gentoo-fallback.efi").write_bytes(make_uki(b"previous"))

            result = self._run_rollback(root, expected_esp="/dev/loop8p1")

            self.assertEqual(result, 2)
            self.assertEqual(production.read_bytes(), current)

    def test_cli_refuses_an_esp_on_a_disk_with_the_wrong_serial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, linux = self._root(Path(temporary))
            production = linux / "gentoo-production.efi"
            current = make_uki(b"current")
            production.write_bytes(current)
            (linux / "gentoo-fallback.efi").write_bytes(make_uki(b"previous"))

            result = self._run_rollback(root, disk_serial="UNAUTHORIZED-DISK")

            self.assertEqual(result, 2)
            self.assertEqual(production.read_bytes(), current)

    def test_cli_refuses_when_target_root_is_not_the_gentoo_btrfs_mapper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, linux = self._root(Path(temporary))
            production = linux / "gentoo-production.efi"
            current = make_uki(b"current")
            production.write_bytes(current)
            (linux / "gentoo-fallback.efi").write_bytes(make_uki(b"previous"))

            result = self._run_rollback(root, root_source="/dev/nvme1n1p2 btrfs")

            self.assertEqual(result, 2)
            self.assertEqual(production.read_bytes(), current)


if __name__ == "__main__":
    unittest.main()
