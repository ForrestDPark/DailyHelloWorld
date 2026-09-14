"""독립 실행 스크립트 — 시스템 미디어 키(재생/일시정지·다음곡·이전곡) 이벤트를
posts한다. Elmedia(Mac App Store 샌드박스 빌드)는 표준 AppleScript pause
동사가 없어서(shift_alarm.py의 ★2026-08-29 항목·`_send_media_play_pause_key`와
같은 이유) 앱별 제어 대신 시스템 전체 미디어 키를 누른다.

이 파일이 shift_alarm.py 안이 아니라 별도 스크립트인 이유: 미디어 키
전송(Quartz.CGEventPost)은 호출 프로세스에 macOS Accessibility 권한이
필요한데, 이미 그 권한을 갖고 있(었)을 `/opt/anaconda3/bin/python3` 신원을
그대로 빌려 쓰기 위해 다른 프로세스(chatapp 서버 등)가
`subprocess.run(["/opt/anaconda3/bin/python3", "send_media_key.py", action])`로
호출한다 — chatapp 서버 자신의 venv 인터프리터로 실행하면 그 인터프리터가
따로 Accessibility 승인을 받아야 하는 새 신원이 된다.

사용법: python3 send_media_key.py <playpause|next|previous>
"""
import sys

from AppKit import NSEvent
import Quartz

NX_KEYTYPE_PLAY = 16
NX_KEYTYPE_NEXT = 17
NX_KEYTYPE_PREVIOUS = 18

KEY_MAP = {"playpause": NX_KEYTYPE_PLAY, "next": NX_KEYTYPE_NEXT, "previous": NX_KEYTYPE_PREVIOUS}


def send_media_key(key_type):
    for key_down in (True, False):
        event = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            Quartz.NSSystemDefined, (0, 0), 0xa00 if key_down else 0xb00, 0, 0, 0, 8,
            (key_type << 16) | ((0xa if key_down else 0xb) << 8), -1,
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event.CGEvent())


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    key_type = KEY_MAP.get(action)
    if key_type is None:
        print(f"알 수 없는 동작: {action!r} (playpause|next|previous 중 하나)", file=sys.stderr)
        sys.exit(1)
    send_media_key(key_type)
