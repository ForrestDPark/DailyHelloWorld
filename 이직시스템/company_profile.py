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
    # ★ 2026-08-09: 세무·회계·노무 관점 분석용 — DART 요약재무제표에 급여/복리
    # 후생비가 별도 계정으로 잡혀 있으면 인건비 비중을 볼 수 있다(작은 비상장사는
    # 보통 미공시라 없는 게 정상 — 이 경우 그냥 항목이 빠진다).
    "급여": "급여", "복리후생비": "복리후생비",
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


# ★ 2026-08-09 추가: DART가 돌려주는 induty_code는 표준산업분류(KSIC) 코드인데
# 업종명 없이 숫자만 와서("23222") 그동안 "코드만 제공됐고 업종명이 확인되지
# 않았다"고 얼버무렸다(사용자 피드백: "정보가 없으면 네가 찾아서 매칭해줘야지").
# 세세분류(5자리) 전체 표는 수천 개라 통째로 정확히 재현할 자신이 없어 여기
# 넣지 않았고, 대신 신뢰도 높은 중분류(앞 2자리, KSIC 10차 기준 총 76개
# 대분류 밑 분류) 표만 넣는다 — "정밀한 세부 업종"이 아니라 "큰 업종
# 카테고리"만 알려주는 것으로, 없는 것보다는 훨씬 유용하지만 5자리 전체의
# 정확한 세세분류명이 필요하면 KSIC_LOOKUP_URL에서 직접 확인해야 한다.
KSIC_LOOKUP_URL = "https://kssc.kostat.go.kr/ksscNew_web/link.do?gubun=001"
_KSIC_DIVISION_NAMES = {
    "01": "농업", "02": "임업", "03": "어업",
    "05": "석탄, 원유 및 천연가스 광업", "06": "금속 광업", "07": "비금속광물 광업(연료용 제외)", "08": "광업 지원 서비스업",
    "10": "식료품 제조업", "11": "음료 제조업", "12": "담배 제조업",
    "13": "섬유제품 제조업(의복 제외)", "14": "의복, 의복액세서리 및 모피제품 제조업",
    "15": "가죽, 가방 및 신발 제조업", "16": "목재 및 나무제품 제조업(가구 제외)",
    "17": "펄프, 종이 및 종이제품 제조업", "18": "인쇄 및 기록매체 복제업",
    "19": "코크스, 연탄 및 석유정제품 제조업", "20": "화학물질 및 화학제품 제조업(의약품 제외)",
    "21": "의료용 물질 및 의약품 제조업", "22": "고무제품 및 플라스틱제품 제조업",
    "23": "비금속 광물제품 제조업", "24": "1차 금속 제조업",
    "25": "금속가공제품 제조업(기계 및 가구 제외)", "26": "전자부품, 컴퓨터, 영상, 음향 및 통신장비 제조업",
    "27": "의료, 정밀, 광학기기 및 시계 제조업", "28": "전기장비 제조업",
    "29": "기타 기계 및 장비 제조업", "30": "자동차 및 트레일러 제조업",
    "31": "기타 운송장비 제조업", "32": "가구 제조업", "33": "기타 제품 제조업",
    "35": "전기, 가스, 증기 및 공기조절 공급업",
    "36": "수도업", "37": "하수, 폐수 및 분뇨 처리업", "38": "폐기물 수집, 운반, 처리 및 원료 재생업", "39": "환경 정화 및 복원업",
    "41": "종합 건설업", "42": "전문직별 공사업",
    "45": "자동차 및 부품 판매업", "46": "도매 및 상품중개업", "47": "소매업(자동차 제외)",
    "49": "육상운송 및 파이프라인 운송업", "50": "수상 운송업", "51": "항공 운송업", "52": "창고 및 운송관련 서비스업",
    "55": "숙박업", "56": "음식점 및 주점업",
    "58": "출판업", "59": "영상·오디오 기록물 제작 및 배급업", "60": "방송업",
    "61": "통신업", "62": "컴퓨터 프로그래밍, 시스템 통합 및 관리업", "63": "정보서비스업",
    "64": "금융업", "65": "보험 및 연금업", "66": "금융 및 보험 관련 서비스업",
    "68": "부동산업",
    "70": "연구개발업", "71": "전문서비스업", "72": "건축기술, 엔지니어링 및 기타 과학기술 서비스업",
    "73": "기타 전문, 과학 및 기술 서비스업", "74": "사업시설 관리 및 조경 서비스업", "75": "사업지원 서비스업",
    "76": "임대업(부동산 제외)",
    "84": "공공행정, 국방 및 사회보장 행정",
    "85": "교육 서비스업",
    "86": "보건업", "87": "사회복지 서비스업",
    "90": "창작, 예술 및 여가관련 서비스업", "91": "스포츠 및 오락관련 서비스업",
    "94": "협회 및 단체", "95": "개인 및 소비용품 수리업", "96": "기타 개인 서비스업",
    "97": "가구내 고용활동", "98": "달리 분류되지 않은 자가소비를 위한 가구의 재화 및 서비스 생산활동",
    "99": "국제 및 외국기관",
}


