#!/usr/bin/env python3
"""자막 파이프라인 종료 직전에 미완성 미연시(시나리오·이미지)를 이어서 만든다.

기상 알람 에이전트(run_daily_dating_sim_agent)는 하루 한 작품만 처리하므로,
방금 추출한 작품이 AI 일시 오류로 중간에 멈추면 며칠 뒤에나 이어졌다.
여기서는 학습카드가 있는 작품 전부를 한 번씩 이어서 시도한다(실패해도 다음 작품 진행).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import run_daily_dating_sim_agent as agent


# 전체 백로그(수십 편)는 기상 알람 에이전트가 하루 한 편씩 처리한다. 여기서는 방금 만든
# 작품(학습카드가 최근 RECENT_DAYS일 안에 생성됨)과 시나리오가 중간에 멈춘 작품만 이어간다.
RECENT_DAYS = 2


def is_recent_or_partial(folder):
    if (folder / "dating_sim_scenario.partial.json").is_file():
        return True
    cards = folder / "scene_study_cards.json"
    return time.time() - cards.stat().st_mtime < RECENT_DAYS * 86400


def main():
    agent.LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.close(os.open(agent.LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        print("⏭️ 미연시 제작 에이전트가 실행 중이라 건너뜁니다")
        return 0
    try:
        pending = [f for f in agent.candidates() if is_recent_or_partial(f)]
        if not pending:
            print("✅ 이어서 만들 미연시가 없습니다")
            return 0
        for work in pending:
            print(f"🎮 미연시 이어서 생성: {work.name}")
            if not agent.scenario_complete(work):
                subprocess.run([str(agent.PYTHON), str(agent.ROOT / "generate_dating_sim_scenario.py"), str(work)])
            if agent.scenario_complete(work) and not agent.images_complete(work):
                subprocess.run([str(agent.PYTHON), str(agent.ROOT / "generate_dating_sim_images.py"), str(work)])
            ok = agent.scenario_complete(work) and agent.images_complete(work)
            print(("✅ 완성: " if ok else "⚠️ 미완성(다음 실행에서 이어감): ") + work.name)
        return 0
    finally:
        agent.LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
