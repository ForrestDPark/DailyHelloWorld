#!/usr/bin/env python3
"""macOS 앱을 완전히 지운다 — 앱 본체뿐 아니라 샌드박스 컨테이너, 캐시,
환경설정, 로그, LaunchAgent 같은 관련 지원 파일까지 번들 ID 기준으로 찾아서
함께 정리한다. Command.app(Philips Hue) 삭제를 수동으로 했던 절차(앱 찾기 →
번들 ID로 Containers/Group Containers/Application Scripts 뒤지기 → 휴지통
이동)를 재사용 가능한 도구로 일반화했다(2026-08-13).

기본은 항상 dry-run이다 — --delete를 줘야 실제로 지운다. 삭제는 영구 삭제가
아니라 macOS 휴지통으로 이동이라(Finder의 move to trash와 동일) 실수해도
복구할 수 있다.

사용자 홈 폴더(~/Library) 안의 표준 위치만 다룬다. /Library(시스템 전역)나
LaunchDaemons처럼 관리자 권한이 필요한 위치는 찾아서 "직접 확인 필요"로만
알려주고 건드리지 않는다 — sudo 없이, 실수로 다른 사용자·시스템에 영향을
주지 않기 위함.
"""

from __future__ import annotations

import argparse
import plistlib
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

HOME = Path.home()

# ★ 이 위치들은 사용자 권한만으로 안전하게 지울 수 있다. {bundle_id}와
# {token}(번들 ID에서 만든, 회사·제품명 부분만 남긴 느슨한 검색어) 두 가지
# 방식으로 찾는다 — Application Support 등은 번들 ID가 아니라 앱 표시 이름
# 폴더를 쓰는 경우가 많아서 느슨한 매칭도 같이 해야 한다(실측: Command.app의
# Group Container는 "group.com.leporati.huecommand.shared"로 번들 ID
# "com.huecommand.app"과 정확히 일치하지 않고 "huecommand"라는 토큰만 공유).
USER_LOCATIONS: list[tuple[str, Path]] = [
    ("샌드박스 컨테이너", HOME / "Library/Containers"),
    ("그룹 컨테이너", HOME / "Library/Group Containers"),
    ("앱 지원 파일", HOME / "Library/Application Support"),
    ("캐시", HOME / "Library/Caches"),
    ("환경설정", HOME / "Library/Preferences"),
    ("앱 스크립트(샌드박스)", HOME / "Library/Application Scripts"),
    ("저장된 앱 상태", HOME / "Library/Saved Application State"),
    ("WebKit 저장소", HOME / "Library/WebKit"),
    ("HTTP 저장소", HOME / "Library/HTTPStorages"),
    ("쿠키", HOME / "Library/Cookies"),
    ("로그", HOME / "Library/Logs"),
    ("사용자 LaunchAgent", HOME / "Library/LaunchAgents"),
]

# 관리자 권한이 필요해서 자동으로 못 지우는 위치 — 발견하면 알려만 준다.
SYSTEM_LOCATIONS_TO_WARN: list[tuple[str, Path]] = [
    ("시스템 전역 앱 지원 파일", Path("/Library/Application Support")),
    ("시스템 LaunchAgent", Path("/Library/LaunchAgents")),
    ("시스템 LaunchDaemon", Path("/Library/LaunchDaemons")),
]


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()


def find_app(query: str) -> Path:
    """앱 이름(부분 일치) 또는 .app 경로를 받아 실제 .app 번들 경로를 찾는다."""
    candidate = Path(query).expanduser()
    if candidate.suffix == ".app" and candidate.exists():
        return candidate

    # /Applications, ~/Applications에서 이름으로 먼저 찾는다(가장 흔한 경우, 빠름).
    search_dirs = [Path("/Applications"), HOME / "Applications"]
    matches = []
    for d in search_dirs:
        if not d.is_dir():
            continue
        for app in d.glob("*.app"):
            if query.lower() in app.stem.lower():
                matches.append(app)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = "\n".join(f"  - {m}" for m in matches)
        raise SystemExit(f"'{query}'와 일치하는 앱이 여러 개입니다. 정확한 이름이나 경로를 지정하세요:\n{names}")

    # 못 찾으면 Spotlight(mdfind)로 넓게 찾는다(다른 위치에 설치된 경우 대비).
    output = _run(["mdfind", f"kMDItemKind == 'Application' && kMDItemDisplayName == '*{query}*'c"])
    found = [Path(line) for line in output.splitlines() if line]
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        names = "\n".join(f"  - {m}" for m in found)
        raise SystemExit(f"'{query}'와 일치하는 앱이 여러 개입니다. 정확한 이름이나 경로를 지정하세요:\n{names}")

    raise SystemExit(f"'{query}'에 해당하는 앱을 찾지 못했습니다.")


