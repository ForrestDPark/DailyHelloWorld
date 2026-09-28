#!/usr/bin/env python3
"""승인된 계획 파일만 받아 영상부터 EPUB·미연시 이미지까지 안전하게 재제작한다."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JP_DIR = ROOT / "일본어자막추출"
YTDLP = Path("/opt/homebrew/bin/yt-dlp")


def write_state(path: Path, **updates):
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    state.update(updates, updated_at=int(time.time()))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def count_srt(path: Path) -> int:
    return len(re.findall(r"(?m)^\d+\s*$", path.read_text(encoding="utf-8", errors="ignore")))


def count_dialogue_rows(work_dir: Path) -> int:
    """파이프라인의 최종 대사 원본은 SRT가 아니라 transcript JSONL일 수 있다."""
    counts = []
    srt_files = list(work_dir.glob("*.srt"))
    if srt_files:
        counts.append(max((count_srt(path) for path in srt_files), default=0))
    jsonl_total = 0
    for path in work_dir.glob("transcript*.jsonl"):
        jsonl_total += sum(1 for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip())
    counts.append(jsonl_total)
    return max(counts, default=0)


def main() -> int:
    plan_path = Path(sys.argv[1]).resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("status") != "approved":
        raise RuntimeError("승인되지 않은 계획입니다.")
    state_path = Path(plan["state_path"])
    live_dir = Path(plan["work_dir"]).resolve()
    title = live_dir.name
    completed_dir = Path(plan["completed_epub_dir"]).resolve()
    url = plan["video_url"]
    run_root = Path(tempfile.mkdtemp(prefix="dating-full-rebuild-"))
    media_dir, library_dir, epub_dir = run_root / "media", run_root / "library", run_root / "epub"
    for path in (media_dir, library_dir, epub_dir):
        path.mkdir(parents=True, exist_ok=True)
    log_path = Path(plan["log_path"])
    backup_dir = live_dir.with_name(f"{live_dir.name}.backup-{time.strftime('%Y%m%d-%H%M%S')}")
    try:
        write_state(state_path, status="running", stage="download", percent=2, message="원본 영상을 내려받고 있습니다.")
        output = str(media_dir / f"{title}.%(ext)s")
        download_cmd = [str(YTDLP), "--no-playlist", "--newline", "-o", output, url]
        with log_path.open("a", encoding="utf-8") as log:
            proc = subprocess.Popen(download_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout or []:
                log.write(line); log.flush()
                match = re.search(r"\[download\]\s+([\d.]+)%", line)
                if match:
                    write_state(state_path, percent=min(18, 2 + int(float(match.group(1)) * .16)))
            if proc.wait() != 0:
                raise RuntimeError("영상 다운로드가 실패했습니다. 로그를 확인해주세요.")
        media = next((p for p in media_dir.iterdir() if p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}), None)
        if not media or media.stat().st_size < 1024:
            raise RuntimeError("다운로드된 영상 파일을 찾지 못했습니다.")

        write_state(state_path, stage="pipeline", percent=20, message="자막·번역·EPUB·시나리오·이미지를 새로 만들고 있습니다.")
        env = os.environ.copy()
        env.update({
            "WORKING_DIR": str(media_dir), "SCRIPT_DIR": str(JP_DIR),
            "WORKOUT_EXTRACTION_ENABLED": "0", "JP_OPEN_BOOKS": "0",
            "JP_LIBRARY_DIR_OVERRIDE": str(library_dir),
            "JP_COMPLETED_EPUB_DIR_OVERRIDE": str(epub_dir),
            "PYTHONUNBUFFERED": "1",
        })
        markers = [("통합 자막", 36), ("EPUB 생성 완료", 58), ("미연시 시나리오", 72), ("미연시 이미지", 88)]
        with log_path.open("a", encoding="utf-8") as log:
            proc = subprocess.Popen(["/bin/zsh", str(JP_DIR / "subtitle_pipeline_body.sh")], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout or []:
                log.write(line); log.flush()
                for marker, percent in markers:
                    if marker in line:
                        write_state(state_path, percent=percent, message=line.strip()[-180:])
            if proc.wait() != 0:
                raise RuntimeError("재제작 파이프라인이 비정상 종료되었습니다.")

        staged = library_dir / title
        if not staged.is_dir():
            candidates = [p for p in library_dir.iterdir() if p.is_dir()]
            staged = candidates[0] if len(candidates) == 1 else staged
        cue_count = count_dialogue_rows(staged)
        scenario = staged / "dating_sim_scenario.json"
        images = list((staged / "dating_sim_images").glob("*")) if (staged / "dating_sim_images").is_dir() else []
        epub_files = list(epub_dir.glob("*.epub"))
        if not staged.is_dir() or cue_count < 5 or not scenario.is_file() or not images or not epub_files:
            raise RuntimeError(f"검증 실패: 대사 {cue_count}개, 시나리오 {scenario.is_file()}, 이미지 {len(images)}장, EPUB {len(epub_files)}개")

        write_state(state_path, stage="replace", percent=95, message="새 결과를 검증했고 기존 결과를 백업한 뒤 교체합니다.")
        if live_dir.exists():
            os.replace(live_dir, backup_dir)
        try:
            os.replace(staged, live_dir)
        except Exception:
            if backup_dir.exists() and not live_dir.exists():
                os.replace(backup_dir, live_dir)
            raise
        completed_dir.mkdir(parents=True, exist_ok=True)
        for epub in epub_files:
            shutil.copy2(epub, completed_dir / epub.name)
        write_state(state_path, status="completed", stage="done", percent=100,
                    message=f"전체 재제작 완료 · 대사 {cue_count}개 · 이미지 {len(images)}장",
                    backup_path=str(backup_dir), cue_count=cue_count, image_count=len(images))
        return 0
    except Exception as exc:
        write_state(state_path, status="failed", stage="failed", message=str(exc))
        return 1
    finally:
        shutil.rmtree(run_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
