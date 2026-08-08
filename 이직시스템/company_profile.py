#!/usr/bin/env python3
"""회사 하나를 지정하면 DART 공시 재무정보 + 이직시스템에 이미 수집된 채용공고·
경진대회 + 회사 홈페이지 소개 텍스트를 모아 AI로 경영 서사 분석을 만들고
Notion에 발행한다(손자병법 해석의 "역사적 실증사례"처럼, 숫자와 근거를 붙여서
이 회사가 걸어온 궤적과 지금 하려는 것을 서술). job_collector.py analyze와
같은 패턴, 2026-08-07 추가.

DART API 키가 필요하다(무료, opendart.fss.or.kr에서 즉시 발급). DART_API_KEY
환경변수로 줘도 되지만, shift_alarm이 launchd로 실행돼 셸 프로필을 못 읽으므로
기본은 키체인 저장(★ 2026-08-08): `security add-generic-password -a $USER
-s dart_api_key -w "<키>"`. 키가 아예 없으면 재무제표 파트만 건너뛰고
홈페이지·채용공고·경진대회 정보만으로 분석한다 — DART는 상장사·일정 규모 이상
비상장사만 공시 대상이라 작은 스타트업은 키가 있어도 재무제표가 아예 없을 수
있다(이 경우도 동일하게 건너뛴다).
"""

from __future__ import annotations

import argparse
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
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_JOBS_DB = BASE_DIR / "data" / "jobs.db"
DEFAULT_CONTESTS_DB = BASE_DIR / "data" / "contests.db"
DART_CORP_CODE_CACHE = BASE_DIR / "data" / "dart_corp_codes.json"
DART_CORP_CODE_CACHE_MAX_AGE_DAYS = 30
USER_AGENT = "DailyHelloWorld-JobCollector/1.0 (personal job search)"

DART_API_BASE = "https://opendart.fss.or.kr/api"
NOTION_VERSION = "2026-03-11"
NOTION_JOBSYSTEM_PAGE_ID = "3b132a1e-ae80-805d-ad0e-d4f2cae02709"
COMPANY_PROFILE_STATE_DIR = BASE_DIR / "data" / "company_profiles"

_ACCOUNT_LABELS = {
    "매출액": "매출액", "영업수익": "매출액",
    "영업이익": "영업이익", "영업손실": "영업이익",
    "당기순이익": "당기순이익", "당기순손실": "당기순이익",
    "자산총계": "자산총계", "부채총계": "부채총계", "자본총계": "자본총계",
}