def get_bundle_id(app_path: Path) -> str | None:
    output = _run(["mdls", "-name", "kMDItemCFBundleIdentifier", "-raw", str(app_path)])
    if output and output != "(null)":
        return output
    # mdls가 실패하면 Info.plist에서 직접 읽는다.
    info_plist = app_path / "Contents/Info.plist"
    if info_plist.exists():
        try:
            with open(info_plist, "rb") as f:
                data = plistlib.load(f)
            return data.get("CFBundleIdentifier")
        except (plistlib.InvalidFileException, OSError):
            pass
    return None


def get_app_groups(app_path: Path) -> list[str]:
    """codesign 서명 정보에서 application-groups 엔타이틀먼트를 읽는다(있으면).
    실패해도 치명적이지 않음 — 못 읽으면 빈 리스트, 토큰 기반 느슨한 매칭으로 보완."""
    output = subprocess.run(
        ["codesign", "-d", "--entitlements", ":-", str(app_path)],
        capture_output=True, text=True,
    ).stdout
    if not output.strip():
        return []
    try:
        data = plistlib.loads(output.encode("utf-8"))
    except (plistlib.InvalidFileException, ValueError):
        return []
    return list(data.get("com.apple.security.application-groups", []))


def _bundle_token(bundle_id: str) -> str:
    """'com.huecommand.app' → 'huecommand'처럼, 흔한 접두사(com/net/org)와
    'app' 같은 범용 접미사를 뺀 나머지 중 가장 의미 있는 조각을 검색어로 쓴다."""
    parts = [p for p in bundle_id.split(".") if p not in ("com", "net", "org", "io", "app", "mac", "macos")]
    return max(parts, key=len) if parts else bundle_id


def find_related_paths(app_path: Path, bundle_id: str | None, app_groups: list[str]) -> list[Path]:
    found: list[Path] = []
    token = _bundle_token(bundle_id) if bundle_id else app_path.stem.lower()
    app_name = app_path.stem

    for _label, base in USER_LOCATIONS:
        if not base.is_dir():
            continue
        for entry in base.iterdir():
            if _is_related(entry.name, bundle_id, app_groups, token, app_name):
                found.append(entry)

    return found


def _is_related(entry_name: str, bundle_id: str | None, app_groups: list[str], token: str, app_name: str) -> bool:
    """★ 2026-08-13 버그 수정: 처음엔 "짧은 이름이 긴 그룹 문자열 안에 포함되는지"도
    같이 봤는데(`name_lower in group.lower()`), 이러면 "code"가 "...openai.codex..."
    안에 우연히 들어있다는 이유만으로 매칭돼 완전히 무관한 VS Code의 Application
    Support 폴더(779MB)까지 삭제 후보에 걸리는 사고가 실측으로 발견됐다("codex"
    안에 "code"가 그냥 부분 문자열로 들어있을 뿐인데). 짧은 이름 쪽에서 긴 문자열
    "안"을 뒤지는 방향은 아예 없앴다 — 정확히 같거나(exact), 점으로 구분된 단어
    경계에서 시작하거나(prefix), 단어 경계로 둘러싸여야만(\\b) 매칭으로 친다."""
    name_lower = entry_name.lower()
    if bundle_id:
        bid = bundle_id.lower()
        if name_lower == bid or name_lower.startswith(bid + "."):
            return True
    for group in app_groups:
        if name_lower == group.lower():  # Group Container는 그룹 ID와 정확히 같은 이름으로 생성된다
            return True
    if token and len(token) >= 5:
        if re.search(r"\b" + re.escape(token.lower()) + r"\b", name_lower):
            return True
    if app_name and app_name.lower() == Path(entry_name).stem.lower():
        return True
    return False


