#!/usr/bin/env python3
"""폴더의 MP3를 한 개씩 Shazam 인식하고 '아티스트 - 곡명.mp3'로 변경한다."""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


STATE_VERSION = 1


def safe_name(value):
    value = re.sub(r'[/:*?"<>|\\]+', "_", value).strip(" .")
    value = re.sub(r"\s+", " ", value)
    return value[:180] or "Unknown"


def fingerprint(path):
    stat = path.stat()
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "inode": stat.st_ino,
    }


def save_json_atomic(path, data):
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    partial.replace(path)


def media_duration(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def unique_target(folder, stem, current):
    candidate = folder / f"{stem}.mp3"
    if candidate == current or not candidate.exists():
        return candidate
    number = 2
    while True:
        candidate = folder / f"{stem} ({number}).mp3"
        if candidate == current or not candidate.exists():
            return candidate
        number += 1


async def recognize_one(shazam, source, temp_dir):
    duration = media_duration(source)
    sample_seconds = min(15.0, duration)
    sample_at = max(0.0, min(30.0, duration / 3) - sample_seconds / 2)
    sample = temp_dir / "sample.mp3"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{sample_at:.3f}", "-t", f"{sample_seconds:.3f}",
            "-i", str(source), "-vn", "-ac", "1", "-ar", "44100",
            "-b:a", "128k", str(sample),
        ],
        check=True,
    )
    try:
        result = await asyncio.wait_for(
            shazam.recognize(str(sample)), timeout=45
        )
    finally:
        sample.unlink(missing_ok=True)
    track = result.get("track") or {}
    title = (track.get("title") or "").strip()
    artist = (track.get("subtitle") or "").strip()
    if not title:
        return None
    return {
        "artist": artist or "Unknown Artist",
        "title": title,
        "shazam_key": str(track.get("key") or ""),
    }


async def async_main(folder):
    try:
        from shazamio import Shazam
    except ImportError:
        sys.exit("Shazam 전용 환경에 shazamio가 설치되어 있지 않습니다.")

    folder = Path(folder).expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"폴더를 찾을 수 없습니다: {folder}")
    files = sorted(
        path for path in folder.iterdir()
        if (
            path.is_file()
            and path.suffix.lower() == ".mp3"
            and "분절" in path.stem
        )
    )
    if not files:
        sys.exit("선택한 폴더 바로 아래에 이름에 '분절'이 들어간 MP3가 없습니다.")

    state_path = folder / ".mp3_shazam_rename_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    if state.get("version") != STATE_VERSION:
        state = {"version": STATE_VERSION, "files": []}
    records = state.setdefault("files", [])

    shazam = Shazam()
    renamed = 0
    reused = 0
    failed = 0
    print("=" * 60)
    print(f"🎵 MP3 Shazam 제목 변경: {len(files)}개")
    print(f"📂 {folder}")
    print("=" * 60)
    with tempfile.TemporaryDirectory(prefix="mp3_shazam_rename_") as temp:
        temp_dir = Path(temp)
        for index, source in enumerate(files, 1):
            source_fp = fingerprint(source)
            previous = next(
                (
                    item for item in records
                    if item.get("fingerprint") == source_fp
                    and item.get("status") == "renamed"
                ),
                None,
            )
            if previous:
                print(
                    f"[{index}/{len(files)}] ♻️ 기록 재사용: {source.name}",
                    flush=True,
                )
                reused += 1
                continue

            print(
                f"[{index}/{len(files)}] 🔎 Shazam 인식: {source.name}",
                flush=True,
            )
            try:
                info = await recognize_one(shazam, source, temp_dir)
            except Exception as error:
                info = None
                print(f"   ⚠️ 인식 오류: {error}", flush=True)

            if not info:
                print("   ➖ 미인식 — 기존 파일명 유지", flush=True)
                records.append({
                    "fingerprint": source_fp,
                    "original_name": source.name,
                    "current_name": source.name,
                    "status": "unrecognized",
                })
                failed += 1
            else:
                new_stem = safe_name(
                    f"{info['artist']} - {info['title']}"
                )
                target = unique_target(folder, new_stem, source)
                if target != source:
                    source.rename(target)
                print(f"   ✅ {target.name}", flush=True)
                records.append({
                    "fingerprint": source_fp,
                    "original_name": source.name,
                    "current_name": target.name,
                    "status": "renamed",
                    **info,
                })
                renamed += 1
            save_json_atomic(state_path, state)

    print("=" * 60)
    print(
        f"완료: 이름 변경 {renamed}개 / 기록 재사용 {reused}개 / "
        f"미인식 {failed}개"
    )
    print(f"🧾 기록: {state_path}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    args = parser.parse_args()
    asyncio.run(async_main(args.folder))


if __name__ == "__main__":
    main()