def plain(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", html.unescape(str(value))).strip()


def _dart_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{DART_API_BASE}/{path}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"DART API {path} HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"DART API {path} 연결 실패: {exc.reason}") from exc


def fetch_dart_corp_code_map(api_key: str) -> dict[str, str]:
    """전체 상장·공시대상 기업의 회사명→corp_code 매핑을 받아 로컬에 캐시한다
    (수만 건짜리 zip 안 XML — 매번 새로 받기엔 크므로 30일 캐시)."""
    if DART_CORP_CODE_CACHE.exists():
        age_days = (time.time() - DART_CORP_CODE_CACHE.stat().st_mtime) / 86400
        if age_days < DART_CORP_CODE_CACHE_MAX_AGE_DAYS:
            try:
                return json.loads(DART_CORP_CODE_CACHE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass

    request = urllib.request.Request(
        f"{DART_API_BASE}/corpCode.xml?{urllib.parse.urlencode({'crtfc_key': api_key})}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"DART corpCode HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"DART corpCode 연결 실패: {exc.reason}") from exc

    with zipfile.ZipFile(BytesIO(body)) as zf:
        xml_bytes = zf.read(zf.namelist()[0])
    root = ET.fromstring(xml_bytes)

    corp_map: dict[str, str] = {}
    for node in root.findall("list"):
        name = plain(node.findtext("corp_name"))
        code = plain(node.findtext("corp_code"))
        if name and code:
            corp_map[name] = code

    DART_CORP_CODE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    DART_CORP_CODE_CACHE.write_text(json.dumps(corp_map, ensure_ascii=False), encoding="utf-8")
    return corp_map


def find_dart_corp_code(company_name: str, corp_map: dict[str, str]) -> str | None:
    """정확히 일치하는 이름을 우선 찾고, 없으면 회사명이 포함된 항목을 느슨하게 찾는다
    (법인 표기 "(주)"/"주식회사" 유무 차이를 흡수하려고 그 부분을 뗀 이름으로도 시도)."""
    if company_name in corp_map:
        return corp_map[company_name]
    stripped = re.sub(r"^\(주\)|주식회사\s*|\(유\)", "", company_name).strip()
    if stripped in corp_map:
        return corp_map[stripped]
    for name, code in corp_map.items():
        if stripped and stripped in name:
            return code
    return None


def fetch_dart_company_info(corp_code: str, api_key: str) -> dict[str, Any] | None:
    data = _dart_get("company.json", {"crtfc_key": api_key, "corp_code": corp_code})
    if data.get("status") != "000":
        return None
    return data


def fetch_dart_financial_summary(corp_code: str, api_key: str) -> list[dict[str, Any]]:
    """최근 3개년 사업보고서(reprt_code=11011, 연결재무제표 우선)에서 주요 계정
    (매출액/영업이익/당기순이익/자산총계 등)만 뽑아 연도별로 반환. 공시가 없으면
    빈 리스트(작은 비상장사는 흔함 — 정상 상황)."""
    current_year = time.localtime().tm_year
    results = []
    for year in range(current_year - 1, current_year - 4, -1):
        for fs_div in ("CFS", "OFS"):  # 연결 우선, 없으면 별도
            try:
                data = _dart_get("fnlttSinglAcntAll.json", {
                    "crtfc_key": api_key, "corp_code": corp_code,
                    "bsns_year": str(year), "reprt_code": "11011", "fs_div": fs_div,
                })
            except RuntimeError:
                continue
            if data.get("status") != "000":
                continue
            accounts = {}
            for item in data.get("list", []):
                label = _ACCOUNT_LABELS.get(plain(item.get("account_nm")))
                if label and label not in accounts:
                    accounts[label] = plain(item.get("thstrm_amount"))
            if accounts:
                results.append({"year": year, "fs_div": fs_div, **accounts})
                break  # 이 연도는 찾았으니 다음 연도로
    return results


def search_related_jobs(company_name: str, db_path: Path = DEFAULT_JOBS_DB, limit: int = 10) -> list[dict]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT source, title, url, deadline, salary FROM jobs WHERE company LIKE ? "
        "ORDER BY first_seen_at DESC LIMIT ?",
        (f"%{company_name}%", limit),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def search_related_contests(company_name: str, db_path: Path = DEFAULT_CONTESTS_DB, limit: int = 10) -> list[dict]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT title, url, deadline FROM contests WHERE organizer LIKE ? "
        "ORDER BY first_seen_at DESC LIMIT ?",
        (f"%{company_name}%", limit),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def fetch_homepage_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
    except (urllib.error.HTTPError, urllib.error.URLError):
        return ""
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", body))
    return re.sub(r"\s+", " ", text).strip()[:6000]


def build_company_prompt(
    company_name: str, dart_info: dict | None, financials: list[dict],
    jobs: list[dict], contests: list[dict], homepage_text: str,
) -> str:
    dart_block = "DART 공시 정보 없음(비상장 또는 공시대상 아닌 소규모 기업일 가능성)"
    if dart_info:
        dart_block = (
            f"대표자: {dart_info.get('ceo_nm', '')} | 설립일: {dart_info.get('est_dt', '')} | "
            f"업종: {dart_info.get('induty_code', '')} | 상장여부: "
            f"{'상장' if dart_info.get('stock_code') else '비상장'} | "
            f"주소: {dart_info.get('adres', '')}"
        )
    financial_block = "\n".join(
        f"- {f['year']}년({'연결' if f['fs_div'] == 'CFS' else '별도'}): "
        + ", ".join(f"{k}={v}" for k, v in f.items() if k not in ("year", "fs_div"))
        for f in financials
    ) or "공시된 재무제표 없음"
    jobs_block = "\n".join(f"- [{j['source']}] {j['title']} (마감 {j['deadline']})" for j in jobs) or "수집된 채용공고 없음"
    contests_block = "\n".join(f"- {c['title']} (마감 {c['deadline']})" for c in contests) or "수집된 공모전 없음"

    return f"""다음은 "{company_name}"에 대해 여러 출처에서 모은 정보다. 손자병법
해석에서 역사적 실증사례를 드는 것처럼, 각 판단마다 아래 정보 중 무엇을
근거로 삼았는지 명시하면서 서술하라. 근거 없는 부분은 "정보 부족 — 추정:"으로
표시하고 지어내지 마라.

--- DART 기업개황 ---
{dart_block}

--- DART 재무제표 요약(최근 공시분) ---
{financial_block}

--- 이직시스템에 수집된 이 회사 채용공고 ---
{jobs_block}

--- 이직시스템에 수집된 이 회사 관련 공모전/경진대회 ---
{contests_block}

--- 회사 홈페이지/소개 페이지 원문(잡음 포함 가능) ---
{homepage_text or "(제공된 홈페이지 텍스트 없음)"}
--- 끝 ---

한국어로 아래 여섯 항목에 답하라:
1. **기업 개황**: 설립·업종·상장여부·규모 등 확인 가능한 사실 요약.
2. **재무 상태 해석**: 재무제표가 있으면 매출/이익 추이가 뭘 시사하는지 해석.
   없으면 "DART 미등록 — 공시 재무정보 없음"이라고 명시하고 다른 근거(채용
   규모·공고 빈도 등)로 회사 규모를 추정.
3. **채용·공모전 이력에서 보이는 경영 방향**: 어떤 직무를 왜 뽑으려 하는지,
   공모전을 왜 여는지에서 회사가 지금 무엇에 투자하고 있는지 추론.
4. **종합 서사**: 이 회사가 걸어온 궤적과 지금 하려는 것을 하나의 이야기로
   엮어라 — 개별 사실을 나열하지 말고 왜 그 순서로 일어났는지 연결하라.
5. **병법적 해석**: 지금까지 정리한 사실(채용 시점·규모, 공모전 개최 목적,
   재무 추이, 홈페이지에서 드러나는 태도 등)을 손자병법의 개념으로 다시 읽어라.
   예: 유리한 조건을 만든 뒤 움직였는가(선승이후구전, 形/勢), 정보를 안 드러내며
   움직였는가(궤도), 무리한 확장 대신 때를 기다렸는가(진퇴), 경쟁자·시장 상황
   대비 자원을 어디에 집중했는가(허실). **막연한 손자병법 인용이 아니라, 위에서
   근거로 든 구체적 사실 하나하나를 손자병법 개념과 짝지어 설명하라** — 근거가
   부족하면 "이 부분은 병법적으로 해석할 근거가 부족하다"고 명시하고 넘어가라.
6. **관점별 시사점**: 구직자·협업 파트너·(관심 있다면) 투자자 각각에게 이
   회사가 어떤 의미인지 짧게."""


def _notion_token() -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-a", os.environ.get("USER", ""),
         "-s", "jp_subtitle_notion_token", "-w"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _dart_api_key() -> str:
    """DART_API_KEY 환경변수가 있으면 우선 쓰고, 없으면 키체인(dart_api_key)에서
    읽는다(★ 2026-08-08 — shift_alarm이 launchd로 실행돼 셸 프로필의 환경변수를
    못 보므로, jp_subtitle_notion_token과 같은 키체인 패턴으로 저장해뒀다)."""
    env_key = os.environ.get("DART_API_KEY", "").strip()
    if env_key:
        return env_key
    result = subprocess.run(
        ["security", "find-generic-password", "-a", os.environ.get("USER", ""),
         "-s", "dart_api_key", "-w"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _markdown_to_notion_blocks(text: str) -> list[dict[str, Any]]:
    """job_collector.py/contest_collector.py의 동명 함수와 동일(볼드·URL 링크 지원)."""
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


def _notion_publish(token: str, title: str, blocks: list[dict[str, Any]], state_path: Path) -> str:
    """회사별로 별도 상태 파일(company_profiles/<회사명>.json)에 page_id를 저장해서,
    같은 회사를 다시 분석하면 새 페이지 대신 기존 페이지를 갱신한다."""
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
    state_path.write_text(json.dumps({"page_id": page_id, "url": url}, ensure_ascii=False, indent=2), encoding="utf-8")
    return url


def analyze_company(args: argparse.Namespace) -> None:
    company_name = args.company_name
    print(f"'{company_name}' 분석 시작")

    dart_info = None
    financials: list[dict] = []
    api_key = _dart_api_key()
    if api_key:
        try:
            corp_map = fetch_dart_corp_code_map(api_key)
            corp_code = find_dart_corp_code(company_name, corp_map)
            if corp_code:
                print(f"  DART corp_code 발견: {corp_code}")
                dart_info = fetch_dart_company_info(corp_code, api_key)
                financials = fetch_dart_financial_summary(corp_code, api_key)
                print(f"  재무제표 {len(financials)}개년 확보")
            else:
                print("  DART에 등록된 회사명을 못 찾음(비상장 소규모 기업일 가능성)")
        except RuntimeError as exc:
            print(f"  ⚠️ DART 조회 실패: {exc}")
    else:
        print("  ⚠️ DART_API_KEY 없음(환경변수/키체인 모두) — 재무제표 없이 진행(opendart.fss.or.kr에서 무료 발급)")

    jobs = search_related_jobs(company_name)
    contests = search_related_contests(company_name)
    print(f"  관련 채용공고 {len(jobs)}건, 관련 공모전 {len(contests)}건")

    homepage_text = fetch_homepage_text(args.url) if args.url else ""
    if args.url:
        print(f"  홈페이지 텍스트 {len(homepage_text)}자 수집")

    prompt = build_company_prompt(company_name, dart_info, financials, jobs, contests, homepage_text)
    print("\nAI로 분석 중... (codex 실패 시 claude로 자동 전환)\n")
    from ai_exec import run_ai_exec
    try:
        stdout, engine = run_ai_exec(prompt, BASE_DIR, timeout=300)
    except RuntimeError as exc:
        raise SystemExit(f"AI 분석 실패: {exc}")
    text = stdout.strip()

    token = _notion_token()
    if not token:
        print("⚠️  Notion 토큰이 키체인에 없어 Notion 페이지 갱신을 건너뜁니다.")
        print(text)
        return

    title = f"🏢 {company_name} 경영 분석"
    blocks = _markdown_to_notion_blocks(text)
    safe_name = re.sub(r"[^\w가-힣-]+", "_", company_name)
    state_path = COMPANY_PROFILE_STATE_DIR / f"{safe_name}.json"
    try:
        url = _notion_publish(token, title, blocks, state_path)
    except RuntimeError as exc:
        print(f"⚠️  Notion 페이지 갱신 실패: {exc}")
        print(text)
        return
    print(f"\n✅ Notion 페이지 갱신 완료: {url}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="회사 하나를 DART·채용공고·홈페이지 정보로 분석")
    sub = p.add_subparsers(dest="command", required=True)
    an = sub.add_parser("analyze", help="회사 하나를 분석해 Notion에 발행")
    an.add_argument("company_name", help="정확한 법인명이 정확도가 높다(예: \"(주)엔컬처\")")
    an.add_argument("--url", help="회사 홈페이지/소개 페이지 URL(선택, 있으면 서사 분석 품질이 좋아짐)")
    an.set_defaults(func=analyze_company)
    return p


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
