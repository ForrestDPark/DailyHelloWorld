#!/usr/bin/env python3
"""app_uninstaller.py를 Launchpad에서 아이콘으로 보이는 더블클릭 가능한 .app으로
감싼다. AppleScript로 앱 이름을 입력받는 대화상자를 띄운 뒤 Terminal에서
`app_uninstaller.py <이름> --delete`를 실행한다 — 실제 삭제 전 미리보기와
y/N 확인은 app_uninstaller.py 자체가 이미 하므로 안전장치를 새로 만들 필요가
없다. 아이콘은 macOS 기본 이모지 폰트(Apple Color Emoji)를 렌더링해서 만든다
(2026-08-13, "Launchpad에 아이콘으로 보이게 해달라"는 요청으로 추가).

재실행하면 기존 앱을 지우고 다시 만든다(스크립트 경로·아이콘이 바뀌었을 때
다시 빌드하기 위함).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
UNINSTALLER_PY = SCRIPT_DIR / "app_uninstaller.py"
APP_NAME = "App Uninstaller"
INSTALL_DIR = Path.home() / "Applications"
APP_PATH = INSTALL_DIR / f"{APP_NAME}.app"
EMOJI = "🗑️"

ICONSET_SIZES = [16, 32, 64, 128, 256, 512, 1024]  # iconutil이 요구하는 정확한 크기 집합


def build_icns(tmp_dir: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype("/System/Library/Fonts/Apple Color Emoji.ttc", 160)
    base = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(base)
    draw.text((0, 0), EMOJI, font=font, embedded_color=True)
    bbox = base.getbbox()
    if bbox:
        base = base.crop(bbox)

    iconset = tmp_dir / "AppIcon.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    for size in ICONSET_SIZES:
        resized = base.resize((size, size), Image.LANCZOS)
        resized.save(iconset / f"icon_{size}x{size}.png")
        if size <= 512:
            resized2x = base.resize((size * 2, size * 2), Image.LANCZOS)
            resized2x.save(iconset / f"icon_{size}x{size}@2x.png")

    icns_path = tmp_dir / "AppIcon.icns"
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns_path)], check=True)
    return icns_path


def build_app() -> None:
    if not UNINSTALLER_PY.exists():
        raise SystemExit(f"app_uninstaller.py를 찾을 수 없습니다: {UNINSTALLER_PY}")

    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    if APP_PATH.exists():
        shutil.rmtree(APP_PATH)

    # ★ 2026-08-13 실측 버그: 파이썬 f-string에 !r로 경로를 넣으면 작은따옴표로
    # 감싸지는데, AppleScript 문자열 리터럴은 큰따옴표만 허용한다 — osacompile이
    # 엉뚱한 줄(실제 오류 지점보다 앞선 줄)을 가리키며 "Expected expression but
    # found unknown token"을 내서 원인 찾기 까다로웠다. 항상 큰따옴표로 직접 감쌀 것.
    applescript_src = f'''
display dialog "완전히 삭제할 앱 이름을 입력하세요 (예: Command, ChatGPT):" default answer "" with title "앱 완전 삭제" with icon note
set appName to text returned of result
if appName is "" then
    display dialog "앱 이름을 입력해야 합니다." buttons {{"확인"}} default button 1 with icon caution
    return
end if

set scriptPath to "{UNINSTALLER_PY.as_posix()}"
set cmd to "python3 " & quoted form of scriptPath & " " & quoted form of appName & " --delete; echo; echo '엔터를 누르면 창이 닫힙니다.'; read"

tell application "Terminal"
    activate
    do script cmd
end tell
'''
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        script_path = tmp_dir / "launcher.applescript"
        script_path.write_text(applescript_src, encoding="utf-8")

        print("🔨 .app 빌드 중...")
        subprocess.run(["osacompile", "-o", str(APP_PATH), str(script_path)], check=True)

        print("🎨 아이콘 생성 중...")
        icns_path = build_icns(tmp_dir)
        resources_dir = APP_PATH / "Contents/Resources"
        # osacompile이 만든 기본 애플릿 아이콘(보통 applet.icns)을 우리 아이콘으로 교체.
        for existing_icns in resources_dir.glob("*.icns"):
            existing_icns.unlink()
        shutil.copy(icns_path, resources_dir / "applet.icns")

    subprocess.run(["touch", str(APP_PATH)], check=False)  # Launch Services가 바로 다시 스캔하게
    subprocess.run(["/usr/bin/killall", "Dock"], check=False)  # Launchpad 캐시 새로고침

    print(f"✅ 완료: {APP_PATH}")
    print("   Launchpad에서 'App Uninstaller'로 검색하면 보입니다(Dock이 잠깐 재시작됩니다).")


if __name__ == "__main__":
    build_app()
