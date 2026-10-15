import hashlib
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from installer.cli import main
from installer.planning.storage import render_storage_plan
from installer.provisioning.packages import render_emerge_commands


ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "config" / "workstation.yaml").read_text(encoding="utf-8"))
PACKAGE_CONFIG = json.loads((ROOT / "config" / "packages.yaml").read_text(encoding="utf-8"))
BY_ID = "/dev/disk/by-id/nvme-Samsung_SSD_990_PRO_0025384B3140238C"
UNAVAILABLE_ATOM_LOG = 'emerge: there are no ebuilds to satisfy "sys-firmware/old".\n'


def identified_blank_target():
    target = CONFIG["storage"]["system_target"]
    return {
        "read_only": True,
        "firmware": {"boot_mode": "UEFI"},
        "target": {"status": "identified", "match_count": 1},
        "block_devices": [
            {
                "type": "disk",
                "path": "/dev/nvme0n1",
                "model": target["model"],
                "serial": target["serial"],
                "size": 2_000_396_321_280,
                "by_id": [BY_ID],
                "pttype": None,
                "fstype": None,
                "mountpoints": [],
                "children": [],
            }
        ],
    }


class PackageRecoveryCliIntegrationTests(unittest.TestCase):
    def _fixture(self, directory: Path):
        report = identified_blank_target()
        plan = render_storage_plan(report, CONFIG, BY_ID)
        plan_path = directory / "storage-plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        state_dir = directory / "state"
        logs_dir = state_dir / "logs"
        logs_dir.mkdir(parents=True)
        commands = render_emerge_commands(PACKAGE_CONFIG, "base", non_interactive=True)
        (state_dir / "gentoo-storage-state.json").write_text(
            json.dumps({"plan_sha256": plan["sha256"]}), encoding="utf-8"
        )
        (state_dir / "gentoo-base-config-state.json").write_text(
            json.dumps({"storage_plan_sha256": plan["sha256"]}), encoding="utf-8"
        )
        (state_dir / "gentoo-packages-base.json").write_text(
            json.dumps(
                {
                    "package_set": "base",
                    "complete": False,
                    "started": 1,
                    "completed": [0],
                    "command_sha256": "old-command-hash",
                    "storage_plan_sha256": plan["sha256"],
                }
            ),
            encoding="utf-8",
        )
        failed_log = logs_dir / "packages-base-command-1-attempt-02.log"
        failed_log.write_text(UNAVAILABLE_ATOM_LOG, encoding="utf-8")
        events = [
            {"event": "package-command-started", "package_set": "base", "index": 0, "argv": commands[0]},
            {
                "event": "package-command-failed",
                "package_set": "base",
                "index": 1,
                "log": str(failed_log),
            },
        ]
        (state_dir / "gentoo-package-events.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
        )
        digest = hashlib.sha256(failed_log.read_bytes()).hexdigest()
        return state_dir, plan_path, plan, digest

    def _run_cli(self, state_dir, plan_path, digest):
        errors = io.StringIO()
        with (
            patch("installer.cli.load_config", return_value=CONFIG),
            patch("installer.cli.ensure_state_location_off_target"),
            redirect_stdout(io.StringIO()),
            redirect_stderr(errors),
        ):
            result = main(
                [
                    "recover-package",
                    "--set",
                    "base",
                    "--storage-plan",
                    str(plan_path),
                    "--state-dir",
                    str(state_dir),
                    "--command-index",
                    "1",
                    "--confirm-log-sha256",
                    digest,
                    "--non-interactive",
                ]
            )
        return result, errors.getvalue()

    def test_cli_reopens_checkpoint_for_hash_confirmed_unavailable_atom(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_dir, plan_path, _, digest = self._fixture(Path(temporary))

            result, errors = self._run_cli(state_dir, plan_path, digest)

            journal = json.loads((state_dir / "gentoo-packages-base.json").read_text())
            self.assertEqual(result, 0, errors)
            self.assertEqual(journal["completed"], [0])
            self.assertIsNone(journal["started"])
            self.assertEqual(len(journal["recoveries"]), 1)

    def test_cli_keeps_checkpoint_closed_when_failed_log_hash_differs(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_dir, plan_path, _, digest = self._fixture(Path(temporary))

            result, errors = self._run_cli(state_dir, plan_path, "0" * 64)

            journal = json.loads((state_dir / "gentoo-packages-base.json").read_text())
            self.assertEqual(result, 2)
            self.assertIn("log hash does not match", errors)
            self.assertEqual(journal["completed"], [0])
            self.assertEqual(journal["started"], 1)
            self.assertNotIn("recoveries", journal)
            self.assertNotEqual(digest, "0" * 64)


if __name__ == "__main__":
    unittest.main()
