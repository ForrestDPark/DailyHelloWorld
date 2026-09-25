"""미연시 일본어 대사의 사전 생성 음성 카탈로그와 생성 도우미."""
from __future__ import annotations

import datetime
import asyncio
import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable

import edge_tts

from server import dating_sim_story


MODEL = "gpt-4o-mini-tts"
VOICES = {"female": "marin", "male": "cedar"}
EDGE_VOICES = {"female": "ja-JP-NanamiNeural", "male": "ja-JP-KeitaNeural"}
EDGE_KOREAN_VOICES = {"female": "ko-KR-SunHiNeural", "male": "ko-KR-InJoonNeural"}
EDGE_ENGLISH_VOICES = {"female": "en-US-JennyNeural", "male": "en-US-GuyNeural"}
INSTRUCTIONS = {
    "female": (
        "Speak in natural Japanese with a warm, clear, charming young adult female voice. "
        "Use subtle emotion appropriate for a visual novel. Do not add or omit words. "
        "Avoid exaggerated anime acting."
    ),
    "male": (
        "Speak in natural Japanese with a calm, thoughtful young adult male voice. "
        "This is the protagonist's inner monologue or selected reply in a visual novel. "
        "Do not add or omit words. Avoid exaggerated anime acting."
    ),
}
FURIGANA_RE = re.compile(r"\[([^\]|]+)\|([^\]]+)\]")
# ★ 2026-09-24: "일본어 듣기 누르면 다 엣지tts로나와야하는데 아닌것도있네"
# 확인 중 실측 — 작품별 AI 생성 대사 중 하나가 `[どこ]`처럼 "|" 없는
# 깨진 후리가나 태그를 담고 있어서 FURIGANA_RE가 못 잡고 대괄호가 그대로
# 남았다. 남은 단일 대괄호 묶음도 내용은 보존한 채 벗겨낸다.
STRAY_BRACKET_RE = re.compile(r"\[([^\]]+)\]")
JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


def spoken_text(text: str) -> str:
    """화면 표기에서 후리가나와 한국어 번역을 제거한 실제 발화문을 만든다."""
    surface = STRAY_BRACKET_RE.sub(r"\1", FURIGANA_RE.sub(r"\1", text or ""))
    # 생성 중간본에 닫는 `]`가 빠진 `[思|おもってたの` 같은 조각이 들어와도
    # TTS 카탈로그 키에 마크업 기호가 남지 않게 한다. 정상 태그는 위에서 이미
    # 표면형으로 바뀌었고, 여기서는 복구 불가능한 잔여 구분자만 제거한다.
    surface = surface.translate(str.maketrans("", "", "[|]"))
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


def _all_book_stories():
    """서재의 모든 작품을 story_for()로 돌려준다(AI 생성 시나리오가 있으면
    그 실제 대사, 없으면 고정 템플릿 — story_for() 자체가 이미 그 판단을
    한다). ★ 2026-09-24: "일본어 듣기 누르면 다 엣지tts로나와야하는데
    아닌것도있네" 신고 — build_catalog()가 지금까지 고정 템플릿·기본
    프로필 이름 치환분만 커버해서, 작품마다 학습 단어를 녹여 AI가 새로
    쓰는 실제 플레이 대사(대부분의 실제 재생 대사)는 카탈로그에 없어
    브라우저 기본 TTS로 조용히 폴백했다. 실패한 개별 작품은 건너뛰고
    나머지는 계속 처리한다."""
    root = dating_sim_story.JAPANESE_EPUB_ROOT
    if not root.is_dir():
        return
    for path in root.rglob("*.epub"):
        try:
            story_id = "book:" + dating_sim_story._book_id(path)
            yield dating_sim_story.story_for(story_id, seed_key="audio-catalog")
        except (ValueError, OSError, KeyError):
            continue