def find_system_warnings(bundle_id: str | None, app_name: str, app_groups: list[str]) -> list[Path]:
    warnings = []
    token = _bundle_token(bundle_id) if bundle_id else app_name.lower()
    for _label, base in SYSTEM_LOCATIONS_TO_WARN:
        if not base.is_dir():
            continue
        try:
            entries = list(base.iterdir())
        except PermissionError:
            continue
        for entry in entries:
            if _is_related(entry.name, bundle_id, app_groups, token, app_name):
                warnings.append(entry)
    return warnings


def dir_size(path: Path) -> int:
    if path.is_file() or path.is_symlink():
        try:
            return path.lstat().st_size
        except OSError:
            return 0
    total = 0
    try:
        for child in path.rglob("*"):
            try:
                if child.is_file() or child.is_symlink():
                    total += child.lstat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def quit_app(app_path: Path, bundle_id: str | None) -> None:
    app_name = app_path.stem
    subprocess.run(["osascript", "-e", f'tell application "{app_name}" to quit'],
                    capture_output=True, text=True)
    import time
    for _ in range(10):
        result = subprocess.run(["pgrep", "-f", str(app_path / "Contents/MacOS")],
                                 capture_output=True, text=True)
        if result.returncode != 0:
            return
        time.sleep(0.3)
    # 정상 종료가 안 되면 강제 종료.
    subprocess.run(["pkill", "-9", "-f", str(app_path / "Contents/MacOS")],
                    capture_output=True, text=True)


def move_to_trash(paths: list[Path]) -> list[Path]:
    """Finder의 "휴지통으로 이동"과 동일 — 영구 삭제가 아니라 복구 가능."""
    moved = []
    for path in paths:
        script = f'tell application "Finder" to move POSIX file "{path}" to trash'
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if result.returncode == 0:
            moved.append(path)
        else:
            print(f"  ⚠️  실패: {path} ({result.stderr.strip()})")
    return moved


def main() -> None:
    parser = argparse.ArgumentParser(description="macOS 앱을 관련 지원 파일까지 함께 완전히 지운다(기본 dry-run)")
    parser.add_argument("app", help="앱 이름(부분 일치) 또는 .app 경로")
    parser.add_argument("--delete", action="store_true", help="실제로 휴지통으로 이동(기본은 미리보기만)")
    parser.add_argument("--yes", action="store_true", help="--delete와 함께 쓰면 확인 프롬프트 생략")
    args = parser.parse_args()

    app_path = find_app(args.app)
    bundle_id = get_bundle_id(app_path)
    app_groups = get_app_groups(app_path)

    print(f"📦 앱: {app_path}")
    print(f"🆔 번들 ID: {bundle_id or '(확인 못함)'}")
    if app_groups:
        print(f"👥 앱 그룹: {', '.join(app_groups)}")

    related = find_related_paths(app_path, bundle_id, app_groups)
    all_paths = [app_path] + related
    warnings = find_system_warnings(bundle_id, app_path.stem, app_groups)

    print(f"\n🗑️  삭제 대상 {len(all_paths)}개:")
    total = 0
    for p in all_paths:
        size = dir_size(p)
        total += size
        print(f"   {human_size(size):>8}  {p}")
    print(f"   {'합계':>8}  {human_size(total)}")

    if warnings:
        print(f"\n⚠️  관리자 권한이 필요해 자동으로 못 지우는 항목 {len(warnings)}개(직접 확인·삭제 필요):")
        for p in warnings:
            print(f"   - {p}")

    if not args.delete:
        print("\nℹ️  미리보기만 했습니다. 실제로 지우려면 --delete를 붙이세요.")
        return

    if not args.yes:
        answer = input(f"\n정말로 위 {len(all_paths)}개 항목을 휴지통으로 옮길까요? [y/N] ").strip().lower()
        if answer != "y":
            print("취소했습니다.")
            return

    print("\n🛑 앱 종료 중...")
    quit_app(app_path, bundle_id)

    print("🗑️  휴지통으로 이동 중...")
    moved = move_to_trash(all_paths)
    print(f"\n✅ {len(moved)}/{len(all_paths)}개 항목을 휴지통으로 옮겼습니다.")


if __name__ == "__main__":
    main()
