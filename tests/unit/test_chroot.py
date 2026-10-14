from pathlib import Path
import tempfile
import unittest
from unittest.mock import call

from installer.stages.chroot import mounted_chroot


class MountedChrootTests(unittest.TestCase):
    def test_mounts_and_unmounts_live_pseudofilesystems_and_resolver(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "gentoo"
            (root / "etc").mkdir(parents=True)
            resolver_source = Path(directory) / "live-resolv.conf"
            resolver_source.write_text("nameserver 127.0.0.1\n")
            resolver = root / "etc" / "resolv.conf"
            resolver.symlink_to("../run/systemd/resolve/stub-resolv.conf")
            calls = []

            def runner(argv, **kwargs):
                calls.append(argv)
                if argv[0] == "mountpoint":
                    return type("Result", (), {"returncode": 1})()
                return type("Result", (), {"returncode": 0})()

            with mounted_chroot(
                root, runner=runner, require_fixed_root=False, resolver_source=resolver_source
            ):
                self.assertTrue(resolver.is_file())
                self.assertFalse(resolver.is_symlink())

            self.assertTrue(resolver.is_symlink())
            self.assertEqual(resolver.readlink(), Path("../run/systemd/resolve/stub-resolv.conf"))
            self.assertIn(["mount", "--rbind", "/dev", str(root / "dev")], calls)
            self.assertIn(["mount", "--rbind", "/proc", str(root / "proc")], calls)
            self.assertIn(["mount", "--rbind", "/sys", str(root / "sys")], calls)
            self.assertIn(["mount", "--rbind", "/run", str(root / "run")], calls)
            self.assertIn(["mount", "--bind", str(resolver_source), str(resolver)], calls)
            self.assertIn(["umount", "--recursive", str(root / "dev")], calls)

    def test_does_not_adopt_unexpected_preexisting_mount(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "gentoo"
            (root / "etc").mkdir(parents=True)
            resolver_source = Path(directory) / "live-resolv.conf"
            resolver_source.write_text("nameserver 127.0.0.1\n")
            calls = []

            def runner(argv, **kwargs):
                calls.append(argv)
                return type("Result", (), {"returncode": 0})()

            with self.assertRaisesRegex(RuntimeError, "already mounted"):
                with mounted_chroot(
                    root,
                    runner=runner,
                    require_fixed_root=False,
                    resolver_source=resolver_source,
                ):
                    pass
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
