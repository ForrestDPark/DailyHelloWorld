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
CANDIDATE_PROFILE_PATH = BASE_DIR / "candidate_profile.json"
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
# 알바천국(alba.co.kr) — robots.txt가 /job/을 명시적으로 허용. 검색결과 페이지
# (/Job/List, /job/Total 등)는 뭘 시도해도 "일시적인 장애가 발생하였습니다"라는
# 안내 페이지(HTTP 200)만 돌아와 실제 검색 API를 못 찾았다(2026-08-08 재시도해도
# 동일). 대신 sitemap.xml에 공고 상세 URL(/job/Detail?adid=)이 그대로 나열돼
# 있고, 그 상세 페이지는 서버 렌더링이라 og:title/og:description 메타 태그에
# "[알바천국] 지역 / 회사명 / 공고명 / 급여" 형식으로 필요한 정보가 이미 정리돼
# 있다 — 검색 대신 최신 사이트맵에서 상세 URL을 모아 하나씩 가져오는 방식으로 우회.
ALBA_SITEMAP_INDEX_URL = "https://www.alba.co.kr/sitemap.xml"
ALBA_DETAIL_URL_RE = re.compile(r"https://www\.alba\.co\.kr/job/Detail\?adid=(\d+)")
ALBA_CRAWL_MAX_RESULTS = 100
ALBA_CRAWL_DELAY_SECONDS = 1.0
ALBA_SOURCE = "알바천국(크롤링)"
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


_ALBA_SITEMAP_ENTRY_RE = re.compile(
    r"<loc>(https://www\.alba\.co\.kr/sitemap/sitemap\d*\.xml)</loc>\s*<lastmod>([^<]*)</lastmod>"
)
_ALBA_OG_TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]*)"')
_ALBA_OG_DESC_RE = re.compile(r'<meta property="og:description" content="([^"]*)"')
ALBA_MATCHED_QUERY_LABEL = "알바천국 최신 공고(사이트맵)"


