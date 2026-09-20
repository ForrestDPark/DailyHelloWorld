import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("refine_translations.py")
SPEC = importlib.util.spec_from_file_location("refine_translations", MODULE_PATH)
refine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refine)


class FakeResponse:
    status_code = 200

    def json(self):
        return [[
            ["[[[T0000]]]\n안녕하세요.\n", ""],
            ["[[[T0001]]]\n고마워요.", ""],
        ]]


class TranslationRecoveryTests(unittest.TestCase):
    @patch.object(refine.requests, "post", return_value=FakeResponse())
    def test_google_batch_preserves_sentence_alignment(self, post):
        result = refine._google_batch(["こんにちは", "ありがとう"])
        self.assertEqual(result, ["안녕하세요.", "고마워요."])
        self.assertEqual(post.call_count, 1)

    @patch.object(refine, "_google_batch", return_value=["안녕하세요.", "고마워요."])
    def test_failed_rows_are_recovered_and_saved_to_memory(self, batch):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "transcript_part1.jsonl"
            rows = [
                {"path": transcript, "line": 0, "data": {"ja": "こんにちは", "ko": "[번역 실패]"}},
                {"path": transcript, "line": 1, "data": {"ja": "ありがとう", "ko": "[번역 실패]"}},
            ]
            memory = {}
            with patch.object(refine, "MEMORY_PATH", Path(tmp) / "memory.json"):
                count, unavailable = refine.recover_google_failures(rows, memory)
            self.assertEqual(count, 2)
            self.assertFalse(unavailable)
            self.assertEqual(memory["ありがとう"], "고마워요.")
            saved = [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(saved[0]["ko"], "안녕하세요.")


if __name__ == "__main__":
    unittest.main()
