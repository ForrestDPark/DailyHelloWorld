import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import persona_worker


class SunziPipelineLockTest(unittest.TestCase):
    def test_stale_legacy_lock_is_reclaimed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / "pipeline.lock"
            status = root / "status.json"
            lock.mkdir()
            status.write_text(json.dumps({"pid": 999_999_999}), encoding="utf-8")
            with patch.object(persona_worker, "SUNZI_PIPELINE_LOCK_DIR", lock), patch.object(
                persona_worker, "SUNZI_PIPELINE_STATUS_PATH", status
            ):
                self.assertFalse(persona_worker._sunzi_pipeline_lock_active())
                self.assertFalse(lock.exists())

    def test_live_owner_lock_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "pipeline.lock"
            lock.mkdir()
            (lock / "owner_pid").write_text(str(os.getpid()), encoding="utf-8")
            with patch.object(persona_worker, "SUNZI_PIPELINE_LOCK_DIR", lock):
                self.assertTrue(persona_worker._sunzi_pipeline_lock_active())
                self.assertTrue(lock.exists())


if __name__ == "__main__":
    unittest.main()
