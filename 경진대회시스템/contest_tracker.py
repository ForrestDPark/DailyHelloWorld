#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "data" / "contests.db"
STATUSES = ("관심", "출전 검토", "참가 중", "제출 완료", "회고 완료", "보류", "종료")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contests (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            platform TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            deadline TEXT,
            contest_type TEXT,
            eligibility TEXT,
            team_size TEXT,
            deliverable TEXT,
            job_fit INTEGER NOT NULL,
            portfolio INTEGER NOT NULL,
            learning INTEGER NOT NULL,
            finishability INTEGER NOT NULL,
            priority_score INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT '관심',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def valid_score(value: int) -> int:
    if not 0 <= value <= 5:
        raise argparse.ArgumentTypeError("점수는 0~5 사이여야 합니다.")
    return value


def priority(job_fit: int, portfolio: int, learning: int, finishability: int) -> int:
    weighted = job_fit * 30 + portfolio * 25 + learning * 20 + finishability * 25
    return round(weighted / 5)


def cmd_add(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    score = priority(args.job_fit, args.portfolio, args.learning, args.finishability)
    try:
        cursor = conn.execute("""
            INSERT INTO contests (title,platform,url,deadline,contest_type,eligibility,team_size,
                deliverable,job_fit,portfolio,learning,finishability,priority_score,status,notes,
                created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (args.title, args.platform, args.url, args.deadline, args.type, args.eligibility,
              args.team_size, args.deliverable, args.job_fit, args.portfolio, args.learning,
              args.finishability, score, args.status, args.notes, stamp, stamp))
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise SystemExit("이미 등록된 URL입니다.") from exc
    print(f"등록 완료: #{cursor.lastrowid} {args.title} (우선순위 {score}점)")


def cmd_list(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    where, values = "", []
    if args.status:
        where, values = "WHERE status = ?", [args.status]
    rows = conn.execute(f"""
        SELECT id,title,platform,deadline,priority_score,status,url FROM contests
        {where} ORDER BY
        CASE WHEN deadline IS NULL OR deadline = '' THEN 1 ELSE 0 END,
        deadline ASC, priority_score DESC
    """, values).fetchall()
    if not rows:
        print("등록된 대회가 없습니다.")
        return
    for row in rows:
        print(f"#{row['id']} [{row['priority_score']:>3}] {row['title']} | {row['platform']} | {row['status']}")
        print(f"    마감 {row['deadline'] or '미정'} | {row['url']}")


def cmd_update(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    cursor = conn.execute(
        "UPDATE contests SET status=?, updated_at=? WHERE id=?",
        (args.status, datetime.now().astimezone().isoformat(timespec="seconds"), args.id),
    )
    conn.commit()
    if cursor.rowcount == 0:
        raise SystemExit(f"#{args.id} 대회를 찾을 수 없습니다.")
    print(f"#{args.id} 상태 변경: {args.status}")


def cmd_stats(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    total = conn.execute("SELECT COUNT(*) FROM contests").fetchone()[0]
    print(f"전체 {total}건")
    for row in conn.execute("SELECT status, COUNT(*) count FROM contests GROUP BY status ORDER BY count DESC"):
        print(f"- {row['status']}: {row['count']}건")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="경진대회 출전·제출·회고 관리")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("--title", required=True)
    add.add_argument("--platform", required=True)
    add.add_argument("--url", required=True)
    add.add_argument("--deadline", default="")
    add.add_argument("--type", default="")
    add.add_argument("--eligibility", default="")
    add.add_argument("--team-size", default="")
    add.add_argument("--deliverable", default="")
    add.add_argument("--job-fit", type=valid_score, required=True)
    add.add_argument("--portfolio", type=valid_score, required=True)
    add.add_argument("--learning", type=valid_score, required=True)
    add.add_argument("--finishability", type=valid_score, required=True)
    add.add_argument("--status", choices=STATUSES, default="관심")
    add.add_argument("--notes", default="")
    add.set_defaults(func=cmd_add)
    listing = sub.add_parser("list")
    listing.add_argument("--status", choices=STATUSES)
    listing.set_defaults(func=cmd_list)
    update = sub.add_parser("update")
    update.add_argument("id", type=int)
    update.add_argument("--status", choices=STATUSES, required=True)
    update.set_defaults(func=cmd_update)
    sub.add_parser("stats").set_defaults(func=cmd_stats)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