def ksic_industry_hint(induty_code: str) -> str:
    """DART induty_code(표준산업분류 코드)의 앞 2자리(중분류)로 대략적인 업종
    카테고리를 알려준다. 정확한 세세분류(5자리 전체)명까지는 이 표에 없으니
    "근사치"임을 항상 밝힌다. 코드가 없거나 표에 없는 중분류면 빈 문자열."""
    code = (induty_code or "").strip()
    if len(code) < 2:
        return ""
    name = _KSIC_DIVISION_NAMES.get(code[:2])
    if not name:
        return ""
    return f"{name}(표준산업분류 중분류 {code[:2]} 기준 근사 — 정확한 세부 분류는 {KSIC_LOOKUP_URL} 참고)"


def dart_filing_search_url(company_name: str) -> str:
    """★ 2026-08-09 추가: corp_code를 몰라도(또는 아예 미등록이라도) 회사명으로
    DART 공시 검색 결과 페이지를 바로 열 수 있는 링크 — "정보 부족"이라고만
    적어두지 말고 사용자가 직접 확인할 수 있게 항상 붙여준다."""
    return "https://dart.fss.or.kr/dsab002/main.do?autoSearch=true&textCrpNm=" + urllib.parse.quote(company_name)


def dart_company_overview_url(corp_code: str) -> str:
    """corp_code를 찾았을 때만 쓸 수 있는, 이 회사의 DART 기업개황(공시 목록) 페이지."""
    return f"https://dart.fss.or.kr/dsae001/main.do?corpCode={corp_code}"


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


def fetch_company_news(company_name: str, limit: int = 8) -> list[dict[str, str]]:
    """★ 2026-08-09 추가: 회사명으로 네이버 뉴스 검색 결과를 최신순으로 긁어와
    제목·링크를 뽑는다. "궤도(詭道)" 해석 요청 — 회사가 대외적으로 어떻게
    비치고 싶어하는지, 무엇을 강조하고 무엇을 감추는지는 재무제표가 아니라
    언론 노출의 제목·빈도에서 드러난다는 취지로 추가했다. 사람인/알바천국
    크롤러와 같은 패턴으로 표준 라이브러리(re)만 쓴다. 네이버가 마크업을 바꾸면
    빈 리스트를 반환할 수 있는데, 뉴스는 있으면 좋은 보조 자료지 필수 데이터가
    아니므로 실패해도 조용히 넘어간다."""
    url = "https://search.naver.com/search.naver?" + urllib.parse.urlencode({
        "where": "news", "query": company_name, "sort": "1",  # sort=1: 최신순
    })
    # ★ 실측: USER_AGENT(커스텀 UA)만 쓰면 네이버가 403으로 막는다. 일반
    # 브라우저 UA에 Accept-Language·Referer까지 더해야 통과한다(실측 확인).
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.naver.com/",
    })
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8", "replace")
    except (urllib.error.HTTPError, urllib.error.URLError):
        return []

    # ★ 실측(2026-08-09): 네이버가 예전 "news_tit" 클래스 방식에서 sds-comps
    # 디자인시스템으로 마크업을 바꿨다. 개별 컴포넌트 클래스는 해시가 붙어
    # 불안정하지만, 제목 링크에 붙는 data-heatmap-target=".tit"과 제목 span의
    # "sds-comps-text-type-headline1" 클래스는 비교적 안정적으로 확인됨.
    items: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    anchor_re = re.compile(r'<a\s+([^>]*data-heatmap-target="\.tit"[^>]*)>(.*?)</a>', re.S)
    span_re = re.compile(r'sds-comps-text-type-headline1[^"]*"[^>]*>(.*?)</span>', re.S)
    for m in anchor_re.finditer(body):
        attrs, inner = m.group(1), m.group(2)
        href_m = re.search(r'href="([^"]+)"', attrs)
        title_m = span_re.search(inner)
        if not href_m or not title_m:
            continue
        href = html.unescape(href_m.group(1))
        if href in seen_urls:
            continue
        title = plain(html.unescape(re.sub(r"<[^>]+>", "", title_m.group(1))))
        if not title:
            continue
        seen_urls.add(href)
        items.append({"title": title, "url": href})
        if len(items) >= limit:
            break
    return items


