#!/usr/bin/env python3
"""
교대근무 메뉴바 앱 (날씨 + Elmedia 폴더 재생 + 근무표 자동 인식 + 오늘 급여 실시간 표시)
설치: pip install rumps
실행: python3 shift_alarm.py

추가된 기능:
- d_team_schedule_2026.json (근무표에서 추출한 D조 날짜별 근무표)을 읽어서
  매일 자정에 "오늘 날짜"에 해당하는 근무(D/S/G/휴)를 자동으로 찾아
  알람을 자동 설정한다.
- 메뉴바에서 수동으로 근무를 눌러서 덮어쓰는 것도 여전히 가능하다
  (수동 선택 시 "자동 모드"는 꺼지고, 다시 켜고 싶으면 메뉴에서 켤 수 있다).
- 오늘 근무 중 "지금까지 벌어들인 급여" 실시간 추정치
  - 급여명세서를 역산해서 얻은 통상시급을 기본값으로 사용
  - 주간(Day)/오후(Swing): 통상시급 그대로
  - 야간(GY, 22:00~06:00): 통상시급 x 1.5 (야간수당 50% 가산분 반영)
  - 자정을 넘기는 야간 근무도 정확히 계산 (어제 시작한 근무를 오늘도 이어서 카운트)
  - 이 값은 급여명세서를 역산한 고정 추정치다.
- 주간 리마인더 (헬스장/엄마 전화/카톡 정리/아울렛 쇼핑): 대부분 근무표의 "휴무 블록"을
  기준으로 판단한다. 헬스장은 예외로 근무·휴무와 무관하게 격일 간격을 반복하며,
  엄마 전화는 휴무 시작일, 카톡 정리는 휴무 마지막날,
  아울렛 쇼핑은 한 달에 한 번(그 달의 첫 번째 휴무 블록 시작일).
  메뉴의 "🔔 리마인더 켜기/끄기"에서 각 항목을 개별적으로 켜고 끌 수 있음.
"""

import rumps
import subprocess
import os
import json
import re
import shlex
import sqlite3
import sys
import urllib.request
import urllib.error
from urllib.parse import urlparse, parse_qs
import threading
import datetime
import random
import math
import concurrent.futures
import shutil
import time
import signal
import ai_usage
import objc
from PyObjCTools import AppHelper
from AppKit import (
    NSApp, NSPanel, NSTextField, NSButton, NSMakeRect, NSFont,
    NSBackingStoreBuffered, NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSModalPanelWindowLevel, NSTextAlignmentCenter, NSRoundedBezelStyle,
    NSColor, NSForegroundColorAttributeName,
)
from Foundation import NSMutableAttributedString, NSRange

# ── 설정 파일 경로 ──────────────────────────────────────────
CONFIG_FILE = os.path.expanduser("~/.shift_alarm_config.json")

# ── 모바일 접근용 상태 파일 ───────────────────────────────────
# iCloud Drive에 오늘의 근무/리마인더/날씨를 JSON으로 써두면 아이폰에서 읽을 수
# 있다. 세 군데에 동시에 쓴다:
# 1) ShiftAlarmStatus 폴더 — iOS 단축어의 "파일 가져오기"에서 수동으로 지정해
#    쓰는 범용 경로(최초 1회 파일 선택 필요, iOS 샌드박스 제약 때문에 불가피).
# 2) Pythonista 3 앱의 iCloud Documents 폴더 — Pythonista는 자기 iCloud
#    Documents를 파일 선택기 없이 항상 바로 읽을 수 있어서, shift_status_pythonista.py
#    를 이 폴더에 같이 넣어두면 파일 선택기 설정 자체가 필요 없다(★ 2026-08-05).
#    단, Pythonista의 위젯(Today Widget/NCWidget)은 iOS 18에서 애플이 완전히
#    제거해서 더 이상 홈 화면/Today View 어디에도 못 놓는다(★ 2026-08-06 확인)
#    — 위젯 용도로는 3)을 쓴다. shift_status_pythonista.py는 앱 안에서 직접
#    실행하는 용도로는 여전히 유효.
# 3) Scriptable 앱의 iCloud Documents 폴더 — 최신 WidgetKit 홈 화면 위젯을
#    지원하는 앱이라 ShiftAlarmWidget.js를 이 폴더에 넣어두면 진짜 홈 화면
#    위젯 타일로 쓸 수 있다(★ 2026-08-06 추가).
MOBILE_STATUS_DIR = os.path.expanduser(
    "~/Library/Mobile Documents/com~apple~CloudDocs/ShiftAlarmStatus"
)
MOBILE_STATUS_FILE = os.path.join(MOBILE_STATUS_DIR, "status.json")

PYTHONISTA_ICLOUD_DIR = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~com~omz-software~Pythonista3/Documents"
)
PYTHONISTA_STATUS_FILE = os.path.join(PYTHONISTA_ICLOUD_DIR, "status.json")

SCRIPTABLE_ICLOUD_DIR = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~dk~simonbs~Scriptable/Documents"
)
SCRIPTABLE_STATUS_FILE = os.path.join(SCRIPTABLE_ICLOUD_DIR, "status.json")

# ── 근무표 JSON 경로 (엑셀에서 추출한 D조 날짜별 근무) ─────────────
# 스크립트와 같은 폴더에 d_team_schedule_2026.json 을 두거나,
# 아래 경로를 실제 위치로 바꿔주세요.
SCHEDULE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "d_team_schedule_2026.json")

# ── 이직시스템(job_collector.py) 연동 ──────────────────────────
JOB_COLLECTOR_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "이직시스템"
)
JOB_COLLECTOR_SCRIPT = os.path.join(JOB_COLLECTOR_DIR, "job_collector.py")
JOB_COLLECTOR_DB = os.path.join(JOB_COLLECTOR_DIR, "data", "jobs.db")
JOB_COLLECTOR_REFRESH_SECONDS = 24 * 60 * 60  # 하루 1번
# 적합도 1위 공고를 AI로 분석해 Notion에 올린 결과(★ 2026-08-07 추가).
# job_collector.py analyze-top이 매일 이 파일을 갱신한다.
# ★ 2026-08-08: 취업/알바는 성격이 달라 카테고리별로 분리(job_collector.py의
# JOB_CATEGORY_LABELS와 키를 맞춘다).
JOB_CATEGORIES = {"career": "커리어", "parttime": "알바"}
JOB_TOP_ANALYSIS_STATE = {
    cat: os.path.join(JOB_COLLECTOR_DIR, "data", f"top_job_notion_{cat}.json") for cat in JOB_CATEGORIES
}
# 링커리어 공모전·경진대회 수집기(★ 2026-08-07 추가). job_collector.py와 같은
# 이직시스템 폴더에 있고 같은 하루 1번 주기로 collect → analyze-top을 이어서 돌린다.
CONTEST_COLLECTOR_SCRIPT = os.path.join(JOB_COLLECTOR_DIR, "contest_collector.py")
# ★ 2026-08-08: AI 특화/일반 공모전으로 분리(contest_collector.py의
# CONTEST_CATEGORY_LABELS와 키를 맞춘다).
CONTEST_CATEGORIES = {"ai": "AI", "general": "일반"}
CONTEST_TOP_ANALYSIS_STATE = {
    cat: os.path.join(JOB_COLLECTOR_DIR, "data", f"top_contest_notion_{cat}.json") for cat in CONTEST_CATEGORIES
}
# "🎎 일일 체크리스트" Notion 페이지(app.notion.com/p/3b532a1eae80803490affd8c9b658711)
# 를 표준 UUID로 표기한 것 — 오늘의 리마인더를 매일 토글+체크박스로 추가한다(★ 2026-08-07).
REMINDER_CHECKLIST_NOTION_PAGE_ID = "3b532a1e-ae80-8034-90af-fd8c9b658711"
REMINDER_CHECKLIST_NOTION_URL = (
    f"https://www.notion.so/{REMINDER_CHECKLIST_NOTION_PAGE_ID.replace('-', '')}"
)
NOTION_VERSION = "2026-03-11"
# "🔔 오늘: ..." 메뉴 항목에서 리마인더마다 색을 다르게 입혀 알록달록하게
# 보이게 한다(★ 2026-08-07: 콜백 없어 회색으로 보이던 걸 개선하면서 같이 추가).
REMINDER_MENU_COLOR_CYCLE = [
    NSColor.systemOrangeColor, NSColor.systemBlueColor, NSColor.systemPurpleColor,
    NSColor.systemGreenColor, NSColor.systemRedColor, NSColor.systemYellowColor,
]
# ★ 2026-08-08: 휴대폰 Notion에서 체크한 상태를 1분마다 당겨와 메뉴바/위젯에
# 반영한다. 로컬 캐시(오늘 날짜분만 유효)를 둬서 재시작 직후에도 빈 상태로
# 보이지 않게 한다.
CHECKLIST_STATE_CACHE_PATH = os.path.expanduser("~/.shift_alarm_checklist_state.json")
CHECKLIST_SYNC_INTERVAL_SECONDS = 60

# ★ 2026-08-09: Claude 라이브 quota는 OAuth 액세스 토큰(수 시간짜리)이 있어야
# 조회되는데, 이 토큰은 claude CLI를 실제로 켜서 쓸 때만 갱신된다. 밤새
# claude를 안 켜두면 토큰이 만료돼 "확인 불가"로 뜨다가, 아침에 claude를
# 다시 켜는 순간 키체인의 토큰은 이미 갱신되지만 shift_alarm이 그걸 알아채는
# 데 최대 12분(정상 주기)이 걸렸다. 실패 상태일 땐 주기를 짧게 당겨서 다음
# claude 세션이 열리자마자 몇 분 안에 자동 복구되게 한다.
AI_USAGE_NORMAL_INTERVAL = 12 * 60
AI_USAGE_RETRY_INTERVAL = 2 * 60


def fetch_reminder_checklist_state(token, date_str):
    """오늘 날짜 토글 밑 체크박스들의 현재 체크 상태를 Notion에서 읽어온다.
    반환: {리마인더 라벨: checked(bool)}. 오늘 토글이 아직 없으면 빈 딕셔너리."""
    def _get(path):
        request = urllib.request.Request(
            f"https://api.notion.com/v1/{path}",
            headers={"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)

    page_children = _get(f"blocks/{REMINDER_CHECKLIST_NOTION_PAGE_ID}/children?page_size=100")
    toggle_id = None
    for block in page_children.get("results", []):
        if block.get("type") != "toggle":
            continue
        rich_text = block.get("toggle", {}).get("rich_text", [])
        text = "".join(t.get("plain_text", "") for t in rich_text)
        if text == date_str:
            toggle_id = block["id"]
            break
    if not toggle_id:
        return {}

    todo_children = _get(f"blocks/{toggle_id}/children?page_size=100")
    state = {}
    for block in todo_children.get("results", []):
        if block.get("type") != "to_do":
            continue
        rich_text = block.get("to_do", {}).get("rich_text", [])
        text = "".join(t.get("plain_text", "") for t in rich_text)
        state[text] = bool(block.get("to_do", {}).get("checked"))
    return state

# ── 근무표 코드(D/S/G/휴) → 앱 내부 근무 이름 매핑 ───────────────
CODE_TO_SHIFT = {
    "D": "Day",
    "S": "Swing",
    "G": "GY",
    "휴": "휴무",
}

# ── 앱 내부 근무 이름 → 메뉴바 타이틀용 짧은 코드 (역매핑) ────────
SHIFT_TO_SHORT_CODE = {v: k for k, v in CODE_TO_SHIFT.items()}

# ── 근무별 알람 시간 ─────────────────────────────────────────
SHIFT_TIMES = {
    "Day":   {"hour": 2,  "minute": 55},
    "Swing": {"hour": 8,  "minute": 30},
    "GY":    {"hour": 16, "minute": 30},
    "휴무":  None
}

# ── 근무별 "전자제품 전원 끄기" 알람 시간 ─────────────────────────
# 근무 끝나고 쉬는(자는) 시간대에 맞춰 전자제품을 끄라고 하루 한 번 알려준다.
# Day:   17:00~02:00 / GY: 08:00~16:00 / Swing: 23:50~08:00
ELECTRONICS_OFF_TIMES = {
    "Day":   {"hour": 17, "minute": 0},
    "GY":    {"hour": 8,  "minute": 0},
    "Swing": {"hour": 23, "minute": 50},
}

# ── 근무별 실제 근무 시작/종료 시각 (근로계약서 기준) ─────────────
SHIFT_WORK_HOURS = {
    "Day":   {"start": (6, 0),  "end": (14, 0), "crosses_midnight": False},
    "Swing": {"start": (14, 0), "end": (22, 0), "crosses_midnight": False},
    "GY":    {"start": (22, 0), "end": (6, 0),  "crosses_midnight": True},
}

# ── 급여 계산용 시급 설정 ────────────────────────────────────
# 급여명세서의 "야간근로수당 = 야간시간 x 통상시급 x 50%" 식을
# 역산해서 얻은 값을 기본값으로 사용한다. 메뉴에서는 변경하지 않는다.
HOURLY_WAGE = 14861

SHIFT_WAGE_MULTIPLIER = {
    "Day":   1.0,
    "Swing": 1.0,
    "GY":    1.5,   # 야간수당 50% 가산
}

LOW_STORAGE_WARNING_GB = 5


def get_free_storage_gb(path="/"):
    """지정 볼륨의 실제 가용 공간을 소수점 없는 GiB 정수로 반환."""
    try:
        return int(shutil.disk_usage(path).free // (1024 ** 3))
    except OSError:
        return None

# ── 주간 리마인더 설정 ───────────────────────────────────────
# 대부분 요일이 아니라 근무표의 "휴무 블록"을 기준으로 잡는다.
# - 헬스장: 근무·휴무와 무관하게 격일 간격 반복. 상체/하체를 번갈아 표시
# - 엄마한테 전화: 휴무 블록의 첫날 (근무 마치고 쉬기 시작하는 날)
# - 허민준한테 전화: 한 달에 한 번. 그 달의 첫 번째 휴무 블록 시작일
# - 동찬이형한테 전화: 2026-08-03을 기준으로 21일마다 한 번
# - 손동주한테 전화: 2026-08-05를 기준으로 7일마다(주 1회) 한 번
# - 에이전틱 코딩 책 읽기: 2026-08-08을 기준으로 3일마다 한 번
# - 손동주 쉬는 날: 동주 본인 근무표(주간 2주/야간 2주 로테이션, 5일 근무+2일 휴무
#   반복) 기준. 2026-08-04(야간 첫날)를 14일 주기 1일째로 놓으면, 주/야간 구분과
#   무관하게 각 14일 블록 내 6·7일째와 13·14일째가 항상 휴무일이 된다.
# - 코털 정리: 근무표와 무관하게 2026-08-03을 기준으로 4일마다 한 번
# - 이어폰 충전: 근무표와 무관하게 2026-08-03을 기준으로 4일마다 한 번
# - 카톡 정리: 휴무 블록의 마지막날 (다시 출근하기 전날)
# - 아울렛 쇼핑: 한 달에 한 번. 그 달의 첫 번째 휴무 블록 시작일에 알림
# - 2만보 걷기: 근무·휴무와 무관하게 7일 주기 안 이틀(0·3일째)에 매주 2회
#   (★ 2026-08-07: 휴무 블록 시작·마지막날 기준이었더니 휴무가 뜸한 주엔 한 번도
#   안 뜨는 문제가 있어 재설계 — "일주일에 2번은 있어야 한다"는 사용자 지적)
# - 빨래: 휴무일마다 매번
# 각 항목은 메뉴의 "🔔 리마인더 켜기/끄기"에서 개별적으로 켜고 끌 수 있음.
REMINDERS = {
    "gym":             {"label": "🏋️ 헬스장 가는 날(상체/하체·격일)", "enabled": True},
    "call_mom":        {"label": "📞 엄마한테 전화하는 날(휴무 시작일)",   "enabled": True},
    "call_heo_minjun": {"label": "📞 허민준한테 전화하는 날(월 1회)", "enabled": True},
    "call_dongchan":   {"label": "📞 동찬이형한테 전화하는 날(21일에 1회)", "enabled": True},
    "call_sondongju":  {"label": "📞 손동주한테 전화하는 날(1주일에 1회)",   "enabled": True},
    "coding_academy":  {"label": "💬 코딩학원 카톡방에 연락하는 날(1주일에 1회)", "enabled": True},
    "agentic_coding_reading": {"label": "📚 에이전틱 코딩 책 읽기(3일에 1회)", "enabled": True},
    "sondongju_off":   {"label": "🎉 손동주 쉬는 날(동주 근무 주기 기준)",         "enabled": True},
    "nose_hair_trim":  {"label": "🪒 코털 정리하는 날(4일에 1회)",       "enabled": True},
    "nail_trim":       {"label": "💅 손톱발톱 정리하는 날(2주에 1회)",   "enabled": True},
    "earphone_charge": {"label": "🎧 이어폰 충전하는 날(4일에 1회)",     "enabled": True},
    "kakao_cleanup":   {"label": "🧹 카톡 정리하는 날(휴무 마지막날)",       "enabled": True},
    "outlet_shopping": {"label": "🛍️ 아울렛 쇼핑하는 날(월 1회)",    "enabled": True},
    "walk_20k":        {"label": "🚶 2만보 걷는 날(주 2회)",         "enabled": True},
    "laundry":         {"label": "🧺 빨래 돌리는 날(휴무일마다)",         "enabled": True},
    "outing":          {"label": "🗺️ 나들이 추천(월 1회)",    "enabled": True},
    "beef_bbq":        {"label": "🥩 소고기 구워먹는 날(월 1회·휴무일)", "enabled": True},
}

# ── 월 1회 나들이 추천 장소 (아산시 기준 + 근교) ────────────────────
# 2026-07-24 추가. 매달 다른 곳이 뜨도록 (연도,월) 기준으로 순환시킨다.
NEARBY_PLACES = [
    "현충사 (아산 — 이순신 사당, 산책로)",
    "외암민속마을 (아산 — 전통 한옥마을)",
    "신정호 국민관광지 (아산 — 호수 둘레길)",
    "온양온천 스파비스 (아산 — 온천)",
    "아산 지중해마을 (아산 — 이국적 테마마을)",
    "곡교천 은행나무길 (아산 — 산책/드라이브)",
    "세계꽃식물원 (아산 — 식물원)",
    "태학산자연휴양림 (아산 — 숲 산책)",
    "도고온천 (아산 — 온천)",
    "독립기념관 (천안 — 아산 인근)",
    "각원사 (천안 — 아산 인근, 대불)",
    "예당호 출렁다리 (예산 — 아산 인근)",
    "공산성 (공주 — 아산에서 당일치기)",
    "무령왕릉 (공주 — 아산에서 당일치기)",
    "간월암 (서산 — 아산에서 당일치기, 일몰 명소)",
]


def pick_monthly_outing_place(d):
    """(연,월) 기준으로 매달 다른 장소를 순환 선택 — 같은 달엔 항상 같은 곳."""
    idx = (d.year * 12 + d.month) % len(NEARBY_PLACES)
    return NEARBY_PLACES[idx]

# ── 실행할 단축어 이름 ────────────────────────────────────────
SHORTCUT_NAME = "아침루틴음악재생"

# ── Elmedia로 열 음악 폴더 ─────────────────────────────────────
PLAYLIST_FOLDER = "/Users/forrestdpark/Desktop/BlogImage/Coffee and Meditation"
FAVORITES_PLAYLIST_FOLDER = "/Users/forrestdpark/Desktop/BlogImage/좋아요플레이"  # ★ 2026-08-07 추가

# ── 아산시 좌표 ──────────────────────────────────────────────
LATITUDE  = 36.78
LONGITUDE = 127.00

# ── launchd / 알람 스크립트 경로 ────────────────────────────────
PLIST_PATH        = os.path.expanduser("~/Library/LaunchAgents/com.shfitalarm.music.plist")
ALARM_SCRIPT_PATH = os.path.expanduser("~/Library/Scripts/shift_alarm_run.sh")

# ── 아침 학습(ebook_reader.py) 관련 경로 ────────────────────────
EBOOK_READER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ebook_reader.py")
EBOOK_READER_LAUNCHER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_ebook_reader.sh")
EBOOK_NOTION_SYNC_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync_ebook_notion.py")
EBOOK_STUDY_EPUB_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_ebook_study_epub.py")
EBOOK_LAST_STATE_FILE = os.path.expanduser("~/.ebook_reader_last.json")
# 터미널 창 스타일링(배경/폰트/전체화면) 전용 미니 앱. launchd로 뜨는 python3는
# 자동화 권한 팝업 자체가 뜨지 않아서, 독립 .app으로 분리해 Finder에서 연 것처럼
# 만들었다 — 최초 1회 "Terminal 제어 허용?" 팝업이 뜨면 사용자가 허용해야 동작함.
STYLE_TERMINAL_APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "StyleEbookTerminal.app")

# ── 일본어자막추출 프로젝트(형제 폴더) 연동 경로 ────────────────────
JP_SUBTITLE_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "일본어자막추출", "whisper_series_stream.sh"
)
# 운동용 고음 영상 추출과 자막·번역·Notion·EPUB 단계를 하나로 묶어서 돌리면
# (JP_SUBTITLE_SCRIPT) 너무 오래 걸려서, 각각 단독으로도 실행할 수 있게 나눈
# 진입점 2개. 실제 로직은 일본어자막추출/subtitle_pipeline_body.sh에 있고
# JP_SUBTITLE_SCRIPT와 JP_SUBTITLE_STAGE2_SCRIPT가 그걸 공유해서 쓴다.
JP_SUBTITLE_STAGE2_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "일본어자막추출", "subtitle_notion_epub_only.sh"
)
JP_WORKOUT_VIDEO_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "일본어자막추출", "extract_high_pitch_video.py"
)
JP_WORKOUT_BGM_DIR = "/Users/forrestdpark/Desktop/BlogImage/BGM_DIR"
JP_LIBRARY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "일본어자막추출", "library"
)
JP_BUILD_READALOUD_EPUB_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "일본어자막추출", "build_readaloud_epub.py"
)
JP_COMPLETED_EPUB_DIR = "/Users/forrestdpark/Desktop/BlogImage/av완성작"
BGM_PLAYLIST_BATCH_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "일본어자막추출", "bgm_playlist_batch.py"
)
MP3_SHAZAM_RENAME_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "일본어자막추출", "rename_mp3_with_shazam.py"
)

