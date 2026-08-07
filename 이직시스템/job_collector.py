#!/usr/bin/env python3
"""사람인·워크넷 공식 채용정보 API 수집기.

표준 라이브러리만 사용하며, API 키는 파일에 저장하지 않고
SARAMIN_ACCESS_KEY / WORK24_ACCESS_KEY 환경변수에서만 읽는다.
두 키 중 있는 것만 사용해서 수집한다(둘 다 없으면 실행 중단).
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
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config.json"
DEFAULT_DB = BASE_DIR / "data" / "jobs.db"
SARAMIN_API_URL = "https://oapi.saramin.co.kr/job-search"
SARAMIN_MAX_RESULTS = 110
WORK24_API_URL = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do"
WORK24_MAX_RESULTS = 100
WORK24_EMP_TP_NAMES = {
    "4": "파견근로",
    "10": "기간의 정함이 없는 근로계약",
    "11": "기간의 정함이 없는 근로계약(시간(선택)제)",
    "20": "기간의 정함이 있는 근로계약",
    "21": "기간의 정함이 있는 근로계약(시간(선택)제)",
    "Y": "대체인력채용",
}
# 사람인 공개 검색결과 페이지 크롤링(로그인/CAPTCHA 우회 없음, robots.txt 허용 범위).
# 잡코리아는 robots.txt가 검색결과 경로를 일반 크롤러 전체에 Disallow하고 있어 제외.
SARAMIN_CRAWL_URL = "https://www.saramin.co.kr/zf_user/search/recruit"
SARAMIN_CRAWL_PAGE_SIZE = 20
SARAMIN_CRAWL_MAX_RESULTS = 100
SARAMIN_CRAWL_DELAY_SECONDS = 1.5
SARAMIN_CRAWL_SOURCE = "사람인(크롤링)"
# 알바몬 공개 검색결과 크롤링(robots.txt가 ClaudeBot 등에 "Allow: /jobs" 명시).
# 검색 결과 페이지가 Next.js SSR이라 __NEXT_DATA__ script 안에 구조화된 JSON으로
# 공고 목록이 그대로 들어있어 HTML 파싱 없이 바로 읽을 수 있다(2026-08-07 확인:
# 실제 URL은 /jobs?keyword=가 아니라 /total-search?keyword=, sitemap.xml에서 확인).
ALBAMON_SEARCH_URL = "https://www.albamon.com/total-search"
ALBAMON_CRAWL_PAGE_SIZE = 20
ALBAMON_CRAWL_MAX_RESULTS = 100
ALBAMON_CRAWL_DELAY_SECONDS = 1.5
ALBAMON_SOURCE = "알바몬(크롤링)"
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
    source: str = "사람인"
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


def parse_saramin_job(raw: dict[str, Any], query: str, config: dict[str, Any]) -> Job:
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
        source="사람인",
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


def fetch_saramin_query(access_key: str, query: str, config: dict[str, Any]) -> list[Job]:
    params: dict[str, Any] = {
        "access-key": access_key,
        "keywords": query,
        "count": min(int(config.get("results_per_query", 30)), SARAMIN_MAX_RESULTS),
        "start": 0,
        "sort": config.get("sort", "pd"),
    }
    if config.get("locations"):
        params["loc_cd"] = ",".join(config["locations"])
    request = urllib.request.Request(
        f"{SARAMIN_API_URL}?{urllib.parse.urlencode(params)}",
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
    return [parse_saramin_job(item, query, config) for item in raw_jobs if isinstance(item, dict)]


def fetch_worknet_query(access_key: str, query: str, config: dict[str, Any]) -> list[Job]:
    params = {
        "authKey": access_key,
        "callTp": "L",
        "returnType": "XML",
        "startPage": 1,
        "display": min(int(config.get("results_per_query", 30)), WORK24_MAX_RESULTS),
        "keyword": query,
    }
    request = urllib.request.Request(
        f"{WORK24_API_URL}?{urllib.parse.urlencode(params)}",
        headers={"Accept": "application/xml", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", "replace")
        raise RuntimeError(f"워크넷 API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"워크넷 API 연결 실패: {exc.reason}") from exc

    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise RuntimeError(f"워크넷 API 응답 파싱 실패: {exc}") from exc

    error = root.findtext("error")
    if error:
        raise RuntimeError(f"워크넷 API 오류: {error}")

    return [parse_worknet_job(node, query, config) for node in root.findall("wanted")]


def parse_worknet_job(node: ET.Element, query: str, config: dict[str, Any]) -> Job:
    def text(tag: str) -> str:
        return plain(node.findtext(tag))

    title = text("title")
    company = text("company")
    industry = text("indTpNm")
    combined = " ".join((title, company, industry))
    skills = detect_skills(combined)
    emp_tp_code = text("empTpCd")
    return Job(
        source="워크넷",
        source_id=text("wantedAuthNo"),
        title=title,
        company=company,
        url=text("wantedInfoUrl"),
        location=text("region"),
        experience=text("career"),
        education=text("maxEdubg") or text("minEdubg"),
        employment_type=WORK24_EMP_TP_NAMES.get(emp_tp_code, emp_tp_code),
        salary=text("sal") or " ~ ".join(filter(None, (text("minSal"), text("maxSal")))),
        posted_at=text("regDt"),
        deadline=text("closeDt"),
        keywords=industry,
        skills=", ".join(skills),
        score=score_job(combined, config),
        matched_query=query,
    )


_SARAMIN_ITEM_START_RE = re.compile(r'<div class="item_recruit"')
_SARAMIN_VALUE_RE = re.compile(r'<div class="item_recruit" value="(\d+)"')
_SARAMIN_TITLE_LINK_RE = re.compile(r'<h2 class="job_tit">.*?<a[^>]*title="([^"]*)"[^>]*href="([^"]*)"', re.S)
_SARAMIN_DEADLINE_RE = re.compile(r'<span class="date">([^<]*)</span>')
_SARAMIN_CONDITION_RE = re.compile(r'<div class="job_condition">(.*?)</div>', re.S)
_SARAMIN_SPAN_RE = re.compile(r'<span[^>]*>(.*?)</span>', re.S)
_SARAMIN_CORP_NAME_RE = re.compile(r'<strong class="corp_name">\s*<a[^>]*>(.*?)</a>', re.S)


def _split_saramin_recruit_blocks(page_html: str) -> list[str]:
    """검색결과 HTML을 `item_recruit` 공고 블록 단위로 자른다(다음 마커 직전까지)."""
    starts = [m.start() for m in _SARAMIN_ITEM_START_RE.finditer(page_html)]
    return [
        page_html[start : starts[i + 1] if i + 1 < len(starts) else len(page_html)]
        for i, start in enumerate(starts)
    ]


def parse_saramin_crawl_block(block: str, query: str, config: dict[str, Any]) -> Job | None:
    """공고 블록 하나를 파싱. 필수 필드(공고ID·제목·링크)를 못 찾으면 None."""
    value_match = _SARAMIN_VALUE_RE.search(block)
    title_match = _SARAMIN_TITLE_LINK_RE.search(block)
    if not value_match or not title_match:
        return None
    source_id = value_match.group(1)
    title = html.unescape(title_match.group(1))
    href = html.unescape(title_match.group(2))
    url = href if href.startswith("http") else f"https://www.saramin.co.kr{href}"

    corp_match = _SARAMIN_CORP_NAME_RE.search(block)
    company = plain(corp_match.group(1)) if corp_match else ""

    deadline_match = _SARAMIN_DEADLINE_RE.search(block)
    deadline = plain(deadline_match.group(1)) if deadline_match else ""

    location = experience = education = employment_type = ""
    condition_match = _SARAMIN_CONDITION_RE.search(block)
    if condition_match:
        spans = [plain(s) for s in _SARAMIN_SPAN_RE.findall(condition_match.group(1))]
        if spans:
            location, rest = spans[0], spans[1:]
            experience = rest[0] if len(rest) > 0 else ""
            education = rest[1] if len(rest) > 1 else ""
            employment_type = rest[2] if len(rest) > 2 else ""

    combined = " ".join((title, company))
    skills = detect_skills(combined)
    return Job(
        source=SARAMIN_CRAWL_SOURCE,
        source_id=source_id,
        title=title,
        company=company,
        url=url,
        location=location,
        experience=experience,
        education=education,
        employment_type=employment_type,
        deadline=deadline,
        skills=", ".join(skills),
        score=score_job(combined, config),
        matched_query=query,
    )


def fetch_saramin_crawl_page(query: str, page: int, config: dict[str, Any]) -> list[Job]:
    """사람인 공개 검색결과 페이지 1장을 가져와 파싱. 로그인/CAPTCHA 우회 없음."""
    params = {
        "searchword": query,
        "recruitPage": page,
        "recruitSort": "relation",
        "recruitPageCount": SARAMIN_CRAWL_PAGE_SIZE,
    }
    request = urllib.request.Request(
        f"{SARAMIN_CRAWL_URL}?{urllib.parse.urlencode(params)}",
        headers={"Accept": "text/html", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"사람인 검색결과 페이지 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"사람인 검색결과 페이지 연결 실패: {exc.reason}") from exc

    jobs = []
    for block in _split_saramin_recruit_blocks(body):
        job = parse_saramin_crawl_block(block, query, config)
        if job is not None:
            jobs.append(job)
    return jobs


def fetch_saramin_crawl_query(query: str, config: dict[str, Any]) -> list[Job]:
    """검색어 하나에 대해 필요한 만큼 페이지를 넘기며 수집(페이지 사이 딜레이 포함)."""
    max_results = min(int(config.get("results_per_query", 30)), SARAMIN_CRAWL_MAX_RESULTS)
    max_pages = max(1, -(-max_results // SARAMIN_CRAWL_PAGE_SIZE))  # ceil
    jobs: list[Job] = []
    for page in range(1, max_pages + 1):
        page_jobs = fetch_saramin_crawl_page(query, page, config)
        if not page_jobs:
            break
        jobs.extend(page_jobs)
        if len(jobs) >= max_results:
            break
        if page < max_pages:
            time.sleep(SARAMIN_CRAWL_DELAY_SECONDS)
    return jobs[:max_results]


_ALBAMON_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)


def parse_albamon_job(raw: dict[str, Any], query: str, config: dict[str, Any]) -> Job:
    title = plain(raw.get("recruitTitle"))
    company = plain(raw.get("companyName"))
    recruit_no = plain(raw.get("recruitNo"))
    # payType은 {"key":"HOURLY_WAGE","value":"A000","description":"시급"} 형태라
    # scalar()의 name/code/value 우선순위로는 내부 코드("A000")가 잡힌다 — 사람이
    # 읽을 텍스트는 description 필드에 있으므로 직접 꺼낸다.
    pay_type = plain((raw.get("payType") or {}).get("description"))
    pay = plain(raw.get("pay"))
    salary = f"{pay_type} {pay}".strip() if pay else pay_type
    parts = [plain(p) for p in (raw.get("parts") or []) if p]
    keywords = ", ".join(parts)
    combined = " ".join((title, company, keywords, plain(raw.get("filterTotal"))))
    skills = detect_skills(combined)
    return Job(
        source=ALBAMON_SOURCE,
        source_id=recruit_no,
        title=title,
        company=company,
        url=f"https://www.albamon.com/jobs/detail/{recruit_no}",
        location=plain(raw.get("workplaceArea") or raw.get("workplaceAddress")),
        experience=plain(raw.get("age")),
        education="",
        employment_type=plain(raw.get("workingWeek")) or "아르바이트",
        salary=salary,
        posted_at=plain(raw.get("postedDate")),
        deadline=plain(raw.get("closingDate")),
        keywords=keywords,
        skills=", ".join(skills),
        score=score_job(combined, config),
        matched_query=query,
    )


def fetch_albamon_crawl_page(query: str, page: int, config: dict[str, Any]) -> list[Job]:
    """알바몬 공개 검색결과 페이지 1장을 가져와 파싱. 로그인/CAPTCHA 우회 없음.
    Next.js SSR 페이지의 __NEXT_DATA__ JSON에서 react-query 캐시 중
    queryKey가 "SEARCH_RECRUIT_LIST"인 항목의 공고 목록을 그대로 읽는다."""
    params = {"keyword": query, "page": page}
    request = urllib.request.Request(
        f"{ALBAMON_SEARCH_URL}?{urllib.parse.urlencode(params)}",
        headers={"Accept": "text/html", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"알바몬 검색결과 페이지 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"알바몬 검색결과 페이지 연결 실패: {exc.reason}") from exc

    match = _ALBAMON_NEXT_DATA_RE.search(body)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    queries = (
        data.get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", [])
    )
    for entry in queries:
        key = entry.get("queryKey")
        if isinstance(key, list) and key and key[0] == "SEARCH_RECRUIT_LIST":
            collection = (
                entry.get("state", {}).get("data", {}).get("base", {}).get("normal", {}).get("collection", [])
            )
            return [parse_albamon_job(item, query, config) for item in collection if isinstance(item, dict)]
    return []


def fetch_albamon_crawl_query(query: str, config: dict[str, Any]) -> list[Job]:
    """검색어 하나에 대해 필요한 만큼 페이지를 넘기며 수집(페이지 사이 딜레이 포함)."""
    max_results = min(int(config.get("results_per_query", 30)), ALBAMON_CRAWL_MAX_RESULTS)
    max_pages = max(1, -(-max_results // ALBAMON_CRAWL_PAGE_SIZE))  # ceil
    jobs: list[Job] = []
    for page in range(1, max_pages + 1):
        page_jobs = fetch_albamon_crawl_page(query, page, config)
        if not page_jobs:
            break
        jobs.extend(page_jobs)
        if len(jobs) >= max_results:
            break
        if page < max_pages:
            time.sleep(ALBAMON_CRAWL_DELAY_SECONDS)
    return jobs[:max_results]


def fingerprint(job: Job) -> str:
    body = "\x1f".join((job.title, job.company, job.location, job.deadline, job.salary))
    return hashlib.sha256(body.encode()).hexdigest()


def upsert_jobs(conn: sqlite3.Connection, jobs: Iterable[Job]) -> tuple[int, int]:
    inserted = updated = 0
    stamp = now_iso()
    for job in jobs:
        exists = conn.execute(
            "SELECT id, fingerprint FROM jobs WHERE source = ? AND source_id = ?", (job.source, job.source_id)
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
                INSERT INTO jobs (source,source_id,title,company,url,location,experience,education,
                    employment_type,salary,posted_at,deadline,keywords,skills,score,matched_query,
                    first_seen_at,last_seen_at,fingerprint)
                VALUES (:source,:source_id,:title,:company,:url,:location,:experience,:education,
                    :employment_type,:salary,:posted_at,:deadline,:keywords,:skills,:score,:matched_query,
                    :stamp,:stamp,:fingerprint)
            """, {**values, "stamp": stamp, "fingerprint": fp})
            inserted += 1
    conn.commit()
    return inserted, updated


