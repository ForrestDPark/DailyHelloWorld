#!/usr/bin/env python3
"""mp3 폴더를 훑어서 각 곡의 동기화된 가사(.lrc)를 만든다. nPlayer(아이폰
음악 플레이어)는 mp3와 같은 폴더에 같은 이름의 .lrc가 있으면 자막처럼 가사를
보여준다. --output-dir을 주면 mp3 옆이 아니라 별도 폴더에 .lrc만 모아서
저장한다(맥과 폰의 mp3 목록이 달라서, .lrc만 골라 폰으로 옮기고 싶을 때).

순서(사용자 지정): 1) lrclib.net(공개 동기화 가사 DB)에서 먼저 찾고,
2) 못 찾은 곡만 whisper-cli(로컬 음성 인식, -olrc로 LRC 직접 출력)로 자체
전사해서 생성한다.

이미 .lrc가 있는 곡은 건너뛴다(--overwrite로 강제 재생성 가능).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_DIR = Path("/Users/forrestdpark/Desktop/BlogImage/좋아요플레이")
WHISPER_EXE = "/opt/homebrew/bin/whisper-cli"
MODEL_PATH = "/opt/homebrew/share/whisper-cpp/models/ggml-medium.bin"
USER_AGENT = "DailyHelloWorld-LyricsSync/1.0 (+https://github.com/ForrestDPark/DailyHelloWorld)"
# 노래(가창)에는 --vad를 절대 쓰지 않는다: Silero VAD는 대화체 음성 검출용으로
# 튜닝돼 있어서, 반주가 깔린 보컬을 "음성 없음"으로 오판해 세그먼트를 0개로
# 걸러버리는 경우가 실측으로 확인됐다(2026-08-13, 노래방 반주 있는 애니메 ED
# 곡에서 VAD 켜면 결과 .lrc가 완전히 비어버림 — VAD 끄면 정상 전사됨).

# yt-dlp가 채워넣는 제목에 흔히 붙는 잡음 — lrclib 검색 정확도를 위해 제거.
NOISE_PATTERNS = [
    r"\(official\s*(music\s*)?video\)",
    r"\(official\s*audio\)",
    r"\(official\s*lyric(s)?\s*video\)",
    r"\(lyric(s)?\s*video\)",
    r"\(audio\)",
    r"\(visualizer\)",
    r"\[official\s*(music\s*)?video\]",
    r"\bm\s*[\\/⧹⧸]\s*v\b",
    r"\bmv\b",
    r"\bofficial\s*music\s*video\b",
]


def clean_title(title: str, artist: str) -> str:
    t = title
    for pat in NOISE_PATTERNS:
        t = re.sub(pat, "", t, flags=re.IGNORECASE)
    # 태그가 "Artist - Title" 형태로 title에 아티스트명을 중복시키는 경우 제거.
    if artist:
        prefix = re.escape(artist)
        t = re.sub(rf"^\s*{prefix}\s*[-–:]\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip(" -–:\"'")


def read_tags(mp3_path: Path) -> tuple[str, str, float]:
    from mutagen.easyid3 import EasyID3
    from mutagen.mp3 import MP3

    audio = MP3(mp3_path)
    duration = audio.info.length
    try:
        tags = EasyID3(mp3_path)
        artist = (tags.get("artist") or [""])[0]
        title = (tags.get("title") or [""])[0]
    except Exception:
        artist, title = "", ""
    if not title:
        title = mp3_path.stem
    return artist, title, duration


def lrclib_request(path: str, params: dict) -> dict | None:
    url = f"https://lrclib.net{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except urllib.error.URLError:
        return None


def find_synced_lyrics(artist: str, title: str, duration: float) -> str | None:
    """lrclib에서 동기화 가사를 찾는다. 정확 매칭 -> 검색 순으로 시도."""
    if title:
        exact = lrclib_request(
            "/api/get",
            {"track_name": title, "artist_name": artist, "duration": round(duration)},
        )
        if exact and exact.get("syncedLyrics"):
            return exact["syncedLyrics"]

    query = {"track_name": title} if title else {}
    if artist:
        query["artist_name"] = artist
    if not query:
        return None
    results = lrclib_request("/api/search", query)
    if not results:
        return None

    candidates = [r for r in results if r.get("syncedLyrics")]
    if not candidates:
        return None
    # 실제 재생 길이와 가장 가까운(±10초 이내) 후보를 우선.
    candidates.sort(key=lambda r: abs((r.get("duration") or 0) - duration))
    best = candidates[0]
    if duration and abs((best.get("duration") or 0) - duration) > 10:
        return None
    return best["syncedLyrics"]


def whisper_transcribe_to_lrc(mp3_path: Path, tmp_dir: Path) -> str | None:
    wav_path = tmp_dir / "audio.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp3_path), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav_path)],
        check=True, capture_output=True,
    )
    out_prefix = tmp_dir / "out"
    cmd = [
        WHISPER_EXE, "-m", MODEL_PATH, "-f", str(wav_path),
        "-olrc", "-l", "auto", "-p", "1", "-t", "8",
        "--beam-size", "1", "--no-speech-thold", "0.3",
        "-of", str(out_prefix),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    lrc_path = out_prefix.with_suffix(".lrc")
    if lrc_path.exists():
        return lrc_path.read_text(encoding="utf-8")
    return None


def process_file(mp3_path: Path, overwrite: bool, output_dir: Path | None) -> str:
    lrc_path = (output_dir / mp3_path.with_suffix(".lrc").name) if output_dir else mp3_path.with_suffix(".lrc")
    if lrc_path.exists() and not overwrite:
        return "skip"

    artist, title, duration = read_tags(mp3_path)
    query_title = clean_title(title, artist)

    try:
        synced = find_synced_lyrics(artist, query_title, duration)
    except Exception as e:
        print(f"  ⚠️  lrclib 조회 실패({e}), whisper로 넘어감")
        synced = None

    if synced:
        lrc_path.write_text(synced, encoding="utf-8")
        return "lrclib"

    with tempfile.TemporaryDirectory() as tmp:
        try:
            synced = whisper_transcribe_to_lrc(mp3_path, Path(tmp))
        except subprocess.CalledProcessError as e:
            print(f"  ⚠️  whisper 전사 실패: {e.stderr.decode(errors='replace')[:200]}")
            return "fail"

    if synced:
        lrc_path.write_text(synced, encoding="utf-8")
        return "whisper"
    return "fail"


def main() -> None:
    parser = argparse.ArgumentParser(description="mp3 폴더에 동기화 가사(.lrc) 생성")
    parser.add_argument("folder", nargs="?", default=str(DEFAULT_DIR), help="mp3가 있는 폴더")
    parser.add_argument("--overwrite", action="store_true", help="이미 .lrc가 있어도 다시 만듦")
    parser.add_argument("--limit", type=int, default=None, help="처리할 최대 곡 수(테스트용)")
    parser.add_argument(
        "--output-dir", default=None,
        help="mp3 옆이 아니라 이 폴더에 .lrc를 모아서 저장(파일명은 mp3와 동일하게 유지)",
    )
    args = parser.parse_args()

    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        raise SystemExit(f"폴더를 찾을 수 없습니다: {folder}")

    output_dir = None
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)

    mp3_files = sorted(folder.glob("*.mp3"))
    if args.limit:
        mp3_files = mp3_files[: args.limit]

    counts = {"lrclib": 0, "whisper": 0, "skip": 0, "fail": 0}
    total = len(mp3_files)
    for i, mp3_path in enumerate(mp3_files, 1):
        print(f"[{i}/{total}] {mp3_path.name}", flush=True)
        result = process_file(mp3_path, args.overwrite, output_dir)
        counts[result] += 1
        label = {
            "lrclib": "✅ lrclib에서 찾음",
            "whisper": "🎙️  whisper로 전사함",
            "skip": "⏭️  이미 있음(건너뜀)",
            "fail": "❌ 실패",
        }[result]
        print(f"  {label}", flush=True)

    print()
    print(f"완료: lrclib {counts['lrclib']}곡 · whisper {counts['whisper']}곡 · "
          f"건너뜀 {counts['skip']}곡 · 실패 {counts['fail']}곡 (총 {total}곡)")


if __name__ == "__main__":
    main()
