import unittest
import json
import tempfile
from pathlib import Path
from pathlib import PurePosixPath
from types import SimpleNamespace
from unittest.mock import patch

from installer.stages.user import setup_user, user_creation_commands, validate_target_mounts


class UserSetupTests(unittest.TestCase):
    def test_resume_after_account_creation_retries_only_interrupted_password_step(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            plan = {"sha256": "plan-hash", "target": {"serial": "target", "by_id": "/dev/disk/by-id/target"}}
            workstation = {"storage": {"system_target": {"serial": "target"}, "data_disk": {"serial": "data"}}}
            (state / "gentoo-storage-state.json").write_text(json.dumps({"plan_sha256": "plan-hash"}))
            (state / "gentoo-packages-desktop.json").write_text(json.dumps({"complete": True, "storage_plan_sha256": "plan-hash"}))
            commands = user_creation_commands("rehearsal")
            (state / "gentoo-user-state.json").write_text(json.dumps({
                "username": "rehearsal", "storage_plan_sha256": "plan-hash",
                "command_sha256": __import__("hashlib").sha256(json.dumps(commands, separators=(",", ":")).encode()).hexdigest(),
                "completed": [0], "started": 1, "complete": False,
            }))
            calls = []

            def runner(argv, **kwargs):
                calls.append((argv, kwargs))
                if argv[2] == "getent":
                    return SimpleNamespace(returncode=0, stdout="rehearsal:x:1000:1000::/home/rehearsal:/bin/bash\n")
                return SimpleNamespace(returncode=0)

            with patch("installer.stages.user.plan_hash_matches", return_value=True), \
                    patch("installer.stages.user.verify_root_mapping"), \
                    patch("installer.stages.user.validate_target_mounts"):
                result = setup_user(
                    "rehearsal", plan, state, workstation, runner=runner,
                    root=PurePosixPath("/mnt/gentoo"),
                    state_location_check=lambda *args: None,
                )

            self.assertEqual(result["status"], "complete")
            self.assertEqual([call[0] for call in calls if call[0][2] != "getent"], [commands[1]])
            self.assertTrue(json.loads((state / "gentoo-user-state.json").read_text())["complete"])

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
