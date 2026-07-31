#!/usr/bin/env python3
"""Notion 페이지의 "책 요약" 섹션을 그대로 가져와 SUMMARY.md를 덮어쓰고 EPUB을
다시 빌드한다.

generate_summary.py가 만든 요약은 sync_book_to_notion.py로 Notion에 올라간
뒤에도 사람이 Notion에서 직접 고치거나 내용을 덧붙일 수 있다. 이 스크립트는
그 반대 방향(Notion → 로컬)으로 최신 내용을 끌어와, 실제로 노션에 올라와 있는
내용이 EPUB 첫 장(줄거리·장면별 목차)에 그대로 반영되도록 한다.
"""

import argparse
import glob
import json
import os
import subprocess
import sys

import requests


NOTION_VERSION = "2022-06-28"


def load_token():
    result = subprocess.run(
        ["security", "find-generic-password", "-a", os.environ.get("USER", ""),
         "-s", "jp_subtitle_notion_token", "-w"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def fetch_all_blocks(page_id, headers):
    blocks = []
    cursor = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        r = requests.get(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=headers, params=params, timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        blocks.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return blocks


def block_to_markdown(block):
    """heading_1/2/3, bulleted_list_item, paragraph만 지원 — 요약 섹션에 이
    타입들만 쓰이므로 그 외 타입은 무시한다(예: 이미지, 콜아웃, 대사 quote 등)."""
    t = block["type"]
    if t not in block or "rich_text" not in block[t]:
        return None
    text = "".join(rt.get("plain_text", "") for rt in block[t]["rich_text"])
    if t == "heading_1":
        # {.ibooks-dark-theme-use-custom-text-color}: h1 CSS의 금색이 Apple
        # Books 다크 테마에서 흰색으로 강제 대체되지 않게 하는 공식 클래스.
        return f"# {text} {{.ibooks-dark-theme-use-custom-text-color}}"
    if t == "heading_2":
        return f"## {text}"
    if t == "heading_3":
        return f"### {text}"
    if t == "bulleted_list_item":
        return f"- {text}"
    if t == "paragraph":
        return text
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book_dir", help="일본어자막추출/library/<작품명> 폴더")
    args = parser.parse_args()

    book_dir = os.path.abspath(args.book_dir)
    manifests = sorted(glob.glob(os.path.join(book_dir, "notion_part*.json")))
    if not manifests:
        sys.exit(f"❌ notion_part*.json이 없습니다: {book_dir}")

    token = load_token()
    if not token:
        sys.exit("❌ macOS 키체인에서 jp_subtitle_notion_token을 찾을 수 없습니다.")
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION}

    # 모든 파트 페이지에 같은 요약이 올라가므로 첫 파트 페이지만 읽으면 된다.
    manifest = json.load(open(manifests[0], encoding="utf-8"))
    page_id = manifest["page_id"]

    blocks = fetch_all_blocks(page_id, headers)

    summary_start = None
    for i, b in enumerate(blocks):
        if b["type"] == "heading_1":
            text = "".join(rt.get("plain_text", "") for rt in b["heading_1"]["rich_text"])
            if text.strip() == "책 요약":
                summary_start = i + 1  # "책 요약" 구분용 제목 자체는 건너뜀
                break

    if summary_start is None:
        sys.exit(
            "⚠️  Notion 페이지에 '책 요약' 섹션이 아직 없습니다 "
            "(generate_summary.py + sync_book_to_notion.py를 먼저 실행하세요)."
        )

    lines = []
    for b in blocks[summary_start:]:
        md = block_to_markdown(b)
        if md is not None:
            lines.append(md)
            lines.append("")  # 블록 사이 빈 줄

    if not lines:
        sys.exit("⚠️  Notion 페이지의 책 요약 섹션이 비어있습니다.")

    summary_path = os.path.join(book_dir, "SUMMARY.md")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"✅ Notion 책 요약을 SUMMARY.md로 반영: {summary_path}")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    result = subprocess.run(
        [sys.executable, os.path.join(script_dir, "finalize_japanese_book.py"), book_dir],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"❌ EPUB 재빌드 실패: {result.stderr.strip()}")
    print(result.stdout.strip())


if __name__ == "__main__":
    main()
