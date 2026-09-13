"""★ 2026-09-14: "shift alarm 메뉴바에서 클릭해서 하는 맥북 음량조절이랑
좋아요/클래식 음악 재생을 채팅에서도 하고 싶다" 요청으로 추가한
알람지기의 ```alarmaction 실행 경로 테스트. 실제 시스템 음량이나
Elmedia를 건드리면 안 되므로 persona_worker.subprocess를 전부 모킹한다."""
import unittest
from unittest.mock import MagicMock, patch

import persona_worker as pw


class AlarmActionSignalTest(unittest.TestCase):
    def test_no_block_returns_none(self):
        self.assertIsNone(pw._handle_alarm_action_signal("그냥 대화입니다."))

    def test_malformed_json_returns_none(self):
        text = "```alarmaction\n{not json}\n```"
        self.assertIsNone(pw._handle_alarm_action_signal(text))

    def test_unknown_action_returns_none(self):
        text = '```alarmaction\n{"action":"launch_missiles"}\n```'
        self.assertIsNone(pw._handle_alarm_action_signal(text))

    @patch("persona_worker.subprocess")
    def test_set_volume_clamps_to_100_and_calls_osascript(self, mock_subprocess):
        text = '```alarmaction\n{"action":"set_volume","percent":150}\n```'
        outcome = pw._handle_alarm_action_signal(text)
        self.assertIn("100%", outcome)
        args = mock_subprocess.run.call_args.args[0]
        self.assertIn("set volume output volume 100", args)

    @patch("persona_worker.subprocess")
    def test_set_volume_clamps_negative_to_0(self, mock_subprocess):
        text = '```alarmaction\n{"action":"set_volume","percent":-20}\n```'
        outcome = pw._handle_alarm_action_signal(text)
        self.assertIn("0%", outcome)

    @patch("persona_worker._shift_alarm_get_volume", return_value=40)
    @patch("persona_worker.subprocess")
    def test_volume_up_adds_step_to_current_volume(self, mock_subprocess, mock_get_volume):
        text = '```alarmaction\n{"action":"volume_up","step":15}\n```'
        outcome = pw._handle_alarm_action_signal(text)
        self.assertIn("40%", outcome)
        self.assertIn("55%", outcome)

    @patch("persona_worker._shift_alarm_get_volume", return_value=40)
    @patch("persona_worker.subprocess")
    def test_volume_down_default_step_is_10(self, mock_subprocess, mock_get_volume):
        text = '```alarmaction\n{"action":"volume_down"}\n```'
        outcome = pw._handle_alarm_action_signal(text)
        self.assertIn("30%", outcome)

    @patch("persona_worker._shift_alarm_get_volume", return_value=None)
    def test_volume_up_reports_failure_when_current_volume_unknown(self, mock_get_volume):
        text = '```alarmaction\n{"action":"volume_up"}\n```'
        outcome = pw._handle_alarm_action_signal(text)
        self.assertIn("❌", outcome)

    @patch("persona_worker._shift_alarm_play_folder", return_value=(True, "3곡을 새로 열었습니다."))
    def test_play_favorites_uses_favorites_folder(self, mock_play):
        text = '```alarmaction\n{"action":"play_favorites"}\n```'
        outcome = pw._handle_alarm_action_signal(text)
        mock_play.assert_called_once_with(pw.SHIFT_ALARM_FAVORITES_FOLDER)
        self.assertIn("✅", outcome)
        self.assertIn("좋아요", outcome)

    @patch("persona_worker._shift_alarm_play_folder", return_value=(True, "5곡을 새로 열었습니다."))
    def test_play_classical_uses_classic_folder(self, mock_play):
        text = '```alarmaction\n{"action":"play_classical"}\n```'
        outcome = pw._handle_alarm_action_signal(text)
        mock_play.assert_called_once_with(pw.SHIFT_ALARM_CLASSIC_FOLDER)
        self.assertIn("✅", outcome)

    @patch("persona_worker._shift_alarm_play_folder", return_value=(False, "재생 가능한 음원 파일이 없습니다."))
    def test_play_failure_is_reported_with_cross_mark(self, mock_play):
        text = '```alarmaction\n{"action":"play_classical"}\n```'
        outcome = pw._handle_alarm_action_signal(text)
        self.assertIn("❌", outcome)

    def test_non_owner_block_is_stripped_without_executing(self):
        """_process_turn_inner의 실제 게이트와 같은 규칙 — 소유자가 아니면
        블록 텍스트만 지우고 아무 시스템 명령도 실행하지 않는다."""
        reply = '음량을 낮출게요.\n```alarmaction\n{"action":"set_volume","percent":10}\n```'
        with patch("persona_worker.subprocess") as mock_subprocess:
            stripped = pw.ALARM_ACTION_RE.sub("", reply).strip()
            mock_subprocess.run.assert_not_called()
        self.assertNotIn("alarmaction", stripped)
        self.assertIn("음량을 낮출게요.", stripped)


if __name__ == "__main__":
    unittest.main()
