import json
import tempfile
import unittest
from pathlib import Path

from server import dating_audio


class DatingAudioTests(unittest.TestCase):
    def test_spoken_text_removes_furigana_and_translation(self):
        text = "[私|わたし]はソイです。\n저는 소이예요."
        self.assertEqual(dating_audio.spoken_text(text), "私はソイです。")

    def test_catalog_contains_all_unique_japanese_lines(self):
        catalog = dating_audio.build_catalog()
        self.assertGreaterEqual(len(catalog), 120)
        self.assertEqual(len(catalog), len(set(catalog)))
        self.assertTrue(all(dating_audio.JAPANESE_RE.search(text) for text in catalog))
        self.assertTrue(all("|" not in text and "[" not in text for text in catalog))

    def test_manifest_uses_stable_clip_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            text = "今日はいい天気ですね。"
            filename = dating_audio.clip_name(text)
            dating_audio.write_manifest(
                output, {text: f"/dating-sim/audio/{filename}"}
            )
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["model"], "gpt-4o-mini-tts")
            self.assertEqual(manifest["voice"], "marin")
            self.assertTrue(manifest["ai_generated"])
            self.assertEqual(manifest["clips"][text], f"/dating-sim/audio/{filename}")


if __name__ == "__main__":
    unittest.main()
