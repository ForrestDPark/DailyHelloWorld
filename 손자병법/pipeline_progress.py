#!/usr/bin/env python3
"""손자병법 자동 분석의 공개 가능한 진행 상태를 원자적으로 기록한다."""
import argparse
import datetime
import json
import os
from pathlib import Path

STATUS_PATH = Path.home() / "Library/Logs/CodexSunzi/status.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verse", type=int, required=True)
    parser.add_argument("--mode", choices=("light", "full"), required=True)
    parser.add_argument("--progress", type=int, required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--state", choices=("running", "complete", "failed"), default="running")
    parser.add_argument("--pid", type=int, default=0)
    parser.add_argument("--started-at")
    args = parser.parse_args()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    previous = {}
    try:
        previous = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    payload = {
        "verse": args.verse,
        "mode": args.mode,
        "progress": max(0, min(100, args.progress)),
        "stage": args.stage[:120],
        "state": args.state,
        "pid": args.pid or previous.get("pid", 0),
        "started_at": args.started_at or previous.get("started_at") or now,
        "updated_at": now,
    }
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, STATUS_PATH)


if __name__ == "__main__":
    main()