def collect(args: argparse.Namespace) -> None:
    saramin_key = os.environ.get("SARAMIN_ACCESS_KEY", "").strip()
    worknet_key = os.environ.get("WORK24_ACCESS_KEY", "").strip()
    config = load_config(args.config)
    crawl_enabled = bool(config.get("enable_saramin_crawl", False))
    albamon_crawl_enabled = bool(config.get("enable_albamon_crawl", False))
    if not saramin_key and not worknet_key and not crawl_enabled and not albamon_crawl_enabled:
        raise SystemExit(
            "SARAMIN_ACCESS_KEY/WORK24_ACCESS_KEY가 모두 없고 사람인·알바몬 크롤링도 꺼져 있습니다. "
            "README의 API 키 설정 방법을 따르거나 config.json에 \"enable_saramin_crawl\"/\"enable_albamon_crawl\": true를 추가하세요."
        )
    conn = connect(args.db)
    collected: dict[tuple[str, str], Job] = {}

    def merge(jobs: list[Job], query: str) -> None:
        for job in jobs:
            key = (job.source, job.source_id)
            previous = collected.get(key)
            if previous:
                previous.matched_query = ", ".join(dict.fromkeys((previous.matched_query + ", " + query).split(", ")))
            else:
                collected[key] = job

    for index, query in enumerate(config["queries"], 1):
        print(f"[{index}/{len(config['queries'])}] '{query}' 검색 중…", flush=True)
        if saramin_key:
            jobs = fetch_saramin_query(saramin_key, query, config)
            print(f"  사람인(API) {len(jobs)}건 수신")
            merge(jobs, query)
        else:
            print("  ⚠️ SARAMIN_ACCESS_KEY 없음 — 사람인(API) 건너뜀")
        if worknet_key:
            jobs = fetch_worknet_query(worknet_key, query, config)
            print(f"  워크넷 {len(jobs)}건 수신")
            merge(jobs, query)
        else:
            print("  ⚠️ WORK24_ACCESS_KEY 없음 — 워크넷 건너뜀")
        if crawl_enabled:
            jobs = fetch_saramin_crawl_query(query, config)
            print(f"  사람인(크롤링) {len(jobs)}건 수신")
            merge(jobs, query)
            if index < len(config["queries"]):
                time.sleep(SARAMIN_CRAWL_DELAY_SECONDS)
        if albamon_crawl_enabled:
            jobs = fetch_albamon_crawl_query(query, config)
            print(f"  알바몬(크롤링) {len(jobs)}건 수신")
            merge(jobs, query)
            if index < len(config["queries"]):
                time.sleep(ALBAMON_CRAWL_DELAY_SECONDS)

    inserted, updated = upsert_jobs(conn, collected.values())
    print(f"\n완료: 신규 {inserted}건 / 기존 갱신 {updated}건 / 중복 제거 후 {len(collected)}건")