def build_catalog() -> list[tuple[str, str]]:
    profile_names = [profile["jp"] for profile in dating_sim_story.BOOK_CHARACTER_PROFILES]
    profile_names.append("椿リカ")
    character_lines = [
        raw.replace("ソイ", name)
        for name in profile_names
        for beat in dating_sim_story.DAY_BEATS.values()
        for raw in beat[0]
    ]
    protagonist_choices = [
        raw.replace("ソイ", name)
        for name in profile_names
        for beat in dating_sim_story.DAY_BEATS.values()
        for raw in beat[1]
    ]
    female_sources = [
        # 장면의 첫째·셋째 줄, 장소 사건, 여주 반응과 엔딩은 여주 목소리다.
        character_lines,
        dating_sim_story.LOCATION_LINES,
        dating_sim_story.VARIANT_2_LOCATION_LINES,
        dating_sim_story.HIDDEN_EVENTS,
        dating_sim_story.ENDINGS,
        dating_sim_story.POSITIVE_REACTIONS,
        dating_sim_story.NEGATIVE_REACTIONS,
    ]
    book_story = _book_template_story()
    female_sources.extend(
        scene["lines"]
        for day_scenes in book_story["scenes"].values()
        for scene in day_scenes.values()
    )
    female_sources.append(book_story["endings"])
    male_sources = [
        dating_sim_story.DAY_NARRATION,
        protagonist_choices,
    ]
    male_sources.extend(
        scene["choices"]
        for day_scenes in book_story["scenes"].values()
        for scene in day_scenes.values()
    )
    for story in _all_book_stories():
        female_sources.extend(
            scene["lines"]
            for day_scenes in story["scenes"].values()
            for scene in day_scenes.values()
        )
        female_sources.append(story["endings"])
        male_sources.extend(
            scene["choices"]
            for day_scenes in story["scenes"].values()
            for scene in day_scenes.values()
        )
    catalog = {
        (role, spoken)
        for role, sources in (("female", female_sources), ("male", male_sources))
        for raw in _strings(sources)
        if (spoken := spoken_text(raw))
    }
    for raw_opening in _strings(dating_sim_story.DAY_OPENINGS):
        for name in profile_names:
            opening = raw_opening.replace("ソイ", name)
            japanese = "\n".join(
                line for line in opening.splitlines() if JAPANESE_RE.search(line)
            )
            quote = re.match(r"^(.*?)「(.+?)」(.*)$", japanese, re.DOTALL)
            if quote:
                for role, segment in (("male", quote[1]), ("female", quote[2]), ("male", quote[3])):
                    if spoken := spoken_text(segment):
                        catalog.add((role, spoken))
            elif spoken := spoken_text(japanese):
                catalog.add(("male", spoken))
    return sorted(catalog)


def clip_name(role: str, text: str) -> str:
    return hashlib.sha256(f"{role}\0{text}".encode("utf-8")).hexdigest()[:20] + ".mp3"


def request_speech(api_key: str, role: str, text: str, voice: str | None = None) -> bytes:
    if role not in VOICES:
        raise ValueError("지원하지 않는 미연시 음성 역할입니다")
    payload = json.dumps({
        "model": MODEL,
        "voice": voice or VOICES[role],
        "input": text,
        "instructions": INSTRUCTIONS[role],
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


def request_edge_speech(
    role: str,
    text: str,
    voice: str | None = None,
    *,
    language: str = "ja",
) -> bytes:
    """Edge TTS의 일본어·한국어·영어 성별 음성을 MP3 바이트로 생성한다."""
    if role not in EDGE_VOICES:
        raise ValueError("지원하지 않는 미연시 음성 역할입니다")
    voices = {
        "ja": EDGE_VOICES,
        "ko": EDGE_KOREAN_VOICES,
        "en": EDGE_ENGLISH_VOICES,
    }.get(language)
    if voices is None:
        raise ValueError("지원하지 않는 음성 언어입니다")

    async def collect() -> bytes:
        chunks = []
        communicator = edge_tts.Communicate(text, voice or voices[role])
        async for item in communicator.stream():
            if item.get("type") == "audio" and item.get("data"):
                chunks.append(item["data"])
        return b"".join(chunks)

    try:
        audio = asyncio.run(collect())
    except Exception as error:
        raise RuntimeError(f"Edge TTS 음성 생성 오류: {error}") from error
    if not audio:
        raise RuntimeError("Edge TTS 음성 생성 오류: 오디오를 받지 못했습니다")
    return audio


def write_manifest(
    output_dir: Path,
    clips: dict[str, dict[str, str]],
    *,
    provider: str = "openai",
) -> None:
    voices = EDGE_VOICES if provider == "edge" else VOICES
    manifest = {
        "version": 2,
        "provider": provider,
        "model": "edge-tts" if provider == "edge" else MODEL,
        "voices": voices,
        "ai_generated": True,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "clips": clips,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary = output_dir / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output_dir / "manifest.json")
