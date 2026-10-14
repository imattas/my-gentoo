import json
import unittest
from pathlib import Path

from installer.discovery.devices import identify_system_target
from installer.discovery.host import parse_cpu_model

ROOT = Path(__file__).resolve().parents[2]


class WorkstationConfigTests(unittest.TestCase):
    def test_system_target_is_exact_990_pro_and_data_drive_is_not_writable_target(self):
        config = json.loads((ROOT / "config" / "workstation.yaml").read_text())
        target = config["storage"]["system_target"]

        self.assertEqual(target["model"], "Samsung SSD 990 PRO with Heatsink 2TB")
        self.assertEqual(target["serial"], "0025_384B_3140_238C.")
        self.assertEqual(config["storage"]["data_disk_policy"], "never-auto-target")
        self.assertNotIn("writable_target", config["storage"]["data_disk"])

    def test_target_requires_one_exact_model_and_serial_match(self):
        config = json.loads((ROOT / "config" / "workstation.yaml").read_text())
        device = {
            "type": "disk",
            "model": "Samsung SSD 990 PRO with Heatsink 2TB",
            "serial": "0025_384B_3140_238C.",
            "path": "/dev/nvme0n1",
        }

        result = identify_system_target([device], config)

        self.assertEqual(result["status"], "identified")
        self.assertEqual(result["device"]["path"], "/dev/nvme0n1")

    def test_duplicate_exact_target_matches_are_ambiguous(self):
        config = json.loads((ROOT / "config" / "workstation.yaml").read_text())
        device = {
            "type": "disk",
            "model": "Samsung SSD 990 PRO with Heatsink 2TB",
            "serial": "0025_384B_3140_238C.",
        }

        result = identify_system_target([device, dict(device)], config)

        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["device"])

    def test_cpu_model_comes_from_linux_cpuinfo(self):
        info = "processor : 0\nvendor_id : AuthenticAMD\nmodel name : AMD Ryzen 7 7800X3D\n"

        self.assertEqual(parse_cpu_model(info), "AMD Ryzen 7 7800X3D")


if __name__ == "__main__":
    unittest.main()
