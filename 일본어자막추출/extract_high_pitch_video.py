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
from datetime import datetime
import glob
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time

VIDEO_EXTS = (".mp4", ".webm", ".mkv", ".mov")
DEFAULT_BGM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bgm")
DEFAULT_BGM_VOLUME = 0.28
HISTORY_VERSION = 1
# ★ 2026-07-28: 배경음 입힌 운동용 영상을 한곳에 몰아보고 싶다는 요청으로 추가.
AV_MUSIC_DIR = "/Users/forrestdpark/Desktop/BlogImage/avMusic"
_TRASH_RECOVERY_ATTEMPTED = False
# ★ 2026-08-08: BGM이 계속 반복되는 것처럼 느껴진다는 지적 — shift_alarm.py의
# 랜덤 북마크 추천(pick_random_bookmarks)과 같은 패턴으로, 전체 곡을 한 바퀴
# 다 쓰기 전에는 같은 곡이 다시 안 뽑히게 이력을 영상 처리 "회차 간"에도
# 영구 저장한다(기존엔 build_bgm_track() 호출 한 번 안에서만 안 겹쳤음).
BGM_HISTORY_FILE = os.path.expanduser("~/.jp_workout_bgm_history.json")
# ★ 2026-08-10: BGM_HISTORY_FILE은 "다음에 뭘 안 겹치게 뽑을지"를 위한 로테이션
# 상태값일 뿐, 사람이 "이 영상에 무슨 곡이 나왔지?"를 나중에 물어봤을 때 답할
# 기록은 아니다(파일 경로 목록만 있고 어느 영상에 썼는지·언제 썼는지가 없음).
# 그래서 별도로 영상별 사용 기록을 남긴다 — JSON Lines라 항상 끝에 한 줄만
# append하면 되고, 파일이 커져도 기존 줄을 다시 쓸 필요가 없다.
BGM_USAGE_LOG_FILE = os.path.expanduser("~/.jp_workout_bgm_usage_log.jsonl")


def format_elapsed(seconds):
    """로그에서 바로 읽기 좋은 `1시간 2분 3초` 형식."""
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours}시간")
    if minutes or hours:
        parts.append(f"{minutes}분")
    parts.append(f"{secs}초")
    return " ".join(parts)


def empty_user_trash():
    """현재 사용자의 macOS 휴지통을 영구 비우고 삭제 항목 수를 반환한다."""
    trash_dir = os.path.expanduser("~/.Trash")
    removed = 0
    try:
        entries = list(os.scandir(trash_dir))
    except OSError as exc:
        print(f"⚠️ 휴지통을 열 수 없어 자동 비우기 실패: {exc}")
        return 0
    for entry in entries:
        try:
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry.path)
            else:
                os.unlink(entry.path)
            removed += 1
        except OSError as exc:
            print(f"⚠️ 휴지통 항목 삭제 실패: {entry.name}: {exc}")
    return removed


def run_ffmpeg_with_disk_recovery(command, partial_output):
    """디스크 부족일 때만 휴지통을 비우고 같은 ffmpeg 명령을 한 번 재시도한다."""
    global _TRASH_RECOVERY_ATTEMPTED
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode == 0:
        return
    error_text = (result.stderr or "") + (result.stdout or "")
    print(error_text.rstrip(), file=sys.stderr)
    no_space = "No space left on device" in error_text or result.returncode == 228
    if no_space and not _TRASH_RECOVERY_ATTEMPTED:
        _TRASH_RECOVERY_ATTEMPTED = True
        print("🗑️ 저장 공간 부족 감지 — macOS 휴지통 자동 비우기")
        removed = empty_user_trash()
        print(f"🗑️ 휴지통 {removed}개 항목 영구 삭제 완료")
        try:
            if partial_output and os.path.exists(partial_output):
                os.unlink(partial_output)
        except OSError:
            pass
        retry = subprocess.run(command, capture_output=True, text=True)
        if retry.returncode == 0:
            print("✅ 공간 확보 후 ffmpeg 자동 재시도 성공")
            return
        retry_text = (retry.stderr or "") + (retry.stdout or "")
        print(retry_text.rstrip(), file=sys.stderr)
        raise subprocess.CalledProcessError(
            retry.returncode, command, output=retry.stdout, stderr=retry.stderr
        )
    raise subprocess.CalledProcessError(
        result.returncode, command, output=result.stdout, stderr=result.stderr
    )


