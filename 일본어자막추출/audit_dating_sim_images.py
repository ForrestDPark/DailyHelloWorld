#!/usr/bin/env python3
"""기존 미연시 이미지를 전수 검사하고 불량 장면만 자동 재생성한다."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import generate_dating_sim_images as image_agent
import run_daily_dating_sim_agent as agent


STATE = Path.home() / ".tulpachat" / "dating_image_quality_audit.json"


def save(payload):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(STATE)


def audit_manifest(work):
    manifest_path = work / image_agent.IMAGE_DIR_NAME / image_agent.MANIFEST_NAME
    if not manifest_path.is_file():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["portrait"]
    image_dir = manifest_path.parent
    failed = []
    if not image_agent.image_quality_report(image_dir / str(manifest.get("portrait", "")))["passed"]:
        failed.append("portrait")
    for key, record in (manifest.get("scenes") or {}).items():
        if not image_agent.image_quality_report(image_dir / str(record.get("file", "")))["passed"]:
            failed.append(key)
    return failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock-held", action="store_true",
                        help="상위 자동 작업이 공용 잠금을 이미 보유한 경우")
    args = parser.parse_args()
    owns_lock = False
    if not args.lock_held:
        agent.LOCK.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.close(os.open(agent.LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
            owns_lock = True
        except FileExistsError:
            save({"status": "skipped_locked", "checked_at": dt.datetime.now().isoformat(timespec="seconds")})
            return 0
    try:
        works = [folder for folder in sorted(agent.LIBRARY.iterdir())
                 if folder.is_dir() and agent.scenario_complete(folder)] if agent.LIBRARY.is_dir() else []
        state = {"status": "running", "total": len(works), "checked": 0, "repaired": 0,
                 "failed": [], "started_at": dt.datetime.now().isoformat(timespec="seconds")}
        save(state)
        for work in works:
            failed_keys = audit_manifest(work)
            if failed_keys:
                print(f"🩺 {work.name}: 품질 미달 {len(failed_keys)}장 재생성 — {', '.join(failed_keys)}", flush=True)
                result = subprocess.run([
                    str(agent.PYTHON), str(agent.ROOT / "generate_dating_sim_images.py"),
                    str(work), *(item for key in failed_keys for item in ("--force-key", key)),
                ])
                remaining = audit_manifest(work)
                if result.returncode == 0 and not remaining:
                    state["repaired"] += len(failed_keys)
                else:
                    state["failed"].append({"work": work.name, "keys": remaining or failed_keys})
            else:
                # 구버전 매니페스트도 현재 검사 결과를 기록하도록 에이전트를 한 번
                # 재호출한다. 정상 파일은 재생성하지 않고 품질 메타데이터만 쓴다.
                manifest_path = work / image_agent.IMAGE_DIR_NAME / image_agent.MANIFEST_NAME
                if manifest_path.is_file():
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if manifest.get("quality_status") != "passed":
                        subprocess.run([str(agent.PYTHON), str(agent.ROOT / "generate_dating_sim_images.py"), str(work)])
            state["checked"] += 1
            save(state)
        state.update(status="complete" if not state["failed"] else "partial",
                     finished_at=dt.datetime.now().isoformat(timespec="seconds"))
        save(state)
        return 0 if not state["failed"] else 1
    finally:
        if owns_lock:
            agent.LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
