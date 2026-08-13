#!/usr/bin/env python3
"""app_uninstaller.py를 Launchpad에서 아이콘으로 보이는 더블클릭 가능한 .app으로
감싼다. AppleScript로 앱 이름을 입력받는 대화상자를 띄운 뒤 Terminal에서
`app_uninstaller.py <이름> --delete`를 실행한다 — 실제 삭제 전 미리보기와
y/N 확인은 app_uninstaller.py 자체가 이미 하므로 안전장치를 새로 만들 필요가
없다. 아이콘은 macOS 기본 이모지 폰트(Apple Color Emoji)를 렌더링해서 만든다
(2026-08-13, "Launchpad에 아이콘으로 보이게 해달라"는 요청으로 추가).

재실행하면 기존 앱을 지우고 다시 만든다(스크립트 경로·아이콘이 바뀌었을 때
다시 빌드하기 위함).

★ 2026-08-13 실측 트러블슈팅 기록 — 앱 이름을 "App Uninstaller"에서
"Uninstall App"으로 바꾼 이유: 처음엔 CFBundleIdentifier가 아예 없이 빌드해서
("App Uninstaller"라는 이름 자체를 유사 번들 ID로 자동 대체해 등록됨), 나중에
CFBundleIdentifier를 추가하고 재서명까지 해도 `lsregister -dump`에는 여전히
`bundle id: App Uninstaller`(진짜 CFBundleIdentifier가 아니라 이름 기반 값)로
캐시돼 있었다 — Launchpad DB가 이 앱을 계속 목록에서 빼버렸다(mdfind/Spotlight와
lsregister -f 등록 자체는 잘 됐는데도). `lsregister -u`로 명시적 등록 해제까지
해봐도 안 고쳐졌다. 완전히 새 이름("TestD" 등)으로 빌드하면 바로 정상적으로
Launchpad에 나타나는 것으로 원인을 좁혔다 — Launch Services가 "이름 기반
가짜 번들 ID"로 한번 등록된 경로는 이후 진짜 CFBundleIdentifier로 갱신해도
어떤 이유에서인지 계속 걸러내는 것으로 보인다(정확한 내부 동작은 불명, 재현
방법만 확인). 그래서 아예 새 이름으로 바꿔서 그 캐시 자체를 피해간다."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
UNINSTALLER_PY = SCRIPT_DIR / "app_uninstaller.py"
APP_NAME = "Uninstall App"
BUNDLE_ID = "com.forrestdpark.uninstall-app"
INSTALL_DIR = Path.home() / "Applications"
APP_PATH = INSTALL_DIR / f"{APP_NAME}.app"
LSREGISTER = Path(
    "/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/"
    "LaunchServices.framework/Versions/A/Support/lsregister"
)
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
    # ★ 2026-08-13: 이름을 타이핑하는 대화상자 대신, Applications 폴더를 눈으로
    # 보고 고르는 표준 Finder 열기 대화상자로 바꿨다("application 폴더에서 볼 수
    # 있게 창을 띄워달라"는 피드백). "of type"으로 .app 번들만 선택 가능하게
    # 필터링. 취소를 누르면 AppleScript가 에러 번호 -128을 던지므로 그걸 잡아서
    # 조용히 종료한다(에러 대화상자 안 뜨게).
    applescript_src = f'''
try
    set appFile to choose file with prompt "완전히 삭제할 앱을 선택하세요:" default location (path to applications folder) of type {{"com.apple.application-bundle"}}
on error number -128
    return
end try

set appPath to POSIX path of appFile
if appPath ends with "/" then set appPath to text 1 thru -2 of appPath

set scriptPath to "{UNINSTALLER_PY.as_posix()}"
set cmd to "python3 " & quoted form of scriptPath & " " & quoted form of appPath & " --delete; echo; echo '엔터를 누르면 창이 닫힙니다.'; read"

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

    # ★ 2026-08-13 실측 버그 1: osacompile이 만든 Info.plist에는 CFBundleIdentifier가
    # 아예 없다. Launch Services 등록(lsregister)과 Spotlight(mdfind)는 이것 없이도
    # 되는데, Launchpad 자체 DB(~/...com.apple.dock.launchpad/db/db)는 이게 없으면
    # 앱을 목록에 안 넣는다 — "왜 검색으로만 찾아지고 아이콘 그리드엔 안 보이냐"는
    # 신고로 발견. plutil로 직접 추가한다.
    info_plist_path = APP_PATH / "Contents/Info.plist"
    subprocess.run([
        "plutil", "-insert", "CFBundleIdentifier", "-string", BUNDLE_ID, str(info_plist_path),
    ], check=True)

    # ★ 실측 버그 2: osacompile은 빌드 시점에 앱을 애드혹 서명해두는데, Info.plist를
    # 그 뒤에 수정하면(위 CFBundleIdentifier 삽입, 아이콘 교체) 서명이 깨진다
    # (`codesign -v`가 "invalid Info.plist (plist or signature have been modified)"라고
    # 보고함). Launchpad는 서명이 깨진 앱을 조용히 목록에서 빼는 것으로 보인다 —
    # 그래서 CFBundleIdentifier를 넣었는데도 여전히 안 나타났다. Info.plist와
    # 리소스를 다 바꾼 뒤 마지막에 다시 애드혹 서명해야 한다.
    subprocess.run(["codesign", "--force", "--deep", "-s", "-", str(APP_PATH)], check=True)
    verify = subprocess.run(["codesign", "-v", str(APP_PATH)], capture_output=True, text=True)
    if verify.returncode != 0:
        print(f"⚠️  재서명 후에도 서명 검증 실패: {verify.stderr.strip()}")

    subprocess.run(["/usr/bin/touch", str(APP_PATH)], check=False)
    subprocess.run([str(LSREGISTER), "-f", str(APP_PATH)], check=False)  # Launch Services에 재등록
    subprocess.run(["defaults", "write", "com.apple.dock", "ResetLaunchPad", "-bool", "true"], check=False)
    subprocess.run(["/usr/bin/killall", "Dock"], check=False)  # Launchpad DB 재구성 트리거

    print(f"✅ 완료: {APP_PATH}")
    print(f"   Spotlight(⌘+Space)에서 '{APP_NAME}'로 검색하면 바로 찾아서 실행할 수 있습니다.")
    print("   ⚠️  Launchpad 아이콘 그리드에는 macOS Launch Services 캐시 문제로")
    print("      바로 안 보일 수 있습니다(README의 '알려진 문제' 참고) — 그럴 땐 맥을")
    print("      재시동하면 대부분 해결됩니다. 그전까지는 Spotlight나 Dock에 직접")
    print("      끌어다 놓는 방식으로 실행하세요.")


if __name__ == "__main__":
    build_app()
