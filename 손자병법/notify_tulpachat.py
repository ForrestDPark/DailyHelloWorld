#!/usr/bin/env python3
"""완료된 손자병법 구절을 Tulpa Chat 병법가 방에 알리고 토론을 시작한다."""

import argparse
import html
import json
import re
import subprocess
import urllib.request
from pathlib import Path

ROOM_ID = "병법가"
API_URL = "http://127.0.0.1:8000/api/worker/announcements"
KEYCHAIN_SERVICE = "com.forrest.tulpachat.worker"


def plain(value: str) -> str:
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\*\*|__|`", "", value)
    return " ".join(html.unescape(value).split())


def read_page(path: Path) -> tuple[int, str, str]:
    match = re.search(r"jiudi(\d+)_full_page\.md$", path.name)
    if not match:
        raise ValueError("파일명이 jiudi<번호>_full_page.md 형식이어야 합니다")
    markdown = path.read_text(encoding="utf-8")
    summary = re.search(r"<summary>([\s\S]*?)</summary>", markdown, flags=re.I)
    if not summary:
        raise ValueError("원문 summary를 찾지 못했습니다")
    original = plain(re.split(r"<br\s*/?>", summary.group(1), maxsplit=1, flags=re.I)[0])
    subtitle = plain(re.search(r"^>\s*(.+)$", markdown, flags=re.M).group(1))
    return int(match.group(1)), original, subtitle


def keychain_token() -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("page", type=Path)
    parser.add_argument("--notion-url", required=True)
    parser.add_argument("--site-url", required=True)
    args = parser.parse_args()

    number, original, subtitle = read_page(args.page)
    content = (
        f"📜 손자병법 새 구절 분석이 완료되었습니다 — 구지편 {number}구절\n\n"
        f"원문: {original}\n"
        f"핵심 해석: {subtitle}\n\n"
        f"Notion 정본: {args.notion_url}\n"
        f"사이트 분석: {args.site_url}\n\n"
        "병법가들은 각자의 주석 관점에서 이 구절의 뜻, 역사 사례에서 놓치기 쉬운 조건, "
        "현대에 옮길 때의 오용 위험 가운데 가장 중요하다고 보는 한 가지를 논합니다."
    )
    payload = json.dumps(
        {"room_id": ROOM_ID, "content": content, "dedupe_key": f"sunzi-jiudi-{number}"},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={"Authorization": f"Bearer {keychain_token()}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.load(response)
    if not result.get("ok"):
        raise RuntimeError(f"Tulpa Chat 보고 실패: {result}")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
