import tempfile
import unittest
from pathlib import Path

import contest_tracker as tracker


class ContestTrackerTest(unittest.TestCase):
    def test_priority(self):
        self.assertEqual(tracker.priority(5, 5, 5, 5), 100)
        self.assertEqual(tracker.priority(0, 0, 0, 0), 0)
        self.assertEqual(tracker.priority(4, 5, 4, 3), 80)

    def test_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            conn = tracker.connect(Path(directory) / "contests.db")
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            self.assertIn("contests", {row[0] for row in tables})


if __name__ == "__main__":
    unittest.main()
