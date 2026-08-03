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
  기준으로 판단한다. 헬스장은 예외로 근무·휴무와 무관하게 3일→2일 간격을 반복하며,
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
import urllib.request
import urllib.error
from urllib.parse import urlparse, parse_qs
import threading
import datetime
import random
import concurrent.futures
import shutil
import time
import signal
import objc
from AppKit import (
    NSApp, NSPanel, NSTextField, NSButton, NSMakeRect, NSFont,
    NSBackingStoreBuffered, NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSModalPanelWindowLevel, NSTextAlignmentCenter, NSRoundedBezelStyle,
)

# ── 설정 파일 경로 ──────────────────────────────────────────
CONFIG_FILE = os.path.expanduser("~/.shift_alarm_config.json")

# ── 근무표 JSON 경로 (엑셀에서 추출한 D조 날짜별 근무) ─────────────
# 스크립트와 같은 폴더에 d_team_schedule_2026.json 을 두거나,
# 아래 경로를 실제 위치로 바꿔주세요.
SCHEDULE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "d_team_schedule_2026.json")

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
# - 헬스장: 근무·휴무와 무관하게 3일→2일 간격 반복. 상체/하체를 번갈아 표시
# - 엄마한테 전화: 휴무 블록의 첫날 (근무 마치고 쉬기 시작하는 날)
# - 허민준한테 전화: 한 달에 한 번. 그 달의 첫 번째 휴무 블록 시작일
# - 동찬이형한테 전화: 2026-08-03을 기준으로 21일마다 한 번
# - 코털 정리: 근무표와 무관하게 2026-08-03을 기준으로 7일마다 한 번
# - 카톡 정리: 휴무 블록의 마지막날 (다시 출근하기 전날)
# - 아울렛 쇼핑: 한 달에 한 번. 그 달의 첫 번째 휴무 블록 시작일에 알림
# - 2만보 걷기: 휴무 블록의 첫날과 마지막날(기존 마지막날 1회에서 약 2배로 확대).
#   하루짜리 휴무 블록은 같은 날이 첫날이자 마지막날이므로 한 번만 알림
# - 빨래: 휴무일마다 매번
# 각 항목은 메뉴의 "🔔 리마인더 켜기/끄기"에서 개별적으로 켜고 끌 수 있음.
REMINDERS = {
    "gym":             {"label": "🏋️ 헬스장 가는 날(상체/하체)", "enabled": True},
    "call_mom":        {"label": "📞 엄마한테 전화하는 날",   "enabled": True},
    "call_heo_minjun": {"label": "📞 허민준한테 전화하는 날", "enabled": True},
    "call_dongchan":   {"label": "📞 동찬이형한테 전화하는 날", "enabled": True},
    "nose_hair_trim":  {"label": "🪒 코털 정리하는 날",       "enabled": True},
    "kakao_cleanup":   {"label": "🧹 카톡 정리하는 날",       "enabled": True},
    "outlet_shopping": {"label": "🛍️ 아울렛 쇼핑하는 날",    "enabled": True},
    "walk_20k":        {"label": "🚶 2만보 걷는 날",         "enabled": True},
    "laundry":         {"label": "🧺 빨래 돌리는 날",         "enabled": True},
    "outing":          {"label": "🗺️ 월 1회 나들이 추천",    "enabled": True},
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
NOSE_HAIR_TRIM_ANCHOR = datetime.date(2026, 8, 3)
NOSE_HAIR_TRIM_INTERVAL_DAYS = 7


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
    """3일→2일 간격 운동 주기의 회차. 운동일이 아니면 None."""
    days = (d - GYM_CYCLE_ANCHOR).days
    if days < 0:
        return None
    cycles, remainder = divmod(days, 5)
    if remainder == 0:
        return cycles * 2
    if remainder == 3:
        return cycles * 2 + 1
    return None


def _is_dongchan_call_day(d):
    """기준일부터 21일마다 돌아오는 동찬이형 연락일인지 반환."""
    days = (d - CALL_DONGCHAN_ANCHOR).days
    return days >= 0 and days % CALL_DONGCHAN_INTERVAL_DAYS == 0


def _is_nose_hair_trim_day(d):
    """기준일부터 7일마다 돌아오는 코털 정리일인지 반환."""
    days = (d - NOSE_HAIR_TRIM_ANCHOR).days
    return days >= 0 and days % NOSE_HAIR_TRIM_INTERVAL_DAYS == 0


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

    - 헬스장: 근무·휴무와 무관하게 2026-08-03부터 3일→2일 간격을 반복한다.
      상체/하체는 매회 번갈아 표시하며 운영시간 때문에 알림을 생략하지 않는다.
    - 엄마한테 전화: 오늘이 휴무 블록의 첫날 (어제는 근무였음)
    - 허민준한테 전화: 월 1회, 이번 달의 첫 번째 휴무 블록 시작일
    - 동찬이형한테 전화: 2026-08-03부터 21일마다 한 번
    - 코털 정리: 근무표와 무관하게 2026-08-03부터 7일마다 한 번
    - 카톡 정리: 오늘이 휴무 블록의 마지막날 (내일은 근무)
    - 2만보 걷기: 휴무 블록의 첫날과 마지막날. 하루짜리 휴무는 한 번만 뜬다.
      (2026-08-03: 기존 마지막날 1회에서 빈도를 약 2배로 확대)
    - 빨래: 휴무일마다 매번
    - 나들이 추천: 월 1회, 이번 달의 '마지막' 휴무 블록 시작일(아울렛 쇼핑=첫 번째 블록과
      겹치지 않게). 아산시 기준 근교 명소를 매달 순환 추천. (2026-07-24 추가)
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
        if (is_block_start or is_block_end) and REMINDERS["walk_20k"]["enabled"]:
            reminders.append(REMINDERS["walk_20k"]["label"])
        if REMINDERS["laundry"]["enabled"]:
            reminders.append(REMINDERS["laundry"]["label"])

    if REMINDERS["outlet_shopping"]["enabled"] and _is_first_off_block_start_of_month(schedule, today):
        reminders.append(REMINDERS["outlet_shopping"]["label"])

    if REMINDERS["call_heo_minjun"]["enabled"] and _is_first_off_block_start_of_month(schedule, today):
        reminders.append(REMINDERS["call_heo_minjun"]["label"])

    if REMINDERS["call_dongchan"]["enabled"] and _is_dongchan_call_day(today):
        reminders.append(REMINDERS["call_dongchan"]["label"])

    if REMINDERS["nose_hair_trim"]["enabled"] and _is_nose_hair_trim_day(today):
        reminders.append(REMINDERS["nose_hair_trim"]["label"])

    if REMINDERS["outing"]["enabled"] and _is_last_off_block_start_of_month(schedule, today):
        place = pick_monthly_outing_place(today)
        reminders.append(f"🗺️ 어디 가보자: {place}")

    return reminders


def get_today_reminder_title_tokens(schedule, now=None):
    """메뉴바 타이틀용으로 운동 부위와 통화 대상을 짧게 표시한다."""
    tokens = []
    call_tokens = {
        REMINDERS["call_mom"]["label"]: "📞엄마",
        REMINDERS["call_heo_minjun"]["label"]: "📞민준",
        REMINDERS["call_dongchan"]["label"]: "📞동찬",
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

def play_folder_in_elmedia():
    """Elmedia Video Player로 음악 폴더 자체를 엶"""
    if not os.path.isdir(PLAYLIST_FOLDER):
        return False, "폴더를 찾을 수 없습니다."
    try:
        subprocess.Popen(["open", "-a", "Elmedia Video Player", PLAYLIST_FOLDER])
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


def empty_trash_forcefully():
    """휴지통을 비우기 전에, 휴지통 디렉토리를 물고 있는 프로세스(Finder 자신은 제외)가
    있으면 강제 종료한 뒤 Finder로 휴지통을 비운다.
    ★ 2026-07-31: "Uninstaller sensei"(com.katrych.uninstaller-sensei-watcher) 같은
    서드파티 백그라운드 감시 프로세스가 ~/.Trash 디렉토리를 계속 열어두고 있어서
    휴지통 비우기 버튼을 눌러도 반응이 없던 것을 진단하며 추가한 기능 — 매번 수동으로
    lsof/kill을 안 해도 되게 자동화함.
    반환값: (성공 여부, 종료한 프로세스 이름 목록, 실패 시 에러 메시지)."""
    trash_dir = os.path.expanduser("~/.Trash")
    killed = []
    try:
        result = subprocess.run(
            ["lsof", "+D", trash_dir], capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.strip().splitlines()[1:]:  # 헤더 줄 제외
            parts = line.split()
            if len(parts) < 2:
                continue
            command, pid = parts[0], parts[1]
            if command == "Finder" or not pid.isdigit() or int(pid) == os.getpid():
                continue
            subprocess.run(["kill", "-9", pid], check=False)
            killed.append(f"{command}({pid})")
    except Exception:
        pass

    result = subprocess.run(
        ["osascript", "-e", 'tell application "Finder" to empty trash'],
        capture_output=True, text=True, timeout=120,
    )
    return result.returncode == 0, killed, result.stderr.strip()


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


def _host_alive(host, timeout=3):
    """DNS+TCP+TLS까지 붙어서 뭐라도 HTTP 응답이 왔으면 살아있는 걸로 친다.
    403/503 등 에러 응답도 '서버가 응답했다'는 뜻이라 살아있음으로 간주한다
    (Cloudflare 봇 차단으로 403이 오는 경우가 실제로 있었음, 2026-07-23 확인).
    DNS 실패/연결 거부/타임아웃일 때만 죽은 것으로 판단한다 — 로테이션이 끝난
    옛 서브도메인은 이렇게 응답 자체가 없는 걸로 확인됨(kr42.topgirl.co 사례)."""
    try:
        req = urllib.request.Request(f"https://{host}", method="HEAD",
                                      headers={"User-Agent": "Mozilla/5.0"})
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def _detect_current_kr_subdomain(base_domain, known_numbers, probe_ahead=30):
    """known_numbers 중 지금도 살아있는 것의 최댓값을 우선 채택.
    전부 죽어있으면 그 다음 번호대(known 최댓값+1 ~ +probe_ahead)를 탐색한다.
    못 찾으면 None."""
    candidates = sorted(set(known_numbers), reverse=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        alive_flags = list(ex.map(lambda n: _host_alive(f"kr{n}.{base_domain}"), candidates))
    alive = [n for n, ok in zip(candidates, alive_flags) if ok]
    if alive:
        return max(alive)

    start = max(known_numbers) + 1
    probe_nums = list(range(start, start + probe_ahead))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        probe_flags = list(ex.map(lambda n: _host_alive(f"kr{n}.{base_domain}"), probe_nums))
    found = [n for n, ok in zip(probe_nums, probe_flags) if ok]
    return max(found) if found else None


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
    """실제 알람 시 실행될 셸 스크립트 생성 (폴더 직접 열기 방식)"""
    os.makedirs(os.path.dirname(ALARM_SCRIPT_PATH), exist_ok=True)
    script = f"""#!/bin/bash
# 교대근무 아침 알람 실행 스크립트

# 1. Elmedia로 음악 폴더 직접 열기 (m3u 파싱 문제 우회)
open -a "Elmedia Video Player" "{PLAYLIST_FOLDER}"

# 2. 맥 단축어 실행 (유튜브 랜덤 음악)
/usr/bin/shortcuts run "{SHORTCUT_NAME}"
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
        icon = "🌧️" if rain >= 50 else "⛅" if rain >= 20 else "☀️"
        return {"icon": icon, "text": f"{temp}°C 🌧{rain}%"}
    except Exception:
        return None


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
        self.earnings_item = rumps.MenuItem("오늘 급여: -")
        self.weather_item = rumps.MenuItem("날씨: 로딩 중")
        self.stay_awake_item = rumps.MenuItem("🌙 절전 방지: 확인 중...")
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

    # ── 날씨 ────────────────────────────────────────────────

    def _init_weather(self):
        weather = fetch_weather()
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

    def _today_override(self):
        """자동 모드가 꺼져있으면(연차 등으로 수동 지정) 근무표 대신 쓸 오늘 근무값."""
        if self.config.get("auto_mode", True):
            return None
        return self.config.get("current_shift")

    def _update_title(self):
        # 메뉴바 아이콘이 많으면 macOS가 긴 타이틀을 통째로 숨겨버릴 수 있으므로
        # 타이틀은 최대한 짧게 유지한다. 날씨/자동모드 여부/정확한 금액 등
        # 자세한 정보는 메뉴 항목(드롭다운)과 "현재 설정 확인"에서 확인.
        current = self.config.get("current_shift")
        code = SHIFT_TO_SHORT_CODE.get(current, current or "?")

        # ★ 2026-07-24: 공백 없이 이어붙이면(특히 휴무일처럼 리마인더가 여러 개
        # 동시에 뜨는 날) 이모지들이 서로 겹쳐 보여 찌그러진 것처럼 보였다.
        reminder_icons = " ".join(get_today_reminder_title_tokens(self.schedule))

        storage = (
            f"💾{self.storage_free_gb}"
            if self.storage_free_gb is not None else ""
        )
        shift_text = code if current else "미설정"
        parts = [shift_text, storage, reminder_icons, self.weather_icon]
        self.title = " ".join(p for p in parts if p)

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
                "5GB 이하입니다. Shift Alarm 메뉴에서 휴지통을 비워주세요.",
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

        today_reminders = get_today_reminders(self.schedule)
        reminder_status = " / ".join(today_reminders) if today_reminders else "오늘 예정된 리마인더 없음"
        self.menu.add(rumps.MenuItem(f"🔔 오늘: {reminder_status}"))

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
        self.menu.add(rumps.MenuItem("🎬 Elmedia 지금 바로 재생", callback=self.play_elmedia_now))

        last_ebook = load_last_ebook_state()
        if last_ebook:
            short_name = truncate_title(last_ebook['file_name'])
            resume_label = f"📖 이어하기: {short_name} (P.{last_ebook['page']})"
            self.menu.add(rumps.MenuItem(resume_label, callback=self.resume_ebook_now))
        self.menu.add(rumps.MenuItem("📖 다른 책 선택해서 읽기", callback=self.choose_ebook_now))
        self.menu.add(rumps.MenuItem("☁️ 독서 Notion 기록 동기화", callback=self.sync_ebook_notion_now))
        self.menu.add(rumps.MenuItem("📘 독서 기록 → 학습판 EPUB", callback=self.build_ebook_study_now))
        self.menu.add(rumps.MenuItem("🎲 추천 사이트 열기 (天 폴더 랜덤 3개)", callback=self.open_random_bookmarks_now))

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
        trash_label = f"🗑️ 휴지통 비우기 ({trash_size})" if trash_size else "🗑️ 휴지통 비우기"
        self.menu.add(rumps.MenuItem(trash_label, callback=self.empty_trash_now))
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

    # ── 휴지통 비우기 ────────────────────────────────────────────

    def empty_trash_now(self, _):
        threading.Thread(target=self._empty_trash_thread, daemon=True).start()

    def _empty_trash_thread(self):
        before = get_trash_size_bytes()
        ok, killed, err = empty_trash_forcefully()
        if ok:
            after = get_trash_size_bytes()
            if before is None:
                note = "휴지통을 비웠습니다. 삭제 용량은 계산하지 못했습니다."
            elif before == 0:
                note = "휴지통이 이미 비어 있습니다."
            else:
                remaining = after if after is not None else 0
                deleted = max(0, before - remaining)
                note = f"휴지통에서 {format_file_size(deleted)}를 삭제했습니다."
                if remaining:
                    note += f" 삭제하지 못한 항목 {format_file_size(remaining)}가 남아 있습니다."
            if killed:
                note += f" 사용 중이던 프로세스 {', '.join(killed)}도 종료했습니다."
            rumps.notification("휴지통 비우기 완료", "", note)
            self._check_storage(None)
            self.build_menu()  # 메뉴 항목의 휴지통 용량 표시를 바로 최신화
        else:
            rumps.alert("오류", f"휴지통 비우기 실패:\n{err}")

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