def fetch_alba_sitemap_urls(limit=ALBA_CRAWL_MAX_RESULTS):
    """사이트맵 인덱스에서 가장 최근 갱신된 하위 사이트맵 하나를 골라, 그 안의
    공고 상세 URL에서 adid를 순서를 유지하며 최대 limit개 모은다."""
    request = urllib.request.Request(ALBA_SITEMAP_INDEX_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            index_body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"알바천국 사이트맵 인덱스 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"알바천국 사이트맵 인덱스 연결 실패: {exc.reason}") from exc

    entries = _ALBA_SITEMAP_ENTRY_RE.findall(index_body)
    if not entries:
        return []
    entries.sort(key=lambda pair: pair[1], reverse=True)  # lastmod 최신 우선
    chosen_url = entries[0][0]

    request = urllib.request.Request(chosen_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"알바천국 사이트맵 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"알바천국 사이트맵 연결 실패: {exc.reason}") from exc

    adids = []
    seen = set()
    for adid in ALBA_DETAIL_URL_RE.findall(body):
        if adid in seen:
            continue
        seen.add(adid)
        adids.append(adid)
        if len(adids) >= limit:
            break
    return adids


def fetch_alba_detail(adid: str, config: dict[str, Any]) -> Job | None:
    """공고 상세 페이지 하나를 가져와 og:title/og:description 메타 태그로 파싱한다.
    "[알바천국] 지역 / 회사명 / 공고명 / 급여" 형식(실사용 확인, 2026-08-08)."""
    url = f"https://www.alba.co.kr/job/Detail?adid={adid}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"알바천국 상세 페이지 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"알바천국 상세 페이지 연결 실패: {exc.reason}") from exc

    desc_match = _ALBA_OG_DESC_RE.search(body)
    if not desc_match:
        return None
    # ★ 2026-08-08 실사용 중 확인: og:description 안에 급여 단위를 강조하려고
    # &lt;span class=&#39;detail-pay__unit&#39;&gt;원&lt;/span&gt;처럼 이스케이프된
    # HTML 태그가 통째로 섞여 나오는 공고가 있다(사이트 버그로 보임) — 엔티티를
    # 먼저 풀어야 실제 "<span>" 형태가 되므로, 태그 제거보다 unescape가 먼저다.
    desc = re.sub(r"<[^>]+>", "", html.unescape(desc_match.group(1)))
    desc_body = desc[len("[알바천국]"):].strip() if desc.startswith("[알바천국]") else desc
    parts = [p.strip() for p in desc_body.split(" / ")]
    location = parts[0] if len(parts) > 0 else ""
    company = parts[1] if len(parts) > 1 else ""
    job_title = parts[2] if len(parts) > 2 else ""
    salary = parts[3] if len(parts) > 3 else ""
    if not job_title:
        title_match = _ALBA_OG_TITLE_RE.search(body)
        title_full = html.unescape(title_match.group(1)) if title_match else ""
        job_title = title_full.split(":", 1)[-1].strip() if ":" in title_full else title_full
    if not job_title:
        return None

    combined = " ".join((job_title, company))
    skills = detect_skills(combined)
    return Job(
        source=ALBA_SOURCE,
        source_id=adid,
        title=job_title,
        company=company,
        url=url,
        location=location,
        salary=salary,
        skills=", ".join(skills),
        score=score_job(combined, config),
        matched_query=ALBA_MATCHED_QUERY_LABEL,
    )


def fetch_alba_crawl(config: dict[str, Any]) -> list[Job]:
    """검색 API가 없어(README 3-5 참고) 최신 사이트맵에서 공고 상세 URL을 모은 뒤
    각각을 로컬 키워드 점수로 평가한다. 사람인/알바몬처럼 검색어별로 호출하는
    구조가 아니라, collect() 안에서 검색어 루프와 무관하게 한 번만 실행된다."""
    adids = fetch_alba_sitemap_urls(limit=ALBA_CRAWL_MAX_RESULTS)
    jobs = []
    failed = 0
    for i, adid in enumerate(adids):
        # 상세 페이지 하나당 요청 1건이라(100건까지) 만료/삭제된 공고 하나가
        # 통째로 배치를 죽이지 않게 개별 실패는 건너뛴다.
        try:
            job = fetch_alba_detail(adid, config)
        except RuntimeError:
            failed += 1
            job = None
        if job:
            jobs.append(job)
        if i < len(adids) - 1:
            time.sleep(ALBA_CRAWL_DELAY_SECONDS)
    if failed:
        print(f"  ⚠️ 알바천국 상세 페이지 {failed}건 조회 실패(만료/삭제된 공고일 수 있음) — 건너뜀")
    return jobs


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
    alba_crawl_enabled = bool(config.get("enable_alba_crawl", False))
    if not saramin_key and not worknet_key and not crawl_enabled and not albamon_crawl_enabled and not alba_crawl_enabled:
        raise SystemExit(
            "SARAMIN_ACCESS_KEY/WORK24_ACCESS_KEY가 모두 없고 사람인·알바몬·알바천국 크롤링도 꺼져 있습니다. "
            "README의 API 키 설정 방법을 따르거나 config.json에 \"enable_saramin_crawl\"/\"enable_albamon_crawl\"/\"enable_alba_crawl\": true를 추가하세요."
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

    if alba_crawl_enabled:
        # 검색 API가 없어 검색어 루프와 무관하게 한 번만 실행(fetch_alba_crawl 참고).
        print(f"알바천국(사이트맵) 최신 공고 수집 중(최대 {ALBA_CRAWL_MAX_RESULTS}건)...")
        jobs = fetch_alba_crawl(config)
        print(f"  알바천국(크롤링) {len(jobs)}건 수신")
        merge(jobs, ALBA_MATCHED_QUERY_LABEL)

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


def load_candidate_profile(path: Path = CANDIDATE_PROFILE_PATH) -> dict[str, Any]:
    """Git에 공유된 비식별 후보자 프로필을 읽는다.

    연락처·주소 등 원본 개인정보는 이 파일에 들어가지 않는다. 프로필이 없거나
    깨졌으면 기존 공고 분석은 계속 동작하고 맞춤 작성 섹션만 생략한다.
    """
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    required = {"identity", "skills", "experience", "projects", "story_bank", "writing_rules"}
    return profile if required.issubset(profile) else {}


def candidate_profile_context(profile: dict[str, Any] | None = None) -> str:
    profile = load_candidate_profile() if profile is None else profile
    if not profile:
        return ""
    # 모델이 공고와 연결할 때 필요한 근거만 전달하고 verification_queue를 같이 넣어
    # 미확인 논문·특허·수치를 확정 사실처럼 쓰지 못하게 한다.
    selected = {
        "identity": profile["identity"],
        "target_roles": profile.get("target_roles", []),
        "skills": profile["skills"],
        "experience": profile["experience"],
        "projects": profile["projects"],
        "story_bank": profile["story_bank"],
        "writing_rules": profile["writing_rules"],
        "verification_queue": profile.get("verification_queue", []),
    }
    return json.dumps(selected, ensure_ascii=False, indent=2)


def build_analysis_prompt(row: sqlite3.Row, detail_text: str) -> str:
    candidate_context = candidate_profile_context()
    custom_request = "" if not candidate_context else f"""

--- 비식별 후보자 근거 프로필 ---
{candidate_context}
--- 후보자 프로필 끝 ---

5. **맞춤 포트폴리오 구성**: 공고 요구사항별로 후보자의 어떤 프로젝트·경력 근거를
   연결할지 표로 정리하라. 대표 프로젝트는 2~3개만 고르고 배열 순서, 첫 화면 한 줄,
   강조할 문제·행동·결과, 부족한 증거와 보완 과제를 제시하라. 검증 대기 항목은
   확정 사실처럼 쓰지 말고 반드시 "확인 필요"라고 표시하라.
6. **맞춤 자기소개서 초안**: ①지원 동기 ②직무 수행 경험 ③문제 해결·협업 ④입사 후
   기여의 네 소제목으로 작성하라. 공고의 표현을 복사하지 말고 후보자 근거와 연결하며,
   하지 않은 경험이나 숫자를 만들지 마라. 각 문단은 문제→판단·행동→결과→회사에서의
   활용 순서로 쓰고, 연락처·주소·나이 등 개인정보는 넣지 마라.
"""
    return f"""다음은 채용공고 상세 페이지에서 그대로 긁어온 텍스트다(내비게이션·광고·
푸터 같은 잡음이 섞여 있을 수 있으니 실제 공고 본문(요구사항/우대사항 등)만 골라
판단하라).

회사: {row['company']}
공고 제목: {row['title']}

--- 공고 원문(잡음 포함 가능) ---
{detail_text}
--- 끝 ---

한국어로 아래 항목에 답하라(★ 2026-08-08: 가장 궁금해하는 "회사가 지금 뭘
하려는지" 추론을 1번으로 옮김 — 순서가 곧 Notion 페이지에 보이는 순서):
1. **이 회사가 지금 만들려는/겪고 있는 것 추론**: 요구사항과 우대사항의 조합에서
   이 팀이 실제로 하려는 일을 구체적으로 추론하라(예: "Python 기반 code
   interpreter + C++ 우대 → 실행 성능이 중요한 샌드박스/커널 구현 가능성"). 막연한
   일반론이 아니라, 왜 그 항목들이 함께 요구되는지 연결고리를 짚어라.
2. **요구사항/우대사항 요약**: 실제 기술 스택·자격요건을 간단히 정리.
3. **연습 프로젝트 추천 1~2개**: 지원자가 1번 추론을 뒷받침하려고 짧게 만들어볼 수
   있는 프로젝트를 구체적으로 제안하고, 어떤 요구사항 항목과 연결되는지 명시하라.
4. **1인 사업자로 이 회사를 직접 창업한다면의 사업계획서 항목화**: 지원자가 아니라
   이 회사가 하려는 일 자체를 혼자 시작하는 창업자 입장에서 분석하라. 1번의 추론을
   그대로 사업 아이템으로 놓고, 아래 항목을 채워라(모르는 항목은 "정보 부족 —
   추정:"으로 표시하고 근거 있는 추정을 적을 것, 지어내지 말 것):
   - 사업 아이템/핵심 가치제안: 무엇을 파는가, 왜 그게 필요한가
   - 목표 고객: 이 공고를 낸 회사 같은 업종·규모의 기업들(구체적으로)
   - 수익 모델: 구독/용역/라이선스 등 중 어느 쪽이 맞을지와 그 이유
   - 최소 실행 조직: 혼자 또는 몇 명으로, 어떤 역할 분담이 필요한지(이 공고의
     업무 범위를 그대로 참고)
   - 초기 필요 역량/도구: 2·3번에서 나온 기술 스택 그대로 연결
   - 시장 진입 전략: 첫 고객을 어떻게 확보할지(예: 이 회사가 속한 업종 커뮤니티,
     레퍼런스 고객 확보 방식)
   - 경쟁/대체재 대비 차별점: 기존에 어떻게 해결하고 있었을지와 비교{custom_request}"""


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
# ★ 2026-08-08: 취업공고와 알바공고는 성격이 달라서(정규직 커리어 vs 단기/알바)
# 하나로 뭉쳐서 1건만 추천하면 둘 중 한쪽이 항상 묻힌다는 지적으로 카테고리별로
# 분리했다 — 각각 별도 상태 파일·Notion 페이지를 갖는다.
JOB_SOURCE_CATEGORY = {
    "사람인": "career", "사람인(크롤링)": "career", "워크넷": "career",
    "알바몬(크롤링)": "parttime", "알바천국(크롤링)": "parttime",
}
JOB_CATEGORY_LABELS = {"career": "커리어 공고", "parttime": "알바·단기 공고"}


def top_job_state_path(category: str) -> Path:
    return BASE_DIR / "data" / f"top_job_notion_{category}.json"


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
    sync_book_to_notion.py의 summary_blocks()와 같은 헤딩/불릿 규칙에, **볼드**와
    URL 하이퍼링크 인라인 서식을 추가했다(볼드 없으면 별표가 그대로 보이고, URL도
    링크로 안 만들면 meta 줄의 공고 원문 URL이 그냥 텍스트로만 보여서 2026-08-07
    사용자 피드백으로 추가)."""
    inline_re = re.compile(r"\*\*(.+?)\*\*|(https?://[^\s]+)")

    def rich_text(content: str) -> list[dict[str, Any]]:
        segments = []
        pos = 0
        for m in inline_re.finditer(content):
            if m.start() > pos:
                segments.append({"type": "text", "text": {"content": content[pos:m.start()][:1900]}})
            if m.group(1) is not None:
                segments.append({
                    "type": "text", "text": {"content": m.group(1)[:1900]},
                    "annotations": {"bold": True},
                })
            else:
                url = m.group(2)
                trail = ""
                while url and url[-1] in ".,)]}":
                    trail = url[-1] + trail
                    url = url[:-1]
                segments.append({
                    "type": "text", "text": {"content": url[:1900], "link": {"url": url}},
                })
                if trail:
                    segments.append({"type": "text", "text": {"content": trail}})
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


def _notion_publish(
    token: str, title: str, blocks: list[dict[str, Any]], meta: dict[str, Any],
    state_path: Path = None,
) -> str:
    """저장된 페이지가 있으면 내용을 통째로 교체(기존 자식 블록 archive 후 재작성)
    하고, 없으면 "🎴 이직시스템" 밑에 새로 만든다. 매일 같은 페이지를 갱신해서
    실행할 때마다 새 페이지가 쌓이지 않게 한다. 반환값은 Notion 페이지 URL.
    ★ 2026-08-08: state_path를 인자로 받게 바꿔서 커리어/알바 등 카테고리별로
    서로 다른 상태 파일(=서로 다른 Notion 페이지)을 쓸 수 있게 함
    (contest_collector.py의 동명 함수와 같은 시그니처)."""
    if state_path is None:
        state_path = top_job_state_path("career")  # 하위호환 기본값
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    page_id = state.get("page_id")

    if page_id:
        _notion_request("PATCH", f"pages/{page_id}", token, {
            "properties": {"title": {"title": [{"text": {"content": title}}]}}
        })
        # ★ 2026-08-08 버그 수정: page_size=100 한 페이지만 지우면 블록이 100개
        # 넘는 긴 분석 페이지(흔함)는 이전 내용이 안 지워지고 그 뒤에 새 내용이
        # 계속 쌓였다(실측: 크라우드웍스 페이지에 다믈파워반도체 내용이 그대로
        # 남아 있었음). 삭제하면서 커서가 밀리는 걸 피하려고 매번 "첫 페이지"를
        # 새로 조회해 지우는 방식으로, 결과가 빌 때까지 반복한다.
        while True:
            existing = _notion_request("GET", f"blocks/{page_id}/children?page_size=100", token)
            results = existing.get("results", [])
            if not results:
                break
            for child in results:
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
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"page_id": page_id, "url": url, **meta}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return url


def _append_history_toggle(
    token: str, parent_page_id: str, prefix: str, toggle_title: str, blocks: list[dict[str, Any]],
) -> None:
    """"🎴 이직시스템" 최상위 페이지에 오늘의 추천을 토글로 누적한다(★ 2026-08-08
    사용자 요청: "최상위에 오늘의 추천공고랑 경진대회 페이지들이 축적되도록,
    토글화해서 너무 늘어지지 않게"). `_notion_publish()`의 카테고리별 하위
    페이지는 계속 "하나만 매일 갱신" 방식을 유지하고(최신 스냅샷용), 이 함수는
    그와 별개로 매일의 결과를 접힌 토글로 남겨 과거 기록이 사라지지 않게 한다.
    같은 날 같은 카테고리로 이미 추가된 토글이 있으면(재실행 등) 새로 만들지
    않고 그 안의 내용만 교체한다 — `prefix`(예: "[2026-08-08][career]")로 식별."""
    toggle_id = None
    cursor = None
    while toggle_id is None:
        path = f"blocks/{parent_page_id}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        resp = _notion_request("GET", path, token)
        for child in resp.get("results", []):
            if child.get("type") != "toggle":
                continue
            text = "".join(r.get("plain_text", "") for r in child["toggle"].get("rich_text", []))
            if text.startswith(prefix):
                toggle_id = child["id"]
                break
        if toggle_id or not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")

    if toggle_id:
        while True:
            resp = _notion_request("GET", f"blocks/{toggle_id}/children?page_size=100", token)
            results = resp.get("results", [])
            if not results:
                break
            for child in results:
                _notion_request("DELETE", f"blocks/{child['id']}", token)
    else:
        created = _notion_request("PATCH", f"blocks/{parent_page_id}/children", token, {
            "children": [{
                "object": "block", "type": "toggle",
                "toggle": {"rich_text": [{"type": "text", "text": {"content": toggle_title[:1900]}}]},
            }]
        })
        toggle_id = created["results"][0]["id"]

    for start in range(0, len(blocks), 50):
        _notion_request("PATCH", f"blocks/{toggle_id}/children", token, {"children": blocks[start:start + 50]})


def _format_krw(raw: str) -> str:
    """DART 원 단위 숫자(예: "77002948664")를 사람이 바로 읽을 수 있는 조/억
    단위로 바꾼다(★ 2026-08-08: "77002948664원"처럼 원 단위 그대로 보여주는 게
    "성의 없다"는 피드백으로 추가)."""
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return raw or "-"
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1_0000_0000_0000:
        jo, rem = divmod(n, 1_0000_0000_0000)
        eok = rem // 1_0000_0000
        return f"{sign}{jo}조 {eok:,}억원" if eok else f"{sign}{jo}조원"
    if n >= 1_0000_0000:
        return f"{sign}{n / 1_0000_0000:,.0f}억원"
    return f"{sign}{n:,}원"


_DART_TABLE_COLUMNS = ["매출액", "영업이익", "당기순이익", "자산총계", "부채총계", "자본총계"]


def _dart_financial_table_block(financials: list[dict]) -> dict[str, Any] | None:
    """DART 재무 요약을 슬래시로 이어붙인 한 줄 텍스트 대신 Notion 표 블록으로
    만든다(★ 2026-08-08 피드백: "분석하기 쉽게 요약하고 table을 쓰면 좋겠다").
    최근 연도부터 최대 3개년을 행으로, 계정과목을 열로 둔다."""
    years = financials[:3]
    if not years:
        return None

    def cell(content: str) -> list[dict[str, Any]]:
        return [{"type": "text", "text": {"content": content}}]

    header_row = {
        "object": "block", "type": "table_row",
        "table_row": {"cells": [cell("연도")] + [cell(c) for c in _DART_TABLE_COLUMNS]},
    }
    data_rows = []
    for year_data in years:
        cells = [cell(f"{year_data['year']}년")]
        for col in _DART_TABLE_COLUMNS:
            cells.append(cell(_format_krw(year_data.get(col, ""))))
        data_rows.append({"object": "block", "type": "table_row", "table_row": {"cells": cells}})

    return {
        "object": "block", "type": "table",
        "table": {
            "table_width": len(_DART_TABLE_COLUMNS) + 1,
            "has_column_header": True,
            "has_row_header": True,
            "children": [header_row] + data_rows,
        },
    }


def _rank_candidates_by_analyzability(candidates: list[sqlite3.Row]) -> list[sqlite3.Row]:
    """★ 2026-08-07 추가, ★ 2026-08-09 하드 필터로 강화: 단순 키워드 점수만으로
    "오늘의 추천 공고"를 고르면 재무·경영 이력을 전혀 알 수 없는 무명 소기업이
    뽑히는 경우가 많았다. 처음엔 DART 등록 기업을 우선 순위로만 앞당겼지만,
    그래도 등록 기업이 없으면 결국 "DART 미등록 — 공시 재무정보 없음 / 수집된
    채용공고 없음"처럼 아무 근거도 없이 "정보 부족 — 추정"만 가득한 분석이
    나왔다. 사용자 피드백: 이렇게 아무 정보도 확인할 수 없는 불안정한 회사는
    애초에 추천 후보에서 빼고 싶다 — 그런 회사에 지원하고 싶지 않다. 그래서
    DART 미등록 기업은 아예 후보에서 제외한다. DART_API_KEY가 없으면 등록
    여부 자체를 확인할 수 없으므로(잘못 걸러내는 것을 막기 위해) 필터를 적용하지
    않고 전체 후보를 그대로 반환한다."""
    from company_profile import _dart_api_key, fetch_dart_corp_code_map, find_dart_corp_code
    api_key = _dart_api_key()
    if not api_key:
        print("  ⚠️ DART_API_KEY 없음 — 정보 없는 회사를 걸러내지 못하고 점수 순서로만 고름")
        return candidates
    try:
        corp_map = fetch_dart_corp_code_map(api_key)
    except Exception as exc:  # noqa: BLE001 — DART 조회 실패는 순위만 못 매길 뿐 치명적이지 않음
        print(f"  ⚠️ DART corp_code 조회 실패({exc}) — 걸러내지 못하고 점수 순서로만 고름")
        return candidates

    def is_registered(row: sqlite3.Row) -> bool:
        return find_dart_corp_code(row["company"], corp_map) is not None

    registered = [c for c in candidates if is_registered(c)]
    print(f"  DART 등록 기업 {len(registered)}/{len(candidates)}건 — 미등록(정보 확인 불가) 기업은 추천 후보에서 제외")
    return registered


def top_job_history_path(category: str) -> Path:
    return BASE_DIR / "data" / f"top_job_history_{category}.json"


def _load_top_job_history(category: str) -> set[str]:
    path = top_job_history_path(category)
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("used", []))
    except json.JSONDecodeError:
        return set()


def _save_top_job_history(category: str, used: set[str]) -> None:
    path = top_job_history_path(category)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"used": sorted(used)}, ensure_ascii=False, indent=2), encoding="utf-8")


def _apply_no_repeat_rotation(candidates: list[sqlite3.Row], category: str) -> list[sqlite3.Row]:
    """★ 2026-08-08: 점수·마감일로만 정렬하면 순위 1위 공고(예: 피에스티)가
    마감 전까지 매일 똑같이 뽑혀 "갱신이 안 되는 것처럼" 보인다는 지적으로,
    extract_high_pitch_video.py의 BGM 로테이션과 같은 패턴을 적용한다 — 이미
    추천한 공고는 풀이 소진될 때까지 제외하고, 다 소진되면 초기화해서 다시
    1위부터 순환한다."""
    used = _load_top_job_history(category)
    pool_ids = {f"{c['source']}:{c['source_id']}" for c in candidates}
    used &= pool_ids  # 마감 지나 후보군에서 빠진 공고는 히스토리에서도 정리
    unused = [c for c in candidates if f"{c['source']}:{c['source_id']}" not in used]
    if not unused:
        used = set()
        unused = candidates
    return unused, used


def analyze_top_job(args: argparse.Namespace) -> None:
    """현재 적합도 1위 공고를 골라 AI 분석을 돌리고 결과를 Notion 페이지 하나에
    갱신한다(shift_alarm 메뉴바에서 매일 자동 호출, 2026-08-07 추가). 상위 공고가
    이미지형 등으로 본문을 못 가져오면 다음 순위로 자동으로 내려가며 시도한다.
    후보를 모아 DART 등록 여부(재무·경영 이력 분석 가능 여부)로 우선 재정렬한 뒤,
    이미 추천했던 공고는 풀이 소진될 때까지 제외하는 로테이션을 적용하고, 그중
    본문을 가져올 수 있는 첫 후보를 최종 선택한다.
    ★ 2026-08-08: 취업(career)/알바(parttime) 카테고리별로 후보를 나눠 각자
    독립된 Notion 페이지·로테이션 히스토리를 갖는다(--category 인자)."""
    category = args.category
    conn = connect(args.db)
    sources = [s for s, cat in JOB_SOURCE_CATEGORY.items() if cat == category]
    placeholders = ",".join("?" for _ in sources)
    candidates = conn.execute(
        f"SELECT * FROM jobs WHERE source IN ({placeholders}) "
        "ORDER BY score DESC, deadline ASC LIMIT 50",
        sources,
    ).fetchall()
    if not candidates:
        raise SystemExit(f"[{JOB_CATEGORY_LABELS[category]}] 저장된 공고가 없습니다. collect를 먼저 실행하세요.")
    candidates = _rank_candidates_by_analyzability(candidates)
    if not candidates:
        # ★ 2026-08-09: DART 미등록 기업을 하드 필터로 걸러낸 결과 후보가 하나도
        # 안 남을 수 있다 — 에러가 아니라 "오늘은 추천할 만한 정보 있는 공고가
        # 없었다"는 정상 상황이다. 기존 Notion 페이지는 그대로 두고 조용히 종료.
        print(f"[{JOB_CATEGORY_LABELS[category]}] DART 등록 등 정보를 확인할 수 있는 후보가 없어 오늘은 추천을 건너뜁니다.")
        return
    candidates, used = _apply_no_repeat_rotation(candidates, category)

    row = None
    text = None
    for candidate in candidates:
        text = run_job_analysis(candidate)
        if text:
            row = candidate
            break
        print(f"  ↪️ [{candidate['score']}점] {candidate['company']} 분석 불가 — 다음 순위로 시도\n")
    if row is None:
        raise SystemExit("상위 후보 공고 모두 본문을 못 가져오거나 AI 분석에 실패했습니다.")

    used.add(f"{row['source']}:{row['source_id']}")
    _save_top_job_history(category, used)

    token = _notion_token()
    if not token:
        print("⚠️  Notion 토큰(jp_subtitle_notion_token)이 키체인에 없어 Notion 페이지 갱신을 건너뜁니다.")
        print(text)
        return

    # ★ 2026-08-07: 선택된 회사의 경영 분석(company_profile.py)도 같이 만들어서
    # "이 회사는 어떻게 경영해왔는가/누가 운영하는가/업계 위치는" 질문에 답한다.
    company_notion_url = None
    homepage_url = None
    financials: list[dict] = []
    try:
        from company_profile import (
            _dart_api_key, fetch_dart_company_info, fetch_dart_corp_code_map, fetch_dart_financial_summary,
            find_dart_corp_code, search_related_contests, search_related_jobs, fetch_company_news,
            build_company_prompt, build_reference_links_block, _markdown_to_notion_blocks as company_blocks,
            _notion_publish as company_publish, COMPANY_PROFILE_STATE_DIR,
        )
        api_key = _dart_api_key()
        dart_info = None
        corp_code = None
        if api_key:
            corp_map = fetch_dart_corp_code_map(api_key)
            corp_code = find_dart_corp_code(row["company"], corp_map)
            if corp_code:
                dart_info = fetch_dart_company_info(corp_code, api_key)
                financials = fetch_dart_financial_summary(corp_code, api_key)
        if dart_info:
            homepage_url = (dart_info.get("hm_url") or "").strip() or None
            # DART는 미등록 홈페이지를 빈 문자열 대신 "-" 같은 자리표시자로 주기도 한다
            # (실측: 에스컴퍼니, 2026-08-08) — URL처럼 안 생겼으면 버린다.
            if homepage_url and "." not in homepage_url:
                homepage_url = None
            elif homepage_url and not homepage_url.startswith("http"):
                homepage_url = f"https://{homepage_url}"
        jobs_related = search_related_jobs(row["company"])
        contests_related = search_related_contests(row["company"])
        news_related = fetch_company_news(row["company"])
        prompt = build_company_prompt(row["company"], dart_info, financials, jobs_related, contests_related, "", news_related)
        from ai_exec import run_ai_exec
        stdout, _ = run_ai_exec(prompt, BASE_DIR, timeout=300)
        # ★ 2026-08-09: 참고 링크(DART·대안 정보원·뉴스 원문)는 AI 출력과 별개로
        # 코드가 직접 덧붙인다 — company_profile.py의 analyze_company()와 동일.
        company_text = stdout.strip() + "\n\n" + build_reference_links_block(row["company"], corp_code, news_related)
        company_title = f"🏢 {row['company']} 경영 분석"
        safe_name = re.sub(r"[^\w가-힣-]+", "_", row["company"])
        state_path = COMPANY_PROFILE_STATE_DIR / f"{safe_name}.json"
        company_notion_url = company_publish(token, company_title, company_blocks(company_text), state_path)
        print(f"✅ 기업 경영 분석 페이지도 갱신: {company_notion_url}")
    except Exception as exc:  # noqa: BLE001 — 기업 분석 실패해도 공고 분석 발행은 계속 진행
        print(f"⚠️  기업 경영 분석 생성 실패(공고 분석은 계속 진행): {exc}")

    # ★ 2026-08-08: "회사가 지금 만들려는 것" 추론이 가장 궁금하다는 피드백으로
    # 그 항목을 프롬프트 1번으로 올렸고(위 build_analysis_prompt), 회사 홈페이지·
    # DART 재무 요약도 공고 원문 링크와 함께 페이지 맨 위 meta 블록에 바로 넣는다
    # — 예전엔 재무 정보를 보려면 별도 기업 경영 분석 페이지로 이동해야 했다.
    title = f"🎯 [{JOB_CATEGORY_LABELS[category]}] {row['company']} — {row['title']}"
    meta_lines = [f"점수 {row['score']} | {row['source']} | {row['url']}"]
    if homepage_url:
        meta_lines.append(f"회사 홈페이지: {homepage_url}")
    if company_notion_url:
        meta_lines.append(f"기업 경영 분석 상세(병법적 해석 등): {company_notion_url}")
    meta_line = "\n".join(meta_lines)
    blocks = _markdown_to_notion_blocks(meta_line)
    # ★ 2026-08-08: 슬래시로 이어붙인 텍스트 한 줄 대신 표 블록으로(피드백: "성의
    # 없다, table을 쓰면 좋겠다") — 표는 마크다운 파서가 아니라 직접 블록을 만든다.
    table_block = _dart_financial_table_block(financials)
    if table_block:
        blocks.append(table_block)
    blocks += _markdown_to_notion_blocks(text)
    meta = {
        "category": category,
        "company": row["company"], "title": row["title"],
        "score": row["score"], "source": row["source"], "job_url": row["url"],
        "company_notion_url": company_notion_url,
    }
    try:
        url = _notion_publish(token, title, blocks, meta, top_job_state_path(category))
    except RuntimeError as exc:
        print(f"⚠️  Notion 페이지 갱신 실패: {exc}")
        print(text)
        return
    print(f"\n✅ Notion 페이지 갱신 완료: {url}")

    # ★ 2026-08-08: 최상위 "🎴 이직시스템" 페이지에도 오늘의 추천을 접힌 토글로
    # 남겨 과거 기록이 사라지지 않게 한다(사용자 요청 — 카테고리별 하위 페이지는
    # 최신 스냅샷만 유지하므로 이 토글이 유일한 히스토리다).
    try:
        today = datetime.now().date().isoformat()
        prefix = f"[{today}][{category}]"
        _append_history_toggle(token, NOTION_JOBSYSTEM_PAGE_ID, prefix, f"{prefix} {title}", blocks)
    except RuntimeError as exc:
        print(f"⚠️  최상위 페이지 히스토리 토글 추가 실패(본 발행은 정상 완료): {exc}")


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
    at = sub.add_parser(
        "analyze-top", help="적합도 1위 공고를 AI로 분석해 Notion 페이지 갱신(shift_alarm 자동 호출용)"
    )
    at.add_argument(
        "--category", choices=["career", "parttime"], default="career",
        help="career=정규직 커리어 공고, parttime=알바·단기 공고 (2026-08-08 추가)",
    )
    at.set_defaults(func=analyze_top_job)
    return p


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
