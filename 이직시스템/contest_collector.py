#!/usr/bin/env python3
"""링커리어(linkareer.com) 공모전·경진대회 수집기.

job_collector.py와 같은 패턴(robots.txt 허용 범위 크롤링, 표준 라이브러리만
사용, AI 분석은 ai_exec.py 재사용, Notion 발행은 "🎴 이직시스템" 페이지 재사용)을
공모전/경진대회 도메인에 맞춰 적용했다. 2026-08-07: 링커리어부터 먼저 제대로
만들고, 데이콘(순수 클라이언트 렌더링이라 curl로 데이터가 안 잡힘 — API 엔드포인트
발견 필요)/aichallenge4all/콘테스트코리아/위비티/씽굿/해외 플랫폼은 순차 추가 예정.
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
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config.json"
DEFAULT_DB = BASE_DIR / "data" / "contests.db"
USER_AGENT = "DailyHelloWorld-JobCollector/1.0 (personal job search)"

# 링커리어 공모전 목록(robots.txt User-agent:* Allow:/). ?keyword=는 SSR에
# 반영이 안 돼(서버가 항상 "최신 20건"만 내려줌) 검색 필터링은 못 쓰고,
# 대신 여러 페이지를 모아 job_collector.py와 같은 키워드 점수로 로컬 필터링한다.
LINKAREER_LIST_URL = "https://linkareer.com/list/contest"
LINKAREER_MAX_PAGES = 5
LINKAREER_DELAY_SECONDS = 1.5
LINKAREER_SOURCE = "링커리어"

# 전국민 AI 경진대회(aichallenge4all.or.kr, 정부 주관) — robots.txt Allow:/.
# 목록 페이지(/competitions/all)는 Next.js App Router라 __NEXT_DATA__가 아니라
# React Server Component 스트리밍 페이로드로 데이터가 오는데(파싱하기 까다로움),
# 브라우저가 실제로 호출하는 REST API를 찾아서 그걸 바로 쓴다(2026-08-08 확인).
AICHALLENGE4ALL_API_URL = "https://aichallenge4all.or.kr/api/competitions"
AICHALLENGE4ALL_SOURCE = "AI경진대회(정부)"
AICHALLENGE4ALL_CLOSED_STATUS = "closed"

# 콘테스트코리아(contestkorea.com) — robots.txt Allow:/. 옛날 방식 PHP 게시판
# 사이트라 JSON/JS 없이 순수 서버 렌더링 HTML이라 정규식으로 바로 파싱 가능
# (사람인 크롤러와 같은 블록 분리 패턴). "학문・과학・IT" 카테고리(Txt_bcode=
# 030310001)만 우선 수집 — 다른 카테고리 bcode는 필요해지면 추가.
CONTESTKOREA_LIST_URL = "https://www.contestkorea.com/sub/list.php"
CONTESTKOREA_CATEGORY_BCODE = "030310001"
CONTESTKOREA_CATEGORY_NAME = "학문・과학・IT"
CONTESTKOREA_MAX_PAGES = 5
CONTESTKOREA_DELAY_SECONDS = 1.5
CONTESTKOREA_SOURCE = "콘테스트코리아"

NOTION_VERSION = "2026-03-11"
# "🎴 이직시스템" 페이지 — job_collector.py의 분석 페이지와 같은 부모 밑에 만든다.
NOTION_JOBSYSTEM_PAGE_ID = "3b132a1e-ae80-805d-ad0e-d4f2cae02709"
# ★ 2026-08-08: job_collector.py와 같은 이유로(AI 특화 경진대회 vs 일반 공모전은
# 성격이 달라 하나로 뭉치면 한쪽이 묻힌다) 카테고리별로 분리했다.
CONTEST_SOURCE_CATEGORY = {
    AICHALLENGE4ALL_SOURCE: "ai",
    LINKAREER_SOURCE: "general",
    CONTESTKOREA_SOURCE: "general",
}
CONTEST_CATEGORY_LABELS = {"ai": "AI 경진대회", "general": "일반 공모전"}


def top_contest_state_path(category: str) -> Path:
    return BASE_DIR / "data" / f"top_contest_notion_{category}.json"


def top_contest_history_path(category: str) -> Path:
    return BASE_DIR / "data" / f"top_contest_history_{category}.json"

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


@dataclass
class Contest:
    source_id: str
    title: str
    organizer: str
    url: str
    source: str = LINKAREER_SOURCE
    deadline: str = ""
    score: int = 0
    matched_query: str = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def plain(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", html.unescape(str(value))).strip()


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"설정 파일이 없습니다: {path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def score_text(text: str, config: dict[str, Any]) -> int:
    """job_collector.py의 score_job()과 같은 방식 — config.json의 include/exclude_keywords를
    그대로 재사용한다(AI/데이터/Python 등 이미 기술 중심이라 공모전 관련성 판단에도 맞는다)."""
    haystack = text.casefold()
    includes = sum(1 for word in config.get("include_keywords", []) if word.casefold() in haystack)
    excludes = sum(1 for word in config.get("exclude_keywords", []) if word.casefold() in haystack)
    return max(0, min(100, 40 + includes * 10 - excludes * 25))


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contests (
            id INTEGER PRIMARY KEY,
            source TEXT NOT NULL,
            source_id TEXT NOT NULL,
            title TEXT NOT NULL,
            organizer TEXT,
            url TEXT NOT NULL,
            deadline TEXT,
            score INTEGER NOT NULL DEFAULT 0,
            matched_query TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            UNIQUE(source, source_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contests_score ON contests(score DESC)")
    conn.commit()
    return conn


def fetch_linkareer_page(page: int, config: dict[str, Any]) -> list[Contest]:
    """공모전 목록 페이지 1장을 가져와 파싱. Next.js SSR의 __NEXT_DATA__ 안
    activityItems(제목/URL) + __APOLLO_STATE__(Activity:{id} 정규화 캐시 — 주최·
    마감일 등 상세 필드)를 조합해서 읽는다(job_collector.py의 알바몬 크롤러와
    같은 패턴, HTML 마크업 파싱 불필요)."""
    params = {"page": page}
    request = urllib.request.Request(
        f"{LINKAREER_LIST_URL}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"링커리어 목록 페이지 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"링커리어 목록 페이지 연결 실패: {exc.reason}") from exc

    match = _NEXT_DATA_RE.search(body)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    page_props = data.get("props", {}).get("pageProps", {})
    items = page_props.get("activityItems", [])
    apollo = page_props.get("__APOLLO_STATE__", {})

    contests = []
    for item in items:
        url = plain(item.get("url"))
        source_id = url.rstrip("/").split("/")[-1]
        if not source_id:
            continue
        activity = apollo.get(f"Activity:{source_id}", {})
        title = plain(item.get("name"))
        organizer = plain(activity.get("organizationName"))
        deadline_ms = activity.get("recruitCloseAt")
        deadline = (
            datetime.fromtimestamp(deadline_ms / 1000, tz=timezone.utc).astimezone().date().isoformat()
            if deadline_ms else ""
        )
        combined = " ".join((title, organizer))
        contests.append(Contest(
            source_id=source_id, title=title, organizer=organizer, url=url,
            deadline=deadline, score=score_text(combined, config),
        ))
    return contests


def fetch_linkareer_all(config: dict[str, Any], max_pages: int = LINKAREER_MAX_PAGES) -> list[Contest]:
    contests: list[Contest] = []
    for page in range(1, max_pages + 1):
        page_items = fetch_linkareer_page(page, config)
        if not page_items:
            break
        contests.extend(page_items)
        if page < max_pages:
            time.sleep(LINKAREER_DELAY_SECONDS)
    return contests


def fetch_aichallenge4all(config: dict[str, Any]) -> list[Contest]:
    """전국민 AI 경진대회 API에서 전체 대회 목록(실측 33건, 페이지네이션 없음)을
    받아 종료(closed)된 것만 걸러내고 나머지는 로컬 키워드 점수로 평가한다."""
    request = urllib.request.Request(
        AICHALLENGE4ALL_API_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"AI경진대회 API HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AI경진대회 API 연결 실패: {exc.reason}") from exc

    contests = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if item.get("badgeStatus") == AICHALLENGE4ALL_CLOSED_STATUS:
            continue
        title = plain(item.get("name"))
        source_id = plain(item.get("id") or item.get("slug"))
        if not title or not source_id:
            continue
        slug = plain(item.get("slug"))
        url = (
            plain(item.get("detailUrl")) or plain(item.get("externalUrl"))
            or (f"https://aichallenge4all.or.kr/competitions/{slug}" if slug else "")
        )
        combined = " ".join((title, plain(item.get("description"))))
        # applyPeriod는 "<br/>"이 섞인 HTML 조각을 그대로 담고 있는 필드라(실측
        # 확인) plain()만으로는 안 지워진다 — 태그를 걷어내고 여러 시즌 정보를
        # 줄바꿈 대신 " / "로 이어붙인다.
        deadline_raw = str(item.get("applyPeriod") or "")
        deadline = plain(re.sub(r"<br\s*/?>", " / ", deadline_raw))
        contests.append(Contest(
            source_id=source_id, title=title, organizer="전국민 AI 경진대회(정부 주관)",
            url=url, source=AICHALLENGE4ALL_SOURCE,
            deadline=deadline,
            score=score_text(combined, config),
        ))
    return contests


_CK_ITEM_SPLIT_RE = re.compile(
    r'(?=<li(?:\s+class="[^"]*")?>\s*(?:<!--.*?-->)?\s*<div class="title">)', re.S
)
_CK_HREF_RE = re.compile(r'<a href="(view\.php\?[^"]+)">')
_CK_TITLE_RE = re.compile(r'<span class="txt">([^<]+)</span>')
_CK_HOST_RE = re.compile(r'<strong>주최</strong>\s*\.\s*([^<]+)</li>')
_CK_DEADLINE_RE = re.compile(r'<em>접수</em>\s*([^<]*)')
_CK_STRNO_RE = re.compile(r"str_no=(\d+)")


def parse_contestkorea_block(block: str, config: dict[str, Any]) -> Contest | None:
    href_match = _CK_HREF_RE.search(block)
    title_match = _CK_TITLE_RE.search(block)
    if not href_match or not title_match:
        return None
    strno_match = _CK_STRNO_RE.search(href_match.group(1))
    if not strno_match:
        return None
    title = plain(title_match.group(1))
    host_match = _CK_HOST_RE.search(block)
    organizer = plain(host_match.group(1)) if host_match else ""
    deadline_match = _CK_DEADLINE_RE.search(block)
    deadline = plain(deadline_match.group(1)) if deadline_match else ""
    combined = " ".join((title, organizer))
    return Contest(
        source_id=strno_match.group(1), title=title, organizer=organizer,
        url=f"https://www.contestkorea.com/sub/{href_match.group(1)}",
        source=CONTESTKOREA_SOURCE, deadline=deadline,
        score=score_text(combined, config),
    )


def fetch_contestkorea_page(
    page: int, config: dict[str, Any], bcode: str = CONTESTKOREA_CATEGORY_BCODE
) -> list[Contest]:
    """옛날 방식 PHP 게시판이라 JSON 없이 순수 HTML을 정규식으로 파싱한다
    (사람인 크롤러와 같은 블록 분리 패턴) — `<li class="...">... <div
    class="title">` 시작 지점 기준으로 항목을 자른다."""
    params = {"int_gbn": 1, "Txt_bcode": bcode, "page": page}
    request = urllib.request.Request(
        f"{CONTESTKOREA_LIST_URL}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"콘테스트코리아 목록 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"콘테스트코리아 목록 연결 실패: {exc.reason}") from exc

    idx = body.find("list_style_2")
    if idx == -1:
        return []
    section = body[idx:idx + 80000]
    blocks = _CK_ITEM_SPLIT_RE.split(section)
    contests = []
    for block in blocks[1:]:
        contest = parse_contestkorea_block(block, config)
        if contest:
            contests.append(contest)
    return contests


def fetch_contestkorea_all(config: dict[str, Any], max_pages: int = CONTESTKOREA_MAX_PAGES) -> list[Contest]:
    contests: list[Contest] = []
    for page in range(1, max_pages + 1):
        page_items = fetch_contestkorea_page(page, config)
        if not page_items:
            break
        contests.extend(page_items)
        if page < max_pages:
            time.sleep(CONTESTKOREA_DELAY_SECONDS)
    return contests


def fingerprint(contest: Contest) -> str:
    body = "\x1f".join((contest.title, contest.organizer, contest.deadline))
    return hashlib.sha256(body.encode()).hexdigest()


def upsert_contests(conn: sqlite3.Connection, contests: Iterable[Contest]) -> tuple[int, int]:
    inserted = updated = 0
    stamp = now_iso()
    for contest in contests:
        exists = conn.execute(
            "SELECT id FROM contests WHERE source = ? AND source_id = ?",
            (contest.source, contest.source_id),
        ).fetchone()
        values = asdict(contest)
        fp = fingerprint(contest)
        if exists:
            conn.execute("""
                UPDATE contests SET title=:title, organizer=:organizer, url=:url,
                    deadline=:deadline, score=:score, matched_query=:matched_query,
                    last_seen_at=:stamp, fingerprint=:fingerprint
                WHERE id=:id
            """, {**values, "stamp": stamp, "fingerprint": fp, "id": exists["id"]})
            updated += 1
        else:
            conn.execute("""
                INSERT INTO contests (source, source_id, title, organizer, url,
                    deadline, score, matched_query, first_seen_at, last_seen_at, fingerprint)
                VALUES (:source, :source_id, :title, :organizer, :url,
                    :deadline, :score, :matched_query, :stamp, :stamp, :fingerprint)
            """, {**values, "stamp": stamp, "fingerprint": fp})
            inserted += 1
    conn.commit()
    return inserted, updated


def collect(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    conn = connect(args.db)
    print(f"링커리어 공모전 목록 수집 중(최대 {LINKAREER_MAX_PAGES}페이지)...")
    contests = list(fetch_linkareer_all(config))
    print(f"  {len(contests)}건 수신")

    print("전국민 AI 경진대회 목록 수집 중...")
    try:
        ai_contests = fetch_aichallenge4all(config)
        print(f"  {len(ai_contests)}건 수신")
        contests.extend(ai_contests)
    except RuntimeError as exc:
        print(f"  ⚠️ 전국민 AI 경진대회 수집 실패: {exc}")

    print(f"콘테스트코리아({CONTESTKOREA_CATEGORY_NAME}) 목록 수집 중(최대 {CONTESTKOREA_MAX_PAGES}페이지)...")
    try:
        ck_contests = fetch_contestkorea_all(config)
        print(f"  {len(ck_contests)}건 수신")
        contests.extend(ck_contests)
    except RuntimeError as exc:
        print(f"  ⚠️ 콘테스트코리아 수집 실패: {exc}")

    inserted, updated = upsert_contests(conn, contests)
    print(f"\n완료: 신규 {inserted}건 / 기존 갱신 {updated}건")


def list_contests(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    rows = conn.execute("""
        SELECT source, score, organizer, title, deadline, url
        FROM contests ORDER BY score DESC, deadline ASC LIMIT ?
    """, (args.limit,)).fetchall()
    if not rows:
        print("저장된 공모전이 없습니다. collect를 먼저 실행하세요.")
        return
    for row in rows:
        print(f"[{row['score']:>3}] ({row['source']}) {row['organizer']} | {row['title']}")
        print(f"      마감 {row['deadline']} | {row['url']}")


_CONTENT_MARKERS = ("접수기간", "참여대상", "시상", "공모분야", "지원자격", "응모자격", "모집분야")


def fetch_contest_detail_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"공모전 상세 페이지 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"공모전 상세 페이지 연결 실패: {exc.reason}") from exc
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", body))
    return re.sub(r"\s+", " ", text).strip()[:8000]


def _content_available(detail_text: str) -> bool:
    return len(detail_text) >= 300 and any(marker in detail_text for marker in _CONTENT_MARKERS)


def build_contest_prompt(row: sqlite3.Row, detail_text: str) -> str:
    return f"""다음은 공모전/경진대회 상세 페이지에서 그대로 긁어온 텍스트다(내비게이션·
광고 같은 잡음이 섞여 있을 수 있으니 실제 공모전 안내(참여대상/공모분야/평가기준/
접수기간 등)만 골라 판단하라).

