"""★ 2026-09-15: "웹에서 epub 열기 링크가 있으면 읽기할때 링크를 다읽는데
읽기할때 링크는 안읽었으면 좋겠어" 요청 — 일본어 선생님이 메시지마다 붙이는
"웹에서 EPUB 읽기: https://..." 원문 URL을 TTS 엔진이 그대로 읽어버리던
문제를 검증한다. 화면 표시용 원문은 그대로 두고 합성 직전 텍스트에서만
URL을 지운다."""
import unittest
from unittest.mock import patch

import persona_worker as pw


class TtsUrlStrippingTest(unittest.TestCase):
    def test_strip_urls_removes_bare_link_and_collapses_spacing(self):
        text = "웹에서 EPUB 읽기: https://chat.tulpa-chat.site/epub/?book=afb0410021e876673a90"
        self.assertEqual(pw._strip_urls_for_tts(text), "웹에서 EPUB 읽기:")

    def test_strip_urls_leaves_ordinary_text_untouched(self):
        text = "「それにしても、朝遅いわね」"
        self.assertEqual(pw._strip_urls_for_tts(text), text)

    def test_prepare_tts_text_strips_url_and_furigana_together(self):
        text = "見(み)て https://example.com/x"
        self.assertEqual(pw._prepare_tts_text(text, "ja"), "見て")

    def test_process_tts_job_skips_a_segment_that_is_only_a_link(self):
        job = {
            "id": 1, "message_id": 42, "persona_name": "일본어 선생님",
            "content": "「こんにちは」https://chat.tulpa-chat.site/epub/?book=abc「さようなら」",
        }
        seen_texts = []

        def fake_generate(text, persona_name, persona_cache):
            seen_texts.append(text)
            return f"/uploads/tts_{len(seen_texts)}.mp3", "edge"

        with patch.object(pw, "_generate_tts_for_text", side_effect=fake_generate), \
             patch.object(pw, "_concat_audio_files"), \
             patch.object(pw, "_api") as mock_api:
            pw.process_tts_job(job, {})
        self.assertEqual(len(seen_texts), 2)  # 링크만 남은 가운데 세그먼트는 건너뜀
        self.assertTrue(all("http" not in t for t in seen_texts))
        complete_call = mock_api.call_args
        self.assertEqual(complete_call.args[0], "/api/worker/tts_jobs/complete")
        self.assertNotIn("error", complete_call.args[2])

    def test_process_tts_job_reports_failure_when_entire_message_is_just_a_link(self):
        job = {
            "id": 2, "message_id": 43, "persona_name": "일본어 선생님",
            "content": "https://chat.tulpa-chat.site/epub/?book=abc",
        }
        with patch.object(pw, "_generate_tts_for_text") as mock_generate, \
             patch.object(pw, "_api") as mock_api:
            pw.process_tts_job(job, {})
        mock_generate.assert_not_called()
        complete_call = mock_api.call_args
        self.assertIn("error", complete_call.args[2])


if __name__ == "__main__":
    unittest.main()
