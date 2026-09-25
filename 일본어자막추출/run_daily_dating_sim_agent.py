#!/usr/bin/env python3
"""기상 알람에서 하루 한 작품만 완성하는 미연시 제작 에이전트."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIBRARY = ROOT / "library"
STATE = Path.home() / ".tulpachat" / "dating_sim_daily_agent.json"
LOCK = Path.home() / ".tulpachat" / "dating_sim_daily_agent.lock"
PYTHON = Path(sys.executable)


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def scenario_complete(folder):
    data = _read_json(folder / "dating_sim_scenario.json")
    return data.get("content_version") == 3 and (data.get("coverage") or {}).get("complete") is True


def images_complete(folder):
    data = _read_json(folder / "dating_sim_images" / "manifest.json")
    image_dir = folder / "dating_sim_images"
    files = [data.get("portrait"), *(data.get("assignments") or {}).values()]
    return (data.get("status") == "complete" and data.get("quality_status") == "passed"
            and len(data.get("assignments") or {}) >= 42
            and all(isinstance(name, str) and (image_dir / name).is_file()
                    and (image_dir / name).stat().st_size >= 1024 for name in files))


def candidates():
    if not LIBRARY.is_dir():
        return []
    result = []
    for folder in sorted(LIBRARY.iterdir(), key=lambda p: p.name.casefold()):
        cards = folder / "scene_study_cards.json"
        if folder.is_dir() and cards.is_file() and cards.stat().st_size > 2:
            if not (scenario_complete(folder) and images_complete(folder)):
                result.append(folder)
    return result


def _save(payload):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(STATE)


def run(today=None, force=False):
    today = today or dt.date.today().isoformat()
    previous = _read_json(STATE)
    if not force and previous.get("date") == today:
        print(f"⏭️ 오늘 이미 실행됨: {previous.get('work', '없음')} · {previous.get('status')}")
        return 0
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    except FileExistsError:
        print("⏭️ 미연시 제작 에이전트가 이미 실행 중입니다")
        return 0
    try:
        pending = candidates()
        if not pending:
            _save({"date": today, "status": "nothing_to_do", "work": None})
            print("✅ 준비되지 않은 학습카드 작품이 없습니다")
            return 0
        # 정렬된 첫 작품을 고르므로 재시작·로그 비교가 가능하고 매일 정확히 한 작품만 처리한다.
        work = pending[0]
        state = {"date": today, "status": "running", "work": work.name,
                 "started_at": dt.datetime.now().isoformat(timespec="seconds")}
        _save(state)
        if not scenario_complete(work):
            subprocess.run([str(PYTHON), str(ROOT / "generate_dating_sim_scenario.py"), str(work)], check=True)
        subprocess.run([str(PYTHON), str(ROOT / "generate_dating_sim_images.py"), str(work)], check=True)
        if not (scenario_complete(work) and images_complete(work)):
            raise RuntimeError("파이프라인 종료 뒤 완성 검증을 통과하지 못했습니다")
        state.update(status="complete", finished_at=dt.datetime.now().isoformat(timespec="seconds"))
        _save(state)
        print(f"✅ 오늘의 미연시 작품 완성: {work.name}")
        return 0
    except Exception as exc:
        state = locals().get("state", {"date": today, "work": None})
        state.update(status="failed", error=str(exc)[:500],
                     finished_at=dt.datetime.now().isoformat(timespec="seconds"))
        _save(state)
        print(f"❌ 미연시 제작 실패: {exc}", file=sys.stderr)
        return 1
    finally:
        LOCK.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    return run(force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
