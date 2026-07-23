#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
영상 → 오디오 추출 → 음높이(pitch) 분석 → 평균보다 확연히 높은 "고음 구간"만
모아서 원본 영상에서 잘라 이어붙인 "고음영상"을 별도로 만드는 스크립트.

whisper_series_stream.sh(자막/번역/EPUB 파이프라인)와는 독립적으로 동작한다 —
Notion/메모 앱/EPUB 없이 ffmpeg + 음높이 분석만으로 끝나는 별도 도구.

사용법:
  python3 extract_high_pitch_video.py <영상 파일 또는 영상들이 담긴 폴더>

동작 순서:
  1) ffmpeg로 오디오를 wav로 추출 (모노 22050Hz). 같은 이름의 캐시(temp_<파일명>_pitch.wav)가
     있으면 재사용 — whisper_series_stream.sh의 temp_*.wav 캐시 관례와 동일.
  2) librosa.pyin으로 프레임마다 기본주파수(pitch, Hz)를 추정하고 유성음(voiced) 프레임만
     골라 평균 pitch / 최고 pitch를 계산.
  3) 평균이 아니라 "유성음 pitch 분포의 상위 --top-percent%"를 고음 기준(threshold)으로 삼아,
     그 기준을 넘는 프레임들을 시간축에서 --max-gap 이내로 붙어있으면 하나의 구간으로 묶는다.
  4) --min-duration보다 짧은 구간은 스파이크로 보고 버리고, 남은 구간 앞뒤로 --pad초 여유를 준다.
  5) ffmpeg로 원본 영상에서 그 구간들만 잘라(재인코딩 후 concat) "<파일명>_고음영상.mp4" 생성.
  6) bgm/ 폴더에 mp3가 있으면(--no-bgm 안 줬을 때) 그 안의 (미리 잘라놓은) mp3들을 무작위
     순서로 이어붙여 영상 길이만큼 채운 배경음 트랙을 만들고(부족하면 다시 셔플해서 계속
     이어붙임 — 한 파일을 그대로 반복 재생하는 게 아니라 매번 순서를 바꿔가며 이어붙임),
     "<파일명>_고음영상_bgm.mp4"로 믹스해서 추가 생성. 원본 대사 오디오는 그대로 두고
     그 위에 얹는 것이라 --bgm-volume(기본 0.5)으로 배경음 크기만 조절.

예시:
  # 기본값(상위 10%, 1초 이상, 앞뒤 0.3초 여유)으로 처리
  python3 extract_high_pitch_video.py MIAA-444.mp4

  # 더 화끈하게(상위 5%만) + 짧은 구간도 허용 + 최대 10개 구간만
  python3 extract_high_pitch_video.py MIAA-444.mp4 --top-percent 5 --min-duration 0.5 --max-clips 10

  # 폴더 안 영상 전부 처리
  python3 extract_high_pitch_video.py ./av2/
