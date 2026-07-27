#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
영상 → 오디오 추출 → 음높이(pitch) 분석 → 평균보다 확연히 높은 "고음 구간"만
모아서 원본 영상에서 잘라 이어붙인 "운동용 영상"을 별도로 만드는 스크립트.

whisper_series_stream.sh(자막/번역/EPUB 파이프라인)와는 독립적으로 동작한다 —
Notion/메모 앱/EPUB 없이 ffmpeg + 음높이 분석만으로 끝나는 별도 도구.

사용법:
  python3 extract_high_pitch_video.py <영상 파일 또는 영상들이 담긴 폴더>

동작 순서:
  1) ffmpeg로 오디오를 wav로 추출 (모노 16000Hz — 목소리 최고음 기준 나이퀴스트 여유 충분,
     22050Hz보다 가볍고 빠름). 같은 이름의 캐시(temp_<파일명>_pitch.wav)가 있으면 재사용
     — whisper_series_stream.sh의 temp_*.wav 캐시 관례와 동일.
  2) librosa.pyin으로 프레임마다 기본주파수(pitch, Hz)를 추정하고 유성음(voiced) 프레임만
     골라 평균 pitch / 최고 pitch를 계산. 긴 영상에서도 메모리가 고정되도록 10분 단위
     청크로 나눠서 분석(오디오 전체를 한 번에 메모리에 올리지 않음).
  3) 평균이 아니라 "유성음 pitch 분포의 상위 --top-percent%"를 고음 기준(threshold)으로 삼아,
     그 기준을 넘는 프레임들을 시간축에서 --max-gap 이내로 붙어있으면 하나의 구간으로 묶는다.
  4) --min-duration보다 짧은 구간은 스파이크로 보고 버리고, 남은 구간 앞뒤로 --pad초 여유를 준다.
  5) ffmpeg로 원본 영상에서 그 구간들만 잘라(재인코딩 후 concat)
     "<파일명>_운동용_상위<퍼센트>퍼센트_<분량>분.mp4" 생성.
  6) bgm/ 폴더에 mp3가 있으면(--no-bgm 안 줬을 때) 그 안의 (미리 잘라놓은) mp3들을 무작위
     순서로 이어붙여 영상 길이만큼 채운 배경음 트랙을 만들고(부족하면 다시 셔플해서 계속
     이어붙임 — 한 파일을 그대로 반복 재생하는 게 아니라 매번 순서를 바꿔가며 이어붙임),
     "<파일명>_운동용_상위<퍼센트>퍼센트_<분량>분_bgm.mp4"로 믹스해서 추가 생성.
     원본 대사 오디오는 그대로 두고
     그 위에 얹는 것이라 --bgm-volume(기본 0.28)으로 배경음 크기만 조절.

예시:
  # 기본값(상위 35%, 1초 이상, 앞뒤 0.8초 여유)으로 처리 — 실전 비교(10/30/40/50/60%) 후 35%로 확정
  python3 extract_high_pitch_video.py MIAA-444.mp4

  # 더 화끈하게(상위 5%만) + 짧은 구간도 허용 + 최대 10개 구간만
  python3 extract_high_pitch_video.py MIAA-444.mp4 --top-percent 5 --min-duration 0.5 --max-clips 10

  # 폴더 안 영상 전부 처리
  python3 extract_high_pitch_video.py ./av2/
