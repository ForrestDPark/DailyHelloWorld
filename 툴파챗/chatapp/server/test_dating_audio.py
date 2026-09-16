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
        self.assertGreaterEqual(len(catalog), 100)
        self.assertEqual(len(catalog), len(set(catalog)))
        self.assertEqual({role for role, _text in catalog}, {"female", "male"})
        self.assertTrue(all(dating_audio.JAPANESE_RE.search(text) for _role, text in catalog))
        self.assertTrue(all("|" not in text and "[" not in text for _role, text in catalog))

    def test_manifest_uses_stable_clip_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            text = "今日はいい天気ですね。"
            filename = dating_audio.clip_name("female", text)
            dating_audio.write_manifest(
                output, {"female": {text: f"/dating-sim/audio/{filename}"}, "male": {}}
            )
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["model"], "gpt-4o-mini-tts")
            self.assertEqual(manifest["voices"], {"female": "marin", "male": "cedar"})
            self.assertTrue(manifest["ai_generated"])
            self.assertEqual(manifest["clips"]["female"][text], f"/dating-sim/audio/{filename}")

    def test_edge_manifest_identifies_provider_and_gendered_voices(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            dating_audio.write_manifest(output, {"female": {}, "male": {}}, provider="edge")
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["provider"], "edge")
            self.assertEqual(manifest["model"], "edge-tts")
            self.assertEqual(manifest["voices"], dating_audio.EDGE_VOICES)


if __name__ == "__main__":
    unittest.main()
