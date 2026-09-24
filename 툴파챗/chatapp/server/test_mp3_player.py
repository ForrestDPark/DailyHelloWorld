from server.mp3_player import lrc_timestamp, srt_to_lrc


def test_lrc_timestamp_supports_hour():
    assert lrc_timestamp("01:02:03,450") == "[62:03.45]"


def test_srt_to_lrc_uses_start_time_and_multiline_text():
    source = """1
00:00:01,230 --> 00:00:03,000
첫 줄
둘째 줄

2
00:01:05.900 --> 00:01:07.000
다음 가사
"""
    assert srt_to_lrc(source) == (
        "[by:툴파챗 로컬 Whisper]\n"
        "[00:01.23]첫 줄 둘째 줄\n"
        "[01:05.90]다음 가사\n"
    )
