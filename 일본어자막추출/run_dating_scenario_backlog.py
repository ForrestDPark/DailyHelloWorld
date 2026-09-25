#!/usr/bin/env python3
"""미완성 미연시 시나리오를 주기적으로 이어서 생성한다.

launchd에서 반복 호출해도 이미 실행 중인 생성기·일일 제작 에이전트와 겹치지
않으며, generate_dating_sim_scenario.py --all의 완성본 건너뛰기와 중간 저장본
재개 기능을 그대로 사용한다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import run_daily_dating_sim_agent as agent


STATE = Path.home() / ".tulpachat" / "dating_scenario_backlog.json"
GENERATOR_NAME = "generate_dating_sim_scenario.py"


def generator_is_running() -> bool:
    """잠금 없이 시작된 수동/이전 일괄 생성기도 찾아 중복 실행을 막는다."""
    try:
        result = subprocess.run(
            ["/bin/ps", "-axo", "pid=,command="],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        # 프로세스 조회에 실패했다고 중복 생성기를 띄우는 것보다 다음 회차까지
        # 안전하게 미루는 편이 낫다.
        return True
    own_pid = os.getpid()
    return any(
        GENERATOR_NAME in line and not line.lstrip().startswith(f"{own_pid} ")
        for line in result.stdout.splitlines()
    )


def save_state(status: str, **extra) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "checked_at": dt.datetime.now().isoformat(timespec="seconds"),
        **extra,
    }
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(STATE)


def main() -> int:
    agent.LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.close(os.open(agent.LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        save_state("skipped_locked")
        print("⏭️ 다른 미연시 제작 작업이 실행 중입니다 — 다음 예약 때 다시 확인합니다")
        return 0

    try:
        if generator_is_running():
            save_state("skipped_running")
            print("⏭️ 미연시 시나리오 생성기가 이미 실행 중입니다 — 중복 실행하지 않습니다")
            return 0

        save_state("running", started_at=dt.datetime.now().isoformat(timespec="seconds"))
        result = subprocess.run(
            [str(agent.PYTHON), str(agent.ROOT / GENERATOR_NAME), "--all"],
            check=False,
        )
        quality_result = subprocess.run([
            str(agent.PYTHON), str(agent.ROOT / "audit_dating_sim_images.py"), "--lock-held",
        ], check=False)
        status = "waiting_for_codex" if result.returncode == 75 else (
            "complete" if result.returncode == 0 and quality_result.returncode == 0 else "failed"
        )
        save_state(status, exit_code=result.returncode, quality_exit_code=quality_result.returncode)
        return 0 if result.returncode in (0, 75) and quality_result.returncode in (0, 1) else result.returncode
    finally:
        agent.LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
