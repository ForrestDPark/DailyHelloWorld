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
  - 이 값은 "추정치"예요. 정확한 통상시급은 매달 급여명세서 나올 때마다
    메뉴의 "시급 설정"에서 갱신해주면 더 정확해져요.
- 주간 리마인더 (헬스장/엄마 전화/카톡 정리/아울렛 쇼핑): 요일이 아니라 근무표의 "휴무 블록"을
  기준으로 판단해서 "오늘이 그 날"이면 알림이 뜬다 (교대근무자라 요일이 매번 바뀌므로).
  헬스장은 주 2회(휴무 시작일 + 그로부터 이틀 뒤, 단 근무 종료 시각에 헬스장이 닫혀있으면 그날은 건너뜀 —
  헬스장이 토/일 06:00~17:00만 운영이라 주말 저녁 이후 퇴근이면 스킵), 엄마 전화는 휴무 시작일, 카톡 정리는 휴무 마지막날,
  아울렛 쇼핑은 한 달에 한 번(그 달의 첫 번째 휴무 블록 시작일).
  메뉴의 "🔔 리마인더 켜기/끄기"에서 각 항목을 개별적으로 켜고 끌 수 있음.
"""

import rumps
import subprocess
import os
import json
import shlex
import urllib.request
import threading
import datetime

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

# ── 근무별 실제 근무 시작/종료 시각 (근로계약서 기준) ─────────────
SHIFT_WORK_HOURS = {
    "Day":   {"start": (6, 0),  "end": (14, 0), "crosses_midnight": False},
    "Swing": {"start": (14, 0), "end": (22, 0), "crosses_midnight": False},
    "GY":    {"start": (22, 0), "end": (6, 0),  "crosses_midnight": True},
}

# ── 급여 계산용 시급 설정 ────────────────────────────────────
# 급여명세서의 "야간근로수당 = 야간시간 x 통상시급 x 50%" 식을
# 역산해서 얻은 값을 기본값으로 사용. 매달 명세서 나오면
# 메뉴 "시급 설정"에서 이 값을 갱신하면 됨 (설정은 CONFIG_FILE에 저장되어 재실행해도 유지됨).
HOURLY_WAGE = 14861

SHIFT_WAGE_MULTIPLIER = {
    "Day":   1.0,
    "Swing": 1.0,
    "GY":    1.5,   # 야간수당 50% 가산
}

# ── 주간 리마인더 설정 ───────────────────────────────────────
# 교대근무자는 요일이 아니라 근무표의 "휴무 블록"을 기준으로 리마인더를 잡는다.
# - 헬스장: 주 2회. 휴무 블록 연속 이틀을 몰아가면 복귀 근무가 힘드므로,
#   휴무 시작일 + 그로부터 이틀 뒤(근무 복귀 후여도 무방)로 분산.
#   헬스장은 24시간이지만 토/일은 06:00~17:00만 운영이라, 근무 끝나는 시각에
#   헬스장이 닫혀있으면(주말 저녁~다음날 새벽) 그날은 리마인더를 건너뜀
# - 엄마한테 전화: 휴무 블록의 첫날 (근무 마치고 쉬기 시작하는 날)
# - 카톡 정리: 휴무 블록의 마지막날 (다시 출근하기 전날)
# - 아울렛 쇼핑: 한 달에 한 번. 그 달의 첫 번째 휴무 블록 시작일에 알림
# 각 항목은 메뉴의 "🔔 리마인더 켜기/끄기"에서 개별적으로 켜고 끌 수 있음.
REMINDERS = {
    "gym":             {"label": "🏋️ 헬스장 가는 날",       "enabled": True},
    "call_mom":        {"label": "📞 엄마한테 전화하는 날",   "enabled": True},
    "kakao_cleanup":   {"label": "🧹 카톡 정리하는 날",       "enabled": True},
    "outlet_shopping": {"label": "🛍️ 아울렛 쇼핑하는 날",    "enabled": True},
}

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
EBOOK_PY_PATH = "/opt/anaconda3/bin/python3"
EBOOK_READER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ebook_reader.py")
EBOOK_LAST_STATE_FILE = os.path.expanduser("~/.ebook_reader_last.json")


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


def get_today_reminders(schedule, now=None):
    """
    오늘 근무표 기준으로 해당하는 리마인더 라벨 목록을 반환.

    - 헬스장: 주 2회. 휴무 블록 첫날 1회 + 그로부터 이틀 뒤 1회
      (근무 복귀 후라도 상관없음, 연속 휴무일에 몰아가면 다음 근무가 힘드므로 분산).
      단, 그날 "근무 끝나고" 헬스장에 가는 시각에 헬스장이 닫혀있으면(주말 저녁~새벽)
      그날은 리마인더를 띄우지 않는다.
    - 엄마한테 전화: 오늘이 휴무 블록의 첫날 (어제는 근무였음)
    - 카톡 정리: 오늘이 휴무 블록의 마지막날 (내일은 근무)
    """
    now = now or datetime.datetime.now()
    today = now.date()

    reminders = []
    if REMINDERS["gym"]["enabled"] and _gym_time_ok(schedule, today) and (
        _is_off_block_start(schedule, today)
        or _is_off_block_start(schedule, today - datetime.timedelta(days=2))
    ):
        reminders.append(REMINDERS["gym"]["label"])

    if get_shift_for_date(schedule, today) == "휴무":
        yesterday = today - datetime.timedelta(days=1)
        tomorrow = today + datetime.timedelta(days=1)
        is_block_start = get_shift_for_date(schedule, yesterday) != "휴무"
        is_block_end = get_shift_for_date(schedule, tomorrow) != "휴무"
        if is_block_start and REMINDERS["call_mom"]["enabled"]:
            reminders.append(REMINDERS["call_mom"]["label"])
        if is_block_end and REMINDERS["kakao_cleanup"]["enabled"]:
            reminders.append(REMINDERS["kakao_cleanup"]["label"])

    if REMINDERS["outlet_shopping"]["enabled"] and _is_first_off_block_start_of_month(schedule, today):
        reminders.append(REMINDERS["outlet_shopping"]["label"])

    return reminders


def get_today_reminder_icons(schedule, now=None):
    """메뉴바 타이틀용: 오늘의 리마인더 라벨에서 이모지만 뽑아 반환."""
    return [label.split(" ", 1)[0] for label in get_today_reminders(schedule, now=now)]


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


def open_ebook_reader_terminal(file_path):
    """ebook_reader.py를 새 터미널 창에서 실행 (검정 배경 + 초록 글씨, 확대 폰트 + 전체창, 볼륨 80%)"""
    py_cmd = f"{EBOOK_PY_PATH} {shlex.quote(EBOOK_READER_SCRIPT)} {shlex.quote(file_path)}"
    apple_script = f'''
set volume output volume 80

tell application "Terminal"
    activate
    do script "{py_cmd}"
    delay 1
    tell window 1
        set background color to {{0, 0, 0}}
        set normal text color to {{10000, 65535, 10000}}
        set font size to 28
        set zoomed to true
    end tell
end tell
'''
    subprocess.Popen(["osascript", "-e", apple_script])


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

        current = config.get("current_shift")
        title = f"⏰ {current}" if current else "⏰ 근무미설정"
        super().__init__(title, quit_button=None)

        self.weather_str = ""
        self.weather_icon = ""
        self.earnings_item = rumps.MenuItem("오늘 급여: -")
        self.weather_item = rumps.MenuItem("날씨: 로딩 중")
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

        # 급여 실시간 갱신 (30초마다)
        self.earnings_timer = rumps.Timer(self._refresh_earnings, 30)
        self.earnings_timer.start()
        self._refresh_earnings(None)

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

        money = ""
        if self.config.get("show_earnings", True):
            status = get_earnings_status(self.schedule, today_override=self._today_override())
            if status["state"] == "active":
                money = format_won_short(status["earned_so_far"])
            elif status["state"] == "waiting":
                money = format_won_short(status["total_when_done"])

        reminder_icons = "".join(get_today_reminder_icons(self.schedule))

        parts = [code, money, reminder_icons, self.weather_icon]
        self.title = " ".join(p for p in parts if p) if current else "미설정"

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
        earnings_on = self.config.get("show_earnings", True)

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
        earnings_label = f"{'✓ ' if earnings_on else ''}메뉴바에 급여 표시"
        self.menu.add(rumps.MenuItem(earnings_label, callback=self.toggle_earnings_display))
        self.menu.add(rumps.MenuItem(f"시급 설정 (현재 {HOURLY_WAGE:,}원)", callback=self.change_hourly_wage))
        self.menu.add(self.weather_item)

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

        time_menu = rumps.MenuItem("⚙️ 알람 시간 설정")
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
        self.menu.add(rumps.MenuItem("현재 설정 확인", callback=self.show_status))
        self.menu.add(None)
        self.menu.add(rumps.MenuItem("종료", callback=self.quit_app))

    # ── 시급 수정 ────────────────────────────────────────────

    def change_hourly_wage(self, _):
        threading.Thread(target=self._change_hourly_wage_thread, daemon=True).start()

    def _change_hourly_wage_thread(self):
        global HOURLY_WAGE
        val = ask_input("시급 설정", "통상시급을 입력하세요 (원)\\n※ 급여명세서 나올 때마다 업데이트 권장", str(HOURLY_WAGE))
        if val is None:
            return
        try:
            new_wage = int(val.strip().replace(",", ""))
            assert new_wage > 0
        except Exception:
            subprocess.run(["osascript", "-e", 'display alert "오류" message "숫자만 입력하세요."'])
            return
        HOURLY_WAGE = new_wage
        self.config["hourly_wage"] = new_wage
        save_config(self.config)
        self._refresh_earnings(None)
        self.build_menu()

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
        rumps.quit_application()


if __name__ == "__main__":
    ShiftAlarmApp().run()
