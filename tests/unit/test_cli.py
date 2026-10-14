import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from installer.cli import main


class InstallerCliTests(unittest.TestCase):
    def test_inspect_uses_the_explicit_workstation_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "workstation.json"
            config = {"storage": {"system_target": {"serial": "qemu-test-only"}}}
            config_path.write_text(json.dumps(config), encoding="utf-8")
            report = {
                "target": {"status": "identified", "match_count": 1},
                "read_only": True,
            }

            with patch("installer.cli.inspect_host", return_value=report) as inspect:
                with redirect_stdout(io.StringIO()):
                    result = main(["--config", str(config_path), "inspect"])

        self.assertEqual(result, 0)
        inspect.assert_called_once_with(config)


if __name__ == "__main__":
    unittest.main()