"""

import argparse
import glob
import json
import os
import random
import re
import subprocess
import sys
import tempfile

VIDEO_EXTS = (".mp4", ".webm", ".mkv", ".mov")
DEFAULT_BGM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bgm")
DEFAULT_BGM_VOLUME = 0.28
HISTORY_VERSION = 1

# ── 고음 판정 기준 (2026-07-24, 실전 비교 후 확정) ──────────────────
DEFAULT_TOP_PERCENT = 35.0
# 평균-최고 음역 차이가 이보다 작으면(다이나믹 레인지가 좁은 영상) 35%는 너무
# 느슨해서 절반 가까이 뽑혀버리므로, 더 빡빡한 기준으로 자동 전환한다.
LOW_RANGE_GAP_HZ = 200.0
LOW_RANGE_TOP_PERCENT = 15.0


def _ensure_deps():
    """librosa/soundfile이 없으면 조용히 pip install (anaconda python3 기준,
    나머지 스크립트들이 pykakasi/edge-tts를 자동 설치하는 것과 동일한 관례)."""
    try:
        import librosa  # noqa: F401
        import soundfile  # noqa: F401
    except ImportError:
        print("📦 librosa/soundfile 설치 중 (최초 1회)...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "librosa", "soundfile",
             "--quiet", "--disable-pip-version-check"],
            check=False,
        )


_ensure_deps()

import numpy as np  # noqa: E402
import librosa  # noqa: E402
import soundfile as sf  # noqa: E402


OWN_OUTPUT_MARKER = "_운동용"
LEGACY_OUTPUT_MARKERS = ("_고음영상",)


def collect_videos(path):
    """path(폴더/파일)에서 처리할 원본 영상을 모은다.
    폴더 안에 이 스크립트가 만든 결과물(현재 '_운동용', 예전 '_고음영상')이
    원본과 같이 있을 수 있어서, 재추출 시 그것들을 다시 원본인 척 처리하지 않도록
    제외한다."""
    if os.path.isdir(path):
        files = []
        for ext in VIDEO_EXTS:
            files.extend(glob.glob(os.path.join(path, f"*{ext}")))
        output_markers = (OWN_OUTPUT_MARKER, *LEGACY_OUTPUT_MARKERS)
        files = [
            f for f in files
            if not any(marker in os.path.basename(f) for marker in output_markers)
        ]
        return sorted(files)
    if os.path.isfile(path):
        return [path]
    return []


def fmt_time(seconds):
    m, s = divmod(seconds, 60)
    return f"{int(m):02d}:{s:05.2f}"


def fmt_decimal(value):
    """파일명용 소수 한 자리 표기. 정수는 불필요한 .0을 생략한다."""
    return f"{value:.1f}".rstrip("0").rstrip(".")


def extract_audio(video_path, out_wav, sr=16000):
    """오디오를 wav로 추출. 길이가 정상인 캐시만 재사용한다.

    ★ 2026-07-24: 16000Hz면 사람 목소리 최고음(C7≈2093Hz) 기준 나이퀴스트 여유가
    충분해서(8000Hz까지 커버) pitch 분석 용도로는 22050Hz보다 낮춰도 손실이 없다.
    추출 시간/용량이 줄고, 이후 pyin 분석 대상 샘플 수도 같이 줄어든다.

    ★ 2026-07-26: 존재 여부만 확인하면 중간에 끊긴 WAV도 정상 캐시로 오인한다.
    원본 영상과 캐시 길이를 비교하고 2초 넘게 다르면 전체를 다시 추출한다.
    새 WAV는 .partial 파일로 먼저 완성한 뒤 원자적으로 교체하므로, ffmpeg가
    실패하거나 중단돼도 기존 경로에 불완전한 캐시를 남기지 않는다."""
    if os.path.exists(out_wav):
        video_duration = get_media_duration(video_path)
        cache_duration = get_media_duration(out_wav)
        if (video_duration and cache_duration
                and abs(video_duration - cache_duration) <= 2.0):
            print(f"♻️  오디오 캐시 재사용: {out_wav}")
            return out_wav
        print(f"⚠️  불완전한 오디오 캐시 감지: 원본 {(video_duration or 0)/60:.1f}분 / "
              f"캐시 {(cache_duration or 0)/60:.1f}분 — 전체를 다시 추출합니다.")

    print("🎵 오디오 추출 중...")
    partial_wav = out_wav + ".partial.wav"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-ar", str(sr), "-ac", "1", "-vn",
             partial_wav, "-loglevel", "error"],
            check=True,
        )
        video_duration = get_media_duration(video_path)
        extracted_duration = get_media_duration(partial_wav)
        if not extracted_duration or (
            video_duration and abs(video_duration - extracted_duration) > 2.0
        ):
            raise RuntimeError(
                f"오디오 추출 길이 불일치: 원본 {video_duration:.1f}초 / "
                f"추출 {extracted_duration:.1f}초"
            )
        os.replace(partial_wav, out_wav)
    finally:
        if os.path.exists(partial_wav):
            os.remove(partial_wav)
    return out_wav


def analyze_pitch(wav_path, sr=16000, hop_length=2048, chunk_seconds=600.0, chunk_overlap=1.0):
    """프레임별 (시간, pitch Hz, 유성음 여부)를 반환. pitch는 librosa.pyin(확률적 YIN) 사용.

    ★ 2026-07-24: 전체 오디오를 한 번에 메모리에 올려서 pyin을 돌리면 긴 영상(1시간+)
    에서 메모리 사용량이 급증해 컴퓨터가 멈추는 문제가 있었다. chunk_seconds 단위로
    끊어서 읽고(librosa.load의 offset/duration만 사용 — 파일 전체를 메모리에 안 올림)
    분석하도록 바꿔서, 메모리 사용량이 영상 길이와 무관하게 청크 크기로 고정된다.
    hop_length도 512→2048로 늘려 프레임 수를 1/4로 줄여 속도를 크게 높였다 — 어차피
    구간 판정은 초 단위(min_duration/pad)라 128ms 간격이면 정밀도 손실이 없다.
    """
    info = sf.info(wav_path)
    total_duration = info.frames / info.samplerate
    n_chunks = max(1, int(np.ceil(total_duration / chunk_seconds)))

    all_times, all_f0, all_voiced = [], [], []
    offset = 0.0
    chunk_idx = 0
    while offset < total_duration:
        chunk_idx += 1
        read_dur = min(chunk_seconds + chunk_overlap, total_duration - offset)
        y, _ = librosa.load(wav_path, sr=sr, mono=True, offset=offset, duration=read_dur)
        f0, voiced_flag, _voiced_prob = librosa.pyin(
            y,
            fmin=librosa.note_to_hz("C2"),   # ~65Hz
            fmax=librosa.note_to_hz("C7"),   # ~2093Hz — 비명/고음까지 커버
            sr=sr,
            hop_length=hop_length,
        )
        times = librosa.times_like(f0, sr=sr, hop_length=hop_length) + offset

        # 마지막 청크가 아니면 겹친 꼬리 부분(overlap)은 다음 청크에서 다시 다루므로 제외
        keep_end = offset + chunk_seconds
        if keep_end < total_duration:
            keep_mask = times < keep_end
        else:
            keep_mask = np.ones_like(times, dtype=bool)

        all_times.append(times[keep_mask])
        all_f0.append(f0[keep_mask])
        all_voiced.append(np.asarray(voiced_flag, dtype=bool)[keep_mask])

        print(f"   ⏳ 음높이 분석 {chunk_idx}/{n_chunks}청크 완료 "
              f"({fmt_time(offset)} ~ {fmt_time(min(offset + chunk_seconds, total_duration))})")
        offset += chunk_seconds

    times = np.concatenate(all_times)
    f0 = np.concatenate(all_f0)
    voiced_flag = np.concatenate(all_voiced)
    return times, f0, voiced_flag


def find_high_pitch_segments(times, f0, voiced_flag, top_percent=35.0,
                              min_duration=1.0, pad=0.8, max_gap=0.5):
    """평균/최고 pitch + 상위 top_percent% 기준을 넘는 시간 구간 목록을 반환.

    반환: (segments, avg_pitch, peak_pitch, peak_time, threshold)
    segments: [{"start": s, "end": e, "peak_hz": p}, ...] (시간순 정렬)
    """
    voiced_idx = np.where(voiced_flag)[0]
    if len(voiced_idx) == 0:
        return [], None, None, None, None

    voiced_pitches = f0[voiced_idx]
    avg_pitch = float(np.mean(voiced_pitches))
    peak_local = int(np.argmax(voiced_pitches))
    peak_idx = voiced_idx[peak_local]
    peak_pitch = float(f0[peak_idx])
    peak_time = float(times[peak_idx])
    threshold = float(np.percentile(voiced_pitches, 100 - top_percent))

    is_high = voiced_flag & (f0 >= threshold)

    raw_segments = []
    seg_start = None
    last_high_time = None
    for t, high in zip(times, is_high):
        if high:
            if seg_start is None:
                seg_start = t
            last_high_time = t
        elif seg_start is not None and (t - last_high_time) > max_gap:
            raw_segments.append((seg_start, last_high_time))
            seg_start = None
    if seg_start is not None:
        raw_segments.append((seg_start, last_high_time))

    # 앞뒤 여유(pad) 적용 후 겹치는 구간은 하나로 합침
    padded = sorted((max(0.0, s - pad), e + pad) for s, e in raw_segments)
    merged = []
    for s, e in padded:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    segments = []
    for s, e in merged:
        if (e - s) < min_duration:
            continue
        mask = (times >= s) & (times <= e) & voiced_flag
        seg_peak = float(np.max(f0[mask])) if mask.any() else threshold
        segments.append({"start": s, "end": e, "peak_hz": seg_peak})

    return segments, avg_pitch, peak_pitch, peak_time, threshold


def find_top_percent_for_duration(times, f0, voiced_flag, target_min_sec, target_max_sec,
                                   min_duration=1.0, pad=0.8, max_gap=0.5, max_iter=20):
    """결과 영상 길이가 [target_min_sec, target_max_sec] 안에 들어오도록 top_percent를
    이분 탐색으로 자동으로 찾는다. top_percent가 클수록(더 느슨한 기준) 뽑히는 구간의
    총 길이가 늘어나는 단조 관계를 이용 — find_high_pitch_segments 자체는 numpy 연산이라
    가볍기 때문에 pyin을 다시 돌리지 않고 여러 번 반복해도 빠르다.

    반환: find_high_pitch_segments와 동일한 5-튜플 + (top_percent, total_duration)
    목표 범위에 정확히 들어오지 못하면 가장 근접했던 결과를 반환한다.
    """
    lo, hi = 1.0, 90.0
    best = None
    best_dist = None
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        segments, avg_pitch, peak_pitch, peak_time, threshold = find_high_pitch_segments(
            times, f0, voiced_flag, top_percent=mid,
            min_duration=min_duration, pad=pad, max_gap=max_gap,
        )
        total = sum(s["end"] - s["start"] for s in segments)

        if total < target_min_sec:
            dist = target_min_sec - total
        elif total > target_max_sec:
            dist = total - target_max_sec
        else:
            dist = 0.0

        print(f"   🔍 상위 {mid:.1f}% 시도 → 결과 길이 {total/60:.1f}분")

        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = (segments, avg_pitch, peak_pitch, peak_time, threshold, mid, total)

        if dist == 0.0:
            break
        if total < target_min_sec:
            lo = mid  # 더 느슨하게(퍼센트 ↑) → 길이 증가
        else:
            hi = mid  # 더 빡빡하게(퍼센트 ↓) → 길이 감소

    return best


def build_highlight_video(video_path, segments, out_path, tmp_dir):
    """segments 구간들을 원본 영상에서 잘라 이어붙여 out_path로 저장."""
    clip_paths = []
    for i, seg in enumerate(segments):
        clip_path = os.path.join(tmp_dir, f"clip_{i:03d}.mp4")
        duration = seg["end"] - seg["start"]
        subprocess.run(
            ["ffmpeg", "-y",
             "-ss", f"{seg['start']:.3f}", "-i", video_path,
             "-t", f"{duration:.3f}",
             "-c:v", "libx264", "-c:a", "aac", "-avoid_negative_ts", "make_zero",
             clip_path, "-loglevel", "error"],
            check=True,
        )
        if os.path.exists(clip_path):
            clip_paths.append(clip_path)

    if not clip_paths:
        return False

    list_path = os.path.join(tmp_dir, "concat_list.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
         "-c", "copy", out_path, "-loglevel", "error"],
        check=True,
    )
    return os.path.exists(out_path)


def get_media_duration(path):
    """ffprobe로 오디오/영상 길이(초)를 가져옴. 실패하면 None."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def extraction_history_path(work_dir, base):
    """정리 전에는 영상 옆, 정리 후에는 기타 폴더에 있는 추출 기록을 찾는다."""
    filename = f"{base}_운동용_추출기록.json"
    candidates = [
        os.path.join(work_dir, filename),
        os.path.join(work_dir, "기타", filename),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return candidates[0]


def load_extraction_history(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if data.get("version") == HISTORY_VERSION else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_extraction_history(path, data):
    """중단 시 반쪽 JSON이 남지 않도록 임시 파일 완성 후 원자적으로 교체한다."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    partial = path + ".partial"
    with open(partial, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(partial, path)


def source_fingerprint(video_path):
    stat = os.stat(video_path)
    return {
        "name": os.path.basename(video_path),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def highlight_settings(args):
    """음높이 분석과 구간/영상 생성 결과에 영향을 주는 설정."""
    return {
        "target_minutes": args.target_minutes,
        "target_tolerance": args.target_tolerance,
        "top_percent": args.top_percent,
        "min_duration": args.min_duration,
        "pad": args.pad,
        "max_gap": args.max_gap,
        "max_clips": args.max_clips,
        "analysis_sr": 16000,
        "analysis_hop_length": 2048,
    }


def bgm_settings(args):
    """BGM 파일 구성이 바뀌면 믹스만 다시 만들 수 있도록 별도 지문을 만든다."""
    mp3s = sorted(glob.glob(os.path.join(args.bgm_dir or "", "*.mp3")))
    files = []
    for path in mp3s:
        try:
            stat = os.stat(path)
            files.append([os.path.basename(path), stat.st_size, stat.st_mtime_ns])
        except OSError:
            continue
    return {
        "volume": args.bgm_volume,
        "title_enabled": not args.no_bgm_title,
        "title_seconds": args.bgm_title_seconds,
        "files": files,
    }


def resolve_recorded_output(work_dir, recorded_name):
    """최종 정리로 결과가 기타 폴더에 이동된 경우까지 확인한다."""
    if not recorded_name:
        return None
    basename = os.path.basename(recorded_name)
    candidates = [
        os.path.join(work_dir, basename),
        os.path.join(work_dir, "기타", basename),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
            if get_media_duration(candidate):
                return candidate
    return None


def find_compatible_existing_highlight(work_dir, base, args):
    """JSON 기록 도입 전에 만든 무BGM 운동용 영상도 설정이 맞으면 재사용한다.

    목표 분량 실행은 파일명의 실제 결과 분량이 목표±허용오차에 들고 여유 초가
    같으면 호환된다. 고정 top-percent 실행은 퍼센트와 여유 초가 모두 같아야 한다.
    자동 기본 퍼센트 실행은 저음역 자동 보정 여부를 파일명만으로 확정할 수 없어
    기존 파일을 임의 채택하지 않는다.
    """
    escaped_base = re.escape(base)
    pattern = re.compile(
        rf"^{escaped_base}{re.escape(OWN_OUTPUT_MARKER)}_"
        rf"상위(?P<top>\d+(?:\.\d+)?)퍼센트_"
        rf"(?P<minutes>\d+(?:\.\d+)?)분_"
        rf"여유(?P<pad>\d+(?:\.\d+)?)초\.mp4$"
    )
    candidates = []
    for directory in (work_dir, os.path.join(work_dir, "기타")):
        candidates.extend(glob.glob(os.path.join(directory, f"{base}{OWN_OUTPUT_MARKER}_*.mp4")))

    for candidate in sorted(candidates, key=os.path.getmtime, reverse=True):
        match = pattern.match(os.path.basename(candidate))
        if not match or os.path.getsize(candidate) <= 0:
            continue
        top_percent = float(match.group("top"))
        result_minutes = float(match.group("minutes"))
        pad = float(match.group("pad"))
        if abs(pad - args.pad) > 0.0001:
            continue
        if args.target_minutes is not None:
            lower = max(0.0, args.target_minutes - args.target_tolerance)
            upper = args.target_minutes + args.target_tolerance
            if not (lower <= result_minutes <= upper):
                continue
        elif args.top_percent is not None:
            if abs(top_percent - args.top_percent) > 0.05:
                continue
        else:
            continue
        actual_duration = get_media_duration(candidate)
        if not actual_duration:
            continue
        stats_tag = os.path.basename(candidate)[
            len(f"{base}{OWN_OUTPUT_MARKER}_"):-len(".mp4")
        ]
        return {
            "path": candidate,
            "top_percent": top_percent,
            "duration_seconds": actual_duration,
            "stats_tag": stats_tag,
        }
    return None


def build_bgm_track(bgm_dir, target_duration, tmp_dir):
    """bgm_dir 안의 (미리 잘라놓은) mp3들을 무작위 순서로 이어붙여 target_duration초
    이상 되는 오디오 트랙 하나를 만들어 경로를 반환. 파일들을 다 이어붙여도 모자라면
    다시 셔플해서 이어붙이는 걸 반복(재생목록을 반복 순환하는 것과 같은 효과 —
    다만 한 파일을 그대로 반복 재생하는 게 아니라 매번 순서를 바꿔 이어붙임).
    폴더가 없거나 mp3가 하나도 없으면 (None, []).
    반환하는 두 번째 값은 영상에 곡 제목을 표시하기 위한 시작 시각 목록."""
    if not bgm_dir or not os.path.isdir(bgm_dir):
        return None, []
    mp3s = glob.glob(os.path.join(bgm_dir, "*.mp3"))
    if not mp3s:
        return None, []

    durations = {p: (get_media_duration(p) or 3.0) for p in mp3s}

    pool = list(mp3s)
    random.shuffle(pool)
    playlist, title_cues, total, idx = [], [], 0.0, 0
    while total < target_duration:
        if idx >= len(pool):
            random.shuffle(pool)
            idx = 0
        p = pool[idx]
        playlist.append(p)
        clip_duration = durations[p]
        title = os.path.splitext(os.path.basename(p))[0]
        # 자동 분할 파일의 "01 - "과 " - A1B2C3" 고유 ID는 화면에서 숨긴다.
        title = re.sub(r"^\d{2}\s*-\s*", "", title)
        title = re.sub(r"\s*-\s*[A-Fa-f0-9]{6}$", "", title)
        if len(title) > 70:
            title = title[:67].rstrip() + "…"
        title_cues.append({
            "start": total,
            "duration": clip_duration,
            "title": title,
        })
        total += clip_duration
        idx += 1

    inputs = []
    for p in playlist:
        inputs += ["-i", p]
    concat_inputs = "".join(f"[{i}:a]" for i in range(len(playlist)))
    filter_complex = f"{concat_inputs}concat=n={len(playlist)}:v=0:a=1[bgmtrack]"

    bgm_track = os.path.join(tmp_dir, "bgm_track.m4a")
    subprocess.run(
        ["ffmpeg", "-y", *inputs,
         "-filter_complex", filter_complex, "-map", "[bgmtrack]",
         "-c:a", "aac", bgm_track, "-loglevel", "error"],
        check=True,
    )
    if os.path.exists(bgm_track):
        print(f"  🔗 배경음 {len(playlist)}개 클립 이어붙임 (합계 {total:.1f}초): "
              + ", ".join(os.path.basename(p) for p in playlist))
    if not os.path.exists(bgm_track):
        return None, []
    return bgm_track, title_cues


def ass_time(seconds):
    """ASS 자막 시각 형식 H:MM:SS.cc."""
    centiseconds = max(0, int(round(seconds * 100)))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cents = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cents:02d}"


def write_bgm_title_ass(title_cues, path, display_seconds=4.0):
    """BGM이 바뀔 때 잠깐 표시할 제목 ASS 자막을 만든다."""
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: BGM,Apple SD Gothic Neo,52,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,3,1,0,2,80,80,65,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for cue in title_cues:
        start = cue["start"]
        end = start + min(display_seconds, cue["duration"])
        title = cue["title"].replace("\\", r"\\")
        title = title.replace("{", r"\{").replace("}", r"\}")
        title = title.replace("\n", r"\N")
        lines.append(
            f"Dialogue: 0,{ass_time(start)},{ass_time(end)},"
            f"BGM,,0,0,0,,♫ {title}\n"
        )
    with open(path, "w", encoding="utf-8") as file:
        file.writelines(lines)


def mix_background_audio(
    video_path, bgm_track_path, out_path, bgm_volume=DEFAULT_BGM_VOLUME,
    title_cues=None, title_seconds=4.0,
):
    """video_path의 기존 오디오는 100%로 두고 bgm_track_path를 얹어 out_path에 저장.
    amix의 duration=first로 영상 길이에 맞춰 잘림(bgm_track_path는 build_bgm_track에서
    이미 영상 길이 이상으로 만들어둔 상태). amix 자동 정규화는 원본 음성까지 낮추므로
    끄고, 마지막에 limiter로 합산 피크의 클리핑만 방지한다."""
    title_cues = title_cues or []
    filter_parts = []
    video_map = "0:v"
    video_codec = ["-c:v", "copy"]
    ffmpeg_exe = "ffmpeg"
    if title_cues and title_seconds > 0:
        ass_path = os.path.join(
            os.path.dirname(os.path.abspath(bgm_track_path)),
            "bgm_titles.ass",
        )
        write_bgm_title_ass(title_cues, ass_path, title_seconds)
        escaped_ass = ass_path.replace("\\", r"\\").replace(":", r"\:")
        escaped_ass = escaped_ass.replace("'", r"\'")
        filter_parts.append(f"[0:v]ass=filename='{escaped_ass}'[vout]")
        video_map = "[vout]"
        video_codec = ["-c:v", "libx264", "-preset", "medium", "-crf", "18"]
        # Homebrew 기본 빌드에는 libass/drawtext가 빠져 있다. Anaconda판은
        # libass가 포함되어 있으므로 제목 합성 단계에서만 이 실행 파일을 쓴다.
        ffmpeg_exe = "/opt/anaconda3/bin/ffmpeg"
    filter_parts.append(
        f"[1:a]volume={bgm_volume}[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0:"
        f"normalize=0,alimiter=limit=0.95[aout]"
    )
    subprocess.run(
        [ffmpeg_exe, "-y",
         "-i", video_path,
         "-i", bgm_track_path,
         "-filter_complex",
         ";".join(filter_parts),
         "-map", video_map, "-map", "[aout]",
         *video_codec, "-c:a", "aac",
         out_path, "-loglevel", "error"],
        check=True,
    )
    return os.path.exists(out_path)


def process_video(video_path, args):
    base = os.path.splitext(os.path.basename(video_path))[0]
    work_dir = os.path.dirname(os.path.abspath(video_path)) or "."
    tmp_wav = os.path.join(work_dir, f"temp_{base}_pitch.wav")
    history_path = extraction_history_path(work_dir, base)
    history = load_extraction_history(history_path)
    current_source = source_fingerprint(video_path)
    current_settings = highlight_settings(args)

    print(f"\n{'='*54}")
    print(f"🎙️  {base} — 음높이 분석 시작")
    print(f"{'='*54}")

    cached_highlight = None
    if (history.get("source") == current_source
            and history.get("highlight_settings") == current_settings):
        cached_highlight = resolve_recorded_output(
            work_dir, history.get("highlight", {}).get("file")
        )

    if not cached_highlight:
        legacy_highlight = find_compatible_existing_highlight(
            work_dir, base, args
        )
        if legacy_highlight:
            cached_highlight = legacy_highlight["path"]
            history = {
                "version": HISTORY_VERSION,
                "source": current_source,
                "highlight_settings": current_settings,
                "highlight": {
                    "file": os.path.basename(cached_highlight),
                    "top_percent": legacy_highlight["top_percent"],
                    "duration_seconds": legacy_highlight["duration_seconds"],
                    "stats_tag": legacy_highlight["stats_tag"],
                },
            }
            save_extraction_history(history_path, history)
            print(f"🧾 기존 고음 영상에서 재사용 기록 자동 복구: {history_path}")

    if cached_highlight:
        highlight_info = history["highlight"]
        out_path = cached_highlight
        top_percent = highlight_info["top_percent"]
        total_dur = highlight_info["duration_seconds"]
        stats_tag = highlight_info["stats_tag"]
        print(f"♻️  동일한 목표 분량·여유 초의 성공 기록 발견: {history_path}")
        print(f"♻️  음높이 분석과 고음 영상 재인코딩 생략: {out_path}")
    else:
        extract_audio(video_path, tmp_wav)

        print("📈 음높이(pitch) 분석 중...")
        times, f0, voiced_flag = analyze_pitch(tmp_wav)

        if args.target_minutes is not None:
        # ★ 2026-07-24: "퍼센트"가 아니라 "결과 길이(분)"를 직접 지정하고 싶다는 요청 —
        # top_percent를 이분 탐색으로 자동으로 찾아서 목표 길이(±tolerance분) 안에 맞춘다.
            target_min_sec = max(0.0, args.target_minutes - args.target_tolerance) * 60
            target_max_sec = (args.target_minutes + args.target_tolerance) * 60
            print(f"🎯 목표 길이 {args.target_minutes:.0f}분(±{args.target_tolerance:.0f}분)에 맞는 "
                  f"상위 퍼센트 탐색 중...")
            result = find_top_percent_for_duration(
                times, f0, voiced_flag,
                target_min_sec, target_max_sec,
                min_duration=args.min_duration, pad=args.pad, max_gap=args.max_gap,
            )
            if result is None:
                print("⚠️  유성음 구간을 찾지 못했습니다 (오디오에 목소리가 거의 없는 것으로 보임).")
                return
            segments, avg_pitch, peak_pitch, peak_time, threshold, top_percent, total_dur = result
            print(f"✅ 상위 {top_percent:.1f}%로 확정 (결과 길이 {total_dur/60:.1f}분)")
        else:
            top_percent = args.top_percent if args.top_percent is not None else DEFAULT_TOP_PERCENT
            segments, avg_pitch, peak_pitch, peak_time, threshold = find_high_pitch_segments(
                times, f0, voiced_flag,
                top_percent=top_percent, min_duration=args.min_duration,
                pad=args.pad, max_gap=args.max_gap,
            )

            if avg_pitch is None:
                print("⚠️  유성음 구간을 찾지 못했습니다 (오디오에 목소리가 거의 없는 것으로 보임).")
                return

            if args.top_percent is None and (peak_pitch - avg_pitch) < LOW_RANGE_GAP_HZ:
                print(f"ℹ️  평균-최고 음역 차이가 {peak_pitch - avg_pitch:.0f}Hz로 작아서, "
                      f"상위 {top_percent:.0f}% 대신 {LOW_RANGE_TOP_PERCENT:.0f}%로 다시 계산합니다.")
                top_percent = LOW_RANGE_TOP_PERCENT
                segments, avg_pitch, peak_pitch, peak_time, threshold = find_high_pitch_segments(
                    times, f0, voiced_flag,
                    top_percent=top_percent, min_duration=args.min_duration,
                    pad=args.pad, max_gap=args.max_gap,
                )

        print(f"📊 평균 pitch: {avg_pitch:.0f}Hz  /  최고 pitch: {peak_pitch:.0f}Hz ({fmt_time(peak_time)} 지점)")
        print(f"🔺 고음 기준(상위 {top_percent:.0f}%): {threshold:.0f}Hz 이상")

        if not segments:
            print("⚠️  고음 구간을 찾지 못했습니다. --top-percent를 높이거나 --min-duration을 줄여보세요.")
            return

        if args.max_clips and len(segments) > args.max_clips:
            segments = sorted(segments, key=lambda s: -s["peak_hz"])[:args.max_clips]
            segments.sort(key=lambda s: s["start"])

        total_dur = sum(s["end"] - s["start"] for s in segments)
        print(f"🎬 고음 구간 {len(segments)}개 (합계 {total_dur:.1f}초):")
        for seg in segments:
            dur = seg["end"] - seg["start"]
            print(f"   {fmt_time(seg['start'])} ~ {fmt_time(seg['end'])}  ({dur:.1f}초, 피크 {seg['peak_hz']:.0f}Hz)")

        stats_tag = (
            f"상위{fmt_decimal(top_percent)}퍼센트_"
            f"{fmt_decimal(total_dur / 60)}분_"
            f"여유{fmt_decimal(args.pad)}초"
        )
        out_path = os.path.join(work_dir, f"{base}{OWN_OUTPUT_MARKER}_{stats_tag}.mp4")
        print(f"✂️  구간 잘라 이어붙이는 중 → {out_path}")
        with tempfile.TemporaryDirectory() as tmp_dir:
            ok = build_highlight_video(video_path, segments, out_path, tmp_dir)

        if not ok:
            print("❌ 운동용 영상 생성 실패")
            return

        size_mb = os.path.getsize(out_path) / (1024 * 1024)
        print(f"✅ 운동용 영상 생성 완료: {out_path} ({size_mb:.1f}MB)")
        history = {
            "version": HISTORY_VERSION,
            "source": current_source,
            "highlight_settings": current_settings,
            "highlight": {
                "file": os.path.basename(out_path),
                "top_percent": top_percent,
                "duration_seconds": total_dur,
                "stats_tag": stats_tag,
            },
        }
        save_extraction_history(history_path, history)
        print(f"🧾 재사용 기록 저장: {history_path}")

    if args.no_bgm:
        return

    if not (args.bgm_dir and os.path.isdir(args.bgm_dir) and glob.glob(os.path.join(args.bgm_dir, "*.mp3"))):
        print(f"ℹ️  배경음 건너뜀 ({args.bgm_dir}에 mp3 없음) — bgm/ 폴더에 mp3를 넣으면 자동으로 입혀짐.")
        return

    video_duration = get_media_duration(out_path) or total_dur
    bgm_percent = fmt_decimal(args.bgm_volume * 100)
    bgm_out = os.path.join(
        work_dir,
        f"{base}{OWN_OUTPUT_MARKER}_{stats_tag}_"
        f"BGM{bgm_percent}퍼센트_bgm.mp4",
    )
    current_bgm_settings = bgm_settings(args)
    cached_bgm = None
    if history.get("bgm_settings") == current_bgm_settings:
        cached_bgm = resolve_recorded_output(
            work_dir, history.get("bgm", {}).get("file")
        )
    if cached_bgm:
        print(f"♻️  같은 BGM 설정의 완성 영상 재사용: {cached_bgm}")
        return

    print(f"🎵 배경음 입히는 중 (볼륨 {args.bgm_volume:.0%})...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        bgm_track, title_cues = build_bgm_track(
            args.bgm_dir, video_duration, tmp_dir
        )
        bgm_ok = bool(bgm_track) and mix_background_audio(
            out_path, bgm_track, bgm_out,
            bgm_volume=args.bgm_volume,
            title_cues=[] if args.no_bgm_title else title_cues,
            title_seconds=args.bgm_title_seconds,
        )
    if bgm_ok:
        size_mb2 = os.path.getsize(bgm_out) / (1024 * 1024)
        print(f"✅ 배경음 입힌 영상: {bgm_out} ({size_mb2:.1f}MB)")
        history["bgm_settings"] = current_bgm_settings
        history["bgm"] = {"file": os.path.basename(bgm_out)}
        save_extraction_history(history_path, history)
    else:
        print("❌ 배경음 입히기 실패")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("path", help="영상 파일 경로 또는 영상들이 담긴 폴더 경로")
    ap.add_argument("--top-percent", type=float, default=None,
                     help=f"고음 판정 기준: 유성음 pitch 분포 중 상위 N%% (기본 {DEFAULT_TOP_PERCENT:.0f} — 실전 비교 후 확정, 2026-07-24). "
                          f"명시적으로 주면 그 값을 그대로 쓰고, 평균-최고 음역 차이가 작아도 자동조정하지 않는다 "
                          f"(자동조정은 기본값을 쓸 때만 적용됨 — 평균-최고 차이 {LOW_RANGE_GAP_HZ:.0f}Hz 미만이면 {LOW_RANGE_TOP_PERCENT:.0f}%로 전환)")
    ap.add_argument("--min-duration", type=float, default=1.0,
                     help="이보다 짧은 고음 구간은 버림 (초, 기본 1.0)")
    ap.add_argument("--pad", type=float, default=1.0,
                     help="추출 구간 앞뒤 여유 (초, 기본 1.0)")
    ap.add_argument("--max-gap", type=float, default=0.5,
                     help="이 간격(초) 이내로 붙어있는 고음 프레임은 하나의 구간으로 합침 (기본 0.5)")
    ap.add_argument("--max-clips", type=int, default=None,
                     help="피크 pitch 기준 상위 N개 구간만 사용 (기본: 전부 사용)")
    ap.add_argument("--target-minutes", type=float, default=None,
                     help="결과 영상 길이를 퍼센트 대신 '목표 분(分)'으로 지정 — 지정하면 "
                          "--top-percent는 무시하고 이 길이(±--target-tolerance분)에 맞는 "
                          "퍼센트를 이분 탐색으로 자동으로 찾는다. 예: --target-minutes 35")
    ap.add_argument("--target-tolerance", type=float, default=5.0,
                     help="--target-minutes 허용 오차(분, 기본 5 — 즉 목표 35분이면 30~40분에 들어오면 통과)")
    ap.add_argument("--bgm-dir", default=DEFAULT_BGM_DIR,
                     help=f"배경음 mp3가 담긴 폴더 (기본: {DEFAULT_BGM_DIR})")
    ap.add_argument("--bgm-volume", type=float, default=DEFAULT_BGM_VOLUME,
                     help="배경음 볼륨 배율, 0~1 (기본 0.28 — 원본 대사 오디오는 100% 유지)")
    ap.add_argument("--no-bgm", action="store_true",
                     help="배경음 입히기 건너뛰고 운동용 영상만 생성")
    ap.add_argument("--bgm-title-seconds", type=float, default=4.0,
                    help="새 BGM 제목을 영상 하단에 표시할 시간(초, 기본 4)")
    ap.add_argument("--no-bgm-title", action="store_true",
                    help="BGM 제목 화면 표시를 끔")
    args = ap.parse_args()

    videos = collect_videos(args.path)
    if not videos:
        sys.exit(f"처리할 영상을 찾을 수 없습니다: {args.path}")

    print(f"📋 대상 영상 {len(videos)}개: {[os.path.basename(v) for v in videos]}")
    for video_path in videos:
        process_video(video_path, args)

    print(f"\n{'='*54}")
    print("🎉 모든 영상 처리 완료!")
    print(f"{'='*54}")


if __name__ == "__main__":
    main()
