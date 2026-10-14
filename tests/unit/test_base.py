import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from installer.stages.base import sync_gentoo_repository


class GentooRepositorySyncTests(unittest.TestCase):
    def test_sync_checkpoint_makes_retry_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "target"
            state = base / "state"
            timestamp = root / "var/db/repos/gentoo/metadata/timestamp.chk"
            state.mkdir()
            timestamp.parent.mkdir(parents=True)

            def sync(_argv, **_kwargs):
                timestamp.write_text("20261014T220000Z\n")

            runner = Mock(side_effect=sync)
            first = sync_gentoo_repository(root, state, "plan-hash", runner=runner)
            second = sync_gentoo_repository(root, state, "plan-hash", runner=runner)

        self.assertEqual(first["status"], "synced")
        self.assertEqual(second["status"], "already-synced")
        runner.assert_called_once_with(
            ["chroot", str(root), "emerge-webrsync"], check=True
        )

    def test_sync_checkpoint_rejects_corrupted_repository_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "target"
            state = base / "state"
            timestamp = root / "var/db/repos/gentoo/metadata/timestamp.chk"
            state.mkdir()
            timestamp.parent.mkdir(parents=True)
            timestamp.write_text("current\n")
            (state / "gentoo-repo-sync-state.json").write_text(
                '{"complete":true,"storage_plan_sha256":"plan-hash",'
                '"repository_timestamp":"old"}',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "checkpoint is corrupt"):
                sync_gentoo_repository(root, state, "plan-hash", runner=Mock())


if __name__ == "__main__":
    unittest.main()