def list_jobs(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    rows = conn.execute("""
        SELECT source, score, company, title, location, deadline, url
        FROM jobs ORDER BY score DESC, deadline ASC LIMIT ?
    """, (args.limit,)).fetchall()
    if not rows:
        print("저장된 공고가 없습니다. collect를 먼저 실행하세요.")
        return
    for row in rows:
        print(f"[{row['score']:>3}] ({row['source']}) {row['company']} | {row['title']}")
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


def fetch_job_detail_text(url: str, source: str = "", source_id: str = "") -> str:
    """공고 상세 페이지를 가져와 태그를 걷어낸 순수 텍스트로 반환한다(내비게이션·광고
    등 잡음이 섞여도 무방 — analyze_job()의 AI 프롬프트가 실제 공고 본문만 골라
    읽도록 지시한다). AI 프롬프트에 그대로 넣을 것이므로 과도하게 길어지지 않게
    앞부분 8000자만 쓴다.

    ★ 2026-08-07: 사람인 공고 URL(저장된 relay/view 형태)은 본문이 JS로 나중에
    로드돼 curl로는 사이트 메뉴/푸터만 잡히고 실제 자격요건·우대사항은 0글자로
    떨어진다(실사용 중 확인). 반면 구버전 URL `zf_user/jobs/view?rec_idx=`는
    서버 렌더링이라 같은 공고의 본문이 그대로 잡힌다 — 사람인 소스면 저장된 URL
    대신 이 구버전 URL을 우선 시도한다."""
    if source.startswith("사람인") and source_id:
        url = f"https://www.saramin.co.kr/zf_user/jobs/view?rec_idx={source_id}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"공고 상세 페이지 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"공고 상세 페이지 연결 실패: {exc.reason}") from exc
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", body))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:8000]


