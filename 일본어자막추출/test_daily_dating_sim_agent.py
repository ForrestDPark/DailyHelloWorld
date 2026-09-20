import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("run_daily_dating_sim_agent.py")
SPEC = importlib.util.spec_from_file_location("daily_dating", MODULE_PATH)
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


class DailyDatingSimAgentTests(unittest.TestCase):
    def test_candidates_only_include_incomplete_works_with_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            incomplete = root / "A"
            incomplete.mkdir()
            (incomplete / "scene_study_cards.json").write_text("{}", encoding="utf-8")
            usable = root / "B"
            usable.mkdir()
            (usable / "scene_study_cards.json").write_text('{"1": {}}', encoding="utf-8")
            with patch.object(agent, "LIBRARY", root):
                self.assertEqual(agent.candidates(), [usable])

    def test_images_complete_requires_all_42_assignments_and_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            image_dir = work / "dating_sim_images"
            image_dir.mkdir()
            (image_dir / "portrait.png").write_bytes(b"x" * 1024)
            assignments = {}
            for day in range(1, 15):
                for loc in ("first", "walk", "quiet"):
                    name = f"{day}-{loc}.png"
                    (image_dir / name).write_bytes(b"x" * 1024)
                    assignments[f"{day}:{loc}"] = name
            (image_dir / "manifest.json").write_text(json.dumps({
                "status": "complete", "portrait": "portrait.png", "assignments": assignments,
            }), encoding="utf-8")
            self.assertTrue(agent.images_complete(work))
            (image_dir / "1-first.png").unlink()
            self.assertFalse(agent.images_complete(work))


if __name__ == "__main__":
    unittest.main()
