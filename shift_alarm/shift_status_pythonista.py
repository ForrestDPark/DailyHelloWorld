# coding: utf-8
"""ShiftAlarm 상태 확인 — Pythonista(아이폰)용.

같은 폴더(iCloud Drive/Pythonista 3/Documents, 자동 동기화됨)의 status.json을
읽어 오늘 근무/날씨/리마인더/저장공간을 보기 좋게 출력한다. 파일 선택기나
보안 스코프 북마크가 필요 없다 — Pythonista는 자기 iCloud Documents 폴더를
항상 그냥 읽을 수 있기 때문에, Mac의 shift_alarm.py가 이 폴더에 status.json을
써두기만 하면 이 스크립트는 그걸 바로 읽는다.

Pythonista 앱에서 이 파일을 탭해서 실행하면 된다(재생 버튼 ▶).
"""
import json
import os

import console

STATUS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "status.json")

SHIFT_LABELS = {
    "Day": "☀️ 주간",
    "Swing": "\U0001f307 오후",
    "GY": "\U0001f319 야간",
    "휴무": "\U0001f6cc 휴무",
}


def load_status():
    if not os.path.exists(STATUS_FILE):
        return None
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def main():
    console.clear()
    status = load_status()
    if status is None:
        console.set_color(1, 0.3, 0.3)
        print("status.json을 찾을 수 없습니다.")
        console.set_color(1, 1, 1)
        print("Mac의 shift_alarm이 켜져 있고,")
        print("iCloud 동기화가 끝났는지 확인해주세요.")
        return

    shift = status.get("shift")
    shift_label = SHIFT_LABELS.get(shift, shift or "미설정")
    day_num = status.get("shift_day_number")

    console.set_color(1, 1, 1)
    print("=" * 28)
    console.set_color(0.3, 0.7, 1)
    title = f"  {shift_label}"
    if day_num:
        title += f" ({day_num}일째)"
    print(title)
    console.set_color(1, 1, 1)
    print("=" * 28)

    weather = status.get("weather")
    if weather:
        print(f"\U0001f324  날씨: {weather}")

    storage = status.get("storage_free_gb")
    if storage is not None:
        low = storage <= 5
        console.set_color(1, 0.3, 0.3) if low else console.set_color(1, 1, 1)
        print(f"\U0001f4be 저장공간: {storage}GB 남음")
        console.set_color(1, 1, 1)

    reminders = status.get("reminders") or []
    print("")
    if reminders:
        print("\U0001f514 오늘의 리마인더")
        for r in reminders:
            print(f"  · {r}")
    else:
        print("\U0001f514 오늘 예정된 리마인더 없음")

    updated_at = status.get("updated_at")
    if updated_at:
        console.set_color(0.6, 0.6, 0.6)
        print("")
        print(f"업데이트: {updated_at}")
        console.set_color(1, 1, 1)


if __name__ == "__main__":
    main()
