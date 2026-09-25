import json
import sys
import tempfile
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

    def test_all_assigned_vocabulary_expressions_and_grammar_are_required(self):
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
        grammar = [
            {"pattern": "～たらいい？", "explanation": "허락이나 제안을 묻는다."},
            {"pattern": "～みたい", "explanation": "추측을 나타낸다."},
            {"pattern": "～ばかり", "explanation": "한 동작의 반복을 강조한다."},
        ]
        candidate = self._candidate()
        evidence = {
            "first": ("～たらいい？", "どうしたらいいですか"),
            "walk": ("～みたい", "雨みたいですね"),
            "quiet": ("～ばかり", "話してばかりですね"),
        }
        for location, (pattern, quote) in evidence.items():
            candidate["scenes"][location]["lines"][0] += f" {quote}。"
            candidate["scenes"][location]["grammar_evidence"] = [{"pattern": pattern, "quote": quote}]
        self.assertTrue(generator.validate_day(candidate, words, expressions, grammar))
        candidate["scenes"]["walk"]["lines"][0] = "[出張|しゅっちょう]へ行く。\n출장을 간다."
        self.assertFalse(generator.validate_day(candidate, words, expressions, grammar))
        missing = generator.missing_day_materials(candidate, words, expressions, grammar)
        self.assertIn("walk 표현: 競合", missing)
        self.assertIn("walk 문법: ～みたい", missing)

    def test_load_grammar_patterns_extracts_tilde_forms(self):
        with tempfile.TemporaryDirectory() as directory:
            work_dir = Path(directory)
            cards = {"1-1": {"grammar": [
                "「～たらいい？」는 허락이나 제안을 묻는다.",
                "「～ばっかり」는 반복을 강조하고 「～みたい」는 추측을 나타낸다.",
            ]}}
            (work_dir / "scene_study_cards.json").write_text(json.dumps(cards), encoding="utf-8")
            loaded = generator.load_grammar_patterns(work_dir)
        self.assertEqual(["～たらいい？", "～ばっかり", "～みたい"],
                         [item["pattern"] for item in loaded])

    def test_prompt_allows_adult_context_but_keeps_consent_boundary(self):
        prompt = generator.build_day_prompt("하루", 2, "재회", "관계를 이어간다", [], [], False)
        self.assertIn("모두 20세 이상의 성인", prompt)
        self.assertIn("합의된 연애·성적 맥락을\n  일괄 배제하지 않는다", prompt)
        self.assertIn("미성년자, 강압, 비동의, 착취", prompt)
        self.assertNotIn("노골적/성적/폭력적 내용은 절대", prompt)

    def test_load_expressions_filters_out_verbatim_explicit_dialogue(self):
        """★ 2026-09-22 실제 사고: ABF-161_J의 학습카드 "핵심 표현" 216개
        중 7개가 원본에서 그대로 뽑힌 노골적 성적 대사(性欲が溜まる,
        パンツ履いてんのか？, 中に入れたい 등)였다. 시나리오 생성기가
        이걸 "일본어 어순·어휘를 유지해 그대로 쓰라"고 필수 재료로
        요구하자 Claude가 작성을 거부해 DAY 8이 5회 재시도 끝에 실패했다
        (실측). "핵심 표현은 이미 정제됐다"는 가정이 틀렸으므로, 로드
        단계에서 걸러야 한다 — 안전한 표현은 그대로 남아야 한다."""
        explicit_examples = [
            "性欲が溜まる", "舐め出したら", "中に入れたい", "パンツ履いてんのか？",
            "どんどんエッチになっちゃうね", "酒が染み込んでる", "全部飲んだっていい",
            "今の先生の中に出したいんでしょ?", "私を妊娠させていいの", "どこでも発情しちゃう",
        ]
        safe_examples = ["同棲を始めて3ヶ月", "近くのスーパー", "手作りの料理", "気にすんな"]
        with tempfile.TemporaryDirectory() as directory:
            work_dir = Path(directory)
            cards = {"1-1": {"expressions": [
                {"ja": ja, "reading": "よみ", "ko": "뜻"}
                for ja in explicit_examples + safe_examples
            ]}}
            (work_dir / "scene_study_cards.json").write_text(json.dumps(cards), encoding="utf-8")
            loaded = {e["ja"] for e in generator.load_expressions(work_dir)}
        for ja in explicit_examples:
            self.assertNotIn(ja, loaded, f"노골적 표현이 안 걸러짐: {ja}")
        for ja in safe_examples:
            self.assertIn(ja, loaded, f"안전한 표현이 잘못 걸러짐: {ja}")

    def test_repair_missing_materials_updates_scene_and_coverage_metadata(self):
        days = {
            "2": {
                "scenes": {
                    "first": {
                        "lines": ["今日は静かですね。\n오늘은 조용하네요."],
                        "vocab_used": [],
                        "expressions_used": [],
                    }
                }
            }
        }
        words = [{"ja": "約束", "reading": "やくそく", "ko": "약속"}]
        expressions = [{"ja": "また会いましょう", "reading": "またあいましょう", "ko": "다시 만나요"}]

        generator.repair_missing_materials(days, words, expressions)

        scene = days["2"]["scenes"]["first"]
        self.assertIn("約束", scene["lines"][0])
        self.assertIn("약속", scene["lines"][0])
        self.assertIn("また会いましょう", scene["lines"][0])
        self.assertIn("다시 만나요", scene["lines"][0])
        self.assertEqual(words, scene["vocab_used"])
        self.assertEqual(expressions, scene["expressions_used"])

    def test_select_shard_partitions_targets_without_overlap(self):
        targets = [Path(str(index)) for index in range(8)]
        shards = [generator.select_shard(targets, index, 3) for index in range(3)]
        self.assertEqual(targets, sorted(sum(shards, []), key=lambda item: int(item.name)))
        self.assertFalse(set(shards[0]) & set(shards[1]))
        with self.assertRaises(ValueError):
            generator.select_shard(targets, 3, 3)


if __name__ == "__main__":
    unittest.main()