def build_reference_links_block(company_name: str, corp_code: str | None, news: list[dict[str, str]]) -> str:
    """★ 2026-08-09 추가: AI가 본문 안에 링크를 정확하게 인용한다는 보장이 없으므로,
    실제로 클릭 가능한 참고 링크는 AI 출력과 별개로 코드가 직접 덧붙인다. ★ 같은
    날 정리: 크레딧잡·잡플래닛·홈택스처럼 코드가 직접 확인하지 못하는 곳은
    "가서 확인해보라"는 링크로도 보여주지 않는다(사용자 피드백: "내가 파악할 수
    없는 자료는 아예 보이지 않게 하라"). 실제로 코드가 확인한 것만 링크로 남긴다
    — DART(직접 조회), 뉴스(직접 크롤링). 원문 URL을 그대로 노출하지 않고 짧은
    라벨 링크로 건다(피드백: "URL 그대로 보이지 않게, ~바로가기 이런식으로")."""
    lines = ["## 🔗 참고 링크", f"- [DART 공시 검색 바로가기]({dart_filing_search_url(company_name)})"]
    if corp_code:
        lines.append(f"- [DART 기업개황(공시 목록) 바로가기]({dart_company_overview_url(corp_code)})")
    lines.append("### 최근 관련 뉴스(네이버 뉴스 검색, 최신순 — 직접 크롤링해 확인한 것만 표시)")
    if news:
        for item in news:
            lines.append(f"- {item['title']} — [기사 원문 바로가기]({item['url']})")
    else:
        q = urllib.parse.quote(company_name)
        lines.append(f"- 검색된 뉴스 없음(언론 노출이 적거나 회사명 검색이 모호할 수 있음) — "
                      f"[네이버 뉴스에서 직접 검색]({'https://search.naver.com/search.naver?where=news&query=' + q})")
    return "\n".join(lines)


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


_HOMEPAGE_SECTION_RULES = (
    ("공식 채용공고", re.compile(r"채용공고|채용정보|recruit", re.I)),
    ("인사제도", re.compile(r"인사제도|인재상|인사관리", re.I)),
    ("복리후생", re.compile(r"복리후생|복지|benefit", re.I)),
    ("기업소개", re.compile(r"기업소개|회사소개|인사말|company", re.I)),
    ("경영방침", re.compile(r"경영방침|경영이념|비전|mission", re.I)),
    ("제품소개", re.compile(r"제품소개|제품|product|반도체|display|자동화|챔버", re.I)),
    ("연구·기술", re.compile(r"연구.?기술|연구소|특허|인증", re.I)),
)


