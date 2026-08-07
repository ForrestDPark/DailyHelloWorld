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

NOTION_VERSION = "2026-03-11"
# "🎴 이직시스템" 페이지 — job_collector.py의 분석 페이지와 같은 부모 밑에 만든다.
NOTION_JOBSYSTEM_PAGE_ID = "3b132a1e-ae80-805d-ad0e-d4f2cae02709"
TOP_CONTEST_STATE_PATH = BASE_DIR / "data" / "top_contest_notion.json"

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
    contests = fetch_linkareer_all(config)
    print(f"  {len(contests)}건 수신")
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


def _notion_publish(token: str, title: str, blocks: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    """job_collector.py의 동명 함수와 동일한 "페이지 하나만 갱신" 방식."""
    state = {}
    if TOP_CONTEST_STATE_PATH.exists():
        try:
            state = json.loads(TOP_CONTEST_STATE_PATH.read_text(encoding="utf-8"))
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
    TOP_CONTEST_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOP_CONTEST_STATE_PATH.write_text(
        json.dumps({"page_id": page_id, "url": url, **meta}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return url


def analyze_top_contest(args: argparse.Namespace) -> None:
    """현재 적합도 1위 공모전을 골라 AI 분석 후 Notion 페이지 하나에 갱신한다
    (shift_alarm이 매일 자동 호출, job_collector.py의 analyze_top_job()과 대응)."""
    conn = connect(args.db)
    candidates = conn.execute(
        "SELECT * FROM contests ORDER BY score DESC, deadline ASC LIMIT 5"
    ).fetchall()
    if not candidates:
        raise SystemExit("저장된 공모전이 없습니다. collect를 먼저 실행하세요.")

    row = None
    text = None
    for candidate in candidates:
        text = run_contest_analysis(candidate)
        if text:
            row = candidate
            break
        print(f"  ↪️ [{candidate['score']}점] {candidate['organizer']} 분석 불가 — 다음 순위로 시도\n")
    if row is None:
        raise SystemExit("상위 5개 공모전 모두 본문을 못 가져오거나 AI 분석에 실패했습니다.")

    token = _notion_token()
    if not token:
        print("⚠️  Notion 토큰이 키체인에 없어 Notion 페이지 갱신을 건너뜁니다.")
        print(text)
        return

    title = f"🏆 {row['organizer']} — {row['title']}"
    meta_line = f"점수 {row['score']} | {row['source']} | 마감 {row['deadline']} | {row['url']}"
    blocks = _markdown_to_notion_blocks(meta_line) + _markdown_to_notion_blocks(text)
    meta = {
        "organizer": row["organizer"], "title": row["title"],
        "score": row["score"], "source": row["source"],
        "deadline": row["deadline"], "contest_url": row["url"],
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
    sub.add_parser(
        "analyze-top", help="적합도 1위 공모전을 AI로 분석해 Notion 페이지 갱신(shift_alarm 자동 호출용)"
    ).set_defaults(func=analyze_top_contest)
    sub.add_parser("doctor", help="실행 환경 점검").set_defaults(func=doctor)
    return p


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
