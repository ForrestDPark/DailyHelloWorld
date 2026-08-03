#!/usr/bin/env python3
"""긴 플레이리스트 영상의 곡을 인식하고 곡별 MP3로 자동 분할한다."""

import argparse
import asyncio
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Detection:
    at: float
    key: str
    title: str
    artist: str


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True)


def audio_duration(path):
    probe = run(
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=duration", "-of", "csv=p=0", str(path),
    ).stdout.strip()
    if not probe or probe == "N/A":
        probe = run(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(path),
        ).stdout.strip()
    return float(probe)


def safe_name(value):
    value = re.sub(r'[/:*?"<>|\\]+', "_", value).strip(" .")
    value = re.sub(r"\s+", " ", value)
    return value[:140] or "Unknown Track"


def clock(seconds):
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def load_cache(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(path, cache):
    path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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


def reusable_track_output(audio_output_dir, saved_track, segment):
    """저장된 경계와 MP3가 현재 확정 곡과 같고 파일도 정상이면 경로를 반환."""
    if not saved_track or saved_track.get("key") != segment["key"]:
        return None
    if abs(saved_track.get("start", -1) - segment["start"]) > 0.1:
        return None
    if abs(saved_track.get("end", -1) - segment["end"]) > 0.1:
        return None
    output_name = saved_track.get("output")
    if not output_name:
        return None
    output = audio_output_dir / Path(output_name).name
    if not output.is_file() or output.stat().st_size <= 0:
        return None
    try:
        if abs(audio_duration(output) - (segment["end"] - segment["start"])) > 2.0:
            return None
    except Exception:
        return None
    return output


async def recognize_at(shazam, source, at, sample_seconds, temp_dir):
    clip = temp_dir / f"sample_{at:.2f}.mp3"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{at:.3f}", "-t", f"{sample_seconds:.3f}",
            "-i", str(source), "-vn", "-ac", "1", "-ar", "44100",
            "-b:a", "128k", str(clip),
        ],
        check=True,
    )
    try:
        task = asyncio.create_task(shazam.recognize(str(clip)))
        waited = 0
        while True:
            done, _pending = await asyncio.wait({task}, timeout=10)
            if done:
                result = task.result()
                break
            waited += 10
            print(
                f"      ⏳ Shazam 응답 대기 {waited}/45초...",
                flush=True,
            )
            if waited >= 45:
                task.cancel()
                raise asyncio.TimeoutError("Shazam 응답 시간 초과(45초)")
    finally:
        clip.unlink(missing_ok=True)
    track = result.get("track") or {}
    title = (track.get("title") or "").strip()
    artist = (track.get("subtitle") or "").strip()
    key = str(track.get("key") or "")
    if not key and (title or artist):
        key = f"{artist.casefold()}::{title.casefold()}"
    if not key:
        return None
    return Detection(at=at, key=key, title=title or "Unknown", artist=artist)


async def detect_with_cache(
    shazam, source, at, sample_seconds, temp_dir, cache, cache_path,
):
    cache_key = f"{at:.2f}"
    saved = cache.get(cache_key)
    if saved is not None:
        if not saved:
            return None
        return Detection(at=at, **saved)
    detection = None
    for attempt in range(3):
        try:
            detection = await recognize_at(
                shazam, source, at, sample_seconds, temp_dir
            )
            break
        except Exception as error:
            print(
                f"      ⚠️ {clock(at)} {attempt + 1}/3회 실패: {error}",
                flush=True,
            )
            if attempt < 2:
                print("      🔄 잠시 후 재시도합니다.", flush=True)
                await asyncio.sleep(1.5 * (attempt + 1))
    cache[cache_key] = (
        {
            "key": detection.key,
            "title": detection.title,
            "artist": detection.artist,
        }
        if detection else None
    )
    save_cache(cache_path, cache)
    return detection


def remove_single_probe_noise(detections):
    cleaned = list(detections)
    for index in range(1, len(cleaned) - 1):
        left, current, right = cleaned[index - 1:index + 2]
        if left.key == right.key != current.key:
            cleaned[index] = Detection(
                at=current.at,
                key=left.key,
                title=left.title,
                artist=left.artist,
            )
    return cleaned