def copy_to_av_music(bgm_video_path):
    """완성 영상을 avMusic에 복사하고 검증된 대상 정보 반환. 실패 시 None."""
    try:
        os.makedirs(AV_MUSIC_DIR, exist_ok=True)
        target = os.path.join(AV_MUSIC_DIR, os.path.basename(bgm_video_path))
        shutil.copy2(bgm_video_path, target)
        source_size = os.path.getsize(bgm_video_path)
        target_size = os.path.getsize(target)
        if source_size <= 0 or target_size != source_size:
            raise OSError(f"복사 크기 불일치: 원본 {source_size}, 대상 {target_size}")
        print(f"🎶 avMusic 폴더로 복사 완료: {target}")
        return {
            "file": os.path.basename(target),
            "size": target_size,
            "completed_at": datetime.now().isoformat(timespec="seconds"),
        }
    except OSError as e:
        print(f"⚠️  avMusic 폴더 복사 실패(무시하고 계속): {e}")
        return None

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
    """segments를 Apple 하드웨어 인코더로 잘라 이어붙인다.

    VideoToolbox를 짧게 사전 시험해 실제로 작동할 때만 전체 구간에 사용한다.
    지원하지 않는 Mac/ffmpeg 조합에서는 CPU x264의 빠른 preset으로 자동 복귀한다.
    한 결과물 안에서 서로 다른 인코더의 조각이 섞이지 않게 인코더 선택은 시작 전에
    한 번만 확정한다.
    """
    # 이전 실행이 디스크 부족 등으로 남긴 불완전 합본은 새 임시 조각을 만들기
    # 전에 지워야 그 파일이 차지하던 공간을 즉시 회수할 수 있다.
    if os.path.exists(out_path):
        os.unlink(out_path)
        print(f"🧹 이전 실패로 남은 불완전 출력 삭제: {out_path}")
    encoder_test = os.path.join(tmp_dir, "videotoolbox_test.mp4")
    hardware_test = subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{segments[0]['start']:.3f}",
         "-i", video_path, "-t", "0.5", "-an",
         "-c:v", "h264_videotoolbox", "-q:v", "65",
         "-pix_fmt", "yuv420p", encoder_test, "-loglevel", "error"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if (hardware_test.returncode == 0 and os.path.isfile(encoder_test)
            and os.path.getsize(encoder_test) > 0):
        video_encoder = [
            "-c:v", "h264_videotoolbox", "-q:v", "65",
            "-pix_fmt", "yuv420p",
        ]
        print("⚡ Apple VideoToolbox 하드웨어 인코딩 사용 (발열·CPU 부하 절감)")
    else:
        video_encoder = [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-threads", "2", "-pix_fmt", "yuv420p",
        ]
        print("⚠️ VideoToolbox를 사용할 수 없어 CPU 2개로 제한해 저발열 인코딩")

    clip_paths = []
    for i, seg in enumerate(segments):
        clip_path = os.path.join(tmp_dir, f"clip_{i:03d}.mp4")
        duration = seg["end"] - seg["start"]
        clip_command = ["ffmpeg", "-y",
             "-ss", f"{seg['start']:.3f}", "-i", video_path,
             "-t", f"{duration:.3f}",
             *video_encoder, "-c:a", "aac", "-b:a", "160k",
             "-avoid_negative_ts", "make_zero",
             clip_path, "-loglevel", "error"]
        run_ffmpeg_with_disk_recovery(clip_command, clip_path)
        if os.path.exists(clip_path):
            clip_paths.append(clip_path)

    if not clip_paths:
        return False

    list_path = os.path.join(tmp_dir, "concat_list.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    concat_command = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
        "-c", "copy", out_path, "-loglevel", "error",
    ]
    run_ffmpeg_with_disk_recovery(concat_command, out_path)
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


