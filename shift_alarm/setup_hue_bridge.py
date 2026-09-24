#!/usr/bin/env python3
"""Hue Bridge에 직접 연결해 shift_alarm 전용 앱 키를 발급한다.

★ 2026-09-24: Command 앱의 Group Container 설정 파일은 launchd로 뜬 프로세스가
macOS 권한(TCC)으로 못 읽어 조명 제어가 막혔다. 이 스크립트가 Bridge에서 직접
키를 받아 ~/.shift_alarm_hue.json(권한 600)에 저장하면 shift_alarm.py가 그걸
우선 쓴다. 실행하면 60초 안에 Bridge 윗면의 링크 버튼을 눌러야 한다."""
import json, os, ssl, sys, time, urllib.request

CONFIG = os.path.expanduser("~/.shift_alarm_hue.json")


def discover_ip():
    request = urllib.request.Request("https://discovery.meethue.com", headers={"User-Agent": "shift_alarm"})
    with urllib.request.urlopen(request, timeout=10) as response:
        bridges = json.load(response)
    if not bridges:
        raise SystemExit("Bridge를 찾지 못했습니다. IP를 인자로 넘겨주세요: setup_hue_bridge.py <IP>")
    return bridges[0]["internalipaddress"]


def main():
    ip = sys.argv[1] if len(sys.argv) > 1 else discover_ip()
    print(f"Bridge: {ip}\n👉 지금 Bridge 윗면의 둥근 링크 버튼을 누르세요 (60초 대기)")
    context = ssl._create_unverified_context()
    body = json.dumps({"devicetype": "shift_alarm#mac"}).encode()
    for attempt in range(1, 31):
        request = urllib.request.Request(f"https://{ip}/api", data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10, context=context) as response:
                result = json.load(response)[0]
        except Exception as exc:
            print(f"[{attempt}/30] ❌ Bridge 연결 실패: {exc}")
            print("   → 시스템 설정 > 개인정보 보호 및 보안 > 로컬 네트워크에서 Terminal이 켜져 있는지 확인하세요.")
            time.sleep(2)
            continue
        if "error" in result:
            print(f"[{attempt}/30] ⏳ 링크 버튼 대기 중... ({result['error'].get('description', '')})")
        if "success" in result:
            key = result["success"]["username"]
            fd = os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump({"ip": ip, "app_key": key}, file)
            print(f"✅ 저장 완료: {CONFIG}")
            return 0
        time.sleep(2)
    print("⚠️ 링크 버튼이 눌리지 않았습니다. 다시 실행해주세요.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
