"""★ 2026-09-15: "읽어주기 왜안돼지" 진단 — OpenAI TTS 계정이 크레딧 소진
상태라 「」로 나뉜 세그먼트마다 매번 실패한 뒤 edge-tts로 넘어가는 과정이
반복돼, 세그먼트가 많은 메시지(일본어 스터디의 예문 여러 개 등)는 클라이언트의
30초 폴링 타임아웃을 넘겨버렸다(실측: 메시지 #1343 57초). 크레딧 소진을 한 번
확인하면 쿨다운 동안 OpenAI 호출 자체를 건너뛰는 회로차단기를 검증한다."""
import io
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

import persona_worker as pw


class OpenAiTtsQuotaBreakerTest(unittest.TestCase):
    def setUp(self):
        # 전역 쿨다운 상태가 테스트 간에 새지 않도록 항상 초기화한다.
        pw._OPENAI_TTS_QUOTA_EXHAUSTED_UNTIL = 0.0

    def tearDown(self):
        pw._OPENAI_TTS_QUOTA_EXHAUSTED_UNTIL = 0.0

    def _quota_error(self):
        body = b'{"error": {"message": "You have no credits remaining. Add credits to continue."}}'
        return urllib.error.HTTPError(
            "https://api.openai.com/v1/audio/speech", 429, "Too Many Requests",
            {}, io.BytesIO(body),
        )

    def test_quota_error_trips_breaker_and_skips_next_call_without_network(self):
        with patch.object(pw, "OPENAI_API_KEY", "sk-test"), \
             patch("persona_worker.urllib.request.urlopen", side_effect=self._quota_error()):
            with self.assertRaises(RuntimeError):
                pw._generate_openai_tts("こんにちは", "일본어 선생님", {})
        self.assertGreater(pw._OPENAI_TTS_QUOTA_EXHAUSTED_UNTIL, 0.0)
        # 두 번째 호출은 네트워크를 아예 타지 않고 즉시 실패해야 한다.
        with patch.object(pw, "OPENAI_API_KEY", "sk-test"), \
             patch("persona_worker.urllib.request.urlopen") as mock_urlopen:
            with self.assertRaises(RuntimeError):
                pw._generate_openai_tts("こんにちは", "일본어 선생님", {})
            mock_urlopen.assert_not_called()

    def test_breaker_resets_after_cooldown_expires(self):
        pw._OPENAI_TTS_QUOTA_EXHAUSTED_UNTIL = pw.time.time() - 1  # 이미 만료됨
        response = MagicMock()
        response.read.return_value = b"fake-mp3-bytes"
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with patch.object(pw, "OPENAI_API_KEY", "sk-test"), \
             patch("persona_worker.urllib.request.urlopen", return_value=response) as mock_urlopen, \
             patch.object(pw.Path, "write_bytes"):
            pw._generate_openai_tts("こんにちは", "일본어 선생님", {})
        mock_urlopen.assert_called_once()

    def test_non_quota_error_does_not_trip_breaker(self):
        body = b'{"error": {"message": "invalid_request_error: bad voice name"}}'
        error = urllib.error.HTTPError(
            "https://api.openai.com/v1/audio/speech", 400, "Bad Request", {}, io.BytesIO(body),
        )
        with patch.object(pw, "OPENAI_API_KEY", "sk-test"), \
             patch("persona_worker.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(RuntimeError):
                pw._generate_openai_tts("こんにちは", "일본어 선생님", {})
        self.assertEqual(pw._OPENAI_TTS_QUOTA_EXHAUSTED_UNTIL, 0.0)


if __name__ == "__main__":
    unittest.main()
