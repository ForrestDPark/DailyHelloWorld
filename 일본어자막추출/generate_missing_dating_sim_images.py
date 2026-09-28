#!/usr/bin/env python3
"""완성 시나리오 중 이미지 미완성 작품만 순서대로 ComfyUI로 채운다."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import run_daily_dating_sim_agent as agent


STATE = Path.home() / ".tulpachat" / "dating_sim_image_backlog.json"

# 관리자 이미지 작업 시스템의 `Civitai 2805532 · 고품질 인물` 프리셋과
# 동일한 품질 설정이다. 일괄 생성에서는 기존 작품의 화면비율을 보존해야
# 하므로 --width/--height는 의도적으로 전달하지 않는다.
BATCH_QUALITY_PRESET_ARGS = (
    "--steps", "30",
    "--cfg", "7",
    "--sampler", "dpmpp_2m",
    "--scheduler", "karras",
    "--denoise", "1",
    "--hires-scale", "1.5",
    "--hires-steps", "10",
    "--hires-denoise", "0.28",
)


def generation_command(work: Path) -> list[str]:
    """기존 화면비율을 유지한 고품질 일괄 생성 명령을 만든다."""
    return [
        str(agent.PYTHON),
        str(agent.ROOT / "generate_dating_sim_images.py"),
        str(work),
        *BATCH_QUALITY_PRESET_ARGS,
    ]


def save(payload):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(STATE)


def duration_label(seconds):
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes = max(1, (remainder + 59) // 60) if seconds else 0
    return f"{hours}시간 {minutes}분" if hours else (f"{minutes}분" if minutes else "0분")


def main():
    agent.LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_fd = os.open(agent.LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(lock_fd, str(os.getpid()).encode("ascii"))
        os.close(lock_fd)
    except FileExistsError:
        save({
            "status": "waiting_for_lock",
            "error": "다른 미연시 제작 작업이 실행 중이어 자동 재개를 기다립니다",
            "checked_at": dt.datetime.now().isoformat(timespec="seconds"),
        })
        return 0
    try:
        works = [work for work in agent.candidates()
                 if agent.scenario_complete(work) and not agent.images_complete(work)]
        previous = {}
        try:
            previous = json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        historical = [float(value) for value in (previous.get("work_durations") or [])
                      if isinstance(value, (int, float)) and value > 0]
        # 한 작품은 보통 초상화+장면 수십 장이라 첫 작품이 끝나기 전부터
        # 10분으로 표시하면 실제보다 지나치게 낙관적이다. 과거 실측이 없을
        # 때만 6시간을 사용하고, 첫 작품 완료 뒤에는 최근 실측으로 보정한다.
        default_work_seconds = max(600, float(os.environ.get(
            "JP_DATING_IMAGE_DEFAULT_WORK_SECONDS", "21600")))
        initial_average = (sum(historical) / len(historical)) if historical else default_work_seconds
        started_epoch = int(time.time())
        state = {
            "status": "running", "total": len(works), "completed": 0, "failed": 0,
            "current": None, "started_at": dt.datetime.now().isoformat(timespec="seconds"),
            "started_at_epoch": started_epoch, "updated_at_epoch": started_epoch,
            "average_work_seconds": round(initial_average, 1),
            "eta_seconds": round(len(works) * initial_average),
            "expected_finished_at": started_epoch + round(len(works) * initial_average),
            "work_durations": historical[-10:], "failures": [],
        }
        save(state)
        print(f"🖼️ 미연시 이미지 {len(works)}편 시작 · 초기 예상 {duration_label(state['eta_seconds'])} "
              "(첫 작품 완료 뒤 실측 보정)", flush=True)
        for index, work in enumerate(works, 1):
            state.update(current=work.name, current_index=index,
                         current_started_at=dt.datetime.now().isoformat(timespec="seconds"),
                         updated_at=dt.datetime.now().isoformat(timespec="seconds"))
            save(state)
            print(f"\n▶ {work.name} ({index}/{len(works)}) · 전체 남은 시간 약 "
                  f"{duration_label(state.get('eta_seconds'))}", flush=True)
            work_started = time.monotonic()
            result = subprocess.run(generation_command(work))
            if result.returncode == 0 and agent.images_complete(work):
                state["completed"] += 1
            else:
                state["failed"] += 1
                state["failures"].append({"work": work.name, "returncode": result.returncode})
            durations = list(state.get("work_durations") or [])
            durations.append(round(time.monotonic() - work_started, 1))
            state["work_durations"] = durations[-10:]
            average = sum(state["work_durations"]) / len(state["work_durations"])
            state["average_work_seconds"] = round(average, 1)
            state["eta_seconds"] = round(max(0, len(works) - index) * average)
            state["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
            state["updated_at_epoch"] = int(time.time())
            state["expected_finished_at"] = state["updated_at_epoch"] + state["eta_seconds"]
            save(state)
            print(f"✓ {work.name} 종료 · {index}/{len(works)}편 · 경과 "
                  f"{duration_label(state['updated_at_epoch'] - started_epoch)} · 남은 약 "
                  f"{duration_label(state['eta_seconds'])} · 완료 예상 "
                  f"{dt.datetime.fromtimestamp(state['expected_finished_at']).strftime('%H:%M')}", flush=True)
        state.update(
            status="complete" if not state["failed"] else "partial",
            current=None, finished_at=dt.datetime.now().isoformat(timespec="seconds"),
        )
        save(state)
        return 0 if not state["failed"] else 1
    except Exception as exc:  # noqa: BLE001
        state = locals().get("state", {"total": 0, "completed": 0, "failed": 0})
        state.update(status="failed", current=None, error=str(exc)[:500],
                     finished_at=dt.datetime.now().isoformat(timespec="seconds"))
        save(state)
        return 1
    finally:
        agent.LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