def _load_bgm_history():
    """이전 회차(들)에서 이미 쓴 곡 목록을 읽는다. 손상된 기록은 빈 기록으로 복구."""
    try:
        with open(BGM_HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        used = data.get("used", [])
        return used if isinstance(used, list) else []
    except (OSError, ValueError, TypeError):
        return []


def _save_bgm_history(used):
    """다음 영상 처리 때도 이어서 참조할 수 있게 원자적으로 저장."""
    tmp_path = f"{BGM_HISTORY_FILE}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"used": used}, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, BGM_HISTORY_FILE)


def _log_bgm_usage(video_label, playlist):
    """★ 2026-08-10 추가: 영상 하나에 어떤 곡들이 쓰였는지 사람이 나중에 물어볼
    수 있게 영구 기록한다(요청: "음악 사용된 기록이 있으면 보여주고, 없으면
    보관해뒀다가 알려달라고 하면 알려주게"). 로테이션 상태(BGM_HISTORY_FILE)와는
    별개 파일 — 저건 "다음에 뭘 뽑을지"만 알고 어느 영상에 썼는지는 모른다."""
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "video": video_label,
        "tracks": [os.path.basename(p) for p in playlist],
    }
    try:
        with open(BGM_USAGE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"⚠️ BGM 사용 기록 저장 실패(무시하고 계속): {exc}")


