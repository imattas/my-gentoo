import copy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from installer.authorization.plan import create_authorization_record
from installer.planning.storage import render_storage_plan
from installer.stages.storage import (
    apply_storage_plan,
    assert_state_device_is_unprotected,
    next_unstarted_command,
    validate_stage_authorization,
)
from installer.stages.stage3 import (
    extract_sha512,
    extract_verified_stage3,
    verify_stage3,
    verify_root_mapping,
)


PLAN = {
    "target": {
        "model": "Samsung SSD 990 PRO with Heatsink 2TB",
        "serial": "disk-serial",
        "by_id": "/dev/disk/by-id/nvme-samsung-disk",
    },
    "commands_for_review_only": [["sgdisk", "--zap-all", "/dev/disk/by-id/nvme-samsung-disk"]],
}
PLAN["sha256"] = hashlib.sha256(
    json.dumps(PLAN, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
AUTHORIZATION = {
    "plan_sha256": PLAN["sha256"],
    "target": PLAN["target"],
    "authorized_operation": "partition-and-format-system-disk",
    "single_disk_scope": True,
}
ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "config" / "workstation.yaml").read_text())
BY_ID = "/dev/disk/by-id/nvme-Samsung_SSD_990_PRO_0025384B3140238C"


def workstation_report():
    return {
        "read_only": True,
        "firmware": {"boot_mode": "UEFI"},
        "target": {"status": "identified", "match_count": 1},
        "block_devices": [
            {
                "type": "disk",
                "path": "/dev/nvme0n1",
                "model": CONFIG["storage"]["system_target"]["model"],
                "serial": CONFIG["storage"]["system_target"]["serial"],
                "size": 2_000_396_321_280,
                "by_id": [BY_ID],
                "pttype": None,
                "fstype": None,
                "mountpoints": [],
                "children": [],
            }
        ],
    }


