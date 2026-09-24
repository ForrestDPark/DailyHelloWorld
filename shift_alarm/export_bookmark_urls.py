#!/usr/bin/env python3
"""추천 사이트 폴더(天)의 URL 목록만 ~/.shift_alarm_bookmark_urls.json으로 내보낸다.

★ 2026-09-24: launchd로 뜬 python(웹서버·메뉴바)은 macOS TCC로 Chrome Bookmarks를
못 읽는다. Full Disk Access를 준 ShiftAlarmBookmarkExport.app(osacompile applet)이
이 스크립트를 실행하면 앱 권한으로 읽힌다. URL 외 다른 정보는 담지 않는다."""
import json, os, sys

SRC = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/Bookmarks")
DST = os.path.expanduser("~/.shift_alarm_bookmark_urls.json")
FOLDER = "天"


def collect(node):
    urls = []
    for child in node.get("children", []) or []:
        if child.get("type") == "url" and child.get("url"):
            urls.append(child["url"])
        elif child.get("type") == "folder":
            urls.extend(collect(child))
    return urls


def find(node, name):
    if node.get("type") == "folder" and node.get("name") == name:
        return node
    for child in node.get("children", []) or []:
        found = find(child, name)
        if found:
            return found
    return None


def main():
    with open(SRC, encoding="utf-8") as file:
        roots = json.load(file).get("roots", {})
    folder = next((f for k in ("bookmark_bar", "other", "synced") if k in roots
                   for f in [find(roots[k], FOLDER)] if f), None)
    if not folder:
        return 1
    urls = list(dict.fromkeys(collect(folder)))
    tmp = DST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump({"folder": FOLDER, "urls": urls}, file, ensure_ascii=False)
    os.replace(tmp, DST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