def build_segments(detections, duration):
    if not detections:
        return []
    detections = remove_single_probe_noise(sorted(detections, key=lambda x: x.at))
    groups = []
    for detection in detections:
        if not groups or groups[-1][-1].key != detection.key:
            groups.append([detection])
        else:
            groups[-1].append(detection)
    segments = []
    for index, group in enumerate(groups):
        start = 0.0
        if index:
            start = (groups[index - 1][-1].at + group[0].at) / 2
        end = duration
        if index + 1 < len(groups):
            end = (group[-1].at + groups[index + 1][0].at) / 2
        item = group[len(group) // 2]
        if end - start >= 20:
            segments.append({
                "start": start,
                "end": end,
                "key": item.key,
                "title": item.title,
                "artist": item.artist,
                "probe_count": len(group),
            })
    return segments


def write_reports(output_dir, source, segments):
    json_path = output_dir / "tracklist.json"
    csv_path = output_dir / "tracklist.csv"
    json_path.write_text(
        json.dumps(
            {"source": str(source), "tracks": segments},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["번호", "시작", "종료", "아티스트", "제목", "인식표본"])
        for index, segment in enumerate(segments, 1):
            writer.writerow([
                index, clock(segment["start"]), clock(segment["end"]),
                segment["artist"], segment["title"], segment["probe_count"],
            ])
    return json_path, csv_path


def split_one_track(source, output_dir, segment, index, filename_prefix=""):
    """확정된 곡 하나를 즉시 MP3로 만들어 결과 경로를 반환한다."""
    label = " - ".join(filter(None, [
        segment["artist"], segment["title"]
    ]))
    suffix = f" - {safe_name(filename_prefix)}" if filename_prefix else ""
    output = output_dir / f"{index:02d} - {safe_name(label)}{suffix}.mp3"
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
    print(
        f"   ✅ MP3 즉시 생성: {output.name} "
        f"({clock(segment['start'])}~{clock(segment['end'])})",
        flush=True,
    )
    return output


def split_tracks(source, output_dir, segments, filename_prefix=""):
    for index, segment in enumerate(segments, 1):
        split_one_track(
            source, output_dir, segment, index,
            filename_prefix=filename_prefix,
        )


def move_source_to_trash(source):
    trash_dir = Path.home() / ".Trash"
    trash_dir.mkdir(exist_ok=True)
    target = trash_dir / source.name
    if target.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = trash_dir / f"{source.stem}_{stamp}{source.suffix}"
    shutil.move(str(source), str(target))
    print(f"🗑️ 원본을 휴지통으로 이동: {target}")


async def async_main(args):
    try:
        from shazamio import Shazam
    except ImportError:
        sys.exit(
            "shazamio가 없습니다. 먼저 다음을 실행하세요:\n"
            "/opt/anaconda3/bin/python3 -m pip install shazamio"
        )
    source = Path(args.input).expanduser().resolve()
    if not source.is_file():
        sys.exit(f"입력 파일을 찾을 수 없습니다: {source}")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("ffmpeg와 ffprobe가 필요합니다: brew install ffmpeg")
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else source.parent / f"{source.stem}_tracks"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_output_dir = (
        Path(args.audio_output_dir).expanduser().resolve()
        if args.audio_output_dir else output_dir
    )
    audio_output_dir.mkdir(parents=True, exist_ok=True)
    duration = audio_duration(source)
    cache_path = output_dir / ".recognition_cache.json"
    state_path = output_dir / ".split_state.json"
    current_source = source_fingerprint(source)
    state = load_cache(state_path)
    cache = load_cache(cache_path)
    if not state:
        # 기록 기능 도입 전의 recognition cache는 버리지 않고 새 상태에 승계한다.
        state = {
            "version": 1,
            "source": current_source,
            "status": "running",
            "tracks": [],
        }
        save_json_atomic(state_path, state)
    elif state.get("source") != current_source:
        # 같은 이름의 원본이 교체된 경우에만 예전 Shazam 결과를 무효화한다.
        state = {
            "version": 1,
            "source": current_source,
            "status": "running",
            "tracks": [],
        }
        cache = {}
        save_cache(cache_path, cache)
        save_json_atomic(state_path, state)
    else:
        state.setdefault("tracks", [])

    if state.get("status") == "complete" and state.get("tracks"):
        saved_tracks = state["tracks"]
        all_valid = all(
            reusable_track_output(audio_output_dir, saved, saved) is not None
            for saved in saved_tracks
        )
        if all_valid:
            print(f"♻️  완료 기록 재사용: {len(saved_tracks)}곡 모두 정상")
            print(f"🧾 {state_path}")
            if args.trash_source:
                move_source_to_trash(source)
            return

    sample_seconds = min(args.sample_seconds, max(8.0, args.interval / 2))
    coarse_times = []
    at = min(8.0, max(0.0, duration - sample_seconds))
    while at < max(0.0, duration - sample_seconds):
        coarse_times.append(round(at, 2))
        at += args.interval
    final_probe = max(0.0, duration - sample_seconds)
    if not coarse_times or final_probe - coarse_times[-1] > args.interval / 2:
        coarse_times.append(round(final_probe, 2))

    shazam = Shazam()
    detections = []
    segments = []
    with tempfile.TemporaryDirectory(prefix="bgm_recognize_") as temp:
        temp_dir = Path(temp)
        print(f"🎧 순차 곡 인식·즉시 분할: 최대 {len(coarse_times)}개 표본")
        print("   새 곡이 2회 연속 확인되면 직전 곡 MP3를 바로 생성합니다.")

        current = None
        current_start = 0.0
        current_probe_count = 0
        last_current_at = 0.0
        pending = None
        pending_count = 0

        def finish_current(end_at):
            """현재 곡 경계를 확정하고 보고서와 MP3를 즉시 갱신한다."""
            nonlocal current_start
            if current is None or end_at - current_start < 20:
                return
            segment = {
                "start": current_start,
                "end": end_at,
                "key": current.key,
                "title": current.title,
                "artist": current.artist,
                "probe_count": current_probe_count,
            }
            segments.append(segment)
            _json_path, csv_path = write_reports(output_dir, source, segments)
            print(
                f"🎯 {len(segments):02d}번 곡 확정: "
                f"{clock(segment['start'])}~{clock(segment['end'])} "
                f"{segment['artist']} - {segment['title']}",
                flush=True,
            )
            if not args.analyze_only:
                track_index = len(segments)
                saved_track = (
                    state["tracks"][track_index - 1]
                    if track_index <= len(state["tracks"]) else None
                )
                output = reusable_track_output(
                    audio_output_dir, saved_track, segment
                )
                if output:
                    print(
                        f"   ♻️ 완성 MP3 재사용: {output.name}",
                        flush=True,
                    )
                else:
                    output = split_one_track(
                        source, audio_output_dir, segment, track_index,
                        filename_prefix=args.filename_prefix,
                    )
                saved = dict(segment)
                saved["output"] = output.name
                # 현재까지 다시 확정한 곡만 신뢰하고 예전 뒤쪽 기록은 제거한다.
                state["tracks"] = state["tracks"][:track_index - 1] + [saved]
                state["status"] = "running"
                save_json_atomic(state_path, state)
                print(f"   🧾 재작업 기록 저장: {state_path}", flush=True)
            print(f"   📋 현재까지 결과: {csv_path}", flush=True)

        for index, probe_at in enumerate(coarse_times, 1):
            was_cached = f"{probe_at:.2f}" in cache
            print(
                f"   [{index}/{len(coarse_times)}] {clock(probe_at)} "
                "샘플 추출·인식 중...",
                flush=True,
            )
            detection = await detect_with_cache(
                shazam, source, probe_at, sample_seconds, temp_dir,
                cache, cache_path,
            )
            if detection:
                detections.append(detection)
                print(
                    f"      ✅ {detection.artist} - {detection.title}",
                    flush=True,
                )
                if current is None:
                    current = detection
                    current_probe_count = 1
                    last_current_at = detection.at
                    print("      ▶️ 첫 곡 추적 시작", flush=True)
                elif detection.key == current.key:
                    current_probe_count += 1
                    last_current_at = detection.at
                    pending = None
                    pending_count = 0
                elif pending and detection.key == pending.key:
                    pending_count += 1
                    if pending_count >= 2:
                        # 마지막 기존 곡 인식과 첫 새 곡 인식의 중간을 전환점으로 사용.
                        boundary = (last_current_at + pending.at) / 2
                        finish_current(boundary)
                        current = pending
                        current_start = boundary
                        current_probe_count = pending_count
                        last_current_at = detection.at
                        print(
                            f"      🔄 새 곡 전환 확정: {clock(boundary)} "
                            f"{current.artist} - {current.title}",
                            flush=True,
                        )
                        pending = None
                        pending_count = 0
                else:
                    pending = detection
                    pending_count = 1
                    print(
                        "      ❔ 다른 곡 1회 감지 — 다음 표본에서 한 번 더 확인",
                        flush=True,
                    )
            else:
                print("      ➖ 미인식", flush=True)
            if not was_cached:
                await asyncio.sleep(args.request_delay)

        # 영상 끝에서 새 곡이 한 번만 잡혔더라도 20초 이상 남았다면 마지막 곡으로 인정.
        if pending and duration - pending.at >= 20:
            boundary = (last_current_at + pending.at) / 2
            finish_current(boundary)
            current = pending
            current_start = boundary
            current_probe_count = pending_count
        finish_current(duration)

    if not segments:
        sys.exit("인식된 곡이 없습니다. 표본 간격을 줄이거나 수동 분할하세요.")
    json_path, csv_path = write_reports(output_dir, source, segments)
    print(f"📋 인식 결과: {csv_path}")
    for index, segment in enumerate(segments, 1):
        print(
            f"   {index:02d}. {clock(segment['start'])} "
            f"{segment['artist']} - {segment['title']}"
        )
    if args.analyze_only:
        state["status"] = "analyzed"
        save_json_atomic(state_path, state)
        print("분석만 완료했습니다. CSV 경계를 확인한 뒤 다시 실행하세요.")
        return
    state["status"] = "complete"
    state["tracks"] = state["tracks"][:len(segments)]
    save_json_atomic(state_path, state)
    print(f"🧾 전체 완료 기록 저장: {state_path}")
    print("✅ 모든 곡 MP3가 순차 분석 중 이미 생성되었습니다.")
    if args.trash_source:
        move_source_to_trash(source)
    print(f"✅ 완료: {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Shazam 인식 결과로 긴 플레이리스트를 곡별 MP3로 분할"
    )
    parser.add_argument("input", help="긴 MP4/오디오 파일")
    parser.add_argument("--output-dir", help="출력 폴더(기본: 원본명_tracks)")
    parser.add_argument("--audio-output-dir",
                        help="MP3만 저장할 별도 폴더(기본: output-dir)")
    parser.add_argument("--filename-prefix", default="",
                        help="각 MP3 파일명 앞에 붙일 원본 구분용 문구")
    parser.add_argument("--interval", type=float, default=30.0,
                        help="1차 인식 간격 초(기본 30)")
    parser.add_argument("--sample-seconds", type=float, default=12.0,
                        help="인식 표본 길이 초(기본 12)")
    parser.add_argument("--refine-step", type=float, default=2.0,
                        help="이전 버전 호환 옵션(순차 즉시 분할에서는 사용하지 않음)")
    parser.add_argument("--request-delay", type=float, default=0.25,
                        help="인식 요청 사이 대기 초(기본 0.25)")
    parser.add_argument("--analyze-only", action="store_true",
                        help="tracklist만 만들고 MP3는 자르지 않음")
    parser.add_argument(
        "--trash-source", action="store_true",
        help="모든 MP3 생성이 성공한 뒤 원본을 휴지통으로 이동",
    )
    args = parser.parse_args()
    if args.interval <= 0 or args.sample_seconds <= 0 or args.refine_step <= 0:
        parser.error("간격과 표본 길이는 0보다 커야 합니다.")
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
