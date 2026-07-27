#!/usr/bin/env python3
"""선택한 폴더 바로 아래의 모든 MP4를 곡별 MP3로 순차 변환한다."""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path


ACTIVE_PROCESS = None


def source_id(path):
    """긴 원본명 대신 파일명에 붙일 안정적인 6자리 고유 구분자."""
    return hashlib.sha1(path.name.encode("utf-8")).hexdigest()[:6].upper()


def stop_active_process(signum, _frame):
    """창 닫기·Ctrl+C 때 현재 splitter와 그 하위 ffmpeg까지 함께 종료한다."""
    global ACTIVE_PROCESS
    if ACTIVE_PROCESS and ACTIVE_PROCESS.poll() is None:
        try:
            os.killpg(ACTIVE_PROCESS.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    raise SystemExit(128 + signum)


def main():
    signal.signal(signal.SIGINT, stop_active_process)
    signal.signal(signal.SIGTERM, stop_active_process)
    signal.signal(signal.SIGHUP, stop_active_process)
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    args = parser.parse_args()
    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"폴더를 찾을 수 없습니다: {folder}")

    script_dir = Path(__file__).resolve().parent
    splitter = script_dir / "bgm_silence_splitter.py"
    python = Path("/opt/anaconda3/bin/python3")
    if not python.is_file():
        python = Path(sys.executable)

    videos = sorted(
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() == ".mp4"
    )
    if not videos:
        sys.exit("선택한 폴더 바로 아래에 MP4 파일이 없습니다.")

    report_root = folder / ".bgm_split_reports"
    report_root.mkdir(parents=True, exist_ok=True)
    source_map_path = report_root / "source_map.json"
    try:
        source_map = json.loads(source_map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        source_map = {}
    succeeded = 0
    failed = []
    print("=" * 64)
    print(f"🎵 플레이리스트 자동 분할: MP4 {len(videos)}개")
    print(f"📂 {folder}")
    print("✅ 성공한 원본만 휴지통으로 이동합니다.")
    print("=" * 64)

    for index, video in enumerate(videos, 1):
        identifier = source_id(video)
        source_map[identifier] = video.name
        source_map_path.write_text(
            json.dumps(source_map, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        report_dir = report_root / identifier
        print(f"\n[{index}/{len(videos)}] 🎬 {video.name}")
        print(f"   고유 구분자: {identifier}")
        command = [
            str(python), str(splitter), str(video),
            "--output-dir", str(report_dir),
            "--audio-output-dir", str(folder),
            "--trash-source",
        ]
        global ACTIVE_PROCESS
        ACTIVE_PROCESS = subprocess.Popen(command, start_new_session=True)
        returncode = ACTIVE_PROCESS.wait()
        ACTIVE_PROCESS = None
        if returncode == 0:
            succeeded += 1
        else:
            failed.append(video.name)
            print(f"❌ 실패하여 원본 보존: {video.name}")

    print("\n" + "=" * 64)
    print(f"완료: 성공 {succeeded}개 / 실패 {len(failed)}개")
    if failed:
        print("원본이 유지된 실패 파일:")
        for name in failed:
            print(f"  - {name}")
    print(f"인식 보고서: {report_root}")
    print("=" * 64)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
