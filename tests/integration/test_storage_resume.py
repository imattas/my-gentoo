import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from installer.authorization.plan import create_authorization_record
from installer.cli import main
from installer.planning.storage import render_storage_plan
from installer.stages.storage import apply_storage_plan


ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "config" / "workstation.yaml").read_text(encoding="utf-8"))
BY_ID = "/dev/disk/by-id/nvme-Samsung_SSD_990_PRO_0025384B3140238C"


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


class StorageResumeIntegrationTests(unittest.TestCase):
    @staticmethod
    def _journal(plan, *, started=None):
        return json.dumps(
            {
                "schema_version": 1,
                "plan_sha256": plan["sha256"],
                "command_count": len(plan["commands_for_review_only"]),
                "completed": [],
                "started": started,
                "last_verified_device_state": None,
            }
        )

    def _resume_with_state(self, report, state_contents, plan_report=None):
        plan = render_storage_plan(plan_report or report, CONFIG, BY_ID)
        if callable(state_contents):
            state_contents = state_contents(plan)
        authorization = create_authorization_record(plan, plan["sha256"], plan["target"]["serial"])
        runner = Mock()

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            state_dir = directory / "state"
            state_dir.mkdir()
            plan_path = directory / "plan.json"
            authorization_path = directory / "authorization.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            authorization_path.write_text(json.dumps(authorization), encoding="utf-8")
            (state_dir / "gentoo-storage-state.json").write_text(state_contents, encoding="utf-8")
            errors = io.StringIO()

            def run_stage(*args, **kwargs):
                return apply_storage_plan(
                    *args,
                    **kwargs,
                    runner=runner,
                    report_provider=lambda _: report,
                    state_location_check=lambda *_: None,
                    effective_uid=lambda: 0,
                )

            with (
                patch("installer.cli.load_config", return_value=CONFIG),
                patch("installer.cli.inspect_host", return_value=report),
                patch("installer.cli.platform.system", return_value="Linux"),
                patch("installer.cli.apply_storage_plan", side_effect=run_stage),
                redirect_stdout(io.StringIO()),
                redirect_stderr(errors),
            ):
                result = main(
                    [
                        "resume",
                        "storage",
                        "--plan",
                        str(plan_path),
                        "--authorization",
                        str(authorization_path),
                        "--confirm-plan-hash",
                        plan["sha256"],
                        "--confirm-serial",
                        plan["target"]["serial"],
                        "--confirm-erasure",
                        "ERASE-SYSTEM-DISK",
                        "--state-dir",
                        str(state_dir),
                        "--backup-verified",
                        "--recovery-media-verified",
                    ]
                )

        return result, errors.getvalue(), runner

    def test_cli_rejects_corrupt_storage_checkpoint_before_running_writes(self):
        result, errors, runner = self._resume_with_state(identified_blank_target(), "{truncated")

        self.assertEqual(result, 2)
        self.assertIn("storage checkpoint is unreadable or corrupt; refusing to continue", errors)
        runner.assert_not_called()

    def test_cli_rejects_changed_target_identity_before_running_writes(self):
        report = identified_blank_target()
        report["block_devices"][0]["serial"] = "CHANGED-DISK-SERIAL"
        result, errors, runner = self._resume_with_state(
            report,
            lambda plan: self._journal(plan),
            plan_report=identified_blank_target(),
        )

        self.assertEqual(result, 2)
        self.assertIn("authorized disk no longer has a unique exact identity", errors)
        runner.assert_not_called()

    def test_cli_does_not_replay_a_storage_command_marked_interrupted(self):
        result, errors, runner = self._resume_with_state(
            identified_blank_target(), lambda plan: self._journal(plan, started=0)
        )

        self.assertEqual(result, 2)
        self.assertIn("command 0 was interrupted after it began", errors)
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
