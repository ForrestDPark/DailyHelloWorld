#!/usr/bin/env python3
"""사람인 공식 채용정보 API 수집기.

표준 라이브러리만 사용하며, API 키는 파일에 저장하지 않고
SARAMIN_ACCESS_KEY 환경변수에서만 읽는다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config.json"
DEFAULT_DB = BASE_DIR / "data" / "jobs.db"
API_URL = "https://oapi.saramin.co.kr/job-search"
USER_AGENT = "DailyHelloWorld-JobCollector/1.0 (personal job search)"

SKILL_ALIASES = {
    "Python": ("python", "파이썬"),
    "Java": ("java", "자바"),
    "JavaScript": ("javascript", "node.js", "nodejs", "typescript"),
    "FastAPI": ("fastapi",),
    "Django": ("django",),
    "Spring": ("spring", "spring boot"),
    "SQL": ("sql", "mysql", "postgresql", "oracle"),
    "Docker": ("docker", "도커"),
    "AWS": ("aws", "amazon web services"),
    "AI/ML": ("machine learning", "머신러닝", "deep learning", "딥러닝", "llm", "생성형 ai"),
    "Git": ("git", "github", "gitlab"),
    "Linux": ("linux", "리눅스"),
}


@dataclass
class Job:
    source_id: str
    title: str
    company: str
    url: str
    location: str = ""
    experience: str = ""
    education: str = ""
    employment_type: str = ""
    salary: str = ""
    posted_at: str = ""
    deadline: str = ""
    keywords: str = ""
    skills: str = ""
    score: int = 0
    matched_query: str = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def plain(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("name") or value.get("code") or ""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(value)))).strip()


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"설정 파일이 없습니다: {path}\nconfig.example.json을 config.json으로 복사한 뒤 수정하세요.")
    with path.open(encoding="utf-8") as f:
        config = json.load(f)
    if not config.get("queries"):
        raise SystemExit("config.json의 queries에 검색어를 하나 이상 넣으세요.")
    return config


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY,
            source TEXT NOT NULL DEFAULT '사람인',
            source_id TEXT NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            url TEXT NOT NULL,
            location TEXT, experience TEXT, education TEXT,
            employment_type TEXT, salary TEXT,
            posted_at TEXT, deadline TEXT, keywords TEXT, skills TEXT,
            score INTEGER NOT NULL DEFAULT 0,
            matched_query TEXT,
            status TEXT NOT NULL DEFAULT '신규',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            UNIQUE(source, source_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_deadline ON jobs(deadline)")
    conn.commit()
    return conn


def scalar(obj: Any, default: str = "") -> str:
    if isinstance(obj, dict):
        return plain(obj.get("name") or obj.get("code") or obj.get("value") or default)
    return plain(obj if obj is not None else default)


def detect_skills(text: str) -> list[str]:
    haystack = text.casefold()
    return [name for name, aliases in SKILL_ALIASES.items() if any(alias.casefold() in haystack for alias in aliases)]


def score_job(text: str, config: dict[str, Any]) -> int:
    haystack = text.casefold()
    includes = sum(1 for word in config.get("include_keywords", []) if word.casefold() in haystack)
    excludes = sum(1 for word in config.get("exclude_keywords", []) if word.casefold() in haystack)
    return max(0, min(100, 40 + includes * 10 - excludes * 25))


def parse_job(raw: dict[str, Any], query: str, config: dict[str, Any]) -> Job:
    position = raw.get("position") or {}
    company = raw.get("company") or {}
    detail = position.get("industry") or {}
    job_type = position.get("job-type") or {}
    title = plain(position.get("title"))
    company_name = plain((company.get("detail") or {}).get("name"))
    keywords = plain(position.get("job-code") or detail)
    combined = " ".join((title, company_name, keywords, plain(raw.get("keyword"))))
    skills = detect_skills(combined)
    return Job(
        source_id=plain(raw.get("id")),
        title=title,
        company=company_name,
        url=plain(raw.get("url")),
        location=scalar(position.get("location")),
        experience=scalar(position.get("experience-level")),
        education=scalar(position.get("required-education-level")),
        employment_type=scalar(job_type),
        salary=scalar(raw.get("salary")),
        posted_at=plain(raw.get("posting-date")),
        deadline=plain(raw.get("expiration-date")),
        keywords=keywords,
        skills=", ".join(skills),
        score=score_job(combined, config),
        matched_query=query,
    )


def fetch_query(access_key: str, query: str, config: dict[str, Any]) -> list[Job]:
    params: dict[str, Any] = {
        "access-key": access_key,
        "keywords": query,
        "count": min(int(config.get("results_per_query", 30)), 110),
        "start": 0,
        "sort": config.get("sort", "pd"),
    }
    if config.get("locations"):
        params["loc_cd"] = ",".join(config["locations"])
    request = urllib.request.Request(
        f"{API_URL}?{urllib.parse.urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", "replace")
        raise RuntimeError(f"사람인 API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"사람인 API 연결 실패: {exc.reason}") from exc

    jobs_node = payload.get("jobs") or {}
    if isinstance(jobs_node, dict) and jobs_node.get("error"):
        raise RuntimeError(f"사람인 API 오류: {jobs_node['error']}")
    raw_jobs = jobs_node.get("job", []) if isinstance(jobs_node, dict) else []
    if isinstance(raw_jobs, dict):
        raw_jobs = [raw_jobs]
    return [parse_job(item, query, config) for item in raw_jobs if isinstance(item, dict)]


def fingerprint(job: Job) -> str:
    body = "\x1f".join((job.title, job.company, job.location, job.deadline, job.salary))
    return hashlib.sha256(body.encode()).hexdigest()


def upsert_jobs(conn: sqlite3.Connection, jobs: Iterable[Job]) -> tuple[int, int]:
    inserted = updated = 0
    stamp = now_iso()
    for job in jobs:
        exists = conn.execute(
            "SELECT id, fingerprint FROM jobs WHERE source = '사람인' AND source_id = ?", (job.source_id,)
        ).fetchone()
        fp = fingerprint(job)
        values = asdict(job)
        if exists:
            conn.execute("""
                UPDATE jobs SET title=:title, company=:company, url=:url, location=:location,
                    experience=:experience, education=:education, employment_type=:employment_type,
                    salary=:salary, posted_at=:posted_at, deadline=:deadline, keywords=:keywords,
                    skills=:skills, score=:score, matched_query=:matched_query,
                    last_seen_at=:stamp, fingerprint=:fingerprint
                WHERE id=:id
            """, {**values, "stamp": stamp, "fingerprint": fp, "id": exists["id"]})
            updated += 1
        else:
            conn.execute("""
                INSERT INTO jobs (source_id,title,company,url,location,experience,education,
                    employment_type,salary,posted_at,deadline,keywords,skills,score,matched_query,
                    first_seen_at,last_seen_at,fingerprint)
                VALUES (:source_id,:title,:company,:url,:location,:experience,:education,
                    :employment_type,:salary,:posted_at,:deadline,:keywords,:skills,:score,:matched_query,
                    :stamp,:stamp,:fingerprint)
            """, {**values, "stamp": stamp, "fingerprint": fp})
            inserted += 1
    conn.commit()
    return inserted, updated


def collect(args: argparse.Namespace) -> None:
    key = os.environ.get("SARAMIN_ACCESS_KEY", "").strip()
    if not key:
        raise SystemExit("SARAMIN_ACCESS_KEY가 없습니다. README의 API 키 설정 방법을 따르세요.")
    config = load_config(args.config)
    conn = connect(args.db)
    collected: dict[str, Job] = {}
    for index, query in enumerate(config["queries"], 1):
        print(f"[{index}/{len(config['queries'])}] '{query}' 검색 중…", flush=True)
        jobs = fetch_query(key, query, config)
        print(f"  {len(jobs)}건 수신")
        for job in jobs:
            previous = collected.get(job.source_id)
            if previous:
                previous.matched_query = ", ".join(dict.fromkeys((previous.matched_query + ", " + query).split(", ")))
            else:
                collected[job.source_id] = job
    inserted, updated = upsert_jobs(conn, collected.values())
    print(f"\n완료: 신규 {inserted}건 / 기존 갱신 {updated}건 / 중복 제거 후 {len(collected)}건")


def list_jobs(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    rows = conn.execute("""
        SELECT score, company, title, location, deadline, url
        FROM jobs ORDER BY score DESC, deadline ASC LIMIT ?
    """, (args.limit,)).fetchall()
    if not rows:
        print("저장된 공고가 없습니다. collect를 먼저 실행하세요.")
        return
    for row in rows:
        print(f"[{row['score']:>3}] {row['company']} | {row['title']}")
        print(f"      {row['location']} | 마감 {row['deadline']} | {row['url']}")


def export_csv(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    rows = conn.execute("SELECT * FROM jobs ORDER BY score DESC, deadline ASC").fetchall()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        columns = rows[0].keys() if rows else ["source", "source_id", "title", "company", "url"]
        writer.writerow(columns)
        writer.writerows(tuple(row) for row in rows)
    print(f"{len(rows)}건 내보내기 완료: {args.output}")


def doctor(args: argparse.Namespace) -> None:
    print(f"Python: {sys.version.split()[0]}")
    print(f"API 키: {'설정됨' if os.environ.get('SARAMIN_ACCESS_KEY') else '미설정'}")
    print(f"설정: {args.config} ({'있음' if args.config.exists() else '없음'})")
    print(f"DB: {args.db} ({'있음' if args.db.exists() else '아직 없음'})")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="사람인 공식 API 채용공고 수집기")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("collect", help="공고 수집·갱신").set_defaults(func=collect)
    ls = sub.add_parser("list", help="적합도 순으로 보기")
    ls.add_argument("--limit", type=int, default=20)
    ls.set_defaults(func=list_jobs)
    exp = sub.add_parser("export", help="CSV로 내보내기")
    exp.add_argument("--output", type=Path, default=BASE_DIR / "exports" / "jobs.csv")
    exp.set_defaults(func=export_csv)
    sub.add_parser("doctor", help="실행 환경 점검").set_defaults(func=doctor)
    return p


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