_CONTENT_MARKERS = ("자격요건", "우대사항", "주요업무", "담당업무", "근무조건", "지원자격", "모집분야")


def _content_available(detail_text: str) -> bool:
    """★ 2026-08-07: 사람인 상세 페이지 일부(relay/view 등)는 본문이 JS로 나중에
    로드되거나 회사가 직접 만든 이미지 공고라, curl로는 사이트 내비게이션/푸터
    텍스트(수천 자 분량일 수 있음 — 단순 길이로는 못 걸러냄)만 잡히고 실제
    요구사항은 0글자로 떨어지는 경우를 실사용 중 확인했다(예: rec_idx=54484811,
    추출 1886자 전부가 메뉴/푸터). 표준 채용공고 섹션 제목이 하나도 없으면 실제
    본문을 못 가져온 것으로 본다."""
    return len(detail_text) >= 300 and any(marker in detail_text for marker in _CONTENT_MARKERS)


def build_analysis_prompt(row: sqlite3.Row, detail_text: str) -> str:
    return f"""다음은 채용공고 상세 페이지에서 그대로 긁어온 텍스트다(내비게이션·광고·
푸터 같은 잡음이 섞여 있을 수 있으니 실제 공고 본문(요구사항/우대사항 등)만 골라
판단하라).

회사: {row['company']}
공고 제목: {row['title']}

--- 공고 원문(잡음 포함 가능) ---
{detail_text}
--- 끝 ---

한국어로 아래 세 항목에 답하라:
1. **요구사항/우대사항 요약**: 실제 기술 스택·자격요건을 간단히 정리.
2. **이 회사가 지금 만들려는/겪고 있는 것 추론**: 요구사항과 우대사항의 조합에서
   이 팀이 실제로 하려는 일을 구체적으로 추론하라(예: "Python 기반 code
   interpreter + C++ 우대 → 실행 성능이 중요한 샌드박스/커널 구현 가능성"). 막연한
   일반론이 아니라, 왜 그 항목들이 함께 요구되는지 연결고리를 짚어라.
3. **연습 프로젝트 추천 1~2개**: 지원자가 위 추론을 뒷받침하려고 짧게 만들어볼 수
   있는 프로젝트를 구체적으로 제안하고, 어떤 요구사항 항목과 연결되는지 명시하라."""