class StorageStageTests(unittest.TestCase):
    def test_state_location_identity_tolerates_null_partition_serial(self):
        from installer.stages.storage import assert_state_device_is_unprotected

        assert_state_device_is_unprotected(
            [
                {"path": "/dev/vda", "type": "disk", "serial": "GQ-RUNNER"},
                {"path": "/dev/vda1", "type": "part", "serial": None},
            ],
            "/dev/vdb",
            ("GQ-TARGET", "GQ-DATA"),
        )

    def test_storage_stage_requires_all_explicit_confirmations(self):
        self.assertTrue(
            validate_stage_authorization(
                PLAN, AUTHORIZATION, PLAN["sha256"], "disk-serial", "ERASE-SYSTEM-DISK"
            )["valid"]
        )

    def test_state_storage_refuses_the_separately_protected_data_ssd(self):
        with self.assertRaisesRegex(RuntimeError, "separately protected"):
            assert_state_device_is_unprotected(
                [{"path": "/dev/nvme1n1", "serial": CONFIG["storage"]["data_disk"]["serial"]}],
                "/dev/nvme0n1",
                (CONFIG["storage"]["system_target"]["serial"], CONFIG["storage"]["data_disk"]["serial"]),
                realpath=lambda path: path,
            )
        self.assertFalse(
            validate_stage_authorization(
                PLAN, AUTHORIZATION, "b" * 64, "disk-serial", "ERASE-SYSTEM-DISK"
            )["valid"]
        )
        self.assertFalse(
            validate_stage_authorization(
                PLAN, AUTHORIZATION, PLAN["sha256"], "disk-serial", ""
            )["valid"]
        )

    def test_authorization_rejects_commands_changed_after_plan_hashing(self):
        changed = copy.deepcopy(PLAN)
        changed["commands_for_review_only"][0][-1] = "/dev/sda"

        result = validate_stage_authorization(
            changed,
            AUTHORIZATION,
            PLAN["sha256"],
            "disk-serial",
            "ERASE-SYSTEM-DISK",
        )

        self.assertFalse(result["valid"])

    def test_interrupted_started_command_is_never_replayed_automatically(self):
        journal = {"completed": [], "started": 0}
        with self.assertRaises(RuntimeError):
            next_unstarted_command(PLAN["commands_for_review_only"], journal)

    def test_partition_labels_may_be_unavailable_before_partition_probe(self):
        from installer.stages.storage import _is_expected_partition_settling

        report = workstation_report()
        plan = render_storage_plan(report, CONFIG, BY_ID)
        state = {
            "path": "/dev/nvme0n1",
            "model": CONFIG["storage"]["system_target"]["model"],
            "serial": CONFIG["storage"]["system_target"]["serial"],
            "size_bytes": report["block_devices"][0]["size"],
            "partition_table": "gpt",
            "filesystem": None,
            "mountpoints": [],
            "children": [
                {"path": "/dev/nvme0n1p1", "partlabel": None, "size": 2 * 1024**3, "fstype": None, "mountpoints": []},
                {"path": "/dev/nvme0n1p2", "partlabel": None, "size": 1_800_000_000_000, "fstype": None, "mountpoints": []},
            ],
        }

        self.assertTrue(
            _is_expected_partition_settling(
                state,
                [0, 1, 2, 3],
                4,
                plan,
                plan["commands_for_review_only"],
            )
        )

    def test_partition_labels_must_bind_esp_and_root_to_planned_partition_numbers(self):
        from installer.stages.storage import _assert_expected_partition_table

        report = workstation_report()
        plan = render_storage_plan(report, CONFIG, BY_ID)
        state = {
            "path": "/dev/nvme0n1",
            "model": CONFIG["storage"]["system_target"]["model"],
            "serial": CONFIG["storage"]["system_target"]["serial"],
            "size_bytes": report["block_devices"][0]["size"],
            "partition_table": "gpt",
            "filesystem": None,
            "mountpoints": [],
            "children": [
                {"path": "/dev/nvme0n1p1", "partlabel": "GENTOO-CRYPTROOT", "size": 2 * 1024**3, "fstype": None, "mountpoints": []},
                {"path": "/dev/nvme0n1p2", "partlabel": "GENTOO-ESP", "size": 1_800_000_000_000, "fstype": None, "mountpoints": []},
            ],
        }

        with self.assertRaisesRegex(RuntimeError, "partition label does not match the authorized layout"):
            _assert_expected_partition_table(state, plan)

    def test_completed_commands_are_skipped_when_resuming(self):
        journal = {"completed": [0], "started": None}
        self.assertIsNone(next_unstarted_command(PLAN["commands_for_review_only"], journal))

    def test_stage3_digest_parser_selects_the_exact_archive_entry(self):
        digest = "a" * 128
        signed_text = (
            "-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA256\n\n"
            f"# SHA512 HASH\n{digest} stage3.tar.xz\n"
            f"# BLAKE2B HASH\n{'b' * 128} stage3.tar.xz\n"
            "-----BEGIN PGP SIGNATURE-----\n"
        )

        self.assertEqual(extract_sha512(signed_text, "stage3.tar.xz"), digest)
        with self.assertRaises(ValueError):
            extract_sha512(signed_text, "other.tar.xz")

    def test_stage3_verification_checks_file_hash_after_signature_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            archive = directory / "stage3.tar.xz"
            archive.write_bytes(b"verified test payload")
            digest = hashlib.sha512(archive.read_bytes()).hexdigest()
            digests = directory / "stage3.tar.xz.DIGESTS"
            digests.write_text(
                f"-----BEGIN PGP SIGNED MESSAGE-----\n\n# SHA512 HASH\n{digest} stage3.tar.xz\n"
                "-----BEGIN PGP SIGNATURE-----\n",
                encoding="utf-8",
            )
            signature = directory / "stage3.tar.xz.asc"
            keyring = directory / "gentoo-release.asc"
            signature.touch()
            keyring.touch()
            runner = Mock()

            result = verify_stage3(archive, digests, signature, keyring, runner=runner)

        self.assertEqual(result["sha512"], digest)
        self.assertEqual(result["signature_status"], "verified")
        self.assertEqual(runner.call_count, 3)

    def test_stage3_extraction_requires_verified_artifact_and_exact_btrfs_mount(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            archive = directory / "stage3.tar.xz"
            archive.touch()
            target = directory / "gentoo"
            target.mkdir()
            state_dir = directory / "recovery"
            state_dir.mkdir()
            def fake_tar(_argv, check):
                self.assertTrue(check)
                (target / "etc").mkdir()
                (target / "etc" / "gentoo-release").touch()
                (target / "bin").mkdir()
                (target / "bin" / "bash").touch()

            runner = Mock(side_effect=fake_tar)

            with patch("installer.stages.stage3.GENTOO_ROOT", target):
                result = extract_verified_stage3(
                    archive,
                    directory / "stage3.DIGESTS",
                    directory / "stage3.asc",
                    directory / "release.asc",
                    target,
                    state_dir,
                    "/dev/disk/by-id/nvme-samsung",
                    protected_serials=(
                        CONFIG["storage"]["system_target"]["serial"],
                        CONFIG["storage"]["data_disk"]["serial"],
                    ),
                    verifier=lambda *args: {"signature_status": "verified", "sha512": "f" * 128},
                    mount_probe=lambda _: {"target": str(target), "source": "/dev/mapper/gentoo-root[/@]", "fstype": "btrfs"},
                    runner=runner,
                    state_location_check=lambda *_: None,
                )

        self.assertEqual(result["status"], "complete")
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(runner.call_args.args[0][0], "tar")

    def test_stage3_requires_open_luks_mapping_to_trace_to_authorized_disk(self):
        def runner(argv, **_kwargs):
            if argv[0] == "cryptsetup":
                return type("Result", (), {"stdout": "device: /dev/nvme0n1p2\n"})()
            if argv[0] == "lsblk" and "PARTLABEL" in argv:
                return type("Result", (), {"stdout": "GENTOO-CRYPTROOT\n"})()
            return type("Result", (), {"stdout": "/dev/nvme0n1p2\n/dev/nvme0n1\n"})()

        verify_root_mapping(
            "/dev/disk/by-id/nvme-Samsung_SSD_990_PRO_0025384B3140238C",
            runner=runner,
            realpath=lambda path: {
                "/dev/disk/by-id/nvme-Samsung_SSD_990_PRO_0025384B3140238C": "/dev/nvme0n1",
                "/dev/disk/by-partlabel/GENTOO-CRYPTROOT": "/dev/nvme0n1p2",
                "/dev/nvme0n1p2": "/dev/nvme0n1p2",
                "/dev/nvme0n1": "/dev/nvme0n1",
            }.get(path, path),
        )

        def wrong_disk_runner(argv, **kwargs):
            result = runner(argv, **kwargs)
            if argv[0] == "lsblk" and "PARTLABEL" not in argv:
                result.stdout = "/dev/nvme1n1p2\n/dev/nvme1n1\n"
            return result

        with self.assertRaisesRegex(RuntimeError, "authorized Samsung disk"):
            verify_root_mapping(
                "/dev/disk/by-id/nvme-Samsung_SSD_990_PRO_0025384B3140238C",
                runner=wrong_disk_runner,
                realpath=lambda path: {
                    "/dev/disk/by-id/nvme-Samsung_SSD_990_PRO_0025384B3140238C": "/dev/nvme0n1",
                    "/dev/disk/by-partlabel/GENTOO-CRYPTROOT": "/dev/nvme0n1p2",
                }.get(path, path),
            )

    def test_authorized_storage_run_executes_only_planned_commands_with_mock_runner(self):
        report = workstation_report()
        plan = render_storage_plan(report, CONFIG, BY_ID)
        approval = create_authorization_record(plan, plan["sha256"], plan["target"]["serial"])
        runner = Mock()
        with tempfile.TemporaryDirectory() as temporary:
            result_dir = Path(temporary)
            with (
                patch("installer.stages.storage.platform.system", return_value="Linux"),
                patch("installer.stages.storage._assert_partition_aliases_match_target"),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                result = apply_storage_plan(
                    plan,
                    approval,
                    CONFIG,
                    report,
                    result_dir,
                    confirmed_sha256=plan["sha256"],
                    confirmed_serial=plan["target"]["serial"],
                    erasure_phrase="ERASE-SYSTEM-DISK",
                    backup_verified=True,
                    recovery_media_verified=True,
                    runner=runner,
                    report_provider=lambda _: report,
                    state_location_check=lambda *_: None,
                    effective_uid=lambda: 0,
                )
            self.assertTrue(Path(result["event_log"]).is_file())

        self.assertEqual(result["status"], "complete")
        self.assertEqual(runner.call_count, len(plan["commands_for_review_only"]))

    def test_interrupted_storage_command_is_not_retried(self):
        report = workstation_report()
        plan = render_storage_plan(report, CONFIG, BY_ID)
        approval = create_authorization_record(plan, plan["sha256"], plan["target"]["serial"])
        failing_runner = Mock(side_effect=__import__("subprocess").CalledProcessError(1, ["sgdisk"]))
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            with patch("installer.stages.storage.platform.system", return_value="Linux"):
                with self.assertRaises(__import__("subprocess").CalledProcessError):
                    apply_storage_plan(
                        plan,
                        approval,
                        CONFIG,
                        report,
                        state_dir,
                        confirmed_sha256=plan["sha256"],
                        confirmed_serial=plan["target"]["serial"],
                        erasure_phrase="ERASE-SYSTEM-DISK",
                        backup_verified=True,
                        recovery_media_verified=True,
                        runner=failing_runner,
                        report_provider=lambda _: report,
                        state_location_check=lambda *_: None,
                        effective_uid=lambda: 0,
                    )
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    apply_storage_plan(
                        plan,
                        approval,
                        CONFIG,
                        report,
                        state_dir,
                        confirmed_sha256=plan["sha256"],
                        confirmed_serial=plan["target"]["serial"],
                        erasure_phrase="ERASE-SYSTEM-DISK",
                        backup_verified=True,
                        recovery_media_verified=True,
                        runner=Mock(),
                        report_provider=lambda _: report,
                        state_location_check=lambda *_: None,
                        effective_uid=lambda: 0,
                    )
        self.assertEqual(failing_runner.call_count, 1)


if __name__ == "__main__":
    unittest.main()
