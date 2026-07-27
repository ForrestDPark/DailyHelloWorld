#!/usr/bin/env python3
"""긴 플레이리스트 MP4를 무음 경계 기준으로 3분 이상 MP3 조각으로 나눈다."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


STATE_VERSION = 2


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True)


def media_duration(path):
    value = run(
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ).stdout.strip()
    return float(value)


def source_fingerprint(path):
    stat = path.stat()
    return {
        "name": path.name,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def save_json_atomic(path, data):
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    partial.replace(path)


def clock(seconds):
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def safe_name(value):
    value = re.sub(r'[/:*?"<>|\\]+', "_", value).strip(" .")
    return re.sub(r"\s+", " ", value)[:180] or "플레이리스트"


def detect_silence_midpoints(source, noise_db, silence_duration):
    """ffmpeg silencedetect 결과에서 각 무음 구간의 가운데 시각을 반환한다."""
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(source),
            "-vn", "-af",
            f"silencedetect=noise={noise_db}dB:d={silence_duration}",
            "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    log = result.stderr
    starts = [
        float(value)
        for value in re.findall(r"silence_start:\s*([0-9.]+)", log)
    ]
    ends = [
        float(value)
        for value in re.findall(r"silence_end:\s*([0-9.]+)", log)
    ]
    midpoints = []
    for start, end in zip(starts, ends):
        if end >= start:
            midpoints.append((start + end) / 2)
    return sorted(midpoints)


def choose_segments(duration, silence_tiers, min_seconds=180, ideal_seconds=210,
                    max_preferred_seconds=240, hard_max_seconds=360):
    """단계별 무음 후보를 쓰되 어떤 분절도 hard max를 넘기지 않는다."""
    boundaries = [0.0]
    boundary_methods = []
    cursor = 0.0
    while duration - cursor > min_seconds:
        boundary = None
        method = None

        # 먼저 3~4분 창 안에서 확실→보통→미세 무음 순서로 찾는다.
        for tier_name, points in silence_tiers:
            preferred = [
                p for p in points
                if cursor + min_seconds <= p <= cursor + max_preferred_seconds
            ]
            if preferred:
                boundary = min(
                    preferred,
                    key=lambda p: abs(p - (cursor + ideal_seconds)),
                )
                method = tier_name
                break

        # 4분 안에 없으면 최대 6분 안에서 같은 우선순위로 무음을 찾는다.
        if boundary is None:
            for tier_name, points in silence_tiers:
                extended = [
                    p for p in points
                    if cursor + max_preferred_seconds < p <= cursor + hard_max_seconds
                ]
                if extended:
                    boundary = extended[0]
                    method = f"{tier_name}-연장"
                    break

        # 어떤 단계에서도 무음을 못 찾으면 최대 길이에서 강제로 자른다.
        if boundary is None:
            boundary = min(cursor + hard_max_seconds, duration)
            method = "6분-강제"

        # 6분에서 자르면 마지막이 3분 미만이 되는 긴 꼬리는 남은 길이를
        # 반씩 나눠 양쪽 모두 3~6분으로 맞춘다. 전체가 6분 이하면 합친다.
        if duration - boundary < min_seconds:
            remaining = duration - cursor
            if remaining > hard_max_seconds:
                boundary = cursor + remaining / 2
                method = "마지막-균등"
            else:
                break
        boundaries.append(boundary)
        boundary_methods.append(method)
        cursor = boundary
    boundaries.append(duration)
    segments = [
        {
            "start": start,
            "end": end,
            "boundary_method": (
                boundary_methods[index]
                if index < len(boundary_methods) else "영상-끝"
            ),
        }
        for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]))
        if end - start >= 1
    ]
    return segments


def reusable_output(path, segment):
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    try:
        return abs(
            media_duration(path) - (segment["end"] - segment["start"])
        ) <= 2.0
    except Exception:
        return False


def split_one(source, output, segment):
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{segment['start']:.3f}",
            "-to", f"{segment['end']:.3f}",
            "-i", str(source), "-vn", "-c:a", "libmp3lame",
            "-q:a", "2", str(output),
        ],
        check=True,
    )


def move_source_to_trash(source):
    trash = Path.home() / ".Trash"
    trash.mkdir(exist_ok=True)
    target = trash / source.name
    if target.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = trash / f"{source.stem}_{stamp}{source.suffix}"
    shutil.move(str(source), str(target))
    print(f"🗑️ 원본을 휴지통으로 이동: {target}")


def main():
    parser = argparse.ArgumentParser(
        description="Shazam 없이 무음 경계로 플레이리스트 MP4를 MP3 분절"
    )
    parser.add_argument("input")
    parser.add_argument("--output-dir", required=True, help="기록 저장 폴더")
    parser.add_argument("--audio-output-dir", required=True, help="MP3 저장 폴더")
    parser.add_argument("--min-minutes", type=float, default=3.0)
    parser.add_argument("--ideal-minutes", type=float, default=3.5)
    parser.add_argument("--preferred-max-minutes", type=float, default=4.0)
    parser.add_argument("--hard-max-minutes", type=float, default=6.0)
    parser.add_argument("--silence-db", type=float, default=-38.0)
    parser.add_argument("--silence-duration", type=float, default=0.35)
    parser.add_argument("--trash-source", action="store_true")
    args = parser.parse_args()

    source = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    audio_dir = Path(args.audio_output_dir).expanduser().resolve()
    if not source.is_file():
        sys.exit(f"원본을 찾을 수 없습니다: {source}")
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    settings = {
        "min_minutes": args.min_minutes,
        "ideal_minutes": args.ideal_minutes,
        "preferred_max_minutes": args.preferred_max_minutes,
        "hard_max_minutes": args.hard_max_minutes,
        "silence_db": args.silence_db,
        "silence_duration": args.silence_duration,
    }
    fingerprint = source_fingerprint(source)
    state_path = output_dir / ".silence_split_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}

    if (
        state.get("version") == STATE_VERSION
        and state.get("source") == fingerprint
        and state.get("settings") == settings
        and state.get("status") == "complete"
    ):
        tracks = state.get("tracks", [])
        if tracks and all(
            reusable_output(audio_dir / track["output"], track)
            for track in tracks
        ):
            print(f"♻️ 완료 기록 재사용: MP3 {len(tracks)}개")
            if args.trash_source:
                move_source_to_trash(source)
            return

    duration = media_duration(source)
    silence_profiles = [
        ("확실한무음", args.silence_db, args.silence_duration),
        ("보통무음", -34.0, 0.22),
        ("미세무음", -30.0, 0.12),
    ]
    silence_tiers = []
    print("🔇 유동 무음 탐지 중 (확실 → 보통 → 미세)")
    for label, noise_db, silence_duration in silence_profiles:
        points = detect_silence_midpoints(
            source, noise_db, silence_duration
        )
        silence_tiers.append((label, points))
        print(
            f"   {label}: {noise_db:g}dB 이하 {silence_duration:g}초 "
            f"→ {len(points)}개"
        )
    segments = choose_segments(
        duration,
        silence_tiers,
        min_seconds=args.min_minutes * 60,
        ideal_seconds=args.ideal_minutes * 60,
        max_preferred_seconds=args.preferred_max_minutes * 60,
        hard_max_seconds=args.hard_max_minutes * 60,
    )
    if not segments:
        sys.exit("분절할 오디오 구간을 만들지 못했습니다.")

    old_tracks = (
        state.get("tracks", [])
        if state.get("source") == fingerprint and state.get("settings") == settings
        else []
    )
    state = {
        "version": STATE_VERSION,
        "source": fingerprint,
        "settings": settings,
        "status": "running",
        "silence_points": {
            label: points for label, points in silence_tiers
        },
        "tracks": [],
    }
    stem = safe_name(source.stem)
    print(f"✂️ 무음 경계 기준 MP3 {len(segments)}개 생성")
    forced_count = sum(
        segment["boundary_method"] == "6분-강제"
        for segment in segments
    )
    if forced_count:
        print(f"   ⚠️ 무음을 찾지 못해 6분에서 강제 분절: {forced_count}곳")
    for index, segment in enumerate(segments, 1):
        output = audio_dir / f"{stem} 분절{index}.mp3"
        saved = old_tracks[index - 1] if index <= len(old_tracks) else {}
        same_boundary = (
            abs(saved.get("start", -1) - segment["start"]) <= 0.1
            and abs(saved.get("end", -1) - segment["end"]) <= 0.1
            and saved.get("output") == output.name
        )
        if same_boundary and reusable_output(output, segment):
            print(
                f"   ♻️ [{index}/{len(segments)}] 기존 파일 재사용: "
                f"{output.name}",
                flush=True,
            )
        else:
            split_one(source, output, segment)
            print(
                f"   ✅ [{index}/{len(segments)}] {output.name} "
                f"({clock(segment['start'])}~{clock(segment['end'])}, "
                f"{segment['boundary_method']})",
                flush=True,
            )
        track = dict(segment, output=output.name)
        state["tracks"].append(track)
        save_json_atomic(state_path, state)

    state["status"] = "complete"
    save_json_atomic(state_path, state)
    print(f"🧾 분절 기록 저장: {state_path}")
    if args.trash_source:
        move_source_to_trash(source)


if __name__ == "__main__":
    main()
