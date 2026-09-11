import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("pipeline_progress.py")


class PipelineProgressTest(unittest.TestCase):
    def run_progress(self, status_path, verse, progress, state="running"):
        env = os.environ.copy()
        env["SUNZI_PIPELINE_STATUS_PATH"] = str(status_path)
        subprocess.run(
            [
                "/usr/bin/python3", str(SCRIPT), "--verse", str(verse),
                "--mode", "light", "--progress", str(progress),
                "--stage", "테스트", "--state", state, "--pid", "123",
            ],
            check=True,
            env=env,
        )
        return json.loads(status_path.read_text(encoding="utf-8"))

    def test_same_run_keeps_start_time_but_new_verse_resets_it(self):
        with tempfile.TemporaryDirectory() as directory:
            status_path = Path(directory) / "status.json"
            first = self.run_progress(status_path, 28, 5)
            second = self.run_progress(status_path, 28, 20)
            self.assertEqual(first["started_at"], second["started_at"])

            old_started_at = "2020-01-01T00:00:00+00:00"
            second["started_at"] = old_started_at
            status_path.write_text(json.dumps(second), encoding="utf-8")
            next_verse = self.run_progress(status_path, 29, 5)
            self.assertNotEqual(old_started_at, next_verse["started_at"])
            self.assertEqual(29, next_verse["verse"])


if __name__ == "__main__":
    unittest.main()