def fetch_homepage_sources(homepage_url: str, max_pages: int = 10) -> list[dict[str, str]]:
    """공식 홈페이지의 핵심 메뉴를 같은 도메인 안에서만 제한적으로 따라간다.

    대표 URL 한 페이지만 AI에 넘기던 방식은 채용·인사·제품 정보가 별도 메뉴에
    숨어 있으면 전혀 보지 못했다. 첫 화면의 링크 텍스트/URL에서 핵심 섹션을
    찾아 카테고리별 첫 페이지를 수집하고, 실제 출처 URL과 함께 보존한다.
    """
    parsed = urllib.parse.urlparse(homepage_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return []

    def fetch(url: str) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.read().decode("utf-8", "replace")
        except (urllib.error.HTTPError, urllib.error.URLError):
            return ""

    root = f"{parsed.scheme}://{parsed.netloc}/"
    landing_html = fetch(homepage_url) or (fetch(root) if homepage_url != root else "")
    if not landing_html:
        return []
    candidates: list[tuple[str, str]] = [("공식 홈페이지", homepage_url)]
    for attrs, inner in re.findall(r"<a\b([^>]*)>(.*?)</a>", landing_html, re.S | re.I):
        href_match = re.search(r'href=["\']([^"\']+)', attrs, re.I)
        if not href_match:
            continue
        href = urllib.parse.urljoin(homepage_url, html.unescape(href_match.group(1)))
        target = urllib.parse.urlparse(href)
        if target.netloc != parsed.netloc or target.scheme not in {"http", "https"}:
            continue
        label = plain(html.unescape(re.sub(r"<[^>]+>", " ", inner)))
        haystack = f"{label} {target.path} {target.query}"
        for category, pattern in _HOMEPAGE_SECTION_RULES:
            if pattern.search(haystack):
                candidates.append((category, href))
                break

    sources: list[dict[str, str]] = []
    seen_categories: set[str] = set()
    seen_urls: set[str] = set()
    for category, url in candidates:
        url = urllib.parse.urldefrag(url)[0]
        if category in seen_categories or url in seen_urls:
            continue
        page_html = landing_html if url == homepage_url else fetch(url)
        if not page_html:
            continue
        # 공통 메뉴보다 본문을 우선하되, 사이트마다 마크업이 달라 실패 시 전체를 쓴다.
        main_match = re.search(
            r'<(?:main\b[^>]*|div\b[^>]*id=["\'](?:sub_content|content)["\'][^>]*)>(.*?)(?:</main>|<!--\s*(?:sub_)?content\s*-->)',
            page_html, re.S | re.I,
        )
        body = main_match.group(1) if main_match else page_html
        body = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body))).strip()
        if len(text) < 20:
            continue
        sources.append({"category": category, "url": url, "text": text[:2400]})
        seen_categories.add(category)
        seen_urls.add(url)
        if len(sources) >= max_pages:
            break
    return sources


def homepage_sources_markdown(sources: list[dict[str, str]]) -> str:
    """추천공고 상단에 넣을 공식 홈페이지 출처 하위 목록."""
    lines = []
    for source in sources:
        if source["category"] == "공식 홈페이지":
            continue
        summary = source["text"][:260].strip()
        if len(source["text"]) > 260:
            summary += "…"
        lines.append(f"  - [{source['category']} 바로가기]({source['url']}) — {summary}")
    return "\n".join(lines)


def ensure_company_overview_links(
    text: str,
    company_name: str,
    homepage_url: str | None,
    corp_code: str | None,
) -> str:
    """기업 개황의 첫 사실 문장에 홈페이지·DART를 괄호 출처로 붙인다."""
    links = []
    if homepage_url:
        links.append(f"[기업 홈페이지 바로가기]({homepage_url})")
    links.append(f"[DART 공시 검색 바로가기]({dart_filing_search_url(company_name)})")
    if corp_code:
        links.append(f"[DART 기업개황 바로가기]({dart_company_overview_url(corp_code)})")
    citation = " (출처: " + " · ".join(links) + ")"
    if citation in text:
        return text
    heading = re.search(r"(?m)^(#{1,3}\s*)?1\.\s*\*\*기업 개황\*\*.*$", text)
    if heading:
        sentence_end = text.find(".\n", heading.end())
        if sentence_end >= 0:
            return text[:sentence_end + 1] + citation + text[sentence_end + 1:]
        return text[:heading.end()] + "\n" + company_name + citation + text[heading.end():]
    return "## 1. 기업 개황\n" + company_name + citation + "\n\n" + text


