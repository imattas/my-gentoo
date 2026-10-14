import unittest
from pathlib import PurePosixPath
from types import SimpleNamespace

from installer.stages.user import user_creation_commands, validate_target_mounts


class UserSetupTests(unittest.TestCase):
    def test_user_setup_uses_interactive_password_command_without_secret_arguments(self):
        commands = user_creation_commands("ian")

        self.assertEqual(commands[0][-1], "ian")
        self.assertEqual(commands[1], ["chroot", "/mnt/gentoo", "passwd", "ian"])
        self.assertFalse(any("password" in arg.lower() for command in commands for arg in command))

    def test_usernames_are_validated_before_becoming_command_arguments(self):
        for username in ("root;rm", "../ian", "Ian Name", "-option"):
            with self.subTest(username=username), self.assertRaises(ValueError):
                user_creation_commands(username)

    def test_user_stage_requires_the_authorized_root_and_efi_mounts(self):
        outputs = iter((
            "/mnt/gentoo /dev/mapper/gentoo-root btrfs\n",
            "/mnt/gentoo/efi /dev/nvme0n1p1 vfat\n",
            "/dev/nvme0n1p1\n",
            "/dev/nvme1n1p1\n",
        ))

        def runner(argv, **kwargs):
            return SimpleNamespace(stdout=next(outputs))

        with self.assertRaisesRegex(RuntimeError, "planned GENTOO-ESP"):
            validate_target_mounts(PurePosixPath("/mnt/gentoo"), runner)


if __name__ == "__main__":
    unittest.main()