# ── 손자병법 해석 파이프라인 (별도 폴더, README의 "완료된 구절" 표 참조) ──
SUNZI_README_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "손자병법", "README.md"
)


# ════════════════════════════════════════════════════════════
# 설정 저장/불러오기
# ════════════════════════════════════════════════════════════

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    # auto_mode 기본값 True: 처음 실행하면 자동으로 근무표를 따라간다
    return {"current_shift": None, "auto_mode": True, "show_earnings": True}


def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)


# ════════════════════════════════════════════════════════════
# 근무표 JSON 불러오기 + 오늘 근무 조회
# ════════════════════════════════════════════════════════════

def load_schedule():
    """d_team_schedule_2026.json 을 로드. 실패 시 빈 dict 반환."""
    try:
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_shift_for_date(schedule, date: datetime.date):
    """근무표에서 특정 날짜의 근무 코드(D/S/G/휴)를 찾아
    앱 내부 근무 이름(Day/Swing/GY/휴무)으로 변환해서 반환.
    근무표에 없는 날짜면 None 반환."""
    date_str = date.strftime("%Y-%m-%d")
    code = schedule.get(date_str)
    if code is None:
        return None
    return CODE_TO_SHIFT.get(code)


def _utf16_len(s):
    """NSRange는 UTF-16 코드 유닛 기준이라, 💾 등 서로게이트 페어를 쓰는 문자는
    Python len()(코드포인트 1개)과 어긋난다(실제 2유닛). attributedTitle 색상
    범위 계산에는 항상 이 함수로 잰 길이를 써야 한다."""
    return len(s.encode("utf-16-le")) // 2


def _shift_block_day_number(schedule, d, shift):
    """d를 포함해 shift(수동 오버라이드 반영한 오늘 표시값)가 며칠째 연속인지(1부터) 반환.
    과거 날짜는 근무표 원본(get_shift_for_date) 기준으로 센다."""
    if shift not in ("Day", "Swing", "GY", "휴무"):
        return None
    count = 1
    cursor = d - datetime.timedelta(days=1)
    while get_shift_for_date(schedule, cursor) == shift:
        count += 1
        cursor -= datetime.timedelta(days=1)
    return count


# ════════════════════════════════════════════════════════════
# 오늘 급여 계산
# ════════════════════════════════════════════════════════════

def get_active_shift_window(schedule, now, today_override=None):
    """
    현재 시각(now) 기준으로 "지금 진행 중인 근무"를 찾는다.
    GY(야간)는 어제 시작해서 오늘 새벽까지 이어질 수 있으므로
    어제/오늘 두 날짜를 모두 확인한다.

    today_override: 연차 등으로 근무표와 다르게 오늘 근무를 수동 지정한 경우
    ("Day"/"Swing"/"GY"/"휴무") 근무표 대신 이 값을 오늘 근무로 사용한다.

    반환: (shift_name, start_datetime, end_datetime) 또는 None(근무 없음/휴무)
    """
    today = now.date()
    yesterday = today - datetime.timedelta(days=1)

    # 1) 어제 시작한 GY 근무가 오늘 새벽까지 이어지는 경우
    yshift = get_shift_for_date(schedule, yesterday)
    if yshift == "GY":
        info = SHIFT_WORK_HOURS["GY"]
        start_dt = datetime.datetime.combine(yesterday, datetime.time(*info["start"]))
        end_dt = datetime.datetime.combine(today, datetime.time(*info["end"]))
        if start_dt <= now <= end_dt:
            return "GY", start_dt, end_dt

    # 2) 오늘 시작하는 근무 (Day/Swing/GY)
    tshift = today_override if today_override is not None else get_shift_for_date(schedule, today)
    if tshift in ("Day", "Swing", "GY"):
        info = SHIFT_WORK_HOURS[tshift]
        start_dt = datetime.datetime.combine(today, datetime.time(*info["start"]))
        if info["crosses_midnight"]:
            end_dt = datetime.datetime.combine(today + datetime.timedelta(days=1), datetime.time(*info["end"]))
        else:
            end_dt = datetime.datetime.combine(today, datetime.time(*info["end"]))
        if start_dt <= now <= end_dt:
            return tshift, start_dt, end_dt

    return None


# ════════════════════════════════════════════════════════════
# 근무 시간 전후 절전 방지 (SSH 원격 접속용, 2026-07-24 추가)
# ════════════════════════════════════════════════════════════
# 집 밖에서 SSH(mosh)로 접속하려면 노트북이 잠들면 안 되므로, 근무 시작 1시간
# 전부터 종료 1시간 후까지 `caffeinate -s`로 시스템 절전을 막는다.
STAY_AWAKE_MARGIN = datetime.timedelta(hours=1)
CAFFEINATE_PID_FILE = os.path.expanduser("~/.shift_alarm_caffeinate.pid")


def get_stay_awake_window(schedule, now, today_override=None):
    """get_active_shift_window와 같은 방식으로 오늘(+어제 GY) 근무를 찾되,
    시작 전 1시간부터 이미 창이 열리도록 앞뒤로 STAY_AWAKE_MARGIN만큼 패딩한다.
    반환: (근무명, 패딩된 시작, 패딩된 종료) 또는 지금이 그 범위 밖이면 None."""
    today = now.date()
    yesterday = today - datetime.timedelta(days=1)

    candidates = []

    yshift = get_shift_for_date(schedule, yesterday)
    if yshift == "GY":
        info = SHIFT_WORK_HOURS["GY"]
        start_dt = datetime.datetime.combine(yesterday, datetime.time(*info["start"])) - STAY_AWAKE_MARGIN
        end_dt = datetime.datetime.combine(today, datetime.time(*info["end"])) + STAY_AWAKE_MARGIN
        candidates.append(("GY", start_dt, end_dt))

    tshift = today_override if today_override is not None else get_shift_for_date(schedule, today)
    if tshift in ("Day", "Swing", "GY"):
        info = SHIFT_WORK_HOURS[tshift]
        start_dt = datetime.datetime.combine(today, datetime.time(*info["start"])) - STAY_AWAKE_MARGIN
        if info["crosses_midnight"]:
            end_dt = datetime.datetime.combine(today + datetime.timedelta(days=1), datetime.time(*info["end"])) + STAY_AWAKE_MARGIN
        else:
            end_dt = datetime.datetime.combine(today, datetime.time(*info["end"])) + STAY_AWAKE_MARGIN
        candidates.append((tshift, start_dt, end_dt))

    for shift, s, e in candidates:
        if s <= now <= e:
            return shift, s, e
    return None


def _caffeinate_running():
    """CAFFEINATE_PID_FILE에 적힌 pid가 실제로 살아있는 caffeinate 프로세스인지 확인."""
    if not os.path.exists(CAFFEINATE_PID_FILE):
        return False
    try:
        with open(CAFFEINATE_PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)  # 신호를 보내지 않고 존재 여부만 확인
        return True
    except Exception:
        return False


def start_caffeinate():
    """이미 떠있지 않으면 `caffeinate -s`(시스템 절전만 방지, 화면은 꺼져도 됨)를 백그라운드로 실행."""
    if _caffeinate_running():
        return
    proc = subprocess.Popen(["caffeinate", "-s"])
    with open(CAFFEINATE_PID_FILE, "w") as f:
        f.write(str(proc.pid))


