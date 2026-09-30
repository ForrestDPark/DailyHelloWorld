import unittest

import persona_worker


class ReadingSessionGuardTest(unittest.TestCase):
    def test_detects_automatic_reading_session_trigger(self):
        turn = {"source_message_content": "🔔 오늘 독서 세션 완료 — 책 1~2페이지."}
        self.assertTrue(persona_worker.is_automatic_reading_session_turn(turn))

    def test_regular_conversation_is_not_an_automatic_session(self):
        turn = {"source_message_content": "오늘 읽은 책 이야기해줘"}
        self.assertFalse(persona_worker.is_automatic_reading_session_turn(turn))


if __name__ == "__main__":
    unittest.main()