def run_job_analysis(row: sqlite3.Row) -> str | None:
    """공고 하나를 분석해 AI 응답 텍스트를 반환한다. 본문을 못 가져왔으면(이미지형
    공고 등) 경고를 찍고 None을 반환한다 — analyze_job()/analyze_top_job()이 공유."""
    print(f"[{row['source']}] {row['company']} — {row['title']}")
    print(f"공고 페이지 가져오는 중: {row['url']}")
    detail_text = fetch_job_detail_text(row["url"], source=row["source"], source_id=row["source_id"])
    if not _content_available(detail_text):
        print(
            f"\n⚠️  공고 본문을 못 가져온 것으로 보입니다(추출 {len(detail_text)}자, "
            "채용공고 섹션 제목이 하나도 없음 — 사이트 메뉴/푸터만 잡혔을 가능성). "
            "이 페이지는 JS로 본문을 나중에 불러오거나(정적 크롤링 한계) 이미지형 "
            "채용공고일 가능성이 높습니다. 해당 URL을 직접 열어 요구사항을 확인해 "
            "주세요. 이 상태로 분석을 계속하면 AI가 근거 없이 추측할 수 있습니다.\n"
        )
        return None
    prompt = build_analysis_prompt(row, detail_text)
    print("\nAI로 분석 중... (codex 실패 시 claude로 자동 전환)\n")
    from ai_exec import run_ai_exec
    try:
        stdout, engine = run_ai_exec(prompt, BASE_DIR, timeout=300)
    except RuntimeError as exc:
        print(f"⚠️  AI 분석 실패: {exc}")
        return None
    return stdout.strip()


