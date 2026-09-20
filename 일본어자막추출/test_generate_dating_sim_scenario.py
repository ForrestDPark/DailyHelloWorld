import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_dating_sim_scenario as generator  # noqa: E402


class DatingScenarioGenerationTest(unittest.TestCase):
    def _candidate(self):
        scenes = {}
        values = {
            "first": ("契約成立", "広告業界"),
            "walk": ("出張", "競合"),
            "quiet": ("手強い", "相談する"),
        }
        for location, (word, expression) in values.items():
            scenes[location] = {
                "lines": [
                    f"[{word}|よみ]と{expression}について話した。\n관련 이야기를 했다.",
                    "どう思いますか。\n어떻게 생각해요?",
                ],
                "choices": [
                    {"text": "いいですね。\n좋네요.", "tone": "positive"},
                    {"text": "分かりません。\n모르겠어요.", "tone": "negative"},
                ],
            }
        return {"scenes": scenes}

    def test_all_assigned_vocabulary_and_expressions_are_required(self):
        words = [
            {"ja": "契約成立", "reading": "けいやくせいりつ", "ko": "계약 성립"},
            {"ja": "出張", "reading": "しゅっちょう", "ko": "출장"},
            {"ja": "手強い", "reading": "てごわい", "ko": "만만치 않다"},
        ]
        expressions = [
            {"ja": "広告業界", "reading": "こうこくぎょうかい", "ko": "광고 업계"},
            {"ja": "競合", "reading": "きょうごう", "ko": "경쟁"},
            {"ja": "相談する", "reading": "そうだんする", "ko": "상담하다"},
        ]
        candidate = self._candidate()
        self.assertTrue(generator.validate_day(candidate, words, expressions))
        candidate["scenes"]["walk"]["lines"][0] = "[出張|しゅっちょう]へ行く。\n출장을 간다."
        self.assertFalse(generator.validate_day(candidate, words, expressions))
        self.assertIn("walk 표현: 競合", generator.missing_day_materials(candidate, words, expressions))

    def test_prompt_allows_adult_context_but_keeps_consent_boundary(self):
        prompt = generator.build_day_prompt("하루", 2, "재회", "관계를 이어간다", [], [], False)
        self.assertIn("모두 20세 이상의 성인", prompt)
        self.assertIn("합의된 연애·성적 맥락을\n  일괄 배제하지 않는다", prompt)
        self.assertIn("미성년자, 강압, 비동의, 착취", prompt)
        self.assertNotIn("노골적/성적/폭력적 내용은 절대", prompt)


if __name__ == "__main__":
    unittest.main()
