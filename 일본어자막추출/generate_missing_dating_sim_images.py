#!/usr/bin/env python3
"""완성 시나리오 중 이미지 미완성 작품만 순서대로 ComfyUI로 채운다."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import run_daily_dating_sim_agent as agent


STATE = Path.home() / ".tulpachat" / "dating_sim_image_backlog.json"


def save(payload):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(STATE)


def main():
    agent.LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.close(os.open(agent.LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        save({"status": "failed", "error": "다른 미연시 제작 작업이 이미 실행 중입니다"})
        return 2
    try:
        works = [work for work in agent.candidates()
                 if agent.scenario_complete(work) and not agent.images_complete(work)]
        state = {
            "status": "running", "total": len(works), "completed": 0, "failed": 0,
            "current": None, "started_at": dt.datetime.now().isoformat(timespec="seconds"),
            "failures": [],
        }
        save(state)
        for index, work in enumerate(works, 1):
            state.update(current=work.name, current_index=index)
            save(state)
            result = subprocess.run([
                str(agent.PYTHON), str(agent.ROOT / "generate_dating_sim_images.py"), str(work),
            ])
            if result.returncode == 0 and agent.images_complete(work):
                state["completed"] += 1
            else:
                state["failed"] += 1
                state["failures"].append({"work": work.name, "returncode": result.returncode})
            save(state)
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