def stop_caffeinate():
    """떠있는 caffeinate가 있으면 종료하고 pid 파일 정리."""
    if not os.path.exists(CAFFEINATE_PID_FILE):
        return
    try:
        with open(CAFFEINATE_PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass
    finally:
        try:
            os.remove(CAFFEINATE_PID_FILE)
        except Exception:
            pass


def calc_today_earnings(schedule, now=None, today_override=None):
    """
    지금까지 진행된 근무 시간을 기준으로 오늘 벌어들인 급여(추정치)와
    근무 완료 시 받게 될 총액을 계산해서 반환.

    반환: dict 또는 근무 없음(휴무 등)이면 None
    """
    now = now or datetime.datetime.now()
    window = get_active_shift_window(schedule, now, today_override=today_override)
    if window is None:
        return None

    shift, start_dt, end_dt = window
    elapsed = (now - start_dt).total_seconds() / 3600.0
    elapsed = max(0.0, min(elapsed, 8.0))  # 8시간 근무 기준으로 클램프

    multiplier = SHIFT_WAGE_MULTIPLIER.get(shift, 1.0)
    rate_per_hour = HOURLY_WAGE * multiplier

    earned_so_far = int(elapsed * rate_per_hour)
    total_when_done = int(8.0 * rate_per_hour)

    return {
        "shift": shift,
        "elapsed_hours": round(elapsed, 2),
        "earned_so_far": earned_so_far,
        "total_when_done": total_when_done,
    }


def get_earnings_status(schedule, now=None, today_override=None):
    """
    지금 이 순간의 급여 표시 상태를 반환.
    - state == "active":  지금 근무 중. earned_so_far / elapsed_hours / total_when_done 포함
    - state == "waiting": 오늘 근무는 예정돼 있지만 지금은 근무 시간이 아님(출근 전 등).
                          그 근무를 마치면 받게 될 total_when_done 과 시작 시각(start_time) 포함
    - state == "off":     오늘 근무표에 근무 코드가 없음(휴무) → 급여 표시 안 함

    today_override: 연차 등으로 근무표와 다르게 오늘 근무를 수동 지정한 경우 사용
    ("Day"/"Swing"/"GY"/"휴무"). "휴무"면 무조건 state == "off".
    """
    now = now or datetime.datetime.now()

    if today_override == "휴무":
        return {"state": "off"}

    info = calc_today_earnings(schedule, now, today_override=today_override)
    if info:
        return {"state": "active", **info}

    today = now.date()
    tshift = today_override if today_override is not None else get_shift_for_date(schedule, today)
    if tshift in SHIFT_WORK_HOURS:
        wh = SHIFT_WORK_HOURS[tshift]
        multiplier = SHIFT_WAGE_MULTIPLIER.get(tshift, 1.0)
        total_when_done = int(8.0 * HOURLY_WAGE * multiplier)
        start_dt = datetime.datetime.combine(today, datetime.time(*wh["start"]))
        return {"state": "waiting", "shift": tshift, "start_time": start_dt, "total_when_done": total_when_done}

    return {"state": "off"}


def format_won_short(amount):
    """메뉴바 타이틀용 짧은 금액 표기(반올림). 예: 119000 → '12만'"""
    return f"{round(amount / 10000)}만"


# ════════════════════════════════════════════════════════════
# 주간 리마인더 (헬스장 / 엄마 전화 / 카톡 정리 등)
# ════════════════════════════════════════════════════════════

def _is_off_block_start(schedule, d):
    """d가 휴무 블록의 첫날인지 (그 전날은 근무였는지) 반환."""
    return (get_shift_for_date(schedule, d) == "휴무"
            and get_shift_for_date(schedule, d - datetime.timedelta(days=1)) != "휴무")


# ── 헬스장 운영 시간 ─────────────────────────────────────────
# 평일(월~금)은 24시간, 토/일은 06:00~17:00만 운영.
GYM_WEEKEND_OPEN  = datetime.time(6, 0)
GYM_WEEKEND_CLOSE = datetime.time(17, 0)
GYM_CYCLE_ANCHOR = datetime.date(2026, 8, 3)
CALL_DONGCHAN_ANCHOR = datetime.date(2026, 8, 3)
CALL_DONGCHAN_INTERVAL_DAYS = 21
CALL_SONDONGJU_ANCHOR = datetime.date(2026, 8, 5)
CALL_SONDONGJU_INTERVAL_DAYS = 7
CODING_ACADEMY_CHAT_ANCHOR = datetime.date(2026, 8, 7)
CODING_ACADEMY_CHAT_INTERVAL_DAYS = 7
AGENTIC_CODING_READING_ANCHOR = datetime.date(2026, 8, 8)
AGENTIC_CODING_READING_INTERVAL_DAYS = 3
# 동주 본인 근무표: 야간 2주(14일) → 주간 2주(14일) 로테이션, 각 14일 블록 안에서
# 5일 근무 + 2일 휴무가 두 번 반복(5+2+5+2=14). 2026-08-04이 야간 블록의 1일째이므로
# 그 날을 14일 주기의 0번째 오프셋으로 놓으면, 주/야간 구분과 무관하게
# 블록 내 6·7일째(0-idx 5,6)와 13·14일째(0-idx 12,13)가 항상 휴무일이 된다.
SONDONGJU_SCHEDULE_ANCHOR = datetime.date(2026, 8, 4)
SONDONGJU_CYCLE_DAYS = 14
SONDONGJU_OFF_DAY_OFFSETS = (5, 6, 12, 13)
NOSE_HAIR_TRIM_ANCHOR = datetime.date(2026, 8, 3)
NOSE_HAIR_TRIM_INTERVAL_DAYS = 4  # ★ 2026-08-07: 7일→14일→4일로 재조정(사용자 요청)
NAIL_TRIM_ANCHOR = datetime.date(2026, 8, 7)
NAIL_TRIM_INTERVAL_DAYS = 14  # ★ 2026-08-07 추가: 2주에 1회
EARPHONE_CHARGE_ANCHOR = datetime.date(2026, 8, 3)
EARPHONE_CHARGE_INTERVAL_DAYS = 4
# ★ 2026-08-07: 원래 휴무 블록 시작·마지막날에만 떴는데, 휴무 블록이 뜸한 주에는
# 2만보 걷기가 아예 한 번도 안 뜨는 문제가 있었다("일주일에 2번은 있어야 하는데
# 없다"는 사용자 지적). 근무·휴무와 무관하게 7일 주기 안에서 이틀(0·3일째)
# 걷게 고정 배치해서 매주 반드시 2회씩 뜨도록 재설계.
WALK_20K_ANCHOR = datetime.date(2026, 8, 7)
WALK_20K_CYCLE_DAYS = 7
WALK_20K_OFFSETS = (0, 3)


def is_gym_open(dt):
    """주어진 시각에 헬스장이 열려있는지 (토/일만 06:00~17:00로 제한)."""
    if dt.weekday() in (5, 6):  # 5=토요일, 6=일요일
        return GYM_WEEKEND_OPEN <= dt.time() < GYM_WEEKEND_CLOSE
    return True


def _gym_time_ok(schedule, d):
    """
    d에 헬스장을 간다면(근무일이면 "근무 끝나고" 기준) 그 시각에 헬스장이 열려있는지.
    휴무일이면 언제든 갈 수 있다고 보고 항상 통과 (근무 종료 시각이라는 제약이 없으므로).
    """
    shift = get_shift_for_date(schedule, d)
    info = SHIFT_WORK_HOURS.get(shift)
    if not info:
        return True
    end_date = d + datetime.timedelta(days=1) if info["crosses_midnight"] else d
    end_dt = datetime.datetime.combine(end_date, datetime.time(*info["end"]))
    return is_gym_open(end_dt)


def _gym_cycle_index(d):
    """격일(2일 간격) 운동 주기의 회차. 운동일이 아니면 None.
    ★ 2026-08-07: 기존 3일→2일 교대 간격을 격일 고정으로 단순화(사용자 요청)."""
    days = (d - GYM_CYCLE_ANCHOR).days
    if days < 0 or days % 2 != 0:
        return None
    return days // 2


def _is_dongchan_call_day(d):
    """기준일부터 21일마다 돌아오는 동찬이형 연락일인지 반환."""
    days = (d - CALL_DONGCHAN_ANCHOR).days
    return days >= 0 and days % CALL_DONGCHAN_INTERVAL_DAYS == 0


def _is_sondongju_call_day(d):
    """기준일부터 7일마다(주 1회) 돌아오는 손동주 연락일인지 반환."""
    days = (d - CALL_SONDONGJU_ANCHOR).days
    return days >= 0 and days % CALL_SONDONGJU_INTERVAL_DAYS == 0


def _is_coding_academy_chat_day(d):
    """기준일부터 7일마다(주 1회) 돌아오는 코딩학원 카톡방 연락일인지 반환."""
    days = (d - CODING_ACADEMY_CHAT_ANCHOR).days
    return days >= 0 and days % CODING_ACADEMY_CHAT_INTERVAL_DAYS == 0


def _is_agentic_coding_reading_day(d):
    """2026-08-08부터 3일마다 돌아오는 에이전틱 코딩 책 읽기 날인지 반환."""
    days = (d - AGENTIC_CODING_READING_ANCHOR).days
    return days >= 0 and days % AGENTIC_CODING_READING_INTERVAL_DAYS == 0


def _is_sondongju_off_day(d):
    """동주 본인 근무표 기준 휴무일인지 반환(주/야간 로테이션과 무관하게
    14일 주기 내 6·7일째, 13·14일째)."""
    days = (d - SONDONGJU_SCHEDULE_ANCHOR).days
    return (days % SONDONGJU_CYCLE_DAYS) in SONDONGJU_OFF_DAY_OFFSETS


def _is_nose_hair_trim_day(d):
    """기준일부터 4일마다 돌아오는 코털 정리일인지 반환."""
    days = (d - NOSE_HAIR_TRIM_ANCHOR).days
    return days >= 0 and days % NOSE_HAIR_TRIM_INTERVAL_DAYS == 0


def _is_nail_trim_day(d):
    """기준일부터 14일(2주)마다 돌아오는 손톱발톱 정리일인지 반환."""
    days = (d - NAIL_TRIM_ANCHOR).days
    return days >= 0 and days % NAIL_TRIM_INTERVAL_DAYS == 0


def _is_walk_20k_day(d):
    """근무·휴무와 무관하게 7일 주기 안 이틀(0·3일째)에 해당하면 True — 매주 2회."""
    days = (d - WALK_20K_ANCHOR).days
    if days < 0:
        return False
    return days % WALK_20K_CYCLE_DAYS in WALK_20K_OFFSETS


def _is_earphone_charge_day(d):
    """기준일부터 4일마다 돌아오는 이어폰 충전일인지 반환."""
    days = (d - EARPHONE_CHARGE_ANCHOR).days
    return days >= 0 and days % EARPHONE_CHARGE_INTERVAL_DAYS == 0


def _is_first_off_block_start_of_month(schedule, d):
    """d가 이번 달의 '첫 번째' 휴무 블록 시작일인지 반환 (한 달에 한 번 리마인더용)."""
    if not _is_off_block_start(schedule, d):
        return False
    cursor = d.replace(day=1)
    while cursor < d:
        if _is_off_block_start(schedule, cursor):
            return False
        cursor += datetime.timedelta(days=1)
    return True


def _last_day_of_month(d):
    if d.month == 12:
        return d.replace(day=31)
    return d.replace(month=d.month + 1, day=1) - datetime.timedelta(days=1)


def _is_last_off_block_start_of_month(schedule, d):
    """d가 이번 달의 '마지막' 휴무 블록 시작일인지 반환.
    아울렛 쇼핑(첫 번째 휴무 블록)과 겹치지 않도록 나들이 추천은 마지막 블록에 배정."""
    if not _is_off_block_start(schedule, d):
        return False
    cursor = _last_day_of_month(d)
    while cursor > d:
        if _is_off_block_start(schedule, cursor):
            return False
        cursor -= datetime.timedelta(days=1)
    return True


def get_today_reminders(schedule, now=None):
    """
    오늘 근무표 기준으로 해당하는 리마인더 라벨 목록을 반환.

    - 헬스장: 근무·휴무와 무관하게 2026-08-03부터 격일(2일 간격)로 반복한다.
      상체/하체는 매회 번갈아 표시하며 운영시간 때문에 알림을 생략하지 않는다.
    - 엄마한테 전화: 오늘이 휴무 블록의 첫날 (어제는 근무였음)
    - 허민준한테 전화: 월 1회, 이번 달의 첫 번째 휴무 블록 시작일
    - 동찬이형한테 전화: 2026-08-03부터 21일마다 한 번
    - 손동주한테 전화: 2026-08-05부터 7일마다(주 1회) 한 번
    - 코딩학원 카톡방 연락: 2026-08-07부터 7일마다(주 1회) 한 번
    - 에이전틱 코딩 책 읽기: 2026-08-08(오늘)을 시작일로 3일마다 한 번
    - 손동주 쉬는 날: 동주 본인 근무표(야간 2주/주간 2주 로테이션, 5일 근무+2일 휴무
      반복) 기준. 2026-08-04(야간 첫날)를 14일 주기 1일째로 놓고 계산.
    - 코털 정리: 근무표와 무관하게 2026-08-03부터 4일마다 한 번
    - 손톱발톱 정리: 근무표와 무관하게 2026-08-07부터 14일(2주)마다 한 번
    - 이어폰 충전: 근무표와 무관하게 2026-08-03부터 4일마다 한 번
    - 카톡 정리: 오늘이 휴무 블록의 마지막날 (내일은 근무)
    - 2만보 걷기: 근무·휴무와 무관하게 2026-08-07부터 7일 주기 안 이틀(0·3일째)
      에 매주 2회(★ 2026-08-07: 휴무 블록 기준이었더니 휴무가 뜸한 주엔 안 뜨는
      문제로 재설계)
    - 빨래: 휴무일마다 매번
    - 나들이 추천: 월 1회, 이번 달의 '마지막' 휴무 블록 시작일(아울렛 쇼핑=첫 번째 블록과
      겹치지 않게). 아산시 기준 근교 명소를 매달 순환 추천. (2026-07-24 추가)
    - 소고기 구워먹는 날: 월 1회, 나들이 추천과 같은 날('마지막' 휴무 블록 시작일) —
      휴무일에 있었으면 좋겠다는 요청. (2026-08-07 추가)
    """
    now = now or datetime.datetime.now()
    today = now.date()

    reminders = []
    gym_index = _gym_cycle_index(today) if REMINDERS["gym"]["enabled"] else None
    if gym_index is not None:
        # 실제 운동 순서 기준: 2026-08-03은 하체, 다음 회차부터 상체/하체 교대.
        workout = "하체" if gym_index % 2 == 0 else "상체"
        reminders.append(f"🏋️ {workout} 운동 하는 날")

    if get_shift_for_date(schedule, today) == "휴무":
        yesterday = today - datetime.timedelta(days=1)
        tomorrow = today + datetime.timedelta(days=1)
        is_block_start = get_shift_for_date(schedule, yesterday) != "휴무"
        is_block_end = get_shift_for_date(schedule, tomorrow) != "휴무"
        if is_block_start and REMINDERS["call_mom"]["enabled"]:
            reminders.append(REMINDERS["call_mom"]["label"])
        if is_block_end and REMINDERS["kakao_cleanup"]["enabled"]:
            reminders.append(REMINDERS["kakao_cleanup"]["label"])
        if REMINDERS["laundry"]["enabled"]:
            reminders.append(REMINDERS["laundry"]["label"])

    if REMINDERS["walk_20k"]["enabled"] and _is_walk_20k_day(today):
        reminders.append(REMINDERS["walk_20k"]["label"])

    if REMINDERS["outlet_shopping"]["enabled"] and _is_first_off_block_start_of_month(schedule, today):
        reminders.append(REMINDERS["outlet_shopping"]["label"])

    if REMINDERS["call_heo_minjun"]["enabled"] and _is_first_off_block_start_of_month(schedule, today):
        reminders.append(REMINDERS["call_heo_minjun"]["label"])

    if REMINDERS["call_dongchan"]["enabled"] and _is_dongchan_call_day(today):
        reminders.append(REMINDERS["call_dongchan"]["label"])

    if REMINDERS["call_sondongju"]["enabled"] and _is_sondongju_call_day(today):
        reminders.append(REMINDERS["call_sondongju"]["label"])

    if REMINDERS["coding_academy"]["enabled"] and _is_coding_academy_chat_day(today):
        reminders.append(REMINDERS["coding_academy"]["label"])

    if REMINDERS["agentic_coding_reading"]["enabled"] and _is_agentic_coding_reading_day(today):
        reminders.append(REMINDERS["agentic_coding_reading"]["label"])

    if REMINDERS["sondongju_off"]["enabled"] and _is_sondongju_off_day(today):
        reminders.append(REMINDERS["sondongju_off"]["label"])

    if REMINDERS["nose_hair_trim"]["enabled"] and _is_nose_hair_trim_day(today):
        reminders.append(REMINDERS["nose_hair_trim"]["label"])

    if REMINDERS["nail_trim"]["enabled"] and _is_nail_trim_day(today):
        reminders.append(REMINDERS["nail_trim"]["label"])

    if REMINDERS["earphone_charge"]["enabled"] and _is_earphone_charge_day(today):
        reminders.append(REMINDERS["earphone_charge"]["label"])

    if REMINDERS["outing"]["enabled"] and _is_last_off_block_start_of_month(schedule, today):
        place = pick_monthly_outing_place(today)
        reminders.append(f"🗺️ 어디 가보자: {place}")

    if REMINDERS["beef_bbq"]["enabled"] and _is_last_off_block_start_of_month(schedule, today):
        reminders.append(REMINDERS["beef_bbq"]["label"])

    return reminders


def get_today_reminder_title_tokens(schedule, now=None):
    """메뉴바 타이틀용으로 운동 부위와 통화 대상을 짧게 표시한다."""
    tokens = []
    call_tokens = {
        REMINDERS["call_mom"]["label"]: "📞엄마",
        REMINDERS["call_heo_minjun"]["label"]: "📞민준",
        REMINDERS["call_dongchan"]["label"]: "📞동찬",
        REMINDERS["call_sondongju"]["label"]: "📞동주",
    }
    for label in get_today_reminders(schedule, now=now):
        if label.startswith("🏋️ 상체"):
            tokens.append("🏋️상")
        elif label.startswith("🏋️ 하체"):
            tokens.append("🏋️하")
        elif label in call_tokens:
            tokens.append(call_tokens[label])
        else:
            tokens.append(label.split(" ", 1)[0])
    return tokens


# ════════════════════════════════════════════════════════════
# osascript 입력창
# ════════════════════════════════════════════════════════════

def ask_input(title, message, default=""):
    """osascript로 텍스트 입력창 띄우기 → 입력값 반환 / 취소 시 None"""
    script = (
        f'tell application "System Events"\n'
        f'  activate\n'
        f'  set result to display dialog "{message}" '
        f'default answer "{default}" '
        f'with title "{title}" '
        f'buttons {{"취소", "확인"}} default button "확인"\n'
        f'  if button returned of result is "확인" then\n'
        f'    return text returned of result\n'
        f'  else\n'
        f'    return "__CANCELLED__"\n'
        f'  end if\n'
        f'end tell'
    )
    try:
        out = subprocess.check_output(["osascript", "-e", script], stderr=subprocess.DEVNULL)
        val = out.decode().strip()
        return None if val == "__CANCELLED__" else val
    except subprocess.CalledProcessError:
        return None


# ════════════════════════════════════════════════════════════
# Elmedia 폴더 재생 (m3u 없이 폴더 자체를 직접 엶)
# ════════════════════════════════════════════════════════════

def play_folder_in_elmedia(folder=PLAYLIST_FOLDER):
    """Elmedia Video Player로 음악 폴더 자체를 엶(★ 2026-08-07: 폴더를 인자로
    받게 일반화 — 기본 재생 목록과 "좋아요 플레이" 폴더를 같은 함수로 처리)."""
    if not os.path.isdir(folder):
        return False, "폴더를 찾을 수 없습니다."
    try:
        subprocess.Popen(["open", "-a", "Elmedia Video Player", folder])
        return True, "Elmedia로 폴더를 열었습니다."
    except Exception as e:
        return False, str(e)


# ════════════════════════════════════════════════════════════
# 아침 학습 (ebook_reader.py를 새 터미널 창에서 실행)
# ════════════════════════════════════════════════════════════

def load_last_ebook_state():
    """마지막으로 읽던 책 정보(~/.ebook_reader_last.json)를 불러온다. 없으면 None."""
    if not os.path.exists(EBOOK_LAST_STATE_FILE):
        return None
    try:
        with open(EBOOK_LAST_STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
        if not os.path.exists(state.get("file", "")):
            return None
        return state
    except Exception:
        return None


# ════════════════════════════════════════════════════════════
# 손자병법 해석 파이프라인 (최신 완료 구절 노션 링크)
# ════════════════════════════════════════════════════════════

def get_latest_sunzi_entry():
    """
    손자병법/README.md의 "완료된 구절" 표에서 마지막 줄(가장 최근 완료된 구절)의
    구절명 + 노션 링크를 반환. 파일이 없거나 표를 못 찾으면 None.
    """
    if not os.path.exists(SUNZI_README_PATH):
        return None
    try:
        with open(SUNZI_README_PATH, encoding="utf-8") as f:
            content = f.read()
        rows = re.findall(r'^\|\s*(.+?)\s*\|\s*\[링크\]\((https?://\S+?)\)\s*\|', content, re.MULTILINE)
        if not rows:
            return None
        title, url = rows[-1]
        return {"title": title, "url": url}
    except Exception:
        return None


def truncate_title(name, length=14):
    """메뉴바 표시용으로 파일명을 짧게 자른다 (확장자 제거 + ...말줄임)."""
    stem = os.path.splitext(name)[0]
    if len(stem) <= length:
        return stem
    return stem[:length] + "..."


def choose_ebook_file():
    """macOS 파일 선택 다이얼로그로 pdf/epub 파일을 고른다. 취소하면 None."""
    apple_script = 'POSIX path of (choose file of type {"pdf", "epub"} with prompt "읽을 파일을 선택하세요")'
    try:
        result = subprocess.run(["osascript", "-e", apple_script], capture_output=True, text=True, timeout=120)
        path = result.stdout.strip()
        return path or None
    except Exception:
        return None


# ── 운동용 영상 분량 입력용 숫자 키패드 팝업 ───────────────────────
# ★ 2026-07-24: rumps.Window의 텍스트 입력 필드가 이 환경에서 키보드
# 포커스를 못 받아 타이핑이 안 되는 문제가 있어서, 타이핑 대신 마우스
# 클릭만으로 숫자를 조합하는 커스텀 키패드 창을 PyObjC로 직접 만든다.
class _MinutesKeypadHandler(objc.lookUpClass("NSObject")):
    def initWithDisplay_initialBuffer_(self, display_field, initial_buffer):
        self = objc.super(_MinutesKeypadHandler, self).init()
        if self is None:
            return None
        self.buffer = initial_buffer
        self.result = None  # None=취소, str=확인(빈 문자열이면 호출부에서 기본값 처리)
        self.display = display_field
        return self

    def digitPressed_(self, sender):
        if len(self.buffer) < 3:  # 최대 999분
            self.buffer += sender.title()
            self.display.setStringValue_(self.buffer)

    def clearPressed_(self, sender):
        self.buffer = ""
        self.display.setStringValue_("")

    def backspacePressed_(self, sender):
        self.buffer = self.buffer[:-1]
        self.display.setStringValue_(self.buffer)

    def cancelPressed_(self, sender):
        self.result = None
        NSApp().stopModal()

    def confirmPressed_(self, sender):
        self.result = self.buffer
        NSApp().stopModal()


def show_minutes_keypad(title="운동용 영상 분량 설정", default_minutes=30):
    """숫자 키패드 팝업을 띄워 분(分) 단위 숫자를 마우스 클릭만으로 입력받는다.
    처음엔 default_minutes가 미리 채워져 있어서 그냥 확인만 눌러도 그 값으로 진행되고,
    C(지우기)/⌫(백스페이스)로 지우고 다른 숫자를 눌러 바꿀 수 있다.
    반환: 확인 시 입력한 문자열(빈 문자열이면 호출부에서 default_minutes로 처리), 취소 시 None."""
    BTN_W, BTN_H, GAP = 56, 44, 8
    grid_w = 3 * BTN_W + 2 * GAP
    panel_w = grid_w + 24
    panel_h = 330
    initial_buffer = str(default_minutes)

    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, panel_w, panel_h),
        NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
        NSBackingStoreBuffered,
        False,
    )
    panel.setTitle_(title)
    panel.center()
    # 메뉴바 앱은 일반 앱 창이 없어 activateIgnoringOtherApps_만으로는 패널이
    # 현재 사용 중인 앱의 창 뒤에 남을 수 있다. 모달 패널 레벨로 올리고
    # 비활성 상태에서도 숨기지 않아 사용자가 반드시 바로 볼 수 있게 한다.
    panel.setLevel_(NSModalPanelWindowLevel)
    panel.setHidesOnDeactivate_(False)

    content = panel.contentView()

    display = NSTextField.alloc().initWithFrame_(NSMakeRect(12, panel_h - 70, grid_w, 44))
    display.setEditable_(False)
    display.setSelectable_(False)
    display.setBezeled_(False)
    display.setDrawsBackground_(False)
    display.setAlignment_(NSTextAlignmentCenter)
    display.setFont_(NSFont.systemFontOfSize_(30))
    display.setStringValue_(initial_buffer)
    content.addSubview_(display)

    handler = _MinutesKeypadHandler.alloc().initWithDisplay_initialBuffer_(display, initial_buffer)

    rows = [["7", "8", "9"], ["4", "5", "6"], ["1", "2", "3"], ["C", "0", "⌫"]]
    grid_top_y = panel_h - 130
    for r, row in enumerate(rows):
        y = grid_top_y - r * (BTN_H + GAP)
        for c, label in enumerate(row):
            x = 12 + c * (BTN_W + GAP)
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, BTN_W, BTN_H))
            btn.setTitle_(label)
            btn.setBezelStyle_(NSRoundedBezelStyle)
            btn.setFont_(NSFont.systemFontOfSize_(18))
            if label == "C":
                btn.setTarget_(handler)
                btn.setAction_("clearPressed:")
            elif label == "⌫":
                btn.setTarget_(handler)
                btn.setAction_("backspacePressed:")
            else:
                btn.setTarget_(handler)
                btn.setAction_("digitPressed:")
            content.addSubview_(btn)

    bottom_y = grid_top_y - len(rows) * (BTN_H + GAP) - 6
    cancel_btn = NSButton.alloc().initWithFrame_(NSMakeRect(12, bottom_y, (grid_w - GAP) / 2, BTN_H))
    cancel_btn.setTitle_("취소")
    cancel_btn.setBezelStyle_(NSRoundedBezelStyle)
    cancel_btn.setTarget_(handler)
    cancel_btn.setAction_("cancelPressed:")
    content.addSubview_(cancel_btn)

    confirm_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(12 + (grid_w - GAP) / 2 + GAP, bottom_y, (grid_w - GAP) / 2, BTN_H)
    )
    confirm_btn.setTitle_("확인")
    confirm_btn.setBezelStyle_(NSRoundedBezelStyle)
    confirm_btn.setTarget_(handler)
    confirm_btn.setAction_("confirmPressed:")
    content.addSubview_(confirm_btn)

    NSApp().activateIgnoringOtherApps_(True)
    panel.makeKeyAndOrderFront_(None)
    panel.orderFrontRegardless()
    NSApp().runModalForWindow_(panel)
    panel.close()

    return handler.result


class _TextInputHandler(objc.lookUpClass("NSObject")):
    def initWithField_(self, text_field):
        self = objc.super(_TextInputHandler, self).init()
        if self is None:
            return None
        self.field = text_field
        self.result = None
        return self

    def cancelPressed_(self, sender):
        self.result = None
        NSApp().stopModal()

    def confirmPressed_(self, sender):
        self.result = self.field.stringValue()
        NSApp().stopModal()


def show_text_input_panel(title, message, default_text=""):
    """키보드 입력과 ⌘V가 확실히 동작하는 AppKit 모달 입력창."""
    panel_w, panel_h = 600, 170
    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, panel_w, panel_h),
        NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
        NSBackingStoreBuffered,
        False,
    )
    panel.setTitle_(title)
    panel.center()
    panel.setLevel_(NSModalPanelWindowLevel)
    panel.setHidesOnDeactivate_(False)
    content = panel.contentView()

    label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 118, 560, 24))
    label.setEditable_(False)
    label.setSelectable_(False)
    label.setBezeled_(False)
    label.setDrawsBackground_(False)
    label.setStringValue_(message)
    content.addSubview_(label)

    field = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 72, 560, 32))
    field.setEditable_(True)
    field.setSelectable_(True)
    field.setStringValue_(default_text)
    content.addSubview_(field)

    handler = _TextInputHandler.alloc().initWithField_(field)
    cancel_btn = NSButton.alloc().initWithFrame_(NSMakeRect(380, 18, 95, 36))
    cancel_btn.setTitle_("취소")
    cancel_btn.setBezelStyle_(NSRoundedBezelStyle)
    cancel_btn.setTarget_(handler)
    cancel_btn.setAction_("cancelPressed:")
    cancel_btn.setKeyEquivalent_("\033")
    content.addSubview_(cancel_btn)

    confirm_btn = NSButton.alloc().initWithFrame_(NSMakeRect(485, 18, 95, 36))
    confirm_btn.setTitle_("확인")
    confirm_btn.setBezelStyle_(NSRoundedBezelStyle)
    confirm_btn.setTarget_(handler)
    confirm_btn.setAction_("confirmPressed:")
    confirm_btn.setKeyEquivalent_("\r")
    content.addSubview_(confirm_btn)

    NSApp().activateIgnoringOtherApps_(True)
    panel.setInitialFirstResponder_(field)
    panel.makeKeyAndOrderFront_(None)
    panel.makeFirstResponder_(field)
    panel.orderFrontRegardless()
    field.selectText_(None)
    NSApp().runModalForWindow_(panel)
    panel.close()
    return handler.result


def choose_jp_subtitle_folder():
    """macOS 폴더 선택 다이얼로그로 일본어 영상 폴더를 고른다. 취소하면 None."""
    apple_script = 'POSIX path of (choose folder with prompt "일본어 영상이 있는 폴더를 선택하세요")'
    try:
        result = subprocess.run(["osascript", "-e", apple_script], capture_output=True, text=True, timeout=120)
        path = result.stdout.strip()
        return path or None
    except Exception:
        return None


def choose_jp_library_folder(prompt="일본어자막추출/library/<작품명> 폴더를 선택하세요"):
    """library/<작품명> 폴더를 고른다(기본 위치는 항상 library/ 폴더). 취소하면 None."""
    apple_script = (
        f'POSIX path of (choose folder with prompt "{prompt}" '
        f'default location (POSIX file "{JP_LIBRARY_DIR}"))'
    )
    try:
        result = subprocess.run(["osascript", "-e", apple_script], capture_output=True, text=True, timeout=120)
        path = result.stdout.strip()
        return path or None
    except Exception:
        return None


def choose_jp_epub_folder(
    prompt="EPUB 파일이 들어 있는 폴더를 선택하세요. 완성 파일도 이 폴더에 저장됩니다."
):
    """사용자가 실제로 보는 완성 EPUB 폴더를 고른다. 내부 library 경로는 노출하지 않는다."""
    apple_script = (
        'POSIX path of (choose folder with prompt '
        f'"{prompt}" '
        f'default location (POSIX file "{JP_COMPLETED_EPUB_DIR}"))'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", apple_script],
            capture_output=True, text=True, timeout=120,
        )
        path = result.stdout.strip()
        return path or None
    except Exception:
        return None


def run_build_readaloud_epub(epub_dir):
    """Apple Books 문장 강조·자동 페이지 넘김용 Read Aloud EPUB 생성을 실행한다."""
    if not os.path.exists(JP_BUILD_READALOUD_EPUB_SCRIPT):
        return False
    launcher = "/tmp/_jp_build_readaloud_epub.command"
    command = (
        "#!/bin/zsh\n"
        "export PATH=\"/opt/homebrew/bin:/usr/local/bin:/opt/anaconda3/bin:"
        "/usr/bin:/bin:/usr/sbin:/sbin:$PATH\"\n"
        "worker_pid=''\n"
        "cleanup() {\n"
        "  if [[ -n \"$worker_pid\" ]] && kill -0 \"$worker_pid\" 2>/dev/null; then\n"
        "    kill -TERM \"$worker_pid\" 2>/dev/null\n"
        "    wait \"$worker_pid\" 2>/dev/null\n"
        "  fi\n"
        "}\n"
        "trap cleanup HUP INT TERM EXIT\n"
        f"/opt/anaconda3/bin/python3 {shlex.quote(JP_BUILD_READALOUD_EPUB_SCRIPT)} "
        f"{shlex.quote(epub_dir)} --output-dir {shlex.quote(epub_dir)} &\n"
        "worker_pid=$!\n"
        "wait \"$worker_pid\"\n"
        "job_status=$?\n"
        "worker_pid=''\n"
        "trap - HUP INT TERM EXIT\n"
        "echo\n"
        "if [[ $job_status -eq 0 ]]; then\n"
        "  echo '✅ 낭독판 EPUB 생성 완료'\n"
        "else\n"
        "  echo '⚠️ 낭독판 EPUB 생성 실패. 위 로그를 확인하세요.'\n"
        "fi\n"
        "echo '이 창은 확인 후 닫아도 됩니다.'\n"
    )
    with open(launcher, "w", encoding="utf-8") as file:
        file.write(command)
    os.chmod(launcher, 0o700)
    subprocess.Popen(["open", "-a", "Terminal", launcher])
    return True


def run_jp_subtitle_extraction(folder_path, target_minutes=None, highlight_pad=1):
    """일본어자막추출/whisper_series_stream.sh를 백그라운드로 실행한다.
    스크립트 자체가 새 터미널 창(.command + open)을 띄우고 바로 리턴하므로,
    여기서는 그냥 fire-and-forget으로 실행만 하면 된다.
    target_minutes를 주면 TARGET_MINUTES 환경변수로 전달 — 스크립트가 운동용 영상을
    그 길이(분)에 맞춰 만들도록 extract_high_pitch_video.py --target-minutes로 넘긴다."""
    if not os.path.exists(JP_SUBTITLE_SCRIPT):
        return False
    env = os.environ.copy()
    if target_minutes:
        env["TARGET_MINUTES"] = str(target_minutes)
    env["HIGHLIGHT_PAD"] = str(highlight_pad)
    subprocess.Popen(["zsh", JP_SUBTITLE_SCRIPT, folder_path], env=env)
    return True


def run_jp_subtitle_stage2_only(folder_path):
    """운동용 영상 추출 없이 자막·번역·Notion·EPUB 단계만 실행한다.
    subtitle_notion_epub_only.sh가 스스로 새 iTerm 창을 띄우고 바로
    리턴하므로, 여기서도 fire-and-forget으로 실행만 하면 된다."""
    if not os.path.exists(JP_SUBTITLE_STAGE2_SCRIPT):
        return False
    subprocess.Popen(["zsh", JP_SUBTITLE_STAGE2_SCRIPT, folder_path])
    return True