def build_company_prompt(
    company_name: str, dart_info: dict | None, financials: list[dict],
    jobs: list[dict], contests: list[dict], homepage_text: str,
    news: list[dict[str, str]] | None = None,
    homepage_url: str | None = None,
) -> str:
    dart_search_url = dart_filing_search_url(company_name)
    dart_block = f"DART 공시 정보 없음(비상장 또는 공시대상 아닌 소규모 기업일 가능성) — 직접 검색: {dart_search_url}"
    if dart_info:
        induty_code = dart_info.get("induty_code", "")
        industry_hint = ksic_industry_hint(induty_code)
        industry_label = f"{induty_code}({industry_hint})" if industry_hint else (induty_code or "미상")
        dart_block = (
            f"대표자: {dart_info.get('ceo_nm', '')} | 설립일: {dart_info.get('est_dt', '')} | "
            f"업종코드: {industry_label} | 상장여부: "
            f"{'상장' if dart_info.get('stock_code') else '비상장'} | "
            f"주소: {dart_info.get('adres', '')}"
        )
    financial_block = "\n".join(
        f"- {f['year']}년({'연결' if f['fs_div'] == 'CFS' else '별도'}): "
        + ", ".join(f"{k}={v}" for k, v in f.items() if k not in ("year", "fs_div"))
        for f in financials
    ) or "공시된 재무제표 없음(급여·복리후생비 등 인건비 항목 포함해서 미공시)"
    jobs_block = "\n".join(f"- [{j['source']}] {j['title']} (마감 {j['deadline']})" for j in jobs) or "수집된 채용공고 없음"
    contests_block = "\n".join(f"- {c['title']} (마감 {c['deadline']})" for c in contests) or "수집된 공모전 없음"
    news_block = "\n".join(f"- [{n['title']}]({n['url']})" for n in (news or [])) or "검색된 뉴스 없음(언론 노출이 적을 수 있음)"
    homepage_link = f"[기업 홈페이지 바로가기]({homepage_url})" if homepage_url else "확인된 기업 홈페이지 링크 없음"

    return f"""다음은 "{company_name}"에 대해 여러 출처에서 모은 정보다. 손자병법
해석에서 역사적 실증사례를 드는 것처럼, 각 판단마다 아래 정보 중 무엇을
근거로 삼았는지 명시하면서 서술하라. 근거 없는 부분은 "정보 부족 — 추정:"으로
표시하고 지어내지 마라.

--- DART 기업개황 ---
{dart_block}

--- DART 재무제표 요약(최근 공시분, 매출·이익 외에 급여·복리후생비가 별도
공시돼 있으면 인건비 항목으로 포함됨) ---
{financial_block}

--- 이직시스템에 수집된 이 회사 채용공고 ---
{jobs_block}

--- 이직시스템에 수집된 이 회사 관련 공모전/경진대회 ---
{contests_block}

--- 회사 홈페이지/소개 페이지 원문(잡음 포함 가능) ---
{homepage_link}
{homepage_text or "(제공된 홈페이지 텍스트 없음)"}

--- 최근 언론 보도 제목(네이버 뉴스 검색, 최신순 — 회사가 대외적으로 어떻게
비치는지/무엇을 강조하는지 판단하는 데 쓸 것. 각 제목에는 원문 링크가 붙어 있다.
제목만 보고 원문 내용을 지어내지 말 것) ---
{news_block}

--- 끝 ---

한국어로 아래 일곱 항목에 답하라:
**★ 정보 공백 판단(2026-08-18, 사용자 명시 요청) — 다른 지침보다 먼저 적용**:
DART 미등록이고, 재무제표가 없고, 홈페이지가 없거나 원문이 비어 있고, 위 채용공고가
이 회사에 대해 지금 분석 중인 공고 1건뿐이며(같은 회사의 다른 공고·과거 이력 없음),
뉴스 제목들을 직접 읽어봤을 때 회사명 부분 일치 등으로 걸린 노이즈일 뿐 이 회사를
실제로 가리키는 근거가 하나도 없다면, 아래 일곱 항목을 전부 채우지 말고 다음 형식
그대로 짧게 끝내라(무리하게 "정보 부족 — 추정"을 반복해서 항목을 채우지 말 것):

```
## 분석할 정보 없음

{company_name} — DART 미등록, 홈페이지 확인 안 됨(또는 원문 없음), 관련 뉴스 없음(또는
전부 이 회사와 무관), 확인된 채용공고 1건 외 추가 정보 없음. 이 회사를 판단할 근거가
전혀 없어 상세 분석을 생략한다.
```

이 판단이 아니라면(즉 DART·재무·홈페이지·과거 공고·관련 뉴스 중 단 하나라도 이 회사에
대한 실제 근거가 있다면) 아래 일곱 항목을 평소대로 전부 작성하라.

**출처 링크 의무 규칙**: 별도의 `참고 링크`, `출처 지도`, 링크 모음 섹션을 만들지
마라. 홈페이지·DART·뉴스를 근거로 쓴 문장 끝에 반드시
`(출처: [자료명](URL))` 형식으로 괄호 출처를 붙여라. 특히 내부거래·승계·계열분리·
소송·과로처럼 언론에서 읽은 판단은 바로 그 문장 끝에
`(출처: [기사 제목](URL))`을 붙인다. 한 문장에 출처가 여러 개면 같은 괄호 안에
나란히 넣는다. 링크가 제공되지 않은 구체적 사실은 쓰지 말고 `정보 부족`으로 남긴다.
1. **기업 개황**: 설립·업종·상장여부·규모 등 확인 가능한 사실 요약. 첫 줄에
   `{homepage_link}`를 그대로 넣고, DART 사실에는 [DART 공시 검색]({dart_search_url})을 붙여라.
2. **재무 상태 해석**: 재무제표가 있으면 매출/이익 추이가 뭘 시사하는지 해석.
   없으면 "DART 미등록 — 공시 재무정보 없음"이라고 명시하고 다른 근거(채용
   규모·공고 빈도, 위 뉴스 제목 등)로 회사 규모를 추정하라. **코드가 직접
   확인하지 않은 외부 사이트(크레딧잡·잡플래닛·홈택스 등)를 "가서 확인해보라"고
   안내하지 마라** — 사용자가 직접 조회할 수 없는 자료는 언급 자체를 하지 않는
   편이 낫다(정보 부족은 "정보 부족 — 추정"이라고만 명시하고 넘어갈 것).
3. **채용·공모전 이력에서 보이는 경영 방향**: 어떤 직무를 왜 뽑으려 하는지,
   공모전을 왜 여는지에서 회사가 지금 무엇에 투자하고 있는지 추론.
4. **종합 서사**: 이 회사가 걸어온 궤적과 지금 하려는 것을 하나의 이야기로
   엮어라 — 개별 사실을 나열하지 말고 왜 그 순서로 일어났는지 연결하라.
5. **병법적 해석**: 지금까지 정리한 사실(채용 시점·규모, 공모전 개최 목적,
   재무 추이, 홈페이지에서 드러나는 태도 등)을 손자병법의 개념으로 다시 읽어라.
   **막연한 인용이 아니라, 위에서 근거로 든 구체적 사실 하나하나를 아래
   개념과 짝지어 설명하라** — 근거가 부족하면 "이 부분은 병법적으로 해석할
   근거가 부족하다"고 명시하고 넘어가라. 세 개념을 각각 다뤄라:
   - **形(형)·勢(세)·궤도(詭道) — 하나로 묶어서 다뤄라**: 形은 회사가 스스로를
     "어떻게 보이게 하는가/얼마나 드러내는가"다. 손자병법: "형병지극 지어무형
     (형의 극치는 형태가 없음에 이르는 것) — 무형이면 아무리 가까이서 살펴도
     헤아릴 수 없고 아무리 지혜로운 자도 계략을 꾸밀 수 없다." DART 미공시·
     홈페이지 부재·언론 노출 없음처럼 "안 보이는" 상태는 의도적으로 형을
     감춘 것(무형 전략)일 수도, 그냥 정보가 없는 것일 수도 있다 — 구분할
     근거가 없으면 반드시 그렇게 명시하고, 안 보이기 때문에 남들이 제멋대로
     판단하게 되는 지점(그래서 오히려 허가 드러나는 지점)이 있다면 짚어라.
     반대로 뉴스·홈페이지·공시가 있으면 무엇을 보여주려 하는지(形) 읽어라.
     勢는 이 회사가 어떤 실력·품질로 시장에서 인정받아 지금의 유리한 위치
     (경쟁우위)를 만들었는가, 그리고 그 유리함을 지금 무엇에 쓰고 있는가다
     (채용 규모·공모전 개최·사업 확장 방향과 연결해서 설명). 궤도는 그 세를
     만들고 지키기 위해 자신을 어떻게 보이게 하는가의 구체적 수법이다 —
     "능이시지무능, 용이시지무용"(할 수 있어도 못하는 척, 쓸 수 있어도 안 쓰는
     척)처럼, 위 "최근 언론 보도 제목"에서 실제 상태와 다르게 보이려는 신호가
     있는지 근거를 찾아라. 뉴스가 없으면 그 자체가 무형(形) 전략의 결과일
     수도, 단순 노출 부족일 수도 있으니 단정하지 말고 그 불확실성 자체를
     명시하라. **하나의 사실(마감일이 같은 공모전 2건처럼 사소한 것)만 근거로
     "세를 키우려는 시도" 같은 결론을 성급하게 내지 마라** — 뒷받침할 근거가
     한둘뿐이면 "이 부분은 추정 수준에 머문다"고 정직하게 밝혀라.
   - **진퇴(進退)**: 손자병법 행군편의 관찰 신호를 그대로 대응시켜라 — 겉으로
     보이는 행동과 실제 의도가 다르다는 게 핵심이다. "사비이익비자 진야"(말은
     낮추면서 대비를 늘리는 것은 나아가려는 것) → 공고 문구는 소박한데 채용
     규모·빈도가 늘고 있다면 진(공격적 확장 조짐). "사강이진구자 퇴야"(말은
     강경한데 앞으로 나오는 척하는 것은 실은 물러나려는 것) → 공모전·홍보는
     요란한데 실제 채용·재무 지표는 정체·감소라면 퇴(실은 물러서는 중).
     "경거선출거기측자 진야"(가벼운 전력이 먼저 옆으로 나오는 것은 진을 치려는
     것) → 본 채용 전에 소수 인원을 곁가지 직무로 먼저 뽑는다면 진영을 갖추는
     중. "무약이청화자 모야"(조건 없이 화친을 청하는 것은 계략) → 이례적으로
     좋은 조건을 조건 없이 내미는 채용공고라면 다른 의도가 있을 수 있음.
     "분주이진병거자 기야"(분주하게 진열하는 것은 시기를 정한 것) → 짧은
     기간에 여러 공고·공모전을 한꺼번에 벌인다면 정해둔 시점에 맞춰 움직이는
     신호. "반진반퇴자 유야"(반은 나아가고 반은 물러나는 것은 유인) → 공고를
     냈다가 취소하거나 방향이 오락가락한다면 유인이거나 내부 혼선의 신호.
     **위 신호 쌍 중 실제로 대응하는 구체적 사실이 하나도 없으면 "근거
     부족"이라고 얼버무리지 말고 진퇴 항목 자체를 통째로 생략하라** — 채용을
     안 하고 있다는 사실 하나만으로 "때를 기다린다"는 식의 성급한 결론을
     내지 마라.
   - **허실(虛實)**: "경쟁자 대비 자원을 어디에 집중했는가" 같은 추상적 배분
     이야기가 아니라, **이 회사가 사람을 어떻게 다루는가**로 읽어라. 실(實)은
     보급이 잘 되고(재무가 탄탄하고), 인재풀이 풍성하며, 인력을 혹사시키지
     않고 잘 쉬게 하는(재직자가 로(勞)하지 않는) 상태 — 즉 준비가 잘 되고
     실수익이 탄탄하며 미래 손실 확률이 낮은 상태다. 허(虛)는 노동을 많이
     투입했지만 실제 결과물은 노력에 비해 적거나, 지금은 그럴듯해 보여도
     향후 손실로 돌아올 수 있는 상태다. 판단 근거는 위 뉴스 제목(과로·야근·
     이직률·임금체불·소송 관련 보도 여부), 채용공고가 같은 자리를 반복해서
     올리는지(잦은 재공고는 잦은 퇴사의 신호일 수 있음), 재무제표의 인건비
     비중과 이익률을 함께 봐라. **코드가 직접 확인하지 않은 외부 사이트(크레딧잡·
     잡플래닛 등)를 "가서 확인해보라"고 안내하지 마라** — 근거가 약하면 단정하지
     말고 "정보 부족 — 추정"으로만 표시하라.
6. **세무·회계·노무 관점**: 재무제표에 급여·복리후생비가 공시돼 있으면 매출 대비
   인건비 비중으로 인력 투자 규모를 해석하라. 채용공고에 연봉·수습기간·4대보험
   같은 노무 조건이 명시돼 있으면 노무 관리 수준을 판단하라. 이 항목은 공개
   데이터가 특히 제한적이므로, 확인할 근거가 없으면 추측하지 말고 "정보 부족 —
   추정"이라고만 명시하라(코드가 직접 확인하지 못한 외부 사이트를 확인해보라고
   안내하지 말 것).
7. **관점별 시사점**: 구직자·협업 파트너·(관심 있다면) 투자자 각각에게 이
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
    """job_collector.py/contest_collector.py의 동명 함수와 동일(볼드·URL 링크·
    `[라벨](URL)` 마크다운 링크 지원, ★ 2026-08-09)."""
    inline_re = re.compile(r"\*\*(.+?)\*\*|\[([^\]]+)\]\((https?://[^\s)]+)\)|(https?://[^\s]+)")

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
            elif m.group(2) is not None:
                segments.append({
                    "type": "text", "text": {"content": m.group(2)[:1900], "link": {"url": m.group(3)}},
                })
            else:
                url = m.group(4)
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


_AI_PUBLICATION_FORBIDDEN_MARKERS = (
    "**Bash**:", "<tool_use>", "tool_uses", "functions.exec", "assistant to=",
    "jobs-analyst", "에이전트에 위임", "README를 읽", "작업을 진행하겠습니다",
)


def valid_company_analysis(text: str) -> bool:
    required = ("기업 개황", "사업", "채용")
    return (
        len(text.strip()) >= 600
        and all(marker in text for marker in required)
        and not any(marker in text for marker in _AI_PUBLICATION_FORBIDDEN_MARKERS)
    )


def analyze_company(args: argparse.Namespace) -> None:
    company_name = args.company_name
    print(f"'{company_name}' 분석 시작")

    dart_info = None
    financials: list[dict] = []
    corp_code = None
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

    news = fetch_company_news(company_name)
    print(f"  관련 뉴스 {len(news)}건 수집")

    homepage_url = args.url
    if not homepage_url and dart_info:
        candidate_url = (dart_info.get("hm_url") or "").strip()
        if candidate_url and "." in candidate_url:
            homepage_url = candidate_url if candidate_url.startswith("http") else f"https://{candidate_url}"
    homepage_text = fetch_homepage_text(homepage_url) if homepage_url else ""
    if homepage_url:
        print(f"  홈페이지 텍스트 {len(homepage_text)}자 수집")

    prompt = build_company_prompt(company_name, dart_info, financials, jobs, contests, homepage_text, news, homepage_url)
    print("\nAI로 분석 중... (codex 실패 시 claude로 자동 전환)\n")
    from ai_exec import run_ai_exec
    try:
        stdout, engine = run_ai_exec(prompt, BASE_DIR, timeout=300, validator=valid_company_analysis)
    except RuntimeError as exc:
        raise SystemExit(f"AI 분석 실패: {exc}")
    # 첫 기업개황 문장에는 코드가 괄호형 출처를 보장한다. 별도 링크 목록은 만들지 않는다.
    text = ensure_company_overview_links(stdout.strip(), company_name, homepage_url, corp_code)

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
