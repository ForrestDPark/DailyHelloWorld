"""MP3 가사 플레이어용 SRT → LRC 변환 도우미."""

from __future__ import annotations

import re


_TIME = re.compile(r"(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{3})")
_NON_LYRIC_CUES = re.compile(
    r"^\s*[\[(（【]?(?:music|instrumental|applause|音楽|演奏|拍手|음악|연주|박수|"
    r"музыка|аплодисменты)[\])）】]?\s*$",
    re.IGNORECASE,
)
_PROMOTIONAL_CUES = re.compile(
    r"(?:subscribe|my channel|подписат\w*|канал|チャンネル登録|구독)",
    re.IGNORECASE,
)


def lrc_timestamp(value: str) -> str:
    match = _TIME.search(value)
    if not match:
        raise ValueError("잘못된 자막 시각입니다")
    minutes = int(match.group("h")) * 60 + int(match.group("m"))
    seconds = int(match.group("s"))
    centiseconds = int(match.group("ms")) // 10
    return f"[{minutes:02d}:{seconds:02d}.{centiseconds:02d}]"


def srt_to_lrc(source: str) -> str:
    lines: list[str] = ["[by:툴파챗 로컬 Whisper]"]
    for block in re.split(r"\r?\n\s*\r?\n", source.strip()):
        parts = [part.strip() for part in block.splitlines() if part.strip()]
        time_index = next((i for i, part in enumerate(parts) if "-->" in part), -1)
        if time_index < 0 or time_index + 1 >= len(parts):
            continue
        text = " ".join(parts[time_index + 1 :]).strip()
        if not text or _NON_LYRIC_CUES.search(text) or _PROMOTIONAL_CUES.search(text):
            continue
        lines.append(f"{lrc_timestamp(parts[time_index].split('-->', 1)[0])}{text}")
    if len(lines) == 1:
        raise ValueError("변환할 자막 문장이 없습니다")
    return "\n".join(lines) + "\n"


def lyric_line_count(lrc: str) -> int:
    """LRC 메타데이터를 제외한 실제 시간 가사 줄 수를 센다."""
    return sum(1 for line in lrc.splitlines() if re.match(r"^\[\d{1,3}:\d{2}(?:[.:]\d+)?\]", line))