def run_jp_workout_extraction_only(folder_path, target_minutes=None, highlight_pad=1):
    """Notion/메모/EPUB 없이 운동용 고음 영상(+배경음)만 추출한다.
    extract_high_pitch_video.py가 폴더를 그대로 받아 안의 영상을 전부
    순회하므로, 여기서는 새 Terminal 창에서 그 스크립트 한 번만 돌리면 된다."""
    if not os.path.exists(JP_WORKOUT_VIDEO_SCRIPT):
        return False
    args = [
        "/opt/anaconda3/bin/python3", shlex.quote(JP_WORKOUT_VIDEO_SCRIPT),
        shlex.quote(folder_path),
        "--bgm-dir", shlex.quote(JP_WORKOUT_BGM_DIR),
        "--bgm-volume", "0.28",
        "--pad", str(highlight_pad),
    ]
    if target_minutes:
        args += ["--target-minutes", str(target_minutes)]

    launcher = "/tmp/_jp_workout_video_only.command"
    command = (
        "#!/bin/zsh\n"
        "export PATH=\"/opt/homebrew/bin:/usr/local/bin:/opt/anaconda3/bin:"
        "/usr/bin:/bin:/usr/sbin:/sbin:$PATH\"\n"
        "worker_pid=''\n"
        "cleanup() {\n"
        "  if [[ -n \"$worker_pid\" ]] && kill -0 \"$worker_pid\" 2>/dev/null; then\n"
        "    kill -TERM \"$worker_pid\" 2>/dev/null\n"
        "    wait \"$worker_pid\" 2>/dev/null\n"
        "  fi\n"
        "}\n"
        "trap cleanup HUP INT TERM EXIT\n"
        f"{' '.join(args)} &\n"
        "worker_pid=$!\n"
        "wait \"$worker_pid\"\n"
        "job_status=$?\n"
        "worker_pid=''\n"
        "trap - HUP INT TERM EXIT\n"
        "echo\n"
        "if [[ $job_status -eq 0 ]]; then\n"
        "  echo '✅ 운동용 영상 추출 완료'\n"
        "else\n"
        "  echo '⚠️ 일부 파일이 실패했습니다. 위 로그를 확인하세요.'\n"
        "fi\n"
        "echo '이 창은 확인 후 닫아도 됩니다.'\n"
    )
    with open(launcher, "w", encoding="utf-8") as file:
        file.write(command)
    os.chmod(launcher, 0o700)
    subprocess.Popen(["open", "-a", "Terminal", launcher])
    return True


def get_trash_size_bytes():
    """휴지통 파일들의 합계 바이트를 반환한다. 읽기 실패 시 None."""
    trash_dir = os.path.expanduser("~/.Trash")
    try:
        total = 0
        for root, _dirs, files in os.walk(trash_dir):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    continue
        return total
    except Exception:
        return None


def format_file_size(total):
    """바이트 수를 알림에 적합한 B/KB/MB/GB/TB 문자열로 바꾼다."""
    value = float(max(0, total))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024


def get_trash_size_str():
    """휴지통 현재 용량을 사람이 읽기 쉬운 문자열로 반환한다.
    ★ 2026-07-31: 처음엔 `du -sh`를 subprocess로 불렀는데, 터미널에서 직접
    테스트하면 잘 되면서도 launchd가 띄운 실제 메뉴바 프로세스에서는 항상
    빈 문자열이 나왔다 — launchd GUI 에이전트는 표준 입출력 파일 디스크립터가
    없는 경우가 많아 capture_output=True가 조용히 실패하는 것으로 추정된다.
    subprocess 자체를 없애고 순수 파이썬으로 폴더 크기를 합산하도록 바꿔서
    이 환경 의존성을 없앤다.
    실패하거나 휴지통이 비어있으면 조용히 빈 문자열을 반환 — 메뉴 항목 라벨에
    괄호로 덧붙이는 용도라 실패해도 메뉴 자체는 정상 표시돼야 하기 때문."""
    total = get_trash_size_bytes()
    if total is None or total == 0:
        return ""
    return format_file_size(total)


def choose_bgm_playlist_folder():
    """곡별 MP3로 나눌 플레이리스트 MP4 폴더를 선택한다."""
    apple_script = (
        'POSIX path of (choose folder with prompt '
        '"플레이리스트 MP4 파일들이 있는 폴더를 선택하세요")'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", apple_script],
            capture_output=True, text=True, timeout=120,
        )
        path = result.stdout.strip()
        return path or None
    except Exception:
        return None


def choose_mp3_rename_folder():
    """Shazam으로 제목을 변경할 MP3 폴더를 선택한다."""
    apple_script = (
        'POSIX path of (choose folder with prompt '
        '"제목을 자동 변경할 MP3 폴더를 선택하세요")'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", apple_script],
            capture_output=True, text=True, timeout=120,
        )
        path = result.stdout.strip()
        return path or None
    except Exception:
        return None


def choose_youtube_mp3_folder():
    """YouTube에서 내려받은 MP3를 저장할 폴더를 선택한다."""
    apple_script = (
        'POSIX path of (choose folder with prompt '
        '"YouTube MP3를 저장할 폴더를 선택하세요")'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", apple_script],
            capture_output=True, text=True, timeout=120,
        )
        path = result.stdout.strip()
        return path or None
    except Exception:
        return None


def run_youtube_mp3_download(url, folder_path):
    """단일 영상 또는 재생목록을 최고 음질 MP3로 내려받는다."""
    yt_dlp = "/opt/homebrew/bin/yt-dlp"
    if not os.path.isfile(yt_dlp):
        return False, f"yt-dlp를 찾을 수 없습니다: {yt_dlp}"

    parsed_url = urlparse(url)
    playlist_ids = parse_qs(parsed_url.query).get("list", [])
    playlist_id = playlist_ids[0] if playlist_ids else ""
    is_liked_playlist = playlist_id == "LL"
    if playlist_id == "LL":
        # watch?v=...&list=LL은 재생 화면용 축약 목록(약 100개)만 돌려줄 수 있다.
        # 전체 좋아요 보관함을 읽도록 반드시 playlist 전용 URL로 정규화한다.
        download_url = "https://www.youtube.com/playlist?list=LL"
        source_label = "좋아요 표시한 동영상 전체"
    elif playlist_id:
        download_url = f"https://www.youtube.com/playlist?list={playlist_id}"
        source_label = f"재생목록 전체 ({playlist_id})"
    else:
        download_url = url
        source_label = "단일 영상"

    # 기존에 정상 동작하던 Automator 명령과 동일하게 로그인된 Chrome에서
    # 쿠키를 직접 읽는다. 수동 export 파일은 좋아요 목록용 로그인 쿠키가
    # 일부 빠져 있어 공개 영상 한 개는 되지만 list=LL 전체 조회에는 실패했다.
    # 좋아요 목록은 주소만 먼저 스냅샷한 뒤 영상마다 yt-dlp를 새로 실행한다.
    # 매 실행마다 Chrome의 최신 쿠키를 다시 읽어 장시간 배치 중 세션 회전을 피한다.
    cookie_args = ["--cookies-from-browser", "chrome"]
    target_args = (
        ["$item_url"]
        if is_liked_playlist else [download_url]
    )
    # 저장 폴더에 영구 기록을 둬 앱을 재실행해도 이미 받은 영상은 다시 받지 않는다.
    # 이전 버전으로 내려받은 MP3도 파일명의 [YouTube ID]를 읽어 기록에 편입한다.
    archive_path = os.path.join(folder_path, ".shiftalarm-youtube-download-archive.txt")
    known_ids = set()
    highest_sequence = 0
    if os.path.isfile(archive_path):
        with open(archive_path, "r", encoding="utf-8", errors="ignore") as archive_file:
            for line in archive_file:
                match = re.search(r"(?:^|\s)([\w-]{11})\s*$", line)
                if match:
                    known_ids.add(match.group(1))
    try:
        for name in os.listdir(folder_path):
            sequence_match = re.match(r"^(\d+)\s*-\s*", name)
            if sequence_match:
                highest_sequence = max(highest_sequence, int(sequence_match.group(1)))
            match = re.search(r"\[([\w-]{11})\]\.mp3$", name, re.IGNORECASE)
            if match:
                known_ids.add(match.group(1))
        with open(archive_path, "w", encoding="utf-8") as archive_file:
            for video_id in sorted(known_ids):
                archive_file.write(f"youtube {video_id}\n")
    except OSError as exc:
        return False, f"다운로드 기록을 만들 수 없습니다: {exc}"
    archive_args = ["--download-archive", archive_path]

    launcher = "/tmp/_youtube_mp3_download.command"
    filename_template = (
        "$sequence_number - %(title)s [%(id)s].%(ext)s"
        if is_liked_playlist else
        "%(playlist_index&{} - |)s%(title)s [%(id)s].%(ext)s"
    )
    output_template = os.path.join(folder_path, filename_template)
    common_args = [
        yt_dlp, *cookie_args, *archive_args,
        "--format", "bestaudio[protocol=m3u8_native]/bestaudio/best",
        "--extract-audio", "--audio-format", "mp3", "--audio-quality", "0",
        "--embed-metadata", "--embed-thumbnail", "--convert-thumbnails", "jpg",
        "--yes-playlist", "--newline", "--sleep-requests", "1",
        "--retries", "10",
        "--fragment-retries", "10", "--output", output_template,
    ]

    def quoted_command(client):
        args = common_args + [
            "--paths", "temp:$job_tmp",
            "--extractor-args", f"youtube:player_client={client}",
            *target_args,
        ]
        # $job_tmp만 셸에서 확장되어야 하므로 이 인자만 따로 조립한다.
        pieces = []
        for index, arg in enumerate(args):
            if arg == "$item_url":
                pieces.append('"$item_url"')
            elif "$sequence_number" in arg:
                before, after = arg.split("$sequence_number", 1)
                pieces.append(shlex.quote(before) + '"$sequence_number"' + shlex.quote(after))
            elif arg.startswith("$job_tmp/"):
                pieces.append('"' + arg + '"')
            elif index and args[index - 1] == "--paths":
                pieces.append('"temp:$job_tmp"')
            else:
                pieces.append(shlex.quote(arg))
        return " ".join(pieces)

    safari_command = quoted_command("web_safari")
    embedded_command = quoted_command("web_embedded")
    video_args = [
        # MP4를 받은 뒤 MP3 변환까지 성공해야 완료 기록을 남겨야 하므로
        # 이 단계에는 --download-archive를 넣지 않는다.
        yt_dlp, *cookie_args,
        "--format", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "--write-thumbnail", "--convert-thumbnails", "jpg",
        "--extractor-args", "youtube:player_client=web",
        "--yes-playlist", "--newline", "--sleep-requests", "1",
        "--retries", "10",
        "--fragment-retries", "10",
        "--output", "$job_tmp/" + filename_template,
        *target_args,
    ]
    video_pieces = []
    for arg in video_args:
        if arg == "$item_url":
            video_pieces.append('"$item_url"')
        elif arg.startswith("$job_tmp/"):
            video_pieces.append('"$job_tmp/' + arg[len("$job_tmp/"):] + '"')
        else:
            video_pieces.append(shlex.quote(arg))
    video_command = " ".join(video_pieces)
    quoted_target = shlex.quote(os.path.abspath(folder_path))
    if is_liked_playlist:
        snapshot_command = " ".join(shlex.quote(arg) for arg in [
            yt_dlp, "--cookies-from-browser", "chrome", "--flat-playlist",
            "--print", "%(webpage_url)s", download_url,
        ])
        snapshot_block = (
            "echo '📋 로그인 쿠키로 좋아요 목록 주소를 한 번만 가져옵니다.'\n"
            f"{snapshot_command} > \"$job_tmp/liked_urls.txt\"\n"
            "if [[ $? -ne 0 || ! -s \"$job_tmp/liked_urls.txt\" ]]; then\n"
            "  echo '❌ 좋아요 목록을 읽지 못했습니다. Chrome에서 YouTube에 다시 로그인하세요.'\n"
            "  exit 1\n"
            "fi\n"
            "discovered_total=$(wc -l < \"$job_tmp/liked_urls.txt\" | tr -d ' ')\n"
            "echo \"📚 YouTube 좋아요 전체 목록: ${discovered_total}개\"\n"
            "while IFS= read -r saved_url; do\n"
            "  saved_id=${saved_url#*v=}; saved_id=${saved_id%%&*}\n"
            f"  if ! grep -Fqx \"youtube $saved_id\" {shlex.quote(archive_path)}; then\n"
            "    echo \"$saved_url\" >> \"$job_tmp/pending_urls.txt\"\n"
            "  fi\n"
            "done < \"$job_tmp/liked_urls.txt\"\n"
            "mv \"$job_tmp/pending_urls.txt\" \"$job_tmp/liked_urls.txt\" 2>/dev/null || : > \"$job_tmp/liked_urls.txt\"\n"
            "total_urls=$(wc -l < \"$job_tmp/liked_urls.txt\" | tr -d ' ')\n"
            "echo \"✅ 기존 MP3 제외 완료 — 새로 받을 영상 ${total_urls}개\"\n"
            "if [[ $total_urls -eq 0 ]]; then echo '🎉 이미 전부 다운로드되어 있습니다.'; exit 0; fi\n"
        )
    else:
        snapshot_block = ""
    loop_open = (
        "success_count=0\nfailed_count=0\nitem_index=0\n"
        "while IFS= read -r item_url; do\n"
        "  [[ -z \"$item_url\" ]] && continue\n"
        "  ((item_index++))\n"
        f"  sequence_number=$(({highest_sequence} + success_count + 1))\n"
        "  echo\n"
        "  echo \"══════════ [${item_index}/${total_urls}] 새 쿠키로 개별 다운로드 ══════════\"\n"
        if is_liked_playlist else ""
    )
    loop_close = (
        "  if [[ $job_status -eq 0 ]]; then\n"
        f"    video_id=${{item_url#*v=}}; video_id=${{video_id%%&*}}; "
        f"[[ ${{#video_id}} -eq 11 ]] && echo \"youtube $video_id\" >> {shlex.quote(archive_path)}\n"
        "    ((success_count++))\n"
        "  else\n"
        "    ((failed_count++))\n"
        "  fi\n"
        "  sleep 1\n"
        "done < \"$job_tmp/liked_urls.txt\"\n"
        "echo \"📊 개별 처리 결과: 성공 ${success_count}개 · 실패 ${failed_count}개\"\n"
        "(( success_count > 0 )) && job_status=0\n"
        if is_liked_playlist else ""
    )
    command = (
        "#!/bin/zsh\n"
        "export PATH=\"/opt/homebrew/bin:/usr/local/bin:/opt/anaconda3/bin:"
        "/usr/bin:/bin:/usr/sbin:/sbin:$PATH\"\n"
        "job_tmp=$(mktemp -d /tmp/shiftalarm-youtube-mp3.XXXXXX)\n"
        "cleanup() { /bin/rm -rf -- \"$job_tmp\"; }\n"
        "trap cleanup EXIT\n"
        "trap 'cleanup; exit 130' HUP INT TERM\n"
        "echo '🎵 YouTube MP3 다운로드를 시작합니다.'\n"
        f"echo {shlex.quote('📚 대상: ' + source_label)}\n"
        f"echo '📁 저장 폴더: {folder_path.replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n"
        f"{snapshot_block}"
        f"{loop_open}"
        "echo '🌐 web_safari 방식으로 시도합니다.'\n"
        f"{safari_command}\n"
        "job_status=$?\n"
        "if [[ $job_status -ne 0 ]]; then\n"
        "  echo\n"
        "  echo '↻ 첫 시도 실패 — web_embedded 방식으로 한 번 더 시도합니다.'\n"
        f"  {embedded_command}\n"
        "  job_status=$?\n"
        "fi\n"
        "if [[ $job_status -ne 0 ]]; then\n"
        "  echo\n"
        "  echo '🎬 오디오 직접 다운로드 실패 — 영상을 받은 뒤 MP3로 변환합니다.'\n"
        "  find \"$job_tmp\" -maxdepth 1 -type f "
        "\\( -iname '*.part' -o -iname '*.jpg' -o -iname '*.webp' "
        "-o -iname '*.mp4' -o -iname '*.webm' -o -iname '*.mkv' \\) -delete 2>/dev/null\n"
        f"  {video_command}\n"
        "  job_status=$?\n"
        "  if [[ $job_status -eq 0 ]]; then\n"
        "    converted=0\n"
        "    convert_failed=0\n"
        "    while IFS= read -r -d '' media; do\n"
        "      base_name=${media:t:r}\n"
        "      cover=${media:r}.jpg\n"
        f"      destination={quoted_target}/\"$base_name.mp3\"\n"
        "      echo \"🎧 MP3 변환 중: ${media:t}\"\n"
        "      if [[ -s \"$cover\" ]]; then\n"
        "        echo '🖼️ 유튜브 썸네일을 MP3 앨범 표지로 삽입합니다.'\n"
        "        ffmpeg -y -i \"$media\" -i \"$cover\" -map 0:a:0 -map 1:v:0 "
        "-codec:a libmp3lame -q:a 2 -codec:v mjpeg -id3v2_version 3 "
        "-metadata:s:v title='Album cover' -metadata:s:v comment='Cover (front)' "
        "-disposition:v attached_pic -map_metadata 0 -threads 0 \"$destination\"\n"
        "      else\n"
        "        ffmpeg -y -i \"$media\" -vn -codec:a libmp3lame -q:a 2 "
        "-map_metadata 0 -threads 0 \"$destination\"\n"
        "      fi\n"
        "      convert_status=$?\n"
        "      if [[ $convert_status -eq 0 && -s \"$destination\" ]]; then\n"
        "        ((converted++))\n"
        "        /bin/rm -f -- "
        f"{quoted_target}/\"$base_name.jpg\" {quoted_target}/\"$base_name.webp\"\n"
        "      else\n"
        "        ((convert_failed++))\n"
        "        /bin/rm -f -- \"$destination\"\n"
        "      fi\n"
        "    done < <(find \"$job_tmp\" -maxdepth 1 -type f "
        "\\( -iname '*.mp4' -o -iname '*.webm' -o -iname '*.mkv' \\) -print0)\n"
        "    if [[ $converted -eq 0 || $convert_failed -gt 0 ]]; then\n"
        "      job_status=1\n"
        "    fi\n"
        "  fi\n"
        "fi\n"
        f"{loop_close}"
        "echo\n"
        "if [[ $job_status -eq 0 ]]; then\n"
        "  echo '✅ YouTube MP3 다운로드 완료'\n"
        "else\n"
        "  echo '⚠️ 다운로드가 실패했습니다. 위 오류를 확인하세요.'\n"
        "fi\n"
        "echo '이 창은 확인 후 닫아도 됩니다.'\n"
    )
    with open(launcher, "w", encoding="utf-8") as file:
        file.write(command)
    os.chmod(launcher, 0o700)
    subprocess.Popen(["open", "-a", "Terminal", launcher])
    return True, ""


def run_bgm_playlist_batch(folder_path):
    """선택 폴더의 MP4 전체 자동 인식·분할 작업을 Terminal에서 실행한다."""
    if not os.path.exists(BGM_PLAYLIST_BATCH_SCRIPT):
        return False
    launcher = "/tmp/_bgm_playlist_batch.command"
    command = (
        "#!/bin/zsh\n"
        "export PATH=\"/opt/homebrew/bin:/usr/local/bin:/opt/anaconda3/bin:"
        "/usr/bin:/bin:/usr/sbin:/sbin:$PATH\"\n"
        "worker_pid=''\n"
        "cleanup() {\n"
        "  if [[ -n \"$worker_pid\" ]] && kill -0 \"$worker_pid\" 2>/dev/null; then\n"
        "    kill -TERM \"$worker_pid\" 2>/dev/null\n"
        "    wait \"$worker_pid\" 2>/dev/null\n"
        "  fi\n"
        "}\n"
        "trap cleanup HUP INT TERM EXIT\n"
        f"/opt/anaconda3/bin/python3 {shlex.quote(BGM_PLAYLIST_BATCH_SCRIPT)} "
        f"{shlex.quote(folder_path)} &\n"
        "worker_pid=$!\n"
        "wait \"$worker_pid\"\n"
        "job_status=$?\n"
        "worker_pid=''\n"
        "trap - HUP INT TERM EXIT\n"
        "echo\n"
        "if [[ $job_status -eq 0 ]]; then\n"
        "  echo '✅ 모든 MP4 분할 완료'\n"
        "else\n"
        "  echo '⚠️ 일부 파일이 실패했습니다. 위 로그를 확인하세요.'\n"
        "fi\n"
        "echo '이 창은 확인 후 닫아도 됩니다.'\n"
    )
    with open(launcher, "w", encoding="utf-8") as file:
        file.write(command)
    os.chmod(launcher, 0o700)
    subprocess.Popen(["open", "-a", "Terminal", launcher])
    return True


