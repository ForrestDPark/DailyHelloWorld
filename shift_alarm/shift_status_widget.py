# coding: utf-8
"""ShiftAlarm 상태 확인 — Pythonista Today 위젯용.

같은 폴더(iCloud 동기화)의 status.json을 읽어 근무/날씨/저장공간/리마인더를
위젯 뷰(ui.View)로 그린다. 잠금화면에서 오른쪽으로 스와이프하거나, 홈 화면
첫 페이지에서 왼쪽으로 스와이프하면 나오는 "Today View"에 추가해서 쓴다.

추가 방법: Today View 화면 맨 아래로 스크롤 → "편집" → "위젯 더 보기"에서
Pythonista 찾아 추가 → 그 위젯을 길게 눌러 편집 → 실행할 스크립트로 이 파일
선택.

일반 앱 안에서 재생(▶) 버튼으로 실행하면 위젯이 아니라 일반 화면으로 미리
보기가 뜬다(디버깅용).
"""
import json
import os

import appex
import ui

STATUS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "status.json")

SHIFT_LABELS = {
    "Day": "☀️ 주간",
    "Swing": "\U0001f307 오후",
    "GY": "\U0001f319 야간",
    "휴무": "\U0001f6cc 휴무",
}

BG_COLOR = "#1c1c1e"
TITLE_COLOR = "#5ac8fa"
TEXT_COLOR = "#ffffff"
DIM_COLOR = "#8e8e93"
SUB_COLOR = "#d1d1d6"
WARN_COLOR = "#ff6961"

MAX_REMINDERS_SHOWN = 3


def load_status():
    if not os.path.exists(STATUS_FILE):
        return None
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def make_label(text, y, font_size=14, color=TEXT_COLOR, bold=False):
    lbl = ui.Label()
    lbl.frame = (12, y, 100, font_size + 6)
    lbl.flex = "W"
    lbl.font = ("<system-bold>" if bold else "<system>", font_size)
    lbl.text_color = color
    lbl.text = text
    lbl.number_of_lines = 1
    return lbl


def build_view():
    status = load_status()
    view = ui.View()
    view.bg_color = BG_COLOR

    if status is None:
        view.height = 56
        view.add_subview(make_label("⚠️ status.json을 찾을 수 없습니다", 8, 14, WARN_COLOR))
        view.add_subview(make_label("Mac의 shift_alarm 확인 필요", 30, 12, DIM_COLOR))
        return view

    shift = status.get("shift")
    shift_label = SHIFT_LABELS.get(shift, shift or "미설정")
    day_num = status.get("shift_day_number")
    title = shift_label + (f" ({day_num}일째)" if day_num else "")

    weather = status.get("weather") or ""
    storage = status.get("storage_free_gb")
    reminders = status.get("reminders") or []

    y = 8
    view.add_subview(make_label(title, y, 17, TITLE_COLOR, bold=True))
    y += 26

    if weather:
        view.add_subview(make_label(f"\U0001f324 {weather}", y, 13, TEXT_COLOR))
        y += 20

    if storage is not None:
        color = WARN_COLOR if storage <= 5 else TEXT_COLOR
        view.add_subview(make_label(f"\U0001f4be 저장공간 {storage}GB", y, 13, color))
        y += 20

    y += 4
    if reminders:
        view.add_subview(make_label("\U0001f514 오늘의 리마인더", y, 12, DIM_COLOR, bold=True))
        y += 18
        for r in reminders[:MAX_REMINDERS_SHOWN]:
            view.add_subview(make_label(f"· {r}", y, 12, SUB_COLOR))
            y += 17
        remaining = len(reminders) - MAX_REMINDERS_SHOWN
        if remaining > 0:
            view.add_subview(make_label(f"외 {remaining}건", y, 11, DIM_COLOR))
            y += 16
    else:
        view.add_subview(make_label("\U0001f514 오늘 리마인더 없음", y, 12, DIM_COLOR))
        y += 17

    view.height = y + 8
    return view


def main():
    view = build_view()
    if appex.is_widget():
        appex.set_widget_view(view)
    else:
        view.present("sheet")


if __name__ == "__main__":
    main()
