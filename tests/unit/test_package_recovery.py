import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from installer.provisioning.packages import recover_failed_package_checkpoint, render_emerge_commands


class FailedPackageCheckpointRecoveryTests(unittest.TestCase):
    def _fixture(self, root: Path, log_text: str, package_set="base", command_index=1):
        state = root / "state"
        logs = state / "logs"
        logs.mkdir(parents=True)
        package_config = json.loads(
            (Path(__file__).resolve().parents[2] / "config" / "packages.yaml").read_text()
        )
        commands = render_emerge_commands(package_config, package_set, non_interactive=True)
        state_path = state / f"gentoo-packages-{package_set}.json"
        state_path.write_text(json.dumps({
            "package_set": package_set, "complete": False, "started": command_index,
            "completed": list(range(command_index)), "command_sha256": "old-digest", "storage_plan_sha256": "plan-hash",
        }))
        (state / "gentoo-storage-state.json").write_text(json.dumps({"plan_sha256": "plan-hash"}))
        (state / "gentoo-base-config-state.json").write_text(json.dumps({"storage_plan_sha256": "plan-hash"}))
        log = logs / "packages-base-command-1-attempt-02.log"
        log.write_text(log_text)
        events = [
            {"event": "package-command-started", "package_set": package_set, "index": 0, "argv": commands[0]},
            {"event": "package-command-failed", "package_set": package_set, "index": command_index, "log": str(log)},
        ]
        (state / "gentoo-package-events.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events)
        )
        return state, package_config, log

    def test_recovers_only_hash_confirmed_known_systemd_sysv_helper_failure(self):
        failed = (
            "Synchronizing state of NetworkManager.service with SysV service script.\n"
            "Executing: /usr/lib/systemd/systemd-sysv-install --root=/mnt/gentoo enable NetworkManager\n"
            "chroot: failed to run command '/usr/sbin/update-rc.d': No such file or directory\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            state, package_config, log = self._fixture(
                Path(temporary), failed, package_set="desktop"
            )
            digest = hashlib.sha256(log.read_bytes()).hexdigest()
            with self.assertRaisesRegex(RuntimeError, "explicit repair path"):
                recover_failed_package_checkpoint(
                    "desktop", package_config, state, 1, digest, "plan-hash", non_interactive=True
                )
            result = recover_failed_package_checkpoint(
                "desktop", package_config, state, 1, digest, "plan-hash",
                non_interactive=True, desktop_repair=lambda: "systemd service links repaired\\n",
            )
            self.assertEqual(result["status"], "ready-to-resume")
            journal = json.loads((state / "gentoo-packages-desktop.json").read_text())
            self.assertIsNone(journal["started"])
            events = [
                json.loads(line)
                for line in (state / "gentoo-package-events.jsonl").read_text().splitlines()
            ]
            self.assertTrue(any(event["event"] == "package-desktop-services-repaired" for event in events))

    def test_recovers_only_hash_confirmed_premerge_unavailable_atom_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            state, package_config, log = self._fixture(
                Path(temporary), 'emerge: there are no ebuilds to satisfy "sys-firmware/old".\n'
            )
            digest = hashlib.sha256(log.read_bytes()).hexdigest()
            result = recover_failed_package_checkpoint(
                "base", package_config, state, 1, digest, "plan-hash", non_interactive=True
            )
            journal = json.loads((state / "gentoo-packages-base.json").read_text())
            self.assertEqual(result["status"], "ready-to-resume")
            self.assertIsNone(journal["started"])
            self.assertEqual(journal["completed"], [0])
            self.assertEqual(len(journal["recoveries"]), 1)

    def test_recovers_hash_confirmed_premerge_masked_atom_resolution(self):
        with tempfile.TemporaryDirectory() as temporary:
            state, package_config, log = self._fixture(
                Path(temporary),
                '!!! All ebuilds that could satisfy "cat/pkg" have been masked.\n'
                "!!! One of the following masked packages is required to complete your request:\n",
            )
            digest = hashlib.sha256(log.read_bytes()).hexdigest()
            result = recover_failed_package_checkpoint(
                "base", package_config, state, 1, digest, "plan-hash", non_interactive=True
            )
            self.assertEqual(result["status"], "ready-to-resume")

    def test_kernel_postinst_recovery_requires_and_records_explicit_repair(self):
        failed = (
            "ERROR: sys-kernel/gentoo-kernel-bin-6.18.54 failed (postinst phase):\n"
            "dracut: Module 'btrfs' cannot be installed.\n"
            "Run emerge --config '=sys-kernel/gentoo-kernel-bin-6.18.54'\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            state, package_config, log = self._fixture(Path(temporary), failed)
            digest = hashlib.sha256(log.read_bytes()).hexdigest()
            with self.assertRaisesRegex(RuntimeError, "explicit repair path"):
                recover_failed_package_checkpoint(
                    "base", package_config, state, 1, digest, "plan-hash", non_interactive=True
                )
            result = recover_failed_package_checkpoint(
                "base", package_config, state, 1, digest, "plan-hash",
                non_interactive=True, kernel_repair=lambda: "btrfs-progs installed; kernel config succeeded\n",
            )
            self.assertEqual(result["status"], "ready-to-resume")
            events = [
                json.loads(line)
                for line in (state / "gentoo-package-events.jsonl").read_text().splitlines()
            ]
            self.assertTrue(any(event["event"] == "package-kernel-postinst-repaired" for event in events))

    def test_refuses_recovery_for_a_different_storage_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            state, package_config, log = self._fixture(
                Path(temporary), 'emerge: there are no ebuilds to satisfy "cat/pkg".\n'
            )
            digest = hashlib.sha256(log.read_bytes()).hexdigest()
            with self.assertRaisesRegex(RuntimeError, "checkpoints do not identify"):
                recover_failed_package_checkpoint(
                    "base", package_config, state, 1, digest, "other-plan", non_interactive=True
                )

    def test_rejects_unconfirmed_hash_and_any_log_that_started_a_merge(self):
        for log_text, wrong_hash in (
            ('emerge: there are no ebuilds to satisfy "cat/pkg".\n', True),
            ('emerge: there are no ebuilds to satisfy "cat/pkg".\n>>> emerge (1 of 1) cat/pkg\n', False),
        ):
            with self.subTest(wrong_hash=wrong_hash):
                with tempfile.TemporaryDirectory() as temporary:
                    state, package_config, log = self._fixture(Path(temporary), log_text)
                    digest = hashlib.sha256(log.read_bytes()).hexdigest()
                    if wrong_hash:
                        digest = "0" * 64
                    with self.assertRaises(RuntimeError):
                        recover_failed_package_checkpoint(
                            "base", package_config, state, 1, digest, "plan-hash", non_interactive=True
                        )
                    journal = json.loads((state / "gentoo-packages-base.json").read_text())
                    self.assertEqual(journal["started"], 1)


if __name__ == "__main__":
    unittest.main()