"""

import argparse
import glob
import os
import random
import subprocess
import sys
import tempfile

VIDEO_EXTS = (".mp4", ".webm", ".mkv", ".mov")
DEFAULT_BGM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bgm")


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


def collect_videos(path):
    if os.path.isdir(path):
        files = []
        for ext in VIDEO_EXTS:
            files.extend(glob.glob(os.path.join(path, f"*{ext}")))
        return sorted(files)
    if os.path.isfile(path):
        return [path]
    return []


def fmt_time(seconds):
    m, s = divmod(seconds, 60)
    return f"{int(m):02d}:{s:05.2f}"


def extract_audio(video_path, out_wav, sr=22050):
    """오디오를 wav로 추출. 캐시가 있으면 재사용(휘퍼 파이프라인의 temp_*.wav 관례와 동일)."""
    if os.path.exists(out_wav):
        print(f"♻️  오디오 캐시 재사용: {out_wav}")
        return out_wav
    print("🎵 오디오 추출 중...")
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-ar", str(sr), "-ac", "1", "-vn",
         out_wav, "-loglevel", "error"],
        check=True,
    )
    return out_wav


def analyze_pitch(wav_path, sr=22050, hop_length=512):
    """프레임별 (시간, pitch Hz, 유성음 여부)를 반환. pitch는 librosa.pyin(확률적 YIN) 사용."""
    y, sr = librosa.load(wav_path, sr=sr, mono=True)
    f0, voiced_flag, _voiced_prob = librosa.pyin(
        y,
        fmin=librosa.note_to_hz("C2"),   # ~65Hz
        fmax=librosa.note_to_hz("C7"),   # ~2093Hz — 비명/고음까지 커버
        sr=sr,
        hop_length=hop_length,
    )
    times = librosa.times_like(f0, sr=sr, hop_length=hop_length)
    voiced_flag = np.asarray(voiced_flag, dtype=bool)
    return times, f0, voiced_flag


def find_high_pitch_segments(times, f0, voiced_flag, top_percent=10.0,
                              min_duration=1.0, pad=0.3, max_gap=0.5):
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


def build_bgm_track(bgm_dir, target_duration, tmp_dir):
    """bgm_dir 안의 (미리 잘라놓은) mp3들을 무작위 순서로 이어붙여 target_duration초
    이상 되는 오디오 트랙 하나를 만들어 경로를 반환. 파일들을 다 이어붙여도 모자라면
    다시 셔플해서 이어붙이는 걸 반복(재생목록을 반복 순환하는 것과 같은 효과 —
    다만 한 파일을 그대로 반복 재생하는 게 아니라 매번 순서를 바꿔 이어붙임).
    폴더가 없거나 mp3가 하나도 없으면 None."""
    if not bgm_dir or not os.path.isdir(bgm_dir):
        return None
    mp3s = glob.glob(os.path.join(bgm_dir, "*.mp3"))
    if not mp3s:
        return None

    durations = {p: (get_media_duration(p) or 3.0) for p in mp3s}

    pool = list(mp3s)
    random.shuffle(pool)
    playlist, total, idx = [], 0.0, 0
    while total < target_duration:
        if idx >= len(pool):
            random.shuffle(pool)
            idx = 0
        p = pool[idx]
        playlist.append(p)
        total += durations[p]
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
    return bgm_track if os.path.exists(bgm_track) else None


def mix_background_audio(video_path, bgm_track_path, out_path, bgm_volume=0.5):
    """video_path의 기존 오디오는 그대로 두고 bgm_track_path를 얹어 out_path에 저장.
    amix의 duration=first로 영상 길이에 맞춰 잘림(bgm_track_path는 build_bgm_track에서
    이미 영상 길이 이상으로 만들어둔 상태)."""
    subprocess.run(
        ["ffmpeg", "-y",
         "-i", video_path,
         "-i", bgm_track_path,
         "-filter_complex",
         f"[1:a]volume={bgm_volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0[aout]",
         "-map", "0:v", "-map", "[aout]",
         "-c:v", "copy", "-c:a", "aac",
         out_path, "-loglevel", "error"],
        check=True,
    )
    return os.path.exists(out_path)


def process_video(video_path, args):
    base = os.path.splitext(os.path.basename(video_path))[0]
    work_dir = os.path.dirname(os.path.abspath(video_path)) or "."
    tmp_wav = os.path.join(work_dir, f"temp_{base}_pitch.wav")

    print(f"\n{'='*54}")
    print(f"🎙️  {base} — 음높이 분석 시작")
    print(f"{'='*54}")

    extract_audio(video_path, tmp_wav)

    print("📈 음높이(pitch) 분석 중...")
    times, f0, voiced_flag = analyze_pitch(tmp_wav)
    segments, avg_pitch, peak_pitch, peak_time, threshold = find_high_pitch_segments(
        times, f0, voiced_flag,
        top_percent=args.top_percent, min_duration=args.min_duration,
        pad=args.pad, max_gap=args.max_gap,
    )

    if avg_pitch is None:
        print("⚠️  유성음 구간을 찾지 못했습니다 (오디오에 목소리가 거의 없는 것으로 보임).")
        return

    print(f"📊 평균 pitch: {avg_pitch:.0f}Hz  /  최고 pitch: {peak_pitch:.0f}Hz ({fmt_time(peak_time)} 지점)")
    print(f"🔺 고음 기준(상위 {args.top_percent:.0f}%): {threshold:.0f}Hz 이상")

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

    out_path = os.path.join(work_dir, f"{base}_고음영상.mp4")
    print(f"✂️  구간 잘라 이어붙이는 중 → {out_path}")
    with tempfile.TemporaryDirectory() as tmp_dir:
        ok = build_highlight_video(video_path, segments, out_path, tmp_dir)

    if not ok:
        print("❌ 고음영상 생성 실패")
        return

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"✅ 고음영상 생성 완료: {out_path} ({size_mb:.1f}MB)")

    if args.no_bgm:
        return

    if not (args.bgm_dir and os.path.isdir(args.bgm_dir) and glob.glob(os.path.join(args.bgm_dir, "*.mp3"))):
        print(f"ℹ️  배경음 건너뜀 ({args.bgm_dir}에 mp3 없음) — bgm/ 폴더에 mp3를 넣으면 자동으로 입혀짐.")
        return

    video_duration = get_media_duration(out_path) or total_dur
    bgm_out = os.path.join(work_dir, f"{base}_고음영상_bgm.mp4")
    print(f"🎵 배경음 입히는 중 (볼륨 {args.bgm_volume:.0%})...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        bgm_track = build_bgm_track(args.bgm_dir, video_duration, tmp_dir)
        bgm_ok = bool(bgm_track) and mix_background_audio(
            out_path, bgm_track, bgm_out, bgm_volume=args.bgm_volume
        )
    if bgm_ok:
        size_mb2 = os.path.getsize(bgm_out) / (1024 * 1024)
        print(f"✅ 배경음 입힌 영상: {bgm_out} ({size_mb2:.1f}MB)")
    else:
        print("❌ 배경음 입히기 실패")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("path", help="영상 파일 경로 또는 영상들이 담긴 폴더 경로")
    ap.add_argument("--top-percent", type=float, default=10.0,
                     help="고음 판정 기준: 유성음 pitch 분포 중 상위 N%% (기본 10)")
    ap.add_argument("--min-duration", type=float, default=1.0,
                     help="이보다 짧은 고음 구간은 버림 (초, 기본 1.0)")
    ap.add_argument("--pad", type=float, default=0.3,
                     help="추출 구간 앞뒤 여유 (초, 기본 0.3)")
    ap.add_argument("--max-gap", type=float, default=0.5,
                     help="이 간격(초) 이내로 붙어있는 고음 프레임은 하나의 구간으로 합침 (기본 0.5)")
    ap.add_argument("--max-clips", type=int, default=None,
                     help="피크 pitch 기준 상위 N개 구간만 사용 (기본: 전부 사용)")
    ap.add_argument("--bgm-dir", default=DEFAULT_BGM_DIR,
                     help=f"배경음 mp3가 담긴 폴더 (기본: {DEFAULT_BGM_DIR})")
    ap.add_argument("--bgm-volume", type=float, default=0.5,
                     help="배경음 볼륨 배율, 0~1 (기본 0.5 — 원본 대사 오디오는 그대로 유지)")
    ap.add_argument("--no-bgm", action="store_true",
                     help="배경음 입히기 건너뛰고 고음영상만 생성")
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