def run_mp3_shazam_rename(folder_path):
    """선택 폴더 MP3의 Shazam 제목 변경을 Terminal에서 실행한다."""
    if not os.path.exists(MP3_SHAZAM_RENAME_SCRIPT):
        return False
    python = os.path.join(
        os.path.dirname(MP3_SHAZAM_RENAME_SCRIPT),
        ".venv-shazam", "bin", "python",
    )
    if not os.path.exists(python):
        return False
    launcher = "/tmp/_mp3_shazam_rename.command"
    command = (
        "#!/bin/zsh\n"
        "export PATH=\"/opt/homebrew/bin:/usr/local/bin:/opt/anaconda3/bin:"
        "/usr/bin:/bin:/usr/sbin:/sbin:$PATH\"\n"
        f"{shlex.quote(python)} {shlex.quote(MP3_SHAZAM_RENAME_SCRIPT)} "
        f"{shlex.quote(folder_path)}\n"
        "job_status=$?\n"
        "echo\n"
        "if [[ $job_status -eq 0 ]]; then\n"
        "  echo '✅ MP3 제목 변경 작업 완료'\n"
        "else\n"
        "  echo '⚠️ 작업이 실패했습니다. 위 로그를 확인하세요.'\n"
        "fi\n"
        "echo '이 창은 확인 후 닫아도 됩니다.'\n"
    )
    with open(launcher, "w", encoding="utf-8") as file:
        file.write(command)
    os.chmod(launcher, 0o700)
    subprocess.Popen(["open", "-a", "Terminal", launcher])
    return True


# ════════════════════════════════════════════════════════════
# 랜덤 추천 사이트 (크롬 북마크의 특정 폴더에서 무작위로 몇 개 열기)
# ════════════════════════════════════════════════════════════

CHROME_BOOKMARKS_PATH = os.path.expanduser(
    "~/Library/Application Support/Google/Chrome/Default/Bookmarks"
)
RANDOM_BOOKMARK_FOLDER = "天"  # 이 폴더 안 북마크만 대상 (전체 북마크 아님)
RANDOM_BOOKMARK_HISTORY_FILE = os.path.expanduser(
    "~/.shift_alarm_random_bookmark_history.json"
)


def _collect_all_bookmark_urls(node):
    urls = []
    if node.get("type") == "url":
        u = node.get("url")
        if u:
            urls.append(u)
    for child in node.get("children", []):
        urls.extend(_collect_all_bookmark_urls(child))
    return urls


def _find_bookmark_folder(node, target_name):
    if node.get("type") == "folder":
        if node.get("name") == target_name:
            return node
        for child in node.get("children", []):
            found = _find_bookmark_folder(child, target_name)
            if found:
                return found
    return None


def _load_random_bookmark_history(folder_name):
    """폴더별로 이전 주기에 열었던 URL을 읽는다. 손상된 기록은 빈 기록으로 복구한다."""
    try:
        with open(RANDOM_BOOKMARK_HISTORY_FILE, encoding="utf-8") as file:
            data = json.load(file)
        history = data.get(folder_name, [])
        return history if isinstance(history, list) else []
    except (OSError, ValueError, TypeError):
        return []


def _save_random_bookmark_history(folder_name, visited_urls):
    """추천 이력을 원자적으로 저장해 앱이 중간 종료돼도 파일이 깨지지 않게 한다."""
    data = {}
    try:
        with open(RANDOM_BOOKMARK_HISTORY_FILE, encoding="utf-8") as file:
            loaded = json.load(file)
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, ValueError, TypeError):
        pass

    data[folder_name] = visited_urls
    temp_path = f"{RANDOM_BOOKMARK_HISTORY_FILE}.tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(temp_path, RANDOM_BOOKMARK_HISTORY_FILE)


def pick_random_bookmarks(n=3, folder_name=RANDOM_BOOKMARK_FOLDER):
    """해당 폴더의 모든 URL을 한 번씩 추천하기 전에는 같은 URL을 다시 뽑지 않는다."""
    try:
        with open(CHROME_BOOKMARKS_PATH, encoding="utf-8") as file:
            data = json.load(file)
        roots = data.get("roots", {})
        folder = None
        for key in ("bookmark_bar", "other", "synced"):
            if key in roots:
                folder = _find_bookmark_folder(roots[key], folder_name)
                if folder:
                    break
        if not folder:
            return []
        # 같은 URL이 북마크에 중복 저장돼 있어도 추천은 한 번만 한다.
        urls = list(dict.fromkeys(_collect_all_bookmark_urls(folder)))
        if not urls:
            return []

        current_urls = set(urls)
        visited = [
            url for url in dict.fromkeys(_load_random_bookmark_history(folder_name))
            if url in current_urls
        ]
        unvisited = [url for url in urls if url not in set(visited)]

        # 이전 클릭에서 전체 목록을 모두 소진했다면 여기서 새 주기를 시작한다.
        if not unvisited:
            visited = []
            unvisited = urls

        # 마지막 묶음은 3개보다 적을 수 있다. 새 주기 URL을 섞어 채우지 않아야
        # "전체를 다 돌기 전 중복 없음" 규칙이 클릭 단위로도 명확하게 유지된다.
        selected = random.sample(unvisited, min(n, len(unvisited)))
        _save_random_bookmark_history(folder_name, visited + selected)
        return selected
    except Exception:
        return []


def open_random_bookmarks(n=3):
    """RANDOM_BOOKMARK_FOLDER(天) 폴더에서 무작위로 뽑은 북마크 URL을 크롬 새 탭으로 연다."""
    urls = pick_random_bookmarks(n)
    for url in urls:
        subprocess.Popen(["open", "-a", "Google Chrome", url])
    return urls


# ════════════════════════════════════════════════════════════
# 북마크 최신화 — krNN.도메인 형태 서브도메인 로테이션 자동 감지+교체
# (topgirl.co: kr41→kr44, sogirl.so: kr87 처럼 사이트가 주기적으로
#  서브도메인 번호를 바꾸는데, 루트 도메인(topgirl.co)엔 DNS 레코드가
#  아예 없어서 리다이렉트로는 최신 번호를 알아낼 수 없다 — 확인됨,
#  2026-07-23. 그래서 후보 번호들을 직접 접속 테스트해서 찾는다.)
# ════════════════════════════════════════════════════════════

KR_SUBDOMAIN_RE = re.compile(r'^kr(\d+)\.(.+)$')


