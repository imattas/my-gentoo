import json
import unittest
from pathlib import Path

from installer.planning.storage import render_storage_plan, validate_storage_plan
from installer.authorization.plan import create_authorization_record


ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "config" / "workstation.yaml").read_text())
BY_ID = "/dev/disk/by-id/nvme-Samsung_SSD_990_PRO_0025384B3140238C"


def report():
    return {
        "read_only": True,
        "firmware": {"boot_mode": "UEFI"},
        "target": {"status": "identified", "match_count": 1},
        "block_devices": [
            {
                "type": "disk",
                "path": "/dev/nvme0n1",
                "model": "Samsung SSD 990 PRO with Heatsink 2TB",
                "serial": "0025_384B_3140_238C.",
                "size": 2000396321280,
                "by_id": [BY_ID],
                "pttype": "gpt",
                "mountpoints": [],
                "children": [
                    {"path": "/dev/nvme0n1p1", "size": 1073741824, "mountpoints": [None]}
                ],
            }
        ],
    }


class StoragePlanTests(unittest.TestCase):
    def test_plan_binds_layout_and_destructive_effects_to_exact_by_id_and_serial(self):
        plan = render_storage_plan(report(), CONFIG, BY_ID)

        self.assertEqual(plan["target"]["by_id"], BY_ID)
        self.assertEqual(plan["target"]["serial"], "0025_384B_3140_238C.")
        self.assertEqual(plan["layout"]["efi_size_bytes"], 2 * 1024**3)
        self.assertEqual(plan["layout"]["root_encryption"], "LUKS2")
        self.assertIn("existing partition data will be destroyed", plan["effects"])
        self.assertTrue(
            any(command[:3] == ["btrfs", "subvolume", "create"]
                for command in plan["commands_for_review_only"])
        )
        self.assertEqual(len(plan["sha256"]), 64)

    def test_validation_requires_backup_and_recovery_and_unchanged_device_state(self):
        observed = report()
        plan = render_storage_plan(observed, CONFIG, BY_ID)

        self.assertFalse(validate_storage_plan(plan, observed, False, False, CONFIG)["valid"])
        self.assertTrue(validate_storage_plan(plan, observed, True, True, CONFIG)["valid"])

        changed = report()
        changed["block_devices"][0]["children"].append(
            {"path": "/dev/nvme0n1p2", "size": 1000, "mountpoints": []}
        )
        self.assertFalse(validate_storage_plan(plan, changed, True, True, CONFIG)["valid"])

    def test_validation_rejects_a_self_consistent_plan_with_altered_layout(self):
        import hashlib

        plan = render_storage_plan(report(), CONFIG, BY_ID)
        plan["layout"]["efi_size_bytes"] = 1024**3
        body = {key: value for key, value in plan.items() if key != "sha256"}
        plan["sha256"] = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        result = validate_storage_plan(plan, report(), True, True, CONFIG)

        self.assertFalse(result["valid"])
        self.assertIn("plan content differs from the deterministic configured plan", result["issues"])

    def test_plan_rejects_a_by_id_path_not_linked_to_exact_target(self):
        with self.assertRaises(ValueError):
            render_storage_plan(report(), CONFIG, "/dev/disk/by-id/nvme-other-disk")

    def test_null_model_from_lsblk_round_trips_through_plan_validation(self):
        import copy

        config = copy.deepcopy(CONFIG)
        config["storage"]["system_target"]["model"] = ""
        config["storage"]["system_target"]["serial"] = "GQ-TARGET"
        observed = report()
        observed["block_devices"][0]["model"] = None
        observed["block_devices"][0]["serial"] = "GQ-TARGET"
        observed["block_devices"][0]["by_id"] = ["/dev/disk/by-id/virtio-GQ-TARGET"]
        plan = render_storage_plan(
            observed, config, "/dev/disk/by-id/virtio-GQ-TARGET"
        )

        self.assertTrue(validate_storage_plan(plan, observed, True, True, config)["valid"])

    def test_authorization_requires_exact_plan_hash_and_disk_serial(self):
        plan = render_storage_plan(report(), CONFIG, BY_ID)
        with self.assertRaises(ValueError):
            create_authorization_record(plan, "wrong-hash", plan["target"]["serial"])
        with self.assertRaises(ValueError):
            create_authorization_record(plan, plan["sha256"], "different-disk")
        approval = create_authorization_record(
            plan, plan["sha256"], plan["target"]["serial"]
        )
        self.assertEqual(approval["plan_sha256"], plan["sha256"])
        self.assertEqual(approval["authorized_operation"], "partition-and-format-system-disk")


if __name__ == "__main__":
    unittest.main()
