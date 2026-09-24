#!/usr/bin/env python3
"""자막 파이프라인 종료 직전에 미완성 미연시를 이어서 만든다(시나리오는 Codex 전용).

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


# 시나리오 순서 우선순위용: 방금 만든 작품(학습카드가 최근 RECENT_DAYS일 안)과 중간 저장본이 있는 작품을 먼저.
RECENT_DAYS = 2
CODEX_UNAVAILABLE = 75  # generate_dating_sim_scenario.EXIT_CODEX_UNAVAILABLE


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
        candidates = agent.candidates()
        if not candidates:
            print("✅ 이어서 만들 미연시가 없습니다")
            return 0
        # 1) 이미지 — AI가 필요 없으므로(ComfyUI) 시나리오가 끝난 작품은 항상 진행한다.
        for work in candidates:
            if agent.scenario_complete(work) and not agent.images_complete(work):
                print(f"🖼️ 이미지 생성: {work.name}")
                subprocess.run([str(agent.PYTHON), str(agent.ROOT / "generate_dating_sim_images.py"), str(work)])
        # 2) 시나리오 — Codex 전용. 방금 만든 작품·중간 저장본이 있는 작품을 먼저, 나머지는
        #    그 뒤에 채운다. Codex가 막혀 있으면(종료 코드 75) 바로 멈추고 다음 실행을 기다린다.
        missing = [f for f in candidates if not agent.scenario_complete(f)]
        missing.sort(key=lambda f: not is_recent_or_partial(f))
        for work in missing:
            print(f"📝 시나리오 생성(Codex): {work.name}")
            result = subprocess.run([str(agent.PYTHON), str(agent.ROOT / "generate_dating_sim_scenario.py"), str(work)])
            if result.returncode == CODEX_UNAVAILABLE:
                print("⏸️ Codex를 쓸 수 없어 여기서 멈춥니다 — 토큰이 돌아오면 다음 실행이 빈 작품부터 채웁니다")
                break
            if agent.scenario_complete(work):
                print(f"🖼️ 이미지 생성: {work.name}")
                subprocess.run([str(agent.PYTHON), str(agent.ROOT / "generate_dating_sim_images.py"), str(work)])
        return 0
    finally:
        agent.LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
