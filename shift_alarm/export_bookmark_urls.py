#!/usr/bin/env python3
"""추천 사이트 폴더(天)의 URL 목록만 ~/.shift_alarm_bookmark_urls.json으로 내보낸다.

★ 2026-09-24: launchd로 뜬 python(웹서버·메뉴바)은 macOS TCC로 Chrome Bookmarks를
못 읽는다. Full Disk Access를 준 ShiftAlarmBookmarkExport.app(osacompile applet)이
이 스크립트를 실행하면 앱 권한으로 읽힌다. URL 외 다른 정보는 담지 않는다."""
import json, os, sys

SRC = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/Bookmarks")
# 앱(AppleScript)이 자기 권한으로 읽어 넘겨준 임시 사본 — URL만 추린 뒤 지운다.
RAW = os.path.expanduser("~/.shift_alarm_bookmarks_raw.tmp")
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


BOOKMARKS_HTML = os.path.expanduser("~/bookmarks.html")


def urls_from_html(path, folder_name):
    """Chrome '북마크 내보내기' HTML(Netscape 형식)에서 folder_name 폴더의 URL만 뽑는다.
    macOS 권한(TCC)이 막힌 환경에서도 사용자가 직접 내보낸 파일은 읽을 수 있다."""
    from html.parser import HTMLParser

    class Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack, self.pending, self.in_h3, self.urls = [], None, False, []

        def handle_starttag(self, tag, attrs):
            if tag == "h3":
                self.in_h3 = True
            elif tag == "dl":
                self.stack.append(self.pending)
                self.pending = None
            elif tag == "a" and folder_name in self.stack:
                href = dict(attrs).get("href")
                if href:
                    self.urls.append(href)

        def handle_endtag(self, tag):
            if tag == "h3":
                self.in_h3 = False
            elif tag == "dl" and self.stack:
                self.stack.pop()

        def handle_data(self, data):
            if self.in_h3:
                self.pending = data.strip()

    parser = Parser()
    with open(path, encoding="utf-8") as file:
        parser.feed(file.read())
    return list(dict.fromkeys(parser.urls))


def main():
    if os.path.isfile(BOOKMARKS_HTML) and "--html" in sys.argv:
        urls = urls_from_html(BOOKMARKS_HTML, FOLDER)
        if not urls:
            return 1
        tmp = DST + ".tmp"
        with open(tmp, "w", encoding="utf-8") as file:
            json.dump({"folder": FOLDER, "urls": urls}, file, ensure_ascii=False)
        os.replace(tmp, DST)
        return 0
    path = RAW if os.path.isfile(RAW) else SRC
    try:
        with open(path, encoding="utf-8") as file:
            roots = json.load(file).get("roots", {})
    finally:
        if path == RAW:
            os.remove(RAW)
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
