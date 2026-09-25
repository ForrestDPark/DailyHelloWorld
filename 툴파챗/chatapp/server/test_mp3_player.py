import pytest

from server.mp3_player import lrc_timestamp, lyric_line_count, srt_to_lrc


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


def test_srt_to_lrc_discards_music_and_promotional_hallucinations():
    source = """1
00:00:30,000 --> 00:00:33,000
[музыка]

2
00:04:16,000 --> 00:04:18,000
Не забудьте подписаться на мой канал!
"""
    with pytest.raises(ValueError, match="변환할 자막 문장이 없습니다"):
        srt_to_lrc(source)


def test_lyric_line_count_ignores_metadata():
    assert lyric_line_count("[by:test]\n[00:01.20]하나\n[00:03.40]둘\n") == 2
