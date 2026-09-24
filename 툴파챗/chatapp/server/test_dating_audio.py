import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import dating_audio, dating_sim_story


class DatingAudioTests(unittest.TestCase):
    def test_spoken_text_removes_furigana_and_translation(self):
        text = "[私|わたし]はソイです。\n저는 소이예요."
        self.assertEqual(dating_audio.spoken_text(text), "私はソイです。")

    def test_spoken_text_strips_stray_bracket_without_pipe(self):
        # ★ 2026-09-24: "일본어 듣기 누르면 다 엣지tts로나와야하는데
        # 아닌것도있네" 확인 중 실측 — 일부 AI 생성 대사가 `[どこ]`처럼
        # "|" 없는 깨진 후리가나 태그를 담고 있어서, 정상 FURIGANA_RE만으론
        # 대괄호가 그대로 남아 TTS 카탈로그 매칭이 실패했다.
        self.assertEqual(dating_audio.spoken_text("もちろん。君が行きたいところなら[どこ]でも。"),
                          "もちろん。君が行きたいところならどこでも。")

    def test_spoken_text_strips_incomplete_furigana_delimiters(self):
        spoken = dating_audio.spoken_text("一緒に読みたいと[思|おもってたの。")
        self.assertNotIn("[", spoken)
        self.assertNotIn("|", spoken)

    def test_catalog_includes_ai_generated_book_dialogue_not_just_templates(self):
        # ★ 2026-09-24: "일본어 듣기 누르면 다 엣지tts로나와야하는데
        # 아닌것도있네" 신고 — build_catalog()가 고정 템플릿·기본 프로필
        # 이름 치환분만 커버해서, 실제 플레이에 나오는 작품별 AI 생성 대사는
        # 카탈로그에 없어 브라우저 기본 TTS로 조용히 폴백했다.
        # _all_book_stories()가 서재의 모든 작품(생성 시나리오 포함)을
        # 실제로 반영하는지 검증한다.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            epub = root / "TESTWORK.epub"
            epub.write_bytes(b"")
            library_dir = root / "library" / "TESTWORK"
            library_dir.mkdir(parents=True)
            unique_line = "これは音声카탈로그テスト専用のユニークな台詞です"
            scenario = {
                "content_version": 2,
                "coverage": {"complete": True},
                "days": {
                    str(day): {
                        "narration": "",
                        "scenes": {
                            loc: {
                                "lines": [unique_line] if (day == 1 and loc == "first") else ["普通の台詞です。"],
                                "choices": [{"text": "選択肢一", "affection": 1},
                                            {"text": "選択肢二", "affection": -1}],
                            }
                            for loc in ("first", "walk", "quiet")
                        },
                    }
                    for day in range(1, dating_sim_story.TOTAL_DAYS + 1)
                },
            }
            (library_dir / "dating_sim_scenario.json").write_text(
                json.dumps(scenario, ensure_ascii=False), encoding="utf-8",
            )
            with patch.object(dating_sim_story, "JAPANESE_EPUB_ROOT", root), \
                 patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", root / "library"), \
                 patch.object(dating_sim_story, "_book_title", return_value="TESTWORK"):
                catalog = dating_audio.build_catalog()
        self.assertIn(("female", unique_line), catalog)

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
