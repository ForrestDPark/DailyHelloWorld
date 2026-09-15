"""미연시 일본어 대사의 사전 생성 음성 카탈로그와 생성 도우미."""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable

from server import dating_sim_story


MODEL = "gpt-4o-mini-tts"
VOICE = "marin"
INSTRUCTIONS = (
    "Speak in natural Japanese with a warm, clear, charming young adult female voice. "
    "Use subtle emotion appropriate for a visual novel. Do not add or omit words. "
    "Avoid exaggerated anime acting."
)
FURIGANA_RE = re.compile(r"\[([^\]|]+)\|([^\]]+)\]")
JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


def spoken_text(text: str) -> str:
    """화면 표기에서 후리가나와 한국어 번역을 제거한 실제 발화문을 만든다."""
    surface = FURIGANA_RE.sub(r"\1", text or "")
    return "。".join(
        line.strip() for line in surface.splitlines()
        if line.strip() and JAPANESE_RE.search(line)
    ).strip()


def _strings(value) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _strings(item)


def _book_template_story():
    """실제 EPUB을 읽지 않고 안전한 고정 EPUB 연동 템플릿만 펼친다."""
    original_find = dating_sim_story._find_book
    original_title = dating_sim_story._book_title
    try:
        dating_sim_story._find_book = lambda _book_id: Path("/tmp/dating-audio-template.epub")
        dating_sim_story._book_title = lambda _path: "음성 카탈로그"
        return dating_sim_story.story_for("book:" + "0" * 20, seed_key="audio-catalog")
    finally:
        dating_sim_story._find_book = original_find
        dating_sim_story._book_title = original_title


def build_catalog() -> list[str]:
    sources = [
        dating_sim_story.DAY_NARRATION,
        dating_sim_story.DAY_OPENINGS,
        dating_sim_story.DAY_BEATS,
        dating_sim_story.LOCATION_LINES,
        dating_sim_story.VARIANT_2_LOCATION_LINES,
        dating_sim_story.HIDDEN_EVENTS,
        dating_sim_story.ENDINGS,
        _book_template_story(),
        "[嬉|うれ]しいです。[少|すこ]し[近|ちか]くなれた[気|き]がします。",
        "[大丈夫|だいじょうぶ]です。ゆっくり[知|し]っていきましょう。",
    ]
    return sorted({spoken for raw in _strings(sources) if (spoken := spoken_text(raw))})


def clip_name(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20] + ".mp3"


def request_speech(api_key: str, text: str, voice: str = VOICE) -> bytes:
    payload = json.dumps({
        "model": MODEL,
        "voice": voice,
        "input": text,
        "instructions": INSTRUCTIONS,
        "response_format": "mp3",
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"OpenAI 음성 API 오류 ({error.code}): {detail}") from error


def write_manifest(output_dir: Path, clips: dict[str, str], voice: str = VOICE) -> None:
    manifest = {
        "version": 1,
        "model": MODEL,
        "voice": voice,
        "ai_generated": True,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "clips": clips,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary = output_dir / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output_dir / "manifest.json")