def analyze_job(args: argparse.Namespace) -> None:
    """공고 하나의 요구사항·우대사항을 AI로 읽어, 회사가 실제로 뭘 만들려는지
    추론하고 그걸 뒷받침할 연습 프로젝트를 추천받는다(2026-08-07 추가)."""
    conn = connect(args.db)
    if args.source:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE source = ? AND source_id = ?", (args.source, args.source_id)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM jobs WHERE source_id = ?", (args.source_id,)).fetchall()
    if not rows:
        raise SystemExit(f"source_id={args.source_id}인 공고를 찾을 수 없습니다. list로 먼저 확인하세요.")
    if len(rows) > 1:
        print(f"같은 source_id가 여러 소스에 있습니다. --source로 지정하세요:")
        for row in rows:
            print(f"  --source \"{row['source']}\"  ({row['company']} | {row['title']})")
        return
    text = run_job_analysis(rows[0])
    if text:
        print(text)


NOTION_VERSION = "2026-03-11"
# "🎴 이직시스템" 페이지(app.notion.com/p/3b132a1eae80805dad0ed4f2cae02709)를
# 표준 UUID 형식(8-4-4-4-12)으로 표기한 것 — Notion API의 parent.page_id에 그대로 쓴다.
NOTION_JOBSYSTEM_PAGE_ID = "3b132a1e-ae80-805d-ad0e-d4f2cae02709"
TOP_JOB_STATE_PATH = BASE_DIR / "data" / "top_job_notion.json"