def show_bgm_usage_log(limit=20):
    """최근 BGM 사용 기록을 사람이 읽기 좋게 출력한다. --show-bgm-log로 호출."""
    if not os.path.exists(BGM_USAGE_LOG_FILE):
        print("아직 기록된 BGM 사용 이력이 없습니다(운동용 영상을 만들면 그때부터 쌓입니다).")
        return
    entries = []
    with open(BGM_USAGE_LOG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not entries:
        print("아직 기록된 BGM 사용 이력이 없습니다.")
        return
    print(f"🎵 최근 BGM 사용 기록 (최신 {min(limit, len(entries))}건 / 전체 {len(entries)}건):\n")
    for entry in entries[-limit:][::-1]:
        print(f"[{entry.get('timestamp', '?')}] {entry.get('video', '?')}")
        for track in entry.get("tracks", []):
            print(f"   - {track}")
        print()


def build_bgm_track(bgm_dir, target_duration, tmp_dir, video_label=None):
    """bgm_dir 안의 (미리 잘라놓은) mp3들을 무작위 순서로 이어붙여 target_duration초
    이상 되는 오디오 트랙 하나를 만들어 경로를 반환.

    ★ 2026-08-08 재설계: shift_alarm.py의 랜덤 북마크 추천(pick_random_bookmarks)과
    같은 "전체를 한 바퀴 다 쓰기 전엔 안 겹침" 방식으로 바꿨다. 예전엔 build_bgm_track()
    호출 한 번 안에서만 안 겹쳤어서, 영상을 여러 개 연달아 처리하면 매번 새로 셔플하다
    보니 같은 곡이 자주 다시 걸려 "계속 반복되는 것 같다"는 느낌을 줬다. 이제
    BGM_HISTORY_FILE에 "이미 쓴 곡" 이력을 영구 저장해서, 폴더 안 모든 곡을 최소 한 번씩
    다 쓰기 전에는 같은 곡이 다시 안 뽑힌다(회차 간에도 이어짐). 폴더가 없거나 mp3가
    하나도 없으면 None. `video_label`을 주면 BGM_USAGE_LOG_FILE에 "이 영상에 이 곡들이
    쓰였다"는 기록도 함께 남는다(★ 2026-08-10, show_bgm_usage_log()로 나중에 조회)."""
    if not bgm_dir or not os.path.isdir(bgm_dir):
        return None
    mp3s = glob.glob(os.path.join(bgm_dir, "*.mp3"))
    if not mp3s:
        return None

    durations = {p: (get_media_duration(p) or 3.0) for p in mp3s}

    mp3_set = set(mp3s)
    used = [p for p in _load_bgm_history() if p in mp3_set]  # 삭제된 파일은 이력에서 자연 소거
    unused = [p for p in mp3s if p not in set(used)]
    random.shuffle(unused)

    playlist, total = [], 0.0
    while total < target_duration:
        if not unused:
            # 전체를 다 썼으니 새 주기 시작(이력 초기화하고 다시 섞음).
            used = []
            unused = list(mp3s)
            random.shuffle(unused)
        p = unused.pop()
        playlist.append(p)
        used.append(p)
        total += durations[p]

    _save_bgm_history(used)
    _log_bgm_usage(video_label or os.path.basename(tmp_dir), playlist)

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
        return None
    return bgm_track


def mix_background_audio(video_path, bgm_track_path, out_path, bgm_volume=DEFAULT_BGM_VOLUME):
    """video_path의 기존 오디오는 100%로 두고 bgm_track_path를 얹어 out_path에 저장.
    amix의 duration=first로 영상 길이에 맞춰 잘림(bgm_track_path는 build_bgm_track에서
    이미 영상 길이 이상으로 만들어둔 상태). amix 자동 정규화는 원본 음성까지 낮추므로
    끄고, 마지막에 limiter로 합산 피크의 클리핑만 방지한다.
    ★ 2026-07-31: BGM이 바뀔 때 곡 제목을 영상에 자막으로 태우던 기능은 제거했다
    (사용자가 안 쓴다고 확인). 그 기능은 libass로 영상 전체를 재인코딩해야 해서
    -c:v copy(스트림 복사, 재인코딩 없음)만 쓰는 지금보다 훨씬 느리고 CPU도
    많이 먹었다 — 제목 없이 오디오만 합치면 되므로 video는 항상 그냥 복사한다."""
    filter_complex = (
        f"[1:a]volume={bgm_volume}[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0:"
        f"normalize=0,alimiter=limit=0.95[aout]"
    )
    subprocess.run(
        ["ffmpeg", "-y",
         "-i", video_path,
         "-i", bgm_track_path,
         "-filter_complex", filter_complex,
         "-map", "0:v", "-map", "[aout]",
         "-c:v", "copy", "-c:a", "aac",
         out_path, "-loglevel", "error"],
        check=True,
    )
    return os.path.exists(out_path)


def _delete_plain_highlight_if_bgm_exists(plain_path, bgm_path):
    """★ "BGM 씌우기 전 영상 추출본은 BGM 파일 생기면 바로 삭제해달라" 요청
    (2026-08-29) — 예전엔 파이프라인 맨 끝(EPUB·avMusic 확인까지 끝난 뒤)에야
    기타/ 폴더째로 지워졌다. BGM판이 원본과 똑같은 화면에 배경음만 얹은
    것이라 만들어지는 즉시 pre-BGM판은 대용량 중복일 뿐이므로, 뒷단계를
    기다리지 않고 여기서 바로 지운다."""
    if not plain_path or not bgm_path or plain_path == bgm_path:
        return
    if not os.path.isfile(plain_path):
        return
    try:
        size_mb = os.path.getsize(plain_path) / (1024 * 1024)
        os.remove(plain_path)
        print(f"🗑️  BGM판 확인 완료 — 배경음 입히기 전 영상 삭제: {plain_path} ({size_mb:.1f}MB)")
    except OSError as exc:
        print(f"⚠️ 배경음 입히기 전 영상 삭제 실패: {exc}")


def _process_video(video_path, args):
    base = os.path.splitext(os.path.basename(video_path))[0]
    work_dir = os.path.dirname(os.path.abspath(video_path)) or "."
    tmp_wav = os.path.join(work_dir, f"temp_{base}_pitch.wav")
    history_path = extraction_history_path(work_dir, base)
    history = load_extraction_history(history_path)
    # 정리 단계는 반드시 '이번 실행'의 복사 성공만 인정한다. 이전 실행의 낡은
    # 성공 기록이 남아 있다가 이번 복사 실패를 가리는 일을 막는다.
    if history.pop("avmusic_export", None) is not None:
        save_extraction_history(history_path, history)
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
        stage_start = time.perf_counter()
        extract_audio(video_path, tmp_wav)
        print(f"⏱️ 오디오 추출: {format_elapsed(time.perf_counter() - stage_start)}")

        print("📈 음높이(pitch) 분석 중...")
        stage_start = time.perf_counter()
        times, f0, voiced_flag = analyze_pitch(tmp_wav)
        print(f"⏱️ 음높이 분석: {format_elapsed(time.perf_counter() - stage_start)}")

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
        stage_start = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmp_dir:
            ok = build_highlight_video(video_path, segments, out_path, tmp_dir)
        print(f"⏱️ 구간 인코딩·이어붙이기: {format_elapsed(time.perf_counter() - stage_start)}")

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
        exported = copy_to_av_music(cached_bgm)
        if exported:
            history["avmusic_export"] = exported
            save_extraction_history(history_path, history)
        _delete_plain_highlight_if_bgm_exists(out_path, cached_bgm)
        return

    print(f"🎵 배경음 입히는 중 (볼륨 {args.bgm_volume:.0%})...")
    stage_start = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp_dir:
        bgm_track = build_bgm_track(args.bgm_dir, video_duration, tmp_dir, video_label=os.path.basename(bgm_out))
        bgm_ok = bool(bgm_track) and mix_background_audio(
            out_path, bgm_track, bgm_out, bgm_volume=args.bgm_volume,
        )
    if bgm_ok:
        size_mb2 = os.path.getsize(bgm_out) / (1024 * 1024)
        print(f"✅ 배경음 입힌 영상: {bgm_out} ({size_mb2:.1f}MB)")
        history["bgm_settings"] = current_bgm_settings
        history["bgm"] = {"file": os.path.basename(bgm_out)}
        save_extraction_history(history_path, history)
        exported = copy_to_av_music(bgm_out)
        if exported:
            history["avmusic_export"] = exported
            save_extraction_history(history_path, history)
        print(f"⏱️ BGM 생성·합성·복사: {format_elapsed(time.perf_counter() - stage_start)}")
        _delete_plain_highlight_if_bgm_exists(out_path, bgm_out)
    else:
        print("❌ 배경음 입히기 실패")
        print(f"⏱️ BGM 생성·합성 시도: {format_elapsed(time.perf_counter() - stage_start)}")


def process_video(video_path, args):
    """성공·재사용·중간 종료 여부와 관계없이 영상별 총시간을 항상 표시한다."""
    global _TRASH_RECOVERY_ATTEMPTED
    _TRASH_RECOVERY_ATTEMPTED = False
    started = time.perf_counter()
    try:
        return _process_video(video_path, args)
    finally:
        base = os.path.splitext(os.path.basename(video_path))[0]
        print(f"⏱️ {base} 전체 처리시간: {format_elapsed(time.perf_counter() - started)}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("path", nargs="?", help="영상 파일 경로 또는 영상들이 담긴 폴더 경로")
    ap.add_argument("--show-bgm-log", nargs="?", type=int, const=20, default=None, metavar="N",
                     help="영상 처리 없이 최근 BGM 사용 기록만 N건(기본 20) 출력하고 종료 "
                          "(★ 2026-08-10 추가 — '이 영상에 무슨 곡 나왔지' 나중에 조회용)")
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
    args = ap.parse_args()

    if args.show_bgm_log is not None:
        show_bgm_usage_log(args.show_bgm_log)
        return

    if not args.path:
        ap.error("path가 필요합니다(또는 --show-bgm-log만 단독으로 쓸 수 있습니다)")

    videos = collect_videos(args.path)
    if not videos:
        sys.exit(f"처리할 영상을 찾을 수 없습니다: {args.path}")

    print(f"📋 대상 영상 {len(videos)}개: {[os.path.basename(v) for v in videos]}")
    batch_started = time.perf_counter()
    for video_path in videos:
        process_video(video_path, args)

    print(f"\n{'='*54}")
    print("🎉 모든 영상 처리 완료!")
    print(f"⏱️ 전체 {len(videos)}개 영상 작업시간: {format_elapsed(time.perf_counter() - batch_started)}")
    print(f"{'='*54}")


if __name__ == "__main__":
    main()