주최: {row['organizer']}
공모전명: {row['title']}

--- 원문(잡음 포함 가능) ---
{detail_text}
--- 끝 ---

한국어로 아래 네 항목에 답하라:
1. **참여자격/공모분야/평가기준 요약**: 실제 응모 요건과 어떤 능력을 보려는
   대회인지 간단히 정리.
2. **이 대회가 검증하려는 역량 추론**: 공모 취지·평가기준·주최 기관의 성격을
   조합해서 이 대회가 실제로 어떤 역량/결과물을 원하는지 구체적으로 추론하라.
   막연한 일반론이 아니라 왜 그렇게 판단했는지 근거를 짚어라.
3. **참가 시 접근 전략**: 참가한다면 어떤 주제·구현 방향으로 접근하는 게
   좋을지, 짧게 준비할 수 있는 범위에서 구체적으로 제안하라.
4. **1인 사업자 관점 상품화**: 이 문제를 개인 사업 아이템으로 그대로 상품화
   한다면 어떤 형태(서비스/도구/컨설팅 등)가 될지, 목표 고객과 함께 항목화하라
   (모르는 부분은 "정보 부족 — 추정:"으로 표시하고 근거 있는 추정만 적을 것)."""


def run_contest_analysis(row: sqlite3.Row) -> str | None:
    print(f"[{row['source']}] {row['organizer']} — {row['title']}")
    print(f"공모전 페이지 가져오는 중: {row['url']}")
    detail_text = fetch_contest_detail_text(row["url"])
    if not _content_available(detail_text):
        print(
            f"\n⚠️  공모전 본문을 못 가져온 것으로 보입니다(추출 {len(detail_text)}자). "
            "해당 URL을 직접 열어 확인해 주세요.\n"
        )
        return None
    prompt = build_contest_prompt(row, detail_text)
    print("\nAI로 분석 중... (codex 실패 시 claude로 자동 전환)\n")
    from ai_exec import run_ai_exec
    try:
        stdout, engine = run_ai_exec(prompt, BASE_DIR, timeout=300)
    except RuntimeError as exc:
        print(f"⚠️  AI 분석 실패: {exc}")
        return None
    return stdout.strip()


def _notion_token() -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-a", os.environ.get("USER", ""),
         "-s", "jp_subtitle_notion_token", "-w"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _markdown_to_notion_blocks(text: str) -> list[dict[str, Any]]:
    """job_collector.py의 동명 함수와 동일(볼드·URL 하이퍼링크 지원)."""
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
                segments.append({"type": "text", "text": {"content": url[:1900], "link": {"url": url}}})
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
    """job_collector.py의 동명 함수와 동일한 "페이지 하나만 갱신" 방식.
    ★ 2026-08-08: state_path를 인자로 받아 카테고리(ai/general)별로 서로 다른
    상태 파일(=서로 다른 Notion 페이지)을 쓸 수 있게 함."""
    if state_path is None:
        state_path = top_contest_state_path("general")  # 하위호환 기본값
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
        # ★ 2026-08-08 버그 수정: job_collector.py와 동일 — page_size=100 한 페이지만
        # 지우면 블록 100개 넘는 긴 분석은 이전 내용이 안 지워지고 계속 쌓인다.
        # 삭제하며 커서가 밀리는 걸 피하려고 매번 "첫 페이지"를 새로 조회해 지운다.
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
    """job_collector.py의 동명 함수와 동일 — "🎴 이직시스템" 최상위 페이지에
    오늘의 추천 경진대회를 접힌 토글로 누적한다(★ 2026-08-08 사용자 요청).
    카테고리별 하위 페이지는 계속 "하나만 매일 갱신"으로 최신 스냅샷만 유지하고,
    이 토글이 과거 기록을 남기는 유일한 곳이다. 같은 날 재실행하면 새 토글을
    만들지 않고 기존 토글 내용만 교체한다."""
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


def _load_top_contest_history(category: str) -> set[str]:
    path = top_contest_history_path(category)
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("used", []))
    except json.JSONDecodeError:
        return set()


def _save_top_contest_history(category: str, used: set[str]) -> None:
    path = top_contest_history_path(category)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"used": sorted(used)}, ensure_ascii=False, indent=2), encoding="utf-8")


def _apply_no_repeat_rotation(candidates: list[sqlite3.Row], category: str) -> tuple[list[sqlite3.Row], set[str]]:
    """job_collector.py의 동명 함수와 같은 이유·같은 패턴(2026-08-08) — 매일
    같은 1위 공모전만 추천되는 걸 막기 위해 이미 추천한 건 풀 소진까지 제외."""
    used = _load_top_contest_history(category)
    pool_ids = {f"{c['source']}:{c['source_id']}" for c in candidates}
    used &= pool_ids
    unused = [c for c in candidates if f"{c['source']}:{c['source_id']}" not in used]
    if not unused:
        used = set()
        unused = candidates
    return unused, used


def analyze_top_contest(args: argparse.Namespace) -> None:
    """현재 적합도 1위 공모전을 골라 AI 분석 후 Notion 페이지 하나에 갱신한다
    (shift_alarm이 매일 자동 호출, job_collector.py의 analyze_top_job()과 대응).
    ★ 2026-08-08: AI 특화(ai)/일반(general) 카테고리별로 독립 페이지·로테이션."""
    category = args.category
    conn = connect(args.db)
    sources = [s for s, cat in CONTEST_SOURCE_CATEGORY.items() if cat == category]
    placeholders = ",".join("?" for _ in sources)
    candidates = conn.execute(
        f"SELECT * FROM contests WHERE source IN ({placeholders}) "
        "ORDER BY score DESC, deadline ASC LIMIT 20",
        sources,
    ).fetchall()
    if not candidates:
        raise SystemExit(f"[{CONTEST_CATEGORY_LABELS[category]}] 저장된 공모전이 없습니다. collect를 먼저 실행하세요.")
    candidates, used = _apply_no_repeat_rotation(candidates, category)

    row = None
    text = None
    for candidate in candidates:
        text = run_contest_analysis(candidate)
        if text:
            row = candidate
            break
        print(f"  ↪️ [{candidate['score']}점] {candidate['organizer']} 분석 불가 — 다음 순위로 시도\n")
    if row is None:
        raise SystemExit("상위 후보 공모전 모두 본문을 못 가져오거나 AI 분석에 실패했습니다.")

    used.add(f"{row['source']}:{row['source_id']}")
    _save_top_contest_history(category, used)

    token = _notion_token()
    if not token:
        print("⚠️  Notion 토큰이 키체인에 없어 Notion 페이지 갱신을 건너뜁니다.")
        print(text)
        return

    title = f"🏆 [{CONTEST_CATEGORY_LABELS[category]}] {row['organizer']} — {row['title']}"
    meta_line = f"점수 {row['score']} | {row['source']} | 마감 {row['deadline']} | {row['url']}"
    blocks = _markdown_to_notion_blocks(meta_line) + _markdown_to_notion_blocks(text)
    meta = {
        "category": category,
        "organizer": row["organizer"], "title": row["title"],
        "score": row["score"], "source": row["source"],
        "deadline": row["deadline"], "contest_url": row["url"],
    }
    try:
        url = _notion_publish(token, title, blocks, meta, top_contest_state_path(category))
    except RuntimeError as exc:
        print(f"⚠️  Notion 페이지 갱신 실패: {exc}")
        print(text)
        return
    print(f"\n✅ Notion 페이지 갱신 완료: {url}")

    # ★ 2026-08-08: 최상위 "🎴 이직시스템" 페이지에도 접힌 토글로 남긴다(job_collector.py와 동일).
    try:
        today = datetime.now().date().isoformat()
        prefix = f"[{today}][{category}]"
        _append_history_toggle(token, NOTION_JOBSYSTEM_PAGE_ID, prefix, f"{prefix} {title}", blocks)
    except RuntimeError as exc:
        print(f"⚠️  최상위 페이지 히스토리 토글 추가 실패(본 발행은 정상 완료): {exc}")


def doctor(args: argparse.Namespace) -> None:
    print(f"Python: {sys.version.split()[0]}")
    print(f"설정: {args.config} ({'있음' if args.config.exists() else '없음'})")
    print(f"DB: {args.db} ({'있음' if args.db.exists() else '아직 없음'})")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="링커리어 공모전·경진대회 수집기")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("collect", help="공모전 수집·갱신").set_defaults(func=collect)
    ls = sub.add_parser("list", help="적합도 순으로 보기")
    ls.add_argument("--limit", type=int, default=20)
    ls.set_defaults(func=list_contests)
    at = sub.add_parser(
        "analyze-top", help="적합도 1위 공모전을 AI로 분석해 Notion 페이지 갱신(shift_alarm 자동 호출용)"
    )
    at.add_argument(
        "--category", choices=["ai", "general"], default="general",
        help="ai=AI 특화 경진대회, general=일반 공모전 (2026-08-08 추가)",
    )
    at.set_defaults(func=analyze_top_contest)
    sub.add_parser("doctor", help="실행 환경 점검").set_defaults(func=doctor)
    return p


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