def _notion_token() -> str:
    """일본어자막추출/sync_book_to_notion.py와 동일한 키체인 항목을 재사용한다
    (2026-08-07 사용자 확인: 같은 통합을 "🎴 이직시스템" 페이지에도 공유해둠)."""
    result = subprocess.run(
        ["security", "find-generic-password", "-a", os.environ.get("USER", ""),
         "-s", "jp_subtitle_notion_token", "-w"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _markdown_to_notion_blocks(text: str) -> list[dict[str, Any]]:
    """AI 분석 텍스트(마크다운 헤딩·불릿·**볼드**)를 Notion 블록으로 변환한다.
    sync_book_to_notion.py의 summary_blocks()와 같은 헤딩/불릿 규칙에, **볼드**
    인라인 서식만 추가했다(분석 텍스트에 강조가 많아 없으면 별표가 그대로 보임)."""
    bold_re = re.compile(r"\*\*(.+?)\*\*")

    def rich_text(content: str) -> list[dict[str, Any]]:
        segments = []
        pos = 0
        for m in bold_re.finditer(content):
            if m.start() > pos:
                segments.append({"type": "text", "text": {"content": content[pos:m.start()][:1900]}})
            segments.append({
                "type": "text", "text": {"content": m.group(1)[:1900]},
                "annotations": {"bold": True},
            })
            pos = m.end()
        if pos < len(content):
            segments.append({"type": "text", "text": {"content": content[pos:][:1900]}})
        return segments or [{"type": "text", "text": {"content": ""}}]

    blocks = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("### "):
            block_type, content = "heading_3", line[4:]
        elif line.startswith("## "):
            block_type, content = "heading_2", line[3:]
        elif line.startswith("# "):
            block_type, content = "heading_1", line[2:]
        elif line.startswith("- ") or line.startswith("• "):
            block_type, content = "bulleted_list_item", line[2:].strip()
        else:
            block_type, content = "paragraph", line
        blocks.append({
            "object": "block", "type": block_type,
            block_type: {"rich_text": rich_text(content[:1900])},
        })
    return blocks


def _notion_request(method: str, path: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"https://api.notion.com/v1/{path}", data=body, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read(500).decode("utf-8", "replace")
        raise RuntimeError(f"Notion API {method} {path} HTTP {exc.code}: {detail}") from exc


def _notion_publish(token: str, title: str, blocks: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    """저장된 페이지가 있으면 내용을 통째로 교체(기존 자식 블록 archive 후 재작성)
    하고, 없으면 "🎴 이직시스템" 밑에 새로 만든다. 매일 같은 페이지를 갱신해서
    실행할 때마다 새 페이지가 쌓이지 않게 한다. 반환값은 Notion 페이지 URL."""
    state = {}
    if TOP_JOB_STATE_PATH.exists():
        try:
            state = json.loads(TOP_JOB_STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    page_id = state.get("page_id")

    if page_id:
        _notion_request("PATCH", f"pages/{page_id}", token, {
            "properties": {"title": {"title": [{"text": {"content": title}}]}}
        })
        existing = _notion_request("GET", f"blocks/{page_id}/children?page_size=100", token)
        for child in existing.get("results", []):
            _notion_request("DELETE", f"blocks/{child['id']}", token)
    else:
        created = _notion_request("POST", "pages", token, {
            "parent": {"page_id": NOTION_JOBSYSTEM_PAGE_ID},
            "properties": {"title": {"title": [{"text": {"content": title}}]}},
        })
        page_id = created["id"]

    for start in range(0, len(blocks), 50):
        _notion_request("PATCH", f"blocks/{page_id}/children", token, {"children": blocks[start:start + 50]})

    url = f"https://www.notion.so/{page_id.replace('-', '')}"
    TOP_JOB_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOP_JOB_STATE_PATH.write_text(
        json.dumps({"page_id": page_id, "url": url, **meta}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return url


def analyze_top_job(args: argparse.Namespace) -> None:
    """현재 적합도 1위 공고를 골라 AI 분석을 돌리고 결과를 Notion 페이지 하나에
    갱신한다(shift_alarm 메뉴바에서 매일 자동 호출, 2026-08-07 추가). 상위 공고가
    이미지형 등으로 본문을 못 가져오면 다음 순위로 자동으로 내려가며 시도한다."""
    conn = connect(args.db)
    candidates = conn.execute(
        "SELECT * FROM jobs ORDER BY score DESC, deadline ASC LIMIT 5"
    ).fetchall()
    if not candidates:
        raise SystemExit("저장된 공고가 없습니다. collect를 먼저 실행하세요.")

    row = None
    text = None
    for candidate in candidates:
        text = run_job_analysis(candidate)
        if text:
            row = candidate
            break
        print(f"  ↪️ [{candidate['score']}점] {candidate['company']} 분석 불가 — 다음 순위로 시도\n")
    if row is None:
        raise SystemExit("상위 5개 공고 모두 본문을 못 가져오거나 AI 분석에 실패했습니다.")

    token = _notion_token()
    if not token:
        print("⚠️  Notion 토큰(jp_subtitle_notion_token)이 키체인에 없어 Notion 페이지 갱신을 건너뜁니다.")
        print(text)
        return

    title = f"🎯 {row['company']} — {row['title']}"
    meta_line = f"점수 {row['score']} | {row['source']} | {row['url']}"
    blocks = _markdown_to_notion_blocks(meta_line) + _markdown_to_notion_blocks(text)
    meta = {
        "company": row["company"], "title": row["title"],
        "score": row["score"], "source": row["source"], "job_url": row["url"],
    }
    try:
        url = _notion_publish(token, title, blocks, meta)
    except RuntimeError as exc:
        print(f"⚠️  Notion 페이지 갱신 실패: {exc}")
        print(text)
        return
    print(f"\n✅ Notion 페이지 갱신 완료: {url}")


def doctor(args: argparse.Namespace) -> None:
    print(f"Python: {sys.version.split()[0]}")
    print(f"사람인 API 키: {'설정됨' if os.environ.get('SARAMIN_ACCESS_KEY') else '미설정'}")
    print(f"워크넷 API 키: {'설정됨' if os.environ.get('WORK24_ACCESS_KEY') else '미설정'}")
    print(f"설정: {args.config} ({'있음' if args.config.exists() else '없음'})")
    if args.config.exists():
        cfg = load_config(args.config)
        crawl_enabled = bool(cfg.get("enable_saramin_crawl", False))
        albamon_crawl_enabled = bool(cfg.get("enable_albamon_crawl", False))
        print(f"사람인 크롤링(공개 검색결과): {'켜짐' if crawl_enabled else '꺼짐 (config.json enable_saramin_crawl)'}")
        print(f"알바몬 크롤링(공개 검색결과): {'켜짐' if albamon_crawl_enabled else '꺼짐 (config.json enable_albamon_crawl)'}")
    print(f"DB: {args.db} ({'있음' if args.db.exists() else '아직 없음'})")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="사람인·워크넷 공식 API 채용공고 수집기")
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
    an = sub.add_parser("analyze", help="공고 하나의 요구사항을 AI로 읽어 프로젝트 아이디어 추천")
    an.add_argument("source_id", help="list/export에서 확인한 공고의 source_id")
    an.add_argument("--source", help="같은 source_id가 여러 소스에 있을 때만 지정 (예: \"사람인(크롤링)\")")
    an.set_defaults(func=analyze_job)
    sub.add_parser(
        "analyze-top", help="적합도 1위 공고를 AI로 분석해 Notion 페이지 갱신(shift_alarm 자동 호출용)"
    ).set_defaults(func=analyze_top_job)
    return p


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

