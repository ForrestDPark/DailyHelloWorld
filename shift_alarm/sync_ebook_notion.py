#!/usr/bin/env python3
"""아침 독서 Notion 데이터베이스를 로컬 JSON 캐시로 무손실 동기화한다."""

import json
import os
import subprocess
import sys
import time

import requests


TOKEN_SERVICE = "ebook_reader_notion_token"
DATABASE_ID = "35932a1eae808015a242d20bd707f7f8"
NOTION_VERSION = "2022-06-28"
CACHE_DIR = os.path.expanduser("~/.ebook_reader/notion_cache")


def load_token():
    result = subprocess.run(
        [
            "security", "find-generic-password", "-a", os.environ.get("USER", ""),
            "-s", TOKEN_SERVICE, "-w",
        ],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def request_json(method, url, headers, **kwargs):
    response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()


def query_database(headers):
    pages = []
    cursor = None
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        data = request_json(
            "POST",
            f"https://api.notion.com/v1/databases/{DATABASE_ID}/query",
            headers,
            json=payload,
        )
        pages.extend(data.get("results", []))
        if not data.get("has_more"):
            return pages
        cursor = data.get("next_cursor")


def fetch_children(block_id, headers):
    children = []
    cursor = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        data = request_json(
            "GET",
            f"https://api.notion.com/v1/blocks/{block_id}/children",
            headers,
            params=params,
        )
        for block in data.get("results", []):
            if block.get("has_children"):
                block["children"] = fetch_children(block["id"], headers)
            children.append(block)
        if not data.get("has_more"):
            return children
        cursor = data.get("next_cursor")


def rich_text_plain(items):
    return "".join(item.get("plain_text", "") for item in items or [])


def property_title(page):
    for value in page.get("properties", {}).values():
        if value.get("type") == "title":
            return rich_text_plain(value.get("title"))
    return page["id"]


def main():
    token = load_token()
    if not token:
        print("❌ 키체인에 ebook_reader_notion_token이 없습니다.")
        print('등록: security add-generic-password -a "$USER" -s "ebook_reader_notion_token" -w "새 토큰" -U')
        return 2

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
    os.makedirs(CACHE_DIR, exist_ok=True)
    print("☁️ Notion 독서 기록 목록을 불러옵니다...")
    pages = query_database(headers)
    index = []
    for number, page in enumerate(pages, 1):
        title = property_title(page)
        print(f"[{number}/{len(pages)}] {title}")
        record = {
            "synced_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "page": page,
            "title": title,
            "blocks": fetch_children(page["id"], headers),
        }
        file_name = page["id"].replace("-", "") + ".json"
        with open(os.path.join(CACHE_DIR, file_name), "w", encoding="utf-8") as file:
            json.dump(record, file, ensure_ascii=False, indent=2)
        index.append({"id": page["id"], "title": title, "file": file_name})

    with open(os.path.join(CACHE_DIR, "index.json"), "w", encoding="utf-8") as file:
        json.dump({"synced_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "pages": index}, file, ensure_ascii=False, indent=2)
    print(f"✅ {len(index)}개 책을 동기화했습니다: {CACHE_DIR}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.RequestException as error:
        print(f"❌ Notion 동기화 실패: {error}")
        raise SystemExit(1)
