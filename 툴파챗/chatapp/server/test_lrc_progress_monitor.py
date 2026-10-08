import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import app


class LrcProgressMonitorTests(unittest.TestCase):
    def test_terminal_monitor_stops_when_job_finishes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "progress.log").write_text("시작\n", encoding="utf-8")
            (directory / "status.json").write_text('{"status":"running"}', encoding="utf-8")
            with patch.object(app.subprocess, "Popen") as popen:
                app._open_lrc_progress_terminal(directory, "노래.mp3")
            command = (directory / "LRC 진행상황.command").read_text(encoding="utf-8")
            self.assertIn('"$STATUS" == complete', command)
            self.assertIn('"$STATUS" == failed', command)
            self.assertIn("kill $TAIL_PID", command)
            self.assertIn("LRC 생성과 적용이 완료됐습니다", command)
            popen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