def _resolve_kr_number(host, timeout=3):
    """host에 접속해 최종적으로 도착하는 kr번호를 반환한다. 리다이렉트를 따라가서
    실제 서비스 중인 번호까지 확인한다 — 예전엔 301 등 '뭐라도 응답만 오면' 살아있는
    걸로만 쳤는데, kr44.topgirl.co가 완전히 죽지 않고 301로 kr45.topgirl.co로
    리다이렉트하는 채로 계속 응답하는 케이스가 있어서(2026-08-04 확인) 자동 갱신이
    영영 안 걸리는 문제가 있었다. 403/503 등 에러 응답도 '서버가 응답했다'는 뜻이라
    살아있음으로 간주한다(Cloudflare 봇 차단으로 403이 오는 경우가 실제로 있었음,
    2026-07-23 확인) — 이때는 리다이렉트가 없으므로 원래 번호를 그대로 반환한다.
    DNS 실패/연결 거부/타임아웃일 때만 None(죽은 것으로 판단) — 로테이션이 끝난 옛
    서브도메인은 이렇게 응답 자체가 없는 걸로 확인됨(kr42.topgirl.co 사례)."""
    orig_match = KR_SUBDOMAIN_RE.match(host)
    orig_number = int(orig_match.group(1)) if orig_match else None
    try:
        req = urllib.request.Request(f"https://{host}", method="HEAD",
                                      headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        final_url = resp.geturl()
    except urllib.error.HTTPError as e:
        final_url = e.geturl() if e.geturl() else f"https://{host}"
    except Exception:
        return None
    final_host = urlparse(final_url).hostname or host
    m = KR_SUBDOMAIN_RE.match(final_host)
    return int(m.group(1)) if m else orig_number


def _detect_current_kr_subdomain(base_domain, known_numbers, probe_ahead=30):
    """known_numbers 중 지금도 살아있는(리다이렉트 최종 도착지 포함) 것의 최댓값을
    우선 채택. 전부 죽어있으면 그 다음 번호대(known 최댓값+1 ~ +probe_ahead)를
    탐색한다. 못 찾으면 None."""
    candidates = sorted(set(known_numbers), reverse=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        resolved = list(ex.map(lambda n: _resolve_kr_number(f"kr{n}.{base_domain}"), candidates))
    found = {n for n in resolved if n is not None}
    if found:
        return max(found)

    start = max(known_numbers) + 1
    probe_nums = list(range(start, start + probe_ahead))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        probe_resolved = list(ex.map(lambda n: _resolve_kr_number(f"kr{n}.{base_domain}"), probe_nums))
    probe_found = {n for n in probe_resolved if n is not None}
    return max(probe_found) if probe_found else None


def refresh_kr_subdomains(folder_name=RANDOM_BOOKMARK_FOLDER):
    """folder_name 폴더 안 krNN.도메인 형태 URL을 도메인별로 지금 살아있는
    번호로 일괄 교체한다. 크롬이 켜져있으면 종료 후 반영하고 다시 연다
    (켜진 채로 쓰면 크롬이 종료될 때 메모리에 있던 옛 값으로 덮어써버리므로 —
    북마크관리/fix_bookmarks.py와 동일한 문제, 동일한 해법).
    반환: {"updated": int, "detail": [str,...], "failed_domains": [str,...]} 또는 {"error": str}"""
    try:
        data = json.loads(open(CHROME_BOOKMARKS_PATH, encoding="utf-8").read())
    except Exception as e:
        return {"error": f"북마크 파일을 읽을 수 없습니다: {e}"}

    roots = data.get("roots", {})
    folder = None
    for key in ("bookmark_bar", "other", "synced"):
        if key in roots:
            folder = _find_bookmark_folder(roots[key], folder_name)
            if folder:
                break
    if not folder:
        return {"error": f'"{folder_name}" 폴더를 찾을 수 없습니다.'}

    bookmarks = []

    def _collect_nodes(node):
        if node.get("type") == "url":
            bookmarks.append(node)
        for c in node.get("children", []):
            _collect_nodes(c)

    _collect_nodes(folder)

    domains = {}
    for bm in bookmarks:
        host = urlparse(bm["url"]).hostname or ""
        m = KR_SUBDOMAIN_RE.match(host)
        if m:
            domains.setdefault(m.group(2), set()).add(int(m.group(1)))

    if not domains:
        return {"updated": 0, "detail": [], "failed_domains": []}

    updated = 0
    detail = []
    failed_domains = []
    for base, nums in domains.items():
        current = _detect_current_kr_subdomain(base, nums)
        if current is None:
            failed_domains.append(base)
            continue
        for bm in bookmarks:
            host = urlparse(bm["url"]).hostname or ""
            m = KR_SUBDOMAIN_RE.match(host)
            if m and m.group(2) == base and int(m.group(1)) != current:
                old_host, new_host = host, f"kr{current}.{base}"
                bm["url"] = bm["url"].replace(old_host, new_host, 1)
                updated += 1
                detail.append(f"{bm.get('name', '')}: {old_host} → {new_host}")

    if updated == 0:
        return {"updated": 0, "detail": [], "failed_domains": failed_domains}

    chrome_was_running = subprocess.run(
        ["pgrep", "-f", "Google Chrome$"], capture_output=True
    ).returncode == 0
    if chrome_was_running:
        subprocess.run(["osascript", "-e", 'quit app "Google Chrome"'])
        for _ in range(10):
            still_running = subprocess.run(
                ["pgrep", "-f", "Google Chrome$"], capture_output=True
            ).returncode == 0
            if not still_running:
                break
            time.sleep(1)

    shutil.copy2(CHROME_BOOKMARKS_PATH, CHROME_BOOKMARKS_PATH + ".bak")
    with open(CHROME_BOOKMARKS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=3)

    if chrome_was_running:
        subprocess.Popen(["open", "-a", "Google Chrome"])

    return {"updated": updated, "detail": detail, "failed_domains": failed_domains}


def open_ebook_reader_terminal(file_path):
    """ebook_reader.py를 새 터미널 창에서 실행 (검정 배경 + 초록 글씨, 확대 폰트 + 전체창, 볼륨 80%).

    핵심 실행은 `open`으로 .command 파일을 열어서 처리 — 이 방식은 macOS 자동화
    (Automation) 권한이 없어도 항상 동작한다 (2026-07-23 버그: launchd로 뜨는 이
    python3 프로세스에 그 권한이 없어서 예전 tell application "Terminal" 방식이
    조용히 실패했었음. 자세한 건 README 참고).

    창 스타일링(배경색/폰트 크기/전체화면)은 tell application "Terminal" 이 필요한데,
    launchd로 뜨는 python3에서 직접 osascript로 이걸 보내면 자동화 권한 팝업 자체가
    뜨지 않는다는 게 확인됐다 (2026-07-23) — 그래서 STYLE_TERMINAL_APP이라는 독립
    .app으로 분리했다. `open -a`로 앱을 여는 건 Finder에서 더블클릭한 것과 동일하게
    취급되어 팝업이 정상적으로 뜬다. 최초 1회 "Terminal을 제어하시겠습니까?" 팝업이
    뜨면 허용해야 그 뒤로 계속 스타일링이 적용된다 (허용 안 해도 리더 실행 자체는
    영향 없음 — 위 .command 부분은 이미 완료된 뒤라 항상 창은 뜬다).
    """
    py_cmd = f"{shlex.quote(EBOOK_READER_LAUNCHER)} {shlex.quote(file_path)}"
    launcher_path = "/tmp/_ebook_reader_launch.command"
    with open(launcher_path, "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\n")
        f.write("osascript -e 'set volume output volume 80' >/dev/null 2>&1\n")
        f.write(f"{py_cmd}\n")
    os.chmod(launcher_path, 0o755)
    subprocess.Popen(["open", "-a", "Terminal", launcher_path])

    if os.path.exists(STYLE_TERMINAL_APP):
        subprocess.Popen(["open", "-a", STYLE_TERMINAL_APP])


def open_ebook_notion_sync_terminal():
    """기존 Notion 독서 기록을 로컬 캐시로 내려받는 터미널 작업을 연다."""
    launcher_path = "/tmp/_ebook_notion_sync.command"
    command = f"/opt/anaconda3/bin/python3 {shlex.quote(EBOOK_NOTION_SYNC_SCRIPT)}"
    with open(launcher_path, "w", encoding="utf-8") as file:
        file.write("#!/bin/zsh\n")
        file.write(command + "\n")
        file.write("echo '이 창은 확인 후 닫아도 됩니다.'\n")
    os.chmod(launcher_path, 0o755)
    subprocess.Popen(["open", "-a", "Terminal", launcher_path])


def open_ebook_study_build_terminal(book_path):
    """선택한 책의 로컬·Notion 기록으로 학습판 EPUB을 생성한다."""
    launcher_path = "/tmp/_ebook_study_build.command"
    command = (
        f"/opt/anaconda3/bin/python3 {shlex.quote(EBOOK_STUDY_EPUB_SCRIPT)} "
        f"{shlex.quote(book_path)}"
    )
    with open(launcher_path, "w", encoding="utf-8") as file:
        file.write("#!/bin/zsh\n")
        file.write(command + "\n")
        file.write("echo '이 창은 확인 후 닫아도 됩니다.'\n")
    os.chmod(launcher_path, 0o755)
    subprocess.Popen(["open", "-a", "Terminal", launcher_path])


# ════════════════════════════════════════════════════════════
# 알람 실행 셸 스크립트 (launchd가 이 스크립트를 실행)
# ════════════════════════════════════════════════════════════

def write_alarm_script():
    """실제 알람 시 Elmedia를 새 세션으로 열어 클래식만 재생한다."""
    os.makedirs(os.path.dirname(ALARM_SCRIPT_PATH), exist_ok=True)
    script = f"""#!/bin/bash
# 교대근무 아침 알람 실행 스크립트

# 전날 재생하던 좋아요 큐가 남아 있으면 클래식과 섞이므로 Elmedia를 완전히
# 종료한 뒤 클래식 폴더만 새 인스턴스로 연다. 알람에서는 유튜브 랜덤 음악
# 단축어도 실행하지 않아 기상 음악이 클래식으로만 유지된다.
/usr/bin/killall "Elmedia Video Player" 2>/dev/null || true
/bin/sleep 1
/usr/bin/open -n -a "Elmedia Video Player" "{PLAYLIST_FOLDER}"
"""
    with open(ALARM_SCRIPT_PATH, "w") as f:
        f.write(script)
    os.chmod(ALARM_SCRIPT_PATH, 0o755)


def write_plist(hour, minute):
    write_alarm_script()
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.shfitalarm.music</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>{ALARM_SCRIPT_PATH}</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>
</dict>
</plist>"""
    with open(PLIST_PATH, "w") as f:
        f.write(plist)


def remove_plist():
    if os.path.exists(PLIST_PATH):
        subprocess.run(["launchctl", "unload", PLIST_PATH], capture_output=True)
        os.remove(PLIST_PATH)


def register_alarm(hour, minute):
    remove_plist()
    write_plist(hour, minute)
    subprocess.run(["launchctl", "load", PLIST_PATH], capture_output=True)


def unregister_alarm():
    remove_plist()


# ════════════════════════════════════════════════════════════
# 날씨
# ════════════════════════════════════════════════════════════

def get_job_collector_summary():
    """이직시스템 DB에서 (총건수, 최고점수)를 반환. DB가 없거나 비어있으면 None."""
    if not os.path.exists(JOB_COLLECTOR_DB):
        return None
    try:
        conn = sqlite3.connect(JOB_COLLECTOR_DB)
        row = conn.execute("SELECT COUNT(*), MAX(score) FROM jobs").fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    if not row or not row[0]:
        return None
    return row[0], row[1]


def _notion_keychain_token():
    """일본어자막추출/이직시스템과 동일한 키체인 항목을 재사용한다(★ 2026-08-07).
    사용자가 Notion에서 그 통합을 대상 페이지에 공유해 둬야 정상 동작한다."""
    result = subprocess.run(
        ["security", "find-generic-password", "-a", os.environ.get("USER", ""),
         "-s", "jp_subtitle_notion_token", "-w"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def get_top_job_analysis(category="career"):
    """job_collector.py analyze-top --category가 써 둔 상태 파일을 읽는다. 없거나
    깨졌으면 None — 메뉴에서 항목을 아예 생략한다(★ 2026-08-08: career/parttime
    카테고리별 파일로 분리)."""
    path = JOB_TOP_ANALYSIS_STATE[category]
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def get_top_contest_analysis(category="general"):
    """contest_collector.py analyze-top --category가 써 둔 상태 파일을 읽는다
    (★ 2026-08-07 추가, 2026-08-08 카테고리 분리). 없거나 깨졌으면 None —
    메뉴에서 항목을 아예 생략한다."""
    path = CONTEST_TOP_ANALYSIS_STATE[category]
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def fetch_weather():
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={LATITUDE}&longitude={LONGITUDE}"
            f"&current=temperature_2m,precipitation_probability"
            f"&timezone=Asia/Seoul"
        )
        with urllib.request.urlopen(url, timeout=5) as res:
            data = json.loads(res.read())
        temp = round(data["current"]["temperature_2m"])
        rain = data["current"]["precipitation_probability"]
        icon = "雨" if rain >= 50 else "曇" if rain >= 20 else "晴"
        return {"icon": icon, "text": f"{temp}°C 🌧{rain}%"}
    except Exception:
        return None


# ════════════════════════════════════════════════════════════
# AI(Codex/Claude) 사용량 표시용 포맷팅
# ════════════════════════════════════════════════════════════

def _ai_window_label(window_minutes):
    if not window_minutes:
        return "?"
    hours = window_minutes / 60
    if hours < 24:
        return f"{hours:.0f}시간" if hours == int(hours) else f"{hours:.1f}시간"
    days = hours / 24
    return f"{days:.0f}일" if days == int(days) else f"{days:.1f}일"


def _quota_window_progress(info, now=None):
    """quota 윈도우의 현재 진행일과 전체 일수를 ``(현재, 전체)``로 반환한다.

    Codex가 기록한 ``resets_at``에서 ``window_minutes``를 빼 시작 시각을 구한다.
    둘 중 하나라도 없거나 하루 미만의 윈도우면 표시하지 않는다.
    """
    if not info:
        return None
    window_minutes = info.get("window_minutes")
    resets_at = info.get("resets_at")
    if not window_minutes or not resets_at or window_minutes < 24 * 60:
        return None
    now = time.time() if now is None else now
    window_seconds = window_minutes * 60
    started_at = resets_at - window_seconds
    total_days = max(1, math.ceil(window_minutes / (24 * 60)))
    current_day = math.floor((now - started_at) / (24 * 60 * 60)) + 1
    current_day = min(total_days, max(1, current_day))
    return current_day, total_days


def format_codex_usage(quota):
    """값을 못 가져오면 추측하지 않고 '확인 불가'로 표시."""
    if not quota:
        return "🪙 Codex: 확인 불가"
    parts = []
    for key in ("primary", "secondary"):
        info = quota.get(key)
        if not info or info.get("used_percent") is None:
            continue
        part = f"{_ai_window_label(info.get('window_minutes'))} {info['used_percent']:.0f}%"
        progress = _quota_window_progress(info)
        if progress:
            part += f" ({progress[0]}/{progress[1]}일째)"
        parts.append(part)
    return f"🪙 Codex: {' · '.join(parts)}" if parts else "🪙 Codex: 확인 불가"


def _claude_seven_day_progress(resets_at: str) -> str:
    """seven_day(주간) 윈도우의 resets_at으로부터 "7일 중 N일째"를 계산한다.
    (★ 2026-08-08: 사용률 %만으로는 이번 주 사용 페이스를 가늠하기 어렵다는
    피드백으로 추가 — 예: 3일째에 48%면 아직 여유, 6일째에 48%면 절약 모드.)"""
    if not resets_at:
        return ""
    try:
        reset_dt = datetime.datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc)
        window_start = reset_dt - datetime.timedelta(days=7)
        day_number = int((now - window_start).total_seconds() // 86400) + 1
        day_number = min(7, max(1, day_number))
        return f"({day_number}/7일째)"
    except (ValueError, TypeError):
        return ""


def format_claude_live_usage(data):
    """값을 못 가져오면 추측하지 않고 '확인 불가'로 표시."""
    if not data:
        return "🪙 Claude: 확인 불가"
    parts = []
    for key, val in data.items():
        if not isinstance(val, dict):
            continue
        util = val.get("utilization")
        if util is None:
            continue
        label = f"{key.replace('_', ' ')} {util:.0f}%"
        if key == "seven_day":
            progress = _claude_seven_day_progress(val.get("resets_at"))
            if progress:
                label = f"{label} {progress}"
        parts.append(label)
    return f"🪙 Claude: {' · '.join(parts)}" if parts else "🪙 Claude: 확인 불가"


def format_claude_local_stats(stats):
    """값을 못 가져오면 추측하지 않고 '확인 불가'로 표시."""
    if not stats:
        return "🪙 Claude 로컬: 확인 불가"
    parts = [stats["model"] or "모델 미상", f"턴 {stats['user_turns']}", f"요청 {stats['model_requests']}"]
    if stats.get("cache_hit_percent") is not None:
        parts.append(f"캐시 {stats['cache_hit_percent']}%")
    return f"🪙 Claude 로컬: {' · '.join(parts)}"


CLAUDE_WEEKLY_CRITICAL_PERCENT = 90
CODEX_LIGHT_PURPLE_COLOR = NSColor.colorWithCalibratedRed_green_blue_alpha_(
    0.79, 0.65, 1.0, 1.0
)


def _codex_weekly_critical(quota):
    """현재 진행일까지의 Codex 누적 권장량을 모두 사용했는지.

    7일 윈도우라면 1일째 14.3%, 2일째 28.6%, …, 7일째 100%가
    경고선이다. resets_at이 없어 진행일을 계산할 수 없으면 경고하지 않는다.
    """
    if not quota:
        return False
    primary = quota.get("primary")
    if not primary:
        return False
    pct = primary.get("used_percent")
    progress = _quota_window_progress(primary)
    if pct is None or not progress:
        return False
    current_day, total_days = progress
    threshold = current_day * 100.0 / total_days
    return pct >= threshold


def _claude_weekly_critical(data):
    """Claude 라이브 quota 중 주간(키 이름에 'day' 포함, 예: seven_day) 윈도우가
    90% 이상인지."""
    if not data:
        return False
    for key, val in data.items():
        if not isinstance(val, dict) or "day" not in key.lower():
            continue
        util = val.get("utilization")
        if util is not None and util >= CLAUDE_WEEKLY_CRITICAL_PERCENT:
            return True
    return False


def _codex_primary_percent(quota):
    """메뉴바 타이틀에 바로 찍을 Codex 대표 숫자(주간 primary 사용률)."""
    if not quota:
        return None
    primary = quota.get("primary")
    if not primary:
        return None
    return primary.get("used_percent")


def _codex_primary_window_progress(quota):
    """메뉴바·위젯에 표시할 Codex 주간 윈도우 진행일."""
    if not quota:
        return None
    return _quota_window_progress(quota.get("primary"))


def _claude_five_hour_percent(data):
    """메뉴바 타이틀에 바로 찍을 Claude 대표 숫자(5시간 윈도우 사용률)."""
    if not data:
        return None
    for key, val in data.items():
        if isinstance(val, dict) and "hour" in key.lower():
            util = val.get("utilization")
            if util is not None:
                return util
    return None


def _set_menu_item_color(menu_item, text, color):
    """MenuItem 표시 텍스트에 색을 입힌다(NSMenuItem.attributedTitle 직접 조작).
    color가 None이면 기본색(plain title)으로 표시.
    NSMenuItem을 건드리므로 반드시 메인 스레드에서 실행돼야 한다(2026-08-05 실측 크래시)."""
    if threading.current_thread() is not threading.main_thread():
        AppHelper.callAfter(_set_menu_item_color, menu_item, text, color)
        return
    menu_item.title = text
    if color is None:
        return
    attributed = NSMutableAttributedString.alloc().initWithString_(text)
    attributed.addAttribute_value_range_(
        NSForegroundColorAttributeName, color, NSRange(0, _utf16_len(text))
    )
    menu_item._menuitem.setAttributedTitle_(attributed)


def _build_reminder_status_menu_item(today_reminders, callback, checklist_state=None):
    """"🔔 오늘: ..." 항목을 만든다. 콜백이 없으면 NSMenu가 자동으로 회색/비활성
    표시하는데(★ 2026-08-07 사용자가 "회색으로 표기된다"고 지적한 원인), 콜백을
    지정해 클릭 가능하게 하고(일일 체크리스트 Notion 링크로 이동), 리마인더마다
    REMINDER_MENU_COLOR_CYCLE을 순환시켜 알록달록하게 색을 입힌다.
    ★ 2026-08-08: checklist_state({라벨: checked})가 있으면 각 항목 앞에 ✅/⬜를
    붙여서 휴대폰 Notion에서 체크한 상태가 메뉴바에도 보이게 한다."""
    checklist_state = checklist_state or {}
    if not today_reminders:
        return rumps.MenuItem("🔔 오늘 예정된 리마인더 없음", callback=callback)
    prefix = "🔔 오늘: "
    display_tokens = [
        f"{'✅' if checklist_state.get(label) else '⬜'} {label}" for label in today_reminders
    ]
    text = prefix + " / ".join(display_tokens)
    item = rumps.MenuItem(text, callback=callback)
    attributed = NSMutableAttributedString.alloc().initWithString_(text)
    offset = _utf16_len(prefix)
    for i, token in enumerate(display_tokens):
        color_fn = REMINDER_MENU_COLOR_CYCLE[i % len(REMINDER_MENU_COLOR_CYCLE)]
        token_len = _utf16_len(token)
        attributed.addAttribute_value_range_(
            NSForegroundColorAttributeName, color_fn(), NSRange(offset, token_len)
        )
        offset += token_len + _utf16_len(" / ")
    item._menuitem.setAttributedTitle_(attributed)
    return item


# ════════════════════════════════════════════════════════════
# 메뉴바 앱
# ════════════════════════════════════════════════════════════

class ShiftAlarmApp(rumps.App):
    def __init__(self):
        global HOURLY_WAGE
        config = load_config()
        if "shift_times" in config:
            for shift, t in config["shift_times"].items():
                if shift in SHIFT_TIMES and t:
                    SHIFT_TIMES[shift] = t
        if "hourly_wage" in config:
            HOURLY_WAGE = config["hourly_wage"]
        if "reminders_enabled" in config:
            for key, enabled in config["reminders_enabled"].items():
                if key in REMINDERS:
                    REMINDERS[key]["enabled"] = enabled

        self.config = config
        self.schedule = load_schedule()
        self.storage_free_gb = get_free_storage_gb()
        self._last_storage_warning_date = None

        current = config.get("current_shift")
        title = f"⏰ {current}" if current else "⏰ 근무미설정"
        super().__init__(title, quit_button=None)

        self.weather_str = ""
        self.weather_icon = ""
        self._codex_quota = None
        self._claude_live_quota = None
        self.earnings_item = rumps.MenuItem("오늘 급여: -")
        self.weather_item = rumps.MenuItem("날씨: 로딩 중")
        self.stay_awake_item = rumps.MenuItem("🌙 절전 방지: 확인 중...")
        self.codex_usage_item = rumps.MenuItem("🪙 Codex: 확인 중...")
        self.claude_usage_item = rumps.MenuItem("🪙 Claude: 확인 중...")
        self.claude_stats_item = rumps.MenuItem("🪙 Claude 로컬: 확인 중...")
        # build_menu()가 바로 이어서 _checklist_state를 참조하므로 그 전에 초기화해둔다.
        self._checklist_state = self._load_cached_checklist_state()
        self.build_menu()

        # 날씨 10분마다 갱신
        self.weather_timer = rumps.Timer(self._refresh_weather, 600)
        self.weather_timer.start()
        threading.Thread(target=self._init_weather, daemon=True).start()

        # 자동 모드면, 앱 시작 시 바로 오늘 근무로 맞춘다
        if self.config.get("auto_mode", True):
            self.apply_today_shift(notify=False)

        # 매일 자정(00:01)에 오늘 근무를 다시 계산해서 자동 적용
        self.midnight_timer = rumps.Timer(self._check_midnight, 60)
        self.midnight_timer.start()
        self._last_checked_date = datetime.date.today()

        # 근무별 "전자제품 전원 끄기" 알람 (1분마다 시각 체크)
        self._last_electronics_off_notified = None
        self.electronics_off_timer = rumps.Timer(self._check_electronics_off, 60)
        self.electronics_off_timer.start()

        # 5분마다 메뉴 재빌드 — 손자병법 최신 링크, 이북 이어하기 등
        # 외부(클라우드 루틴 등)에서 파일이 갱신돼도 자정까지 기다리지 않고 반영되게
        self.menu_refresh_timer = rumps.Timer(self._periodic_menu_refresh, 300)
        self.menu_refresh_timer.start()

        # 저장공간은 5분마다 확인하고 메뉴바에 정수 GB로 표시한다.
        self.storage_timer = rumps.Timer(self._check_storage, 300)
        self.storage_timer.start()
        self._check_storage(None)

        # 북마크 krNN 서브도메인은 앱 시작 시와 6시간마다
        # 백그라운드에서 확인한다. 실제 변경이 있을 때만 알림한다.
        self._bookmark_refresh_running = False
        self.bookmark_refresh_timer = rumps.Timer(
            self._auto_refresh_bookmarks, 6 * 60 * 60
        )
        self.bookmark_refresh_timer.start()
        self._auto_refresh_bookmarks(None)

        # 급여 실시간 갱신 (30초마다)
        self.earnings_timer = rumps.Timer(self._refresh_earnings, 30)
        self.earnings_timer.start()
        self._refresh_earnings(None)

        # 근무 전후 1시간 절전 방지 (SSH 접속용, 1분마다 체크)
        self.stay_awake_timer = rumps.Timer(self._check_stay_awake, 60)
        self.stay_awake_timer.start()
        self._check_stay_awake(None)

        # 오늘의 리마인더 알림 (앱 시작 시 한 번)
        self._last_reminder_notified = None
        self._maybe_notify_reminders()

        # ★ 2026-08-08: 휴대폰 Notion에서 체크한 상태를 1분마다 당겨와 메뉴바/
        # 위젯에 반영한다(초기값은 위 build_menu() 전에 이미 로드해둠).
        self.checklist_timer = rumps.Timer(self._refresh_checklist_state, CHECKLIST_SYNC_INTERVAL_SECONDS)
        self.checklist_timer.start()
        self._refresh_checklist_state(None)

        # Codex/Claude 사용량(quota) 12분마다 갱신 + 앱 시작 시 1회
        self.ai_usage_timer = rumps.Timer(self._refresh_ai_usage, AI_USAGE_NORMAL_INTERVAL)
        self.ai_usage_timer.start()
        self._refresh_ai_usage(None)

        # 이직시스템(job_collector.py) 공고 수집을 하루 1번 자동 실행한다.
        # 마지막 실행 시각을 config에 저장해두고 그로부터 24시간이 안 지났으면
        # 건너뛴다 — 앱을 자주 재시작해도 사람인 서버에 매번 요청하지 않게.
        self._job_collector_running = False
        self.job_collector_timer = rumps.Timer(
            self._refresh_job_collector, JOB_COLLECTOR_REFRESH_SECONDS
        )
        self.job_collector_timer.start()
        self._refresh_job_collector(None)

    # ── 날씨 ────────────────────────────────────────────────

    def _init_weather(self):
        # 네트워크 조회는 백그라운드 스레드에서, AppKit(메뉴/타이틀) 갱신은 반드시
        # 메인 스레드에서 — 백그라운드 스레드가 NSStatusItem/NSMenuItem의
        # attributedTitle을 직접 건드리면 CALayer 커밋 시점에 EXC_BREAKPOINT로
        # 크래시할 수 있다(2026-08-05 실측 확인).
        weather = fetch_weather()
        AppHelper.callAfter(self._apply_weather, weather)

    def _apply_weather(self, weather):
        if weather:
            self.weather_str = weather["text"]
            self.weather_icon = weather["icon"]
            self.weather_item.title = f"날씨: {self.weather_str}"
        else:
            self.weather_str = ""
            self.weather_icon = ""
            self.weather_item.title = "날씨: 조회 실패"
        self._update_title()

    def _refresh_weather(self, _):
        threading.Thread(target=self._init_weather, daemon=True).start()

    # ── AI(Codex/Claude) 사용량 ──────────────────────────────

    def _refresh_ai_usage(self, _):
        threading.Thread(target=self._fetch_ai_usage, daemon=True).start()

    def _fetch_ai_usage(self):
        # 네트워크/파일 조회는 백그라운드 스레드에서, AppKit(메뉴 항목) 갱신은
        # 반드시 메인 스레드에서 — _apply_ai_usage로 넘겨서 처리한다.
        codex_quota = ai_usage.get_codex_quota()
        claude_live = ai_usage.get_claude_live_quota()
        claude_local = ai_usage.get_claude_local_stats()
        AppHelper.callAfter(self._apply_ai_usage, codex_quota, claude_live, claude_local)

    def _apply_ai_usage(self, codex_quota, claude_live, claude_local):
        codex_color = (
            NSColor.systemRedColor() if _codex_weekly_critical(codex_quota)
            else CODEX_LIGHT_PURPLE_COLOR
        )
        _set_menu_item_color(self.codex_usage_item, format_codex_usage(codex_quota), codex_color)

        claude_color = (
            NSColor.systemRedColor() if _claude_weekly_critical(claude_live)
            else NSColor.systemOrangeColor()
        )
        _set_menu_item_color(self.claude_usage_item, format_claude_live_usage(claude_live), claude_color)

        self.claude_stats_item.title = format_claude_local_stats(claude_local)

        # 라이브 조회 실패 시(토큰 만료 등) 다음 claude 세션이 열리는 즉시 몇
        # 분 안에 자동 복구되도록 재시도 주기를 짧게, 성공하면 원래대로.
        self.ai_usage_timer.interval = (
            AI_USAGE_RETRY_INTERVAL if claude_live is None else AI_USAGE_NORMAL_INTERVAL
        )

        # 메뉴바 타이틀 자체에도 사용률 숫자를 바로 보이게 캐시해서 반영한다.
        self._codex_quota = codex_quota
        self._claude_live_quota = claude_live
        self._update_title()

    def _today_override(self):
        """자동 모드가 꺼져있으면(연차 등으로 수동 지정) 근무표 대신 쓸 오늘 근무값."""
        if self.config.get("auto_mode", True):
            return None
        return self.config.get("current_shift")

    def _update_title(self):
        # NSStatusItem의 attributedTitle을 건드리므로 반드시 메인 스레드에서 실행돼야
        # 한다(백그라운드 스레드에서 부르면 CALayer 커밋 시점에 EXC_BREAKPOINT로
        # 크래시할 수 있음 — 2026-08-05 실측). 백그라운드 스레드에서 호출됐으면
        # 메인 스레드로 다시 스케줄링하고 즉시 반환.
        if threading.current_thread() is not threading.main_thread():
            AppHelper.callAfter(self._update_title)
            return

        # 메뉴바 아이콘이 많으면 macOS가 긴 타이틀을 통째로 숨겨버릴 수 있으므로
        # 타이틀은 최대한 짧게 유지한다. 자동모드 여부/정확한 금액 등 자세한 정보는
        # 메뉴 항목(드롭다운)과 "현재 설정 확인"에서 확인.
        current = self.config.get("current_shift")
        code = SHIFT_TO_SHORT_CODE.get(current, current or "?")

        # ★ 2026-07-24: 공백 없이 이어붙이면(특히 휴무일처럼 리마인더가 여러 개
        # 동시에 뜨는 날) 이모지들이 서로 겹쳐 보여 찌그러진 것처럼 보였다.
        # ★ 2026-08-07: 리마인더가 몰리는 날(월초 휴무 시작일 등)은 최대 8개까지
        # 겹쳐서 타이틀 전체가 macOS에 의해 통째로 숨겨지는 문제가 실제로 발생함
        # (예: 2026-08-09에 8개 동시 발생 확인). 타이틀에는 최대 3개만 보여주고
        # 나머지는 "+N"으로 압축한다 — 전체 목록은 드롭다운 메뉴에서 계속 확인 가능.
        _reminder_tokens = get_today_reminder_title_tokens(self.schedule)
        _REMINDER_TITLE_LIMIT = 3
        if len(_reminder_tokens) > _REMINDER_TITLE_LIMIT:
            _reminder_tokens = _reminder_tokens[:_REMINDER_TITLE_LIMIT] + [
                f"+{len(_reminder_tokens) - _REMINDER_TITLE_LIMIT}"
            ]
        reminder_icons = " ".join(_reminder_tokens)

        # ★ 2026-08-07: 이모지 없이 숫자만 표시하고, 항상 초록색(부족 시에만 빨강)으로
        # 색을 입혀서 이모지 없이도 한눈에 저장공간 항목인지 구분되게 했다.
        storage_num = self.storage_free_gb
        storage = str(storage_num) if storage_num is not None else ""

        day_num = (
            _shift_block_day_number(self.schedule, datetime.date.today(), current)
            if current else None
        )
        shift_code_text = f"{code}{day_num}" if day_num is not None else (code if current else "미설정")
        # 날씨 한자는 근무 표기 바로 뒤에 "-"로 이어붙인다 (예: "G3-雨").
        shift_text = f"{shift_code_text}-{self.weather_icon}" if self.weather_icon else shift_code_text

        # 근무 며칠째 숫자(GY=노랑/휴무=빨강), 비 오는 날 날씨 한자(파랑) 색.
        shift_color = None
        if day_num is not None:
            if current == "GY":
                shift_color = NSColor.systemYellowColor()
            elif current == "휴무":
                shift_color = NSColor.systemRedColor()
        weather_color = NSColor.systemBlueColor() if self.weather_icon == "雨" else None

        shift_inner = []
        if shift_color is not None:
            num_str = str(day_num)
            start = _utf16_len(shift_code_text) - _utf16_len(num_str)
            shift_inner.append((start, _utf16_len(num_str), shift_color))
        if weather_color is not None:
            start = _utf16_len(shift_code_text) + 1  # "-" 건너뛰기
            shift_inner.append((start, _utf16_len(self.weather_icon), weather_color))

        # 저장공간 숫자는 항상 색을 입힌다 — 평소엔 초록, 부족 시(5GB 이하)만 빨강.
        storage_inner = []
        if storage_num is not None:
            color = (
                NSColor.systemRedColor() if storage_num <= LOW_STORAGE_WARNING_GB
                else NSColor.systemGreenColor()
            )
            storage_inner.append((0, _utf16_len(storage), color))

        # Codex/Claude 사용량을 드롭다운을 열지 않아도 보이도록 상태창 타이틀에 바로
        # "94% 61%" 형태로 표시한다. 순서는 Codex(연보라) → Claude(오렌지)이며,
        # Codex는 현재 진행일까지의 누적 권장량(1일째 14.3%, 2일째 28.6% …)을
        # 다 쓰면, Claude는 주간 윈도우가 90% 이상이면 빨강으로 경고한다.
        codex_pct = _codex_primary_percent(self._codex_quota)
        codex_token = f"{codex_pct:.0f}%" if codex_pct is not None else ""
        codex_color = (
            NSColor.systemRedColor() if _codex_weekly_critical(self._codex_quota)
            else CODEX_LIGHT_PURPLE_COLOR
        )

        claude_pct = _claude_five_hour_percent(self._claude_live_quota)
        claude_token = f"{claude_pct:.0f}%" if claude_pct is not None else ""
        claude_color = (
            NSColor.systemRedColor() if _claude_weekly_critical(self._claude_live_quota)
            else NSColor.systemOrangeColor()
        )

        segments = [
            (shift_text, shift_inner),
            (storage, storage_inner),
            (reminder_icons, []),
            (codex_token, [(0, _utf16_len(codex_token), codex_color)] if codex_token else []),
            (claude_token, [(0, _utf16_len(claude_token), claude_color)] if claude_token else []),
        ]

        self.title = " ".join(text for text, _ in segments if text)

        # rumps의 title setter가 setTitle_()을 호출해 attributedTitle을 초기화시키므로,
        # 반드시 plain title을 먼저 설정한 뒤 setAttributedTitle_()로 덮어써야 한다.
        if not any(inner for _, inner in segments):
            self._write_mobile_status()
            return

        # NSRange는 UTF-16 코드 유닛 기준이라, 💾 같은 서로게이트 페어 문자는
        # Python len()과 어긋난다(1글자인데 2유닛). 반드시 _utf16_len()으로 잰다.
        full_title = self.title
        attributed = NSMutableAttributedString.alloc().initWithString_(full_title)
        offset = 0
        for text, inner_ranges in segments:
            if not text:
                continue
            for local_start, local_len, color in inner_ranges:
                attributed.addAttribute_value_range_(
                    NSForegroundColorAttributeName, color, NSRange(offset + local_start, local_len)
                )
            offset += _utf16_len(text) + 1
        try:
            self._nsapp.nsstatusitem.setAttributedTitle_(attributed)
        except AttributeError:
            pass

        self._write_mobile_status()

    def _write_mobile_status(self):
        """오늘의 근무/리마인더/날씨 요약을 iCloud Drive(ShiftAlarmStatus 폴더 +
        Pythonista + Scriptable iCloud Documents 폴더)에 JSON으로 써서 아이폰에서
        읽어갈 수 있게 한다. 실패해도 메뉴바 앱 동작에는 영향 없음."""
        current = self.config.get("current_shift")
        today = datetime.date.today()
        day_num = (
            _shift_block_day_number(self.schedule, today, current) if current else None
        )
        sunzi_entry = get_latest_sunzi_entry()
        # ★ 2026-08-08: 카테고리별(커리어/알바, AI/일반) 2건씩 배열로 넘긴다.
        job_items = []
        for category, cat_label in JOB_CATEGORIES.items():
            top_job = get_top_job_analysis(category)
            if top_job:
                job_items.append({
                    "category": category, "label": cat_label,
                    "company": top_job.get("company"), "title": top_job.get("title"),
                    "score": top_job.get("score"), "url": top_job.get("job_url"),
                    "notion_url": top_job.get("url"),
                })
        contest_items = []
        for category, cat_label in CONTEST_CATEGORIES.items():
            top_contest = get_top_contest_analysis(category)
            if top_contest:
                contest_items.append({
                    "category": category, "label": cat_label,
                    "organizer": top_contest.get("organizer"), "title": top_contest.get("title"),
                    "score": top_contest.get("score"), "url": top_contest.get("contest_url"),
                    "notion_url": top_contest.get("url"),
                })
        codex_progress = _codex_primary_window_progress(self._codex_quota)
        status = {
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "date": today.isoformat(),
            "shift": current,
            "shift_day_number": day_num,
            "weather": self.weather_str or None,
            "reminders": get_today_reminders(self.schedule),
            "reminders_checked": self._checklist_state,
            "storage_free_gb": self.storage_free_gb,
            "earnings_short": self._earnings_short_text(),
            "codex_percent": _codex_primary_percent(self._codex_quota),
            "codex_window_day": codex_progress[0] if codex_progress else None,
            "codex_window_days": codex_progress[1] if codex_progress else None,
            "codex_critical": _codex_weekly_critical(self._codex_quota),
            "claude_percent": _claude_five_hour_percent(self._claude_live_quota),
            "claude_critical": _claude_weekly_critical(self._claude_live_quota),
            "sunzi_title": sunzi_entry["title"] if sunzi_entry else None,
            "sunzi_url": sunzi_entry["url"] if sunzi_entry else None,
            "job_items": job_items,
            "contest_items": contest_items,
        }
        for target_dir, target_file in (
            (MOBILE_STATUS_DIR, MOBILE_STATUS_FILE),
            (PYTHONISTA_ICLOUD_DIR, PYTHONISTA_STATUS_FILE),
            (SCRIPTABLE_ICLOUD_DIR, SCRIPTABLE_STATUS_FILE),
        ):
            try:
                os.makedirs(target_dir, exist_ok=True)
                tmp_path = target_file + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(status, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, target_file)
            except OSError:
                continue

    # ── 저장공간 ─────────────────────────────────────────────

    def _check_storage(self, _):
        self.storage_free_gb = get_free_storage_gb()
        self._update_title()
        today = datetime.date.today()
        if (
            self.storage_free_gb is not None
            and self.storage_free_gb <= LOW_STORAGE_WARNING_GB
            and self._last_storage_warning_date != today
        ):
            self._last_storage_warning_date = today
            rumps.notification(
                "💾 저장공간 부족",
                f"남은 용량 {self.storage_free_gb}GB",
                "5GB 이하입니다. Shift Alarm 메뉴의 '저장공간 관리'로 정리해주세요.",
            )

    # ── 급여 갱신 ────────────────────────────────────────────

    def _refresh_earnings(self, _):
        status = get_earnings_status(self.schedule, today_override=self._today_override())
        if status["state"] == "active":
            self.earnings_item.title = (
                f"💰 오늘 급여: {status['earned_so_far']:,}원 "
                f"(근무 {status['elapsed_hours']}h / 완료 시 {status['total_when_done']:,}원)"
            )
        elif status["state"] == "waiting":
            start_str = status["start_time"].strftime("%H:%M")
            self.earnings_item.title = (
                f"💰 다음 근무({status['shift']}, {start_str} 시작) 예상: {status['total_when_done']:,}원"
            )
        else:
            self.earnings_item.title = "💰 오늘은 휴무입니다"
        self._update_title()

    def _earnings_short_text(self):
        """모바일 위젯용 짧은 급여 표시. 휴무면 None(위젯에서 그냥 생략)."""
        status = get_earnings_status(self.schedule, today_override=self._today_override())
        if status["state"] == "active":
            return f"💰 {status['earned_so_far']:,}원"
        if status["state"] == "waiting":
            return f"💰 시작 전 (예상 {status['total_when_done']:,}원)"
        return None

    # ── 근무 전후 절전 방지 (SSH 접속용) ───────────────────────

    def _check_stay_awake(self, _):
        # ★ 2026-07-31: 근무 전후 1시간만 절전 방지하던 기존 방식과 별개로,
        # 휴일에 밖에서도 원격 접속하고 싶을 때를 위한 수동 "항상 켜기" 토글을
        # 추가했다 — 켜져 있으면 근무표 일정과 무관하게 무조건 caffeinate.
        if self.config.get("stay_awake_always", False):
            start_caffeinate()
            self.stay_awake_item.title = "🌙 절전 방지 켜짐 (수동, 항상)"
            return

        now = datetime.datetime.now()
        window = get_stay_awake_window(self.schedule, now, today_override=self._today_override())
        if window:
            start_caffeinate()
            shift, s, e = window
            self.stay_awake_item.title = (
                f"🌙 절전 방지 켜짐 ({s.strftime('%H:%M')}~{e.strftime('%H:%M')}, {shift})"
            )
        else:
            stop_caffeinate()
            self.stay_awake_item.title = "🌙 절전 방지 꺼짐 (근무 전후 1시간 아님)"

    def toggle_stay_awake_always(self, _):
        self.config["stay_awake_always"] = not self.config.get("stay_awake_always", False)
        save_config(self.config)
        self.build_menu()
        self._check_stay_awake(None)

    # ── 근무표 자동 적용 ────────────────────────────────────

    def _check_midnight(self, _):
        """1분마다 날짜가 바뀌었는지 확인, 바뀌었으면 자동으로 근무 갱신 + 리마인더 확인"""
        today = datetime.date.today()
        if today != self._last_checked_date:
            self._last_checked_date = today
            if self.config.get("auto_mode", True):
                self.apply_today_shift(notify=True)
            self._maybe_notify_reminders()
            self.build_menu()

    def _check_electronics_off(self, _):
        """1분마다 현재 근무 기준 '전자제품 전원 끄기' 시각인지 확인, 하루 한 번만 알림."""
        current = self.config.get("current_shift")
        t = ELECTRONICS_OFF_TIMES.get(current)
        if not t:
            return
        now = datetime.datetime.now()
        if now.hour != t["hour"] or now.minute != t["minute"]:
            return
        today = now.date()
        if self._last_electronics_off_notified == today:
            return
        self._last_electronics_off_notified = today
        rumps.notification(
            "🔌 전자제품 전원 끄기",
            f"{current} 근무 기준",
            "지금부터 전자제품 전원을 꺼주세요."
        )

    def _periodic_menu_refresh(self, _):
        """5분마다 메뉴 재빌드 (외부 파일 변경 반영용)."""
        self.build_menu()

    def apply_today_shift(self, notify=True, target_date=None):
        """근무표(JSON)를 조회해서 오늘(또는 target_date) 근무를 자동 설정"""
        date = target_date or datetime.date.today()
        self.schedule = load_schedule()  # 혹시 파일이 갱신됐을 수도 있으니 매번 다시 로드
        shift = get_shift_for_date(self.schedule, date)

        if shift is None:
            if notify:
                rumps.notification(
                    "근무표 자동 설정 실패",
                    f"{date.isoformat()} 근무 정보 없음",
                    "근무표 JSON에 해당 날짜가 없습니다. 수동으로 선택해주세요."
                )
            return False

        self._set_shift_internal(shift, notify=notify)
        return True

    # ── 리마인더 (헬스장/엄마 전화/카톡 정리 등) ────────────────

    def _maybe_notify_reminders(self):
        """오늘 하루에 한 번만, 오늘 요일에 해당하는 리마인더를 알림으로 띄운다."""
        today = datetime.date.today()
        if self._last_reminder_notified == today:
            return
        self._last_reminder_notified = today

        todays = get_today_reminders(self.schedule)
        if todays:
            rumps.notification("오늘의 리마인더", "", "\n".join(todays))
            threading.Thread(
                target=self._sync_reminder_checklist_to_notion,
                args=(today, todays), daemon=True,
            ).start()

    def _sync_reminder_checklist_to_notion(self, today, todays):
        """오늘의 리마인더를 "🎎 일일 체크리스트" Notion 페이지에 날짜별 토글 +
        체크박스(to_do)로 추가한다(★ 2026-08-07 추가) — 휴대폰 Notion 앱에서 체크
        해가며 하루를 보낼 수 있게. 네트워크 호출이라 백그라운드 스레드에서만 돌리고
        AppKit은 전혀 건드리지 않는다(크래시 이력 있는 패턴이라 신중하게 분리).

        앱을 하루에 여러 번 재시작해도(코드 수정 후 kickstart 등) 같은 날짜가
        중복으로 안 생기게, config에 마지막으로 동기화한 날짜를 영구 저장해서
        확인한다 — 한 번 만든 뒤엔 사용자가 체크한 상태를 다시 덮어쓰지 않는다."""
        date_str = today.isoformat()
        if self.config.get("reminder_notion_synced_date") == date_str:
            return
        token = _notion_keychain_token()
        if not token:
            return  # Notion 미설정은 정상 상태일 수 있음 — 조용히 건너뜀
        children = [{
            "object": "block", "type": "to_do",
            "to_do": {"rich_text": [{"type": "text", "text": {"content": label}}], "checked": False},
        } for label in todays]
        toggle_block = {
            "object": "block", "type": "toggle",
            "toggle": {
                "rich_text": [{"type": "text", "text": {"content": date_str}}],
                "children": children,
            },
        }
        try:
            request = urllib.request.Request(
                f"https://api.notion.com/v1/blocks/{REMINDER_CHECKLIST_NOTION_PAGE_ID}/children",
                data=json.dumps({"children": [toggle_block]}).encode("utf-8"),
                method="PATCH",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Notion-Version": NOTION_VERSION,
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            print(f"⚠️ 리마인더 Notion 동기화 실패: {exc}")
            return
        self.config["reminder_notion_synced_date"] = date_str
        save_config(self.config)

    def _load_cached_checklist_state(self):
        """오늘 날짜분 캐시만 유효 — 날짜가 바뀌었으면 빈 상태로 시작(어제 체크
        표시가 새 날에 잘못 남지 않게)."""
        try:
            with open(CHECKLIST_STATE_CACHE_PATH, encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("date") == datetime.date.today().isoformat():
                return cached.get("state", {})
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _refresh_checklist_state(self, _):
        """1분마다(타이머) 호출 — 네트워크 I/O라 백그라운드 스레드로 뺀다."""
        threading.Thread(target=self._fetch_checklist_state_thread, daemon=True).start()

    def _fetch_checklist_state_thread(self):
        token = _notion_keychain_token()
        if not token:
            return
        date_str = datetime.date.today().isoformat()
        try:
            state = fetch_reminder_checklist_state(token, date_str)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            print(f"⚠️ 체크리스트 상태 동기화 실패: {exc}")
            return
        self._checklist_state = state
        try:
            with open(CHECKLIST_STATE_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump({"date": date_str, "state": state}, f, ensure_ascii=False)
        except OSError:
            pass
        # NSMenu/NSStatusItem을 안 건드리는 순수 데이터 갱신은 여기까지고,
        # build_menu()/_write_mobile_status()는 AppKit을 건드리므로 메인 스레드로 넘긴다.
        AppHelper.callAfter(self.build_menu)
        AppHelper.callAfter(self._write_mobile_status)

    def make_open_url_callback(self, url):
        def callback(_):
            # https URL을 그냥 `open`에 넘기면 macOS 기본 브라우저가 받는다.
            # Notion 링크는 설치된 데스크톱 앱을 명시해 일일 체크리스트와 AI 분석
            # 페이지가 Chrome이 아니라 Notion에서 열리게 한다(★ 2026-08-09).
            host = (urlparse(url).hostname or "").lower()
            if host == "notion.so" or host.endswith(".notion.so") or host == "notion.com" or host.endswith(".notion.com"):
                subprocess.Popen(["open", "-a", "Notion", url])
            else:
                subprocess.Popen(["open", url])
        return callback

    def make_reminder_toggle_callback(self, key):
        def callback(_):
            REMINDERS[key]["enabled"] = not REMINDERS[key]["enabled"]
            self.config.setdefault("reminders_enabled", {})[key] = REMINDERS[key]["enabled"]
            save_config(self.config)
            self.build_menu()
        return callback

    # ── 근무 선택 (메뉴 클릭 / 자동 적용 공통) ─────────────────

    def _set_shift_internal(self, shift, notify=True):
        time = SHIFT_TIMES.get(shift)
        if time:
            register_alarm(time["hour"], time["minute"])
            if notify:
                rumps.notification("교대근무 알람 설정", f"{shift} 근무",
                                   f"알람이 {time['hour']:02d}:{time['minute']:02d}으로 설정되었습니다.")
        else:
            unregister_alarm()
            if notify:
                rumps.notification("교대근무 알람", "휴무", "알람이 해제되었습니다.")

        self.config["current_shift"] = shift
        save_config(self.config)
        self._update_title()
        self._refresh_earnings(None)
        self.build_menu()

    def make_shift_callback(self, shift):
        def callback(_):
            # 메뉴에서 수동으로 누르면 자동 모드를 끈다 (덮어쓰기 방지)
            self.config["auto_mode"] = False
            save_config(self.config)
            self._set_shift_internal(shift, notify=True)
        return callback

    def toggle_auto_mode(self, _):
        current = self.config.get("auto_mode", True)
        self.config["auto_mode"] = not current
        save_config(self.config)
        if self.config["auto_mode"]:
            rumps.notification("근무표 자동 모드", "켜짐", "매일 자정에 근무표 기준으로 자동 설정됩니다.")
            self.apply_today_shift(notify=True)
        else:
            rumps.notification("근무표 자동 모드", "꺼짐", "이제부터 수동으로 근무를 선택해야 합니다.")
        self._update_title()
        self.build_menu()

    def refresh_today_now(self, _):
        """수동으로 '오늘 근무 다시 불러오기' 버튼"""
        ok = self.apply_today_shift(notify=True)
        if not ok:
            rumps.alert("근무표 조회 실패", "근무표 JSON에서 오늘 날짜를 찾을 수 없습니다.")

    def toggle_earnings_display(self, _):
        current = self.config.get("show_earnings", True)
        self.config["show_earnings"] = not current
        save_config(self.config)
        self._update_title()
        self.build_menu()

    # ── 메뉴 빌드 ────────────────────────────────────────────

    def build_menu(self):
        self.menu.clear()
        current = self.config.get("current_shift")
        auto_on = self.config.get("auto_mode", True)

        for shift, time in SHIFT_TIMES.items():
            if time:
                label = f"{'✓ ' if shift == current else ''}{shift}  ({time['hour']:02d}:{time['minute']:02d} 알람)"
            else:
                label = f"{'✓ ' if shift == current else ''}{shift}"
            self.menu.add(rumps.MenuItem(label, callback=self.make_shift_callback(shift)))

        self.menu.add(None)

        auto_label = f"{'✓ ' if auto_on else ''}근무표 자동 적용 (매일 자정)"
        self.menu.add(rumps.MenuItem(auto_label, callback=self.toggle_auto_mode))
        self.menu.add(rumps.MenuItem("오늘 근무 다시 불러오기", callback=self.refresh_today_now))

        self.menu.add(None)

        self.menu.add(self.earnings_item)
        self.menu.add(self.weather_item)
        storage_text = (
            f"💾 저장공간: {self.storage_free_gb}GB 남음"
            if self.storage_free_gb is not None else "💾 저장공간: 확인 실패"
        )
        self.menu.add(rumps.MenuItem(storage_text))
        self.menu.add(self.stay_awake_item)
        always_awake_on = self.config.get("stay_awake_always", False)
        always_awake_label = f"{'✓ ' if always_awake_on else ''}🌙 절전 방지 항상 켜기 (원격 접속용)"
        self.menu.add(rumps.MenuItem(always_awake_label, callback=self.toggle_stay_awake_always))

        self.menu.add(None)
        self.menu.add(self.codex_usage_item)
        self.menu.add(self.claude_usage_item)
        self.menu.add(self.claude_stats_item)

        self.menu.add(None)
        # ★ 2026-08-07: "N건 저장됨"/상위 공고 목록은 키워드 개수로만 매기는
        # 점수(score_job())라 의미 없는 매칭이 섞여 노이즈가 많다는 사용자 피드백으로
        # 메뉴 노출을 없앴다. collect는 계속 원료 수집용으로만 백그라운드에서 돌고,
        # analyze-top이 그중 실제로 깊이 분석할 가치가 있는 1건만 골라 보여준다.
        # ★ 2026-08-08: 취업/알바는 결이 달라 하나로 뭉치면 한쪽이 묻힌다는 지적으로
        # 카테고리별(커리어/알바) 각 1건씩 보여준다.
        for category, cat_label in JOB_CATEGORIES.items():
            top_analysis = get_top_job_analysis(category)
            if top_analysis:
                score = top_analysis.get("score")
                score_text = f"[{score}점] " if score is not None else ""
                label = f"🎯 {score_text}오늘의 추천 {cat_label} 공고: {top_analysis.get('company', '')} — {truncate_title(top_analysis.get('title', ''), 30)}"
                self.menu.add(rumps.MenuItem(label, callback=self.make_open_url_callback(top_analysis["url"])))

        # ★ 2026-08-08: 경진대회도 같은 이유로 AI 특화/일반 카테고리별 각 1건씩.
        for category, cat_label in CONTEST_CATEGORIES.items():
            top_contest = get_top_contest_analysis(category)
            if top_contest:
                score = top_contest.get("score")
                score_text = f"[{score}점] " if score is not None else ""
                label = f"🏆 {score_text}오늘의 추천 {cat_label} 경진대회: {top_contest.get('organizer', '')} — {truncate_title(top_contest.get('title', ''), 30)}"
                self.menu.add(rumps.MenuItem(label, callback=self.make_open_url_callback(top_contest["url"])))

        self.menu.add(None)

        today_reminders = get_today_reminders(self.schedule)
        self.menu.add(_build_reminder_status_menu_item(
            today_reminders, self.make_open_url_callback(REMINDER_CHECKLIST_NOTION_URL),
            checklist_state=self._checklist_state,
        ))

        reminder_menu = rumps.MenuItem("🔔 리마인더 켜기/끄기")
        for key, r in REMINDERS.items():
            check = "✓ " if r["enabled"] else ""
            reminder_menu.add(rumps.MenuItem(
                f"{check}{r['label']}",
                callback=self.make_reminder_toggle_callback(key)
            ))
        self.menu.add(reminder_menu)

        self.menu.add(None)

        time_menu = rumps.MenuItem("⏰ 알람 시간 설정")
        for shift in ["Day", "Swing", "GY"]:
            t = SHIFT_TIMES[shift]
            time_menu.add(rumps.MenuItem(
                f"{shift} 시간 변경  (현재 {t['hour']:02d}:{t['minute']:02d})",
                callback=self.make_time_change_callback(shift)
            ))
        self.menu.add(time_menu)

        self.menu.add(None)
        self.menu.add(rumps.MenuItem("🎬 Elmedia 지금 바로 재생", callback=self.play_elmedia_now))
        self.menu.add(rumps.MenuItem("⭐ 좋아요 플레이하기", callback=self.play_favorites_now))
        self.menu.add(None)

        last_ebook = load_last_ebook_state()
        if last_ebook:
            short_name = truncate_title(last_ebook['file_name'])
            resume_label = f"📖 이어하기: {short_name} (P.{last_ebook['page']})"
            self.menu.add(rumps.MenuItem(resume_label, callback=self.resume_ebook_now))
        self.menu.add(rumps.MenuItem("📖 다른 책 선택해서 읽기", callback=self.choose_ebook_now))
        self.menu.add(rumps.MenuItem("☁️ 독서 Notion 기록 동기화", callback=self.sync_ebook_notion_now))
        self.menu.add(rumps.MenuItem("📘 독서 기록 → 학습판 EPUB", callback=self.build_ebook_study_now))

        self.menu.add(None)
        self.menu.add(rumps.MenuItem("🎲 추천 사이트 열기 (天 폴더 랜덤 3개)", callback=self.open_random_bookmarks_now))
        self.menu.add(None)

        self.menu.add(rumps.MenuItem("🎥 일본어 자막 추출 - 연달아 (폴더 선택)", callback=self.run_jp_subtitle_now))
        self.menu.add(rumps.MenuItem("🏃 운동용 영상만 추출 (폴더 선택)", callback=self.run_jp_workout_only_now))
        self.menu.add(rumps.MenuItem("📝 자막·번역·낭독판만 (폴더 선택)", callback=self.run_jp_subtitle_stage2_now))
        self.menu.add(rumps.MenuItem(
            "📖 EPUB 폴더 → 낭독판 EPUB (문장 강조)",
            callback=self.build_jp_readaloud_epub_now,
        ))
        self.menu.add(rumps.MenuItem(
            "🎵 플레이리스트 MP4 → 곡별 MP3 (폴더 선택)",
            callback=self.run_bgm_playlist_split_now,
        ))
        self.menu.add(rumps.MenuItem(
            "🏷️ MP3 Shazam 제목 변경 (폴더 선택)",
            callback=self.run_mp3_shazam_rename_now,
        ))
        self.menu.add(rumps.MenuItem(
            "🎵 YouTube → MP3 다운로드",
            callback=self.download_youtube_mp3_now,
        ))

        sunzi_entry = get_latest_sunzi_entry()
        if sunzi_entry:
            short_title = truncate_title(sunzi_entry["title"])
            self.menu.add(rumps.MenuItem(
                f"⚔️ 손자병법 최신: {short_title}", callback=self.open_latest_sunzi
            ))

        trash_size = get_trash_size_str()
        trash_label = f"🗑️ 저장공간 관리 (휴지통 {trash_size})" if trash_size else "🗑️ 저장공간 관리"
        self.menu.add(rumps.MenuItem(trash_label, callback=self.open_storage_settings))
        self.menu.add(rumps.MenuItem("현재 설정 확인", callback=self.show_status))
        self.menu.add(None)
        self.menu.add(rumps.MenuItem("종료", callback=self.quit_app))

    # ── 시간 변경 (osascript 입력창) ─────────────────────────

    def make_time_change_callback(self, shift):
        def callback(_):
            threading.Thread(target=self.change_time, args=(shift,), daemon=True).start()
        return callback

    def change_time(self, shift):
        current = SHIFT_TIMES[shift]

        hour_val = ask_input(
            f"{shift} 시간 변경",
            f"{shift} 알람\\n시(Hour)를 입력하세요 (0~23)",
            str(current["hour"])
        )
        if hour_val is None:
            return
        try:
            hour = int(hour_val.strip())
            assert 0 <= hour <= 23
        except Exception:
            subprocess.run(["osascript", "-e", 'display alert "오류" message "0~23 사이 숫자를 입력하세요."'])
            return

        min_val = ask_input(
            f"{shift} 시간 변경",
            f"{shift} 알람\\n분(Minute)을 입력하세요 (0~59)",
            str(current["minute"])
        )
        if min_val is None:
            return
        try:
            minute = int(min_val.strip())
            assert 0 <= minute <= 59
        except Exception:
            subprocess.run(["osascript", "-e", 'display alert "오류" message "0~59 사이 숫자를 입력하세요."'])
            return

        SHIFT_TIMES[shift]["hour"] = hour
        SHIFT_TIMES[shift]["minute"] = minute
        self.config["shift_times"] = SHIFT_TIMES
        save_config(self.config)

        if self.config.get("current_shift") == shift:
            register_alarm(hour, minute)

        subprocess.run(["osascript", "-e",
            f'display notification "알람이 {hour:02d}:{minute:02d}으로 변경되었습니다." with title "{shift} 시간 변경 완료"'])
        self.build_menu()

    # ── Elmedia 즉시 재생 ─────────────────────────────────────

    def play_elmedia_now(self, _):
        ok, msg = play_folder_in_elmedia()
        if not ok:
            rumps.alert("오류", msg)
            return
        rumps.notification("Elmedia", "재생 시작", msg)

    def play_favorites_now(self, _):
        """★ 2026-08-07 추가: "좋아요 플레이" 폴더를 Elmedia로 연다. 메뉴 클릭
        시에만 실행되는 일반 콜백이라 자동 재생은 절대 일어나지 않는다."""
        ok, msg = play_folder_in_elmedia(FAVORITES_PLAYLIST_FOLDER)
        if not ok:
            rumps.alert("오류", msg)
            return
        rumps.notification("Elmedia", "좋아요 플레이 재생 시작", msg)

    # ── 아침 학습 (ebook_reader.py) ──────────────────────────

    def resume_ebook_now(self, _):
        last = load_last_ebook_state()
        if not last:
            rumps.alert("오류", "이어서 읽을 책 정보가 없습니다.")
            return
        open_ebook_reader_terminal(last["file"])

    def choose_ebook_now(self, _):
        path = choose_ebook_file()
        if path:
            open_ebook_reader_terminal(path)

    def sync_ebook_notion_now(self, _):
        open_ebook_notion_sync_terminal()

    def build_ebook_study_now(self, _):
        path = choose_ebook_file()
        if path:
            open_ebook_study_build_terminal(path)

    def open_random_bookmarks_now(self, _):
        urls = open_random_bookmarks(3)
        if not urls:
            rumps.alert("오류", "북마크를 불러올 수 없습니다.")
            return
        rumps.notification("추천 사이트", f"{len(urls)}개 열었습니다", "\n".join(urls))

    def _auto_refresh_bookmarks(self, _):
        if self._bookmark_refresh_running:
            return
        self._bookmark_refresh_running = True
        threading.Thread(
            target=self._auto_refresh_bookmarks_thread, daemon=True
        ).start()

    def _auto_refresh_bookmarks_thread(self):
        try:
            result = refresh_kr_subdomains()
            if "error" in result:
                print(f"⚠️ 북마크 자동 최신화 실패: {result['error']}")
                return
            if result["updated"] == 0:
                if result["failed_domains"]:
                    print(
                        "⚠️ 북마크 자동 최신화 탐색 실패: "
                        + ", ".join(result["failed_domains"])
                    )
                return
            msg = f"{result['updated']}개 주소를 최신 서브도메인으로 교체했습니다."
            if result["failed_domains"]:
                msg += f" ({', '.join(result['failed_domains'])}는 탐색 실패)"
            rumps.notification("북마크 자동 최신화 완료", "", msg)
        finally:
            self._bookmark_refresh_running = False

    # ── 이직시스템(job_collector.py) 자동 수집 ─────────────────

    def _refresh_job_collector(self, _):
        if self._job_collector_running:
            return
        last_run = self.config.get("job_collector_last_run")
        if last_run:
            try:
                elapsed = (
                    datetime.datetime.now() - datetime.datetime.fromisoformat(last_run)
                ).total_seconds()
            except ValueError:
                elapsed = JOB_COLLECTOR_REFRESH_SECONDS
            if elapsed < JOB_COLLECTOR_REFRESH_SECONDS:
                return
        self._job_collector_running = True
        threading.Thread(target=self._run_job_collector_thread, daemon=True).start()

    def _run_job_collector_thread(self):
        try:
            result = subprocess.run(
                [sys.executable, JOB_COLLECTOR_SCRIPT, "collect"],
                cwd=JOB_COLLECTOR_DIR,
                capture_output=True, text=True, timeout=300,
            )
            self.config["job_collector_last_run"] = datetime.datetime.now().isoformat(timespec="seconds")
            save_config(self.config)

            match = re.search(r"신규 (\d+)건 / 기존 갱신 (\d+)건", result.stdout)
            if match:
                inserted, updated = int(match.group(1)), int(match.group(2))
                if inserted > 0:
                    rumps.notification(
                        "💼 이직시스템 새 공고",
                        f"신규 {inserted}건 / 갱신 {updated}건 수집됨",
                        "터미널에서 job_collector.py list로 확인하세요.",
                    )
            elif result.returncode != 0:
                print(f"⚠️ 이직시스템 수집 실패: {result.stderr.strip()[:300]}")

            self._run_job_analysis_top()
            self._run_contest_collector_and_analysis()
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"⚠️ 이직시스템 수집 실행 오류: {exc}")
        finally:
            self._job_collector_running = False

    def _run_job_analysis_top(self):
        """적합도 1위 공고를 AI로 분석해 Notion에 올린다(★ 2026-08-07 추가).
        collect 직후 같은 백그라운드 스레드에서 이어서 돌아 하루 1번 주기를 그대로
        공유한다. codex/claude 폴백 호출이 상위 후보 여러 개를 시도할 수 있어
        collect보다 훨씬 오래 걸릴 수 있으므로 타임아웃을 넉넉히 둔다.
        ★ 2026-08-08: 커리어/알바 카테고리별로 각각 analyze-top을 돌린다."""
        for category, cat_label in JOB_CATEGORIES.items():
            try:
                result = subprocess.run(
                    [sys.executable, JOB_COLLECTOR_SCRIPT, "analyze-top", "--category", category],
                    cwd=JOB_COLLECTOR_DIR,
                    capture_output=True, text=True, timeout=1800,
                )
                if "Notion 페이지 갱신 완료" in result.stdout:
                    top = get_top_job_analysis(category)
                    if top:
                        score = top.get("score")
                        score_text = f"[{score}점] " if score is not None else ""
                        rumps.notification(
                            f"🎯 오늘의 추천 {cat_label} 공고",
                            f"{score_text}{top.get('company', '')} — {truncate_title(top.get('title', ''), 40)}",
                            "메뉴바에서 클릭하면 Notion 분석으로 이동합니다.",
                        )
                elif result.returncode != 0:
                    print(f"⚠️ {cat_label} 공고 AI 분석 실패: {result.stderr.strip()[:300]}")
            except (OSError, subprocess.TimeoutExpired) as exc:
                print(f"⚠️ {cat_label} 공고 AI 분석 실행 오류: {exc}")

    def _run_contest_collector_and_analysis(self):
        """링커리어 공모전·경진대회를 수집하고 적합도 1위를 AI로 분석해 Notion에
        올린다(★ 2026-08-07 추가). 이직시스템 collect/analyze-top과 같은 백그라운드
        스레드·같은 하루 1번 주기를 그대로 공유한다(job_collector_last_run 가드가
        이 함수 전체를 감쌈). ★ 2026-08-08: collect는 한 번만 돌리고, AI 특화/일반
        카테고리별로 analyze-top을 각각 돌린다."""
        try:
            collect_result = subprocess.run(
                [sys.executable, CONTEST_COLLECTOR_SCRIPT, "collect"],
                cwd=JOB_COLLECTOR_DIR,
                capture_output=True, text=True, timeout=300,
            )
            if collect_result.returncode != 0:
                print(f"⚠️ 경진대회 수집 실패: {collect_result.stderr.strip()[:300]}")
                return

            for category, cat_label in CONTEST_CATEGORIES.items():
                analyze_result = subprocess.run(
                    [sys.executable, CONTEST_COLLECTOR_SCRIPT, "analyze-top", "--category", category],
                    cwd=JOB_COLLECTOR_DIR,
                    capture_output=True, text=True, timeout=1800,
                )
                if "Notion 페이지 갱신 완료" in analyze_result.stdout:
                    top = get_top_contest_analysis(category)
                    if top:
                        score = top.get("score")
                        score_text = f"[{score}점] " if score is not None else ""
                        rumps.notification(
                            f"🏆 오늘의 추천 {cat_label} 경진대회",
                            f"{score_text}{top.get('organizer', '')} — {truncate_title(top.get('title', ''), 40)}",
                            "메뉴바에서 클릭하면 Notion 분석으로 이동합니다.",
                        )
                elif analyze_result.returncode != 0:
                    print(f"⚠️ {cat_label} 경진대회 AI 분석 실패: {analyze_result.stderr.strip()[:300]}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"⚠️ 경진대회 수집/분석 실행 오류: {exc}")

    def _prompt_jp_workout_settings(self):
        """운동용 영상 목표 길이(분)와 고음 구간 앞뒤 여유(초)를 키패드로 물어본다.
        취소하면 None을 반환, 확인하면 (target_minutes, highlight_pad) 튜플을 반환.
        ★ 2026-07-24: rumps.Window 텍스트 입력이 안 먹혀서(키보드 포커스 문제)
        타이핑 대신 마우스 클릭 숫자 키패드로 바꿈 — 기본값이 미리 채워져 있어서
        그냥 확인만 눌러도 되고, 지우고 다른 숫자를 눌러 바꿀 수도 있음."""
        DEFAULT_TARGET_MINUTES = self.config.get("jp_target_minutes", 30)
        text = show_minutes_keypad(default_minutes=DEFAULT_TARGET_MINUTES)
        if text is None:
            return None  # 취소

        text = text.strip()
        if not text:
            target_minutes = DEFAULT_TARGET_MINUTES
        else:
            try:
                target_minutes = float(text)
                if target_minutes <= 0:
                    raise ValueError
            except ValueError:
                rumps.alert("오류", "분량은 0보다 큰 숫자로 입력하세요.")
                return None

        DEFAULT_HIGHLIGHT_PAD = self.config.get("jp_highlight_pad", 1)
        pad_text = show_minutes_keypad(
            title="고음 구간 앞뒤 여유 설정 (초)",
            default_minutes=DEFAULT_HIGHLIGHT_PAD,
        )
        if pad_text is None:
            return None
        pad_text = pad_text.strip()
        if not pad_text:
            highlight_pad = DEFAULT_HIGHLIGHT_PAD
        else:
            try:
                highlight_pad = int(pad_text)
                if highlight_pad < 0:
                    raise ValueError
            except ValueError:
                rumps.alert("오류", "여유 구간은 0 이상의 정수 초로 입력하세요.")
                return None

        # 마지막 확인값을 메뉴바 앱 설정에 저장해 다음 실행의 키패드 기본값으로 쓴다.
        self.config["jp_target_minutes"] = target_minutes
        self.config["jp_highlight_pad"] = highlight_pad
        save_config(self.config)
        return target_minutes, highlight_pad

    def run_jp_subtitle_now(self, _):
        """운동용 영상 추출 + 자막·번역·Notion·EPUB을 연달아 실행."""
        folder = choose_jp_subtitle_folder()
        if not folder:
            return

        settings = self._prompt_jp_workout_settings()
        if settings is None:
            return
        target_minutes, highlight_pad = settings

        ok = run_jp_subtitle_extraction(
            folder,
            target_minutes=target_minutes,
            highlight_pad=highlight_pad,
        )
        if not ok:
            rumps.alert("오류", f"스크립트를 찾을 수 없습니다:\n{JP_SUBTITLE_SCRIPT}")
            return
        minutes_note = (
            f" (목표 {target_minutes:.0f}분 · 앞뒤 여유 {highlight_pad}초)"
            if target_minutes else f" (앞뒤 여유 {highlight_pad}초)"
        )
        rumps.notification("일본어 자막 추출 (연달아)", "시작됨", f"{folder}{minutes_note}\n새 터미널 창에서 진행 상황을 확인하세요.")

    def run_jp_workout_only_now(self, _):
        """Notion/메모/EPUB 없이 운동용 고음 영상만 단독으로 추출."""
        folder = choose_jp_subtitle_folder()
        if not folder:
            return

        settings = self._prompt_jp_workout_settings()
        if settings is None:
            return
        target_minutes, highlight_pad = settings

        ok = run_jp_workout_extraction_only(
            folder,
            target_minutes=target_minutes,
            highlight_pad=highlight_pad,
        )
        if not ok:
            rumps.alert("오류", f"스크립트를 찾을 수 없습니다:\n{JP_WORKOUT_VIDEO_SCRIPT}")
            return
        minutes_note = (
            f" (목표 {target_minutes:.0f}분 · 앞뒤 여유 {highlight_pad}초)"
            if target_minutes else f" (앞뒤 여유 {highlight_pad}초)"
        )
        rumps.notification("운동용 영상만 추출", "시작됨", f"{folder}{minutes_note}\n새 터미널 창에서 진행 상황을 확인하세요.")

    def run_jp_subtitle_stage2_now(self, _):
        """운동용 영상 추출 없이 자막·번역·낭독판 EPUB만 단독으로 실행."""
        folder = choose_jp_subtitle_folder()
        if not folder:
            return

        ok = run_jp_subtitle_stage2_only(folder)
        if not ok:
            rumps.alert("오류", f"스크립트를 찾을 수 없습니다:\n{JP_SUBTITLE_STAGE2_SCRIPT}")
            return
        rumps.notification("자막·번역·낭독판", "시작됨", f"{folder}\n새 iTerm 창에서 진행 상황을 확인하세요.")

    def build_jp_readaloud_epub_now(self, _):
        epub_dir = choose_jp_epub_folder(
            "문장 강조·자동 넘김 책을 만들 EPUB 폴더를 선택하세요. "
            "완성된 낭독판 EPUB도 이 폴더에 저장됩니다."
        )
        if not epub_dir:
            return
        ok = run_build_readaloud_epub(epub_dir)
        if not ok:
            rumps.alert(
                "오류", f"스크립트를 찾을 수 없습니다:\n{JP_BUILD_READALOUD_EPUB_SCRIPT}"
            )
            return
        rumps.notification(
            "낭독판 EPUB 생성", "시작됨",
            f"{epub_dir}\n일본어 문장 강조와 자동 페이지 넘김용 EPUB을 같은 폴더에 저장합니다.",
        )

    def run_bgm_playlist_split_now(self, _):
        folder = choose_bgm_playlist_folder()
        if not folder:
            return
        mp4_count = sum(
            1 for name in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, name))
            and name.lower().endswith(".mp4")
        )
        if mp4_count == 0:
            rumps.alert("MP4 없음", "선택한 폴더 바로 아래에 MP4 파일이 없습니다.")
            return
        if not run_bgm_playlist_batch(folder):
            rumps.alert(
                "오류",
                f"자동 분할 스크립트를 찾을 수 없습니다:\n{BGM_PLAYLIST_BATCH_SCRIPT}",
            )
            return
        rumps.notification(
            "플레이리스트 자동 분할",
            f"MP4 {mp4_count}개 처리 시작",
            "성공한 영상은 곡별 MP3 생성 후 휴지통으로 이동합니다.\n"
            "iTerm에서 진행 상황을 확인하세요.",
        )

    def run_mp3_shazam_rename_now(self, _):
        folder = choose_mp3_rename_folder()
        if not folder:
            return
        mp3_count = sum(
            1 for name in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, name))
            and name.lower().endswith(".mp3")
            and "분절" in os.path.splitext(name)[0]
        )
        if mp3_count == 0:
            rumps.alert(
                "분절 MP3 없음",
                "선택한 폴더 바로 아래에 이름에 '분절'이 들어간 MP3가 없습니다.",
            )
            return
        if not run_mp3_shazam_rename(folder):
            rumps.alert(
                "오류",
                "Shazam 제목 변경 스크립트 또는 전용 환경을 찾을 수 없습니다.",
            )
            return
        rumps.notification(
            "MP3 Shazam 제목 변경",
            f"MP3 {mp3_count}개 처리 시작",
            "인식되는 즉시 아티스트 - 노래제목으로 변경합니다.",
        )

    def download_youtube_mp3_now(self, _):
        try:
            clipboard = subprocess.run(
                ["pbpaste"], capture_output=True, text=True, timeout=2
            ).stdout.strip()
        except Exception:
            clipboard = ""
        default_url = clipboard if re.match(r"^https?://", clipboard) else "https://"
        url = show_text_input_panel(
            "YouTube MP3 다운로드",
            "단일 영상 또는 재생목록 링크 주소를 입력하세요.",
            default_url,
        )
        if url is None:
            return
        url = url.strip()
        if not re.match(r"^https?://", url):
            rumps.alert("주소 확인", "http:// 또는 https://로 시작하는 YouTube 주소를 입력하세요.")
            return
        folder = choose_youtube_mp3_folder()
        if not folder:
            return
        ok, error = run_youtube_mp3_download(url, folder)
        if not ok:
            rumps.alert("YouTube MP3 다운로드 오류", error)
            return
        rumps.notification(
            "YouTube → MP3",
            "다운로드 시작",
            f"{folder}\n새 터미널 창에서 진행 상황을 확인하세요.",
        )

    def open_latest_sunzi(self, _):
        entry = get_latest_sunzi_entry()
        if not entry:
            rumps.alert("오류", "손자병법 완료 구절 정보를 찾을 수 없습니다.")
            return
        subprocess.Popen(["open", entry["url"]])

    # ── 저장공간 관리 ────────────────────────────────────────

    def open_storage_settings(self, _):
        """★ 2026-08-08: 기존엔 Finder AppleScript로 휴지통을 직접 비우려 했으나
        launchd로 뜬 백그라운드 프로세스에서는 AppleEvent 자동화 권한이 제대로
        안 붙어 클릭해도 조용히 아무 반응이 없었다(이 코드베이스에서 반복적으로
        겪은 launchd·AppleEvent 문제와 같은 패턴). 자동 삭제를 억지로 고치는
        대신, 사용자가 직접 정리할 수 있게 시스템 설정의 저장 공간 화면을
        열어주는 것으로 단순화했다."""
        subprocess.Popen(["open", "x-apple.systempreferences:com.apple.settings.Storage"])

    # ── 상태 확인 ────────────────────────────────────────────

    def show_status(self, _):
        current = self.config.get("current_shift")
        auto_on = self.config.get("auto_mode", True)
        auto_text = "자동(근무표 기준)" if auto_on else "수동"
        status = get_earnings_status(self.schedule, today_override=self._today_override())
        if status["state"] == "active":
            earnings_text = f"오늘 급여: {status['earned_so_far']:,}원"
        elif status["state"] == "waiting":
            earnings_text = f"다음 근무({status['shift']}) 예상 급여: {status['total_when_done']:,}원"
        else:
            earnings_text = "오늘은 휴무입니다"

        today_reminders = get_today_reminders(self.schedule)
        reminders_text = " / ".join(today_reminders) if today_reminders else "없음"

        if current and SHIFT_TIMES.get(current):
            t = SHIFT_TIMES[current]
            msg = (f"현재 근무: {current} ({auto_text})\n"
                   f"알람 시간: {t['hour']:02d}:{t['minute']:02d}\n"
                   f"{earnings_text}\n"
                   f"오늘의 리마인더: {reminders_text}\n"
                   f"날씨: {self.weather_str or '로딩 중'}")
        elif current == "휴무":
            msg = (f"현재: 휴무 ({auto_text}, 알람 없음)\n{earnings_text}\n"
                   f"오늘의 리마인더: {reminders_text}\n날씨: {self.weather_str or '로딩 중'}")
        else:
            msg = f"근무가 설정되지 않았습니다.\n오늘의 리마인더: {reminders_text}"
        rumps.alert("현재 설정", msg)

    def quit_app(self, _):
        stop_caffeinate()
        rumps.quit_application()


if __name__ == "__main__":
    ShiftAlarmApp().run()
