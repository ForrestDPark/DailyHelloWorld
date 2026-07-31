#!/usr/bin/env python3
"""대표 이미지를 Notion에 직접 업로드하고 Codex 요약을 작품 페이지에 연결한다."""

import argparse
import glob
import json
import mimetypes
import os
import re
import subprocess
import sys

import requests


NOTION_VERSION = "2026-03-11"


def load_token():
    result = subprocess.run(
        [
            "security", "find-generic-password",
            "-a", os.environ.get("USER", ""),
            "-s", "jp_subtitle_notion_token", "-w",
        ],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def summary_blocks(text):
    """SUMMARY.md 텍스트를 Notion 블록으로 변환한다.
    ★ 2026-07-31: "- 장면 N: ..." 불릿 줄을 예전엔 "-"를 떼어내고 그냥 paragraph로
    만들었는데, 이러면 나중에 Notion 내용을 다시 읽어와 EPUB에 반영할 때(pull_
    notion_summary_to_epub.py) 원래 불릿 목록이었다는 정보가 사라져 있다.
    bulleted_list_item으로 만들어야 Notion 화면에서도 목록으로 보이고,
    되돌릴 때도 "- "를 그대로 복원할 수 있다."""
    blocks = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            block_type, content = "heading_1", line[2:]
        elif line.startswith("## "):
            block_type, content = "heading_2", line[3:]
        elif line.startswith("### "):
            block_type, content = "heading_3", line[4:]
        elif line.startswith("- "):
            block_type, content = "bulleted_list_item", line[2:].strip()
        else:
            block_type, content = "paragraph", line
        blocks.append({
            "object": "block",
            "type": block_type,
            block_type: {
                "rich_text": [{"type": "text", "text": {"content": content[:1900]}}]
            },
        })
    return blocks


def upload_image(token, image_path):
    """로컬 이미지 파일을 Notion 저장소에 올리고 첨부용 FileUpload ID를 반환한다."""
    filename = os.path.basename(image_path)
    content_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
    api_headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
    }
    response = requests.post(
        "https://api.notion.com/v1/file_uploads",
        headers={**api_headers, "Content-Type": "application/json"},
        json={
            "mode": "single_part",
            "filename": filename,
            "content_type": content_type,
        },
        timeout=30,
    )
    response.raise_for_status()
    upload = response.json()
    upload_url = upload.get("upload_url") or (
        f"https://api.notion.com/v1/file_uploads/{upload['id']}/send"
    )
    with open(image_path, "rb") as image_file:
        response = requests.post(
            upload_url,
            headers=api_headers,
            files={"file": (filename, image_file, content_type)},
            timeout=90,
        )
    response.raise_for_status()
    uploaded = response.json()
    if uploaded.get("status") != "uploaded":
        sys.exit(f"Notion 이미지 업로드가 완료되지 않았습니다: {filename}")
    return upload["id"]


def insert_blocks_near_top(page_id, blocks, headers):
    """Notion 페이지에 파일 블록을 추가한다."""
    child_url = f"https://api.notion.com/v1/blocks/{page_id}/children"

    for index in range(0, len(blocks), 50):
        payload = {"children": blocks[index:index + 50]}
        response = requests.patch(
            child_url,
            headers=headers,
            json=payload,
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(
                f"Notion 블록 삽입 실패 ({response.status_code}): {response.text}"
            )
        inserted = response.json().get("results", [])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book_dir")
    parser.add_argument("--images-only", action="store_true")
    args = parser.parse_args()
    book_dir = os.path.abspath(args.book_dir)
    summary_path = os.path.join(book_dir, "SUMMARY.md")
    if not args.images_only and not os.path.isfile(summary_path):
        sys.exit("SUMMARY.md가 없습니다.")
    summary = (
        open(summary_path, encoding="utf-8").read()
        if os.path.isfile(summary_path) else ""
    )
    if not args.images_only and "요약 대기 중" in summary:
        sys.exit("Codex 요약이 아직 완료되지 않았습니다.")

    manifests = sorted(glob.glob(os.path.join(book_dir, "notion_part*.json")))
    if not manifests:
        sys.exit("notion_part*.json이 없습니다.")
    token = load_token()
    if not token:
        sys.exit("macOS 키체인에서 jp_subtitle_notion_token을 찾을 수 없습니다.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    rel_book = os.path.relpath(book_dir, repo_root).replace(os.sep, "/")

    for manifest_path in manifests:
        manifest = json.load(open(manifest_path, encoding="utf-8"))
        page_id = manifest["page_id"]
        page_check = requests.get(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers,
            timeout=20,
        )
        if page_check.status_code == 404:
            print(f"⚠️ 접근할 수 없는 Notion 페이지 건너뜀: {manifest['page_url']}")
            continue
        page_check.raise_for_status()
        child_check = requests.get(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=headers,
            params={"page_size": 1},
            timeout=20,
        )
        if child_check.status_code == 404:
            print(f"⚠️ 블록에 접근할 수 없는 Notion 페이지 건너뜀: {manifest['page_url']}")
            continue
        child_check.raise_for_status()
        images_already_synced = manifest.get("notion_images_synced", False)
        summary_already_synced = manifest.get("notion_summary_synced", False)
        if args.images_only and images_already_synced:
            continue
        if not args.images_only and summary_already_synced:
            continue
        part_match = re.search(r"notion_part(\d+)\.json$", manifest_path)
        if not part_match:
            sys.exit(f"파트 번호를 알 수 없는 manifest입니다: {manifest_path}")
        part_num = int(part_match.group(1))
        images = sorted(glob.glob(
            os.path.join(book_dir, "images", f"part{part_num}_scene*.jpg")
        ))
        blocks = []
        if not args.images_only:
            blocks.extend([
                {
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {"rich_text": [{"type": "text", "text": {
                        "content": "책 요약"
                    }}]},
                },
                *summary_blocks(summary),
            ])
        if not images_already_synced:
            image_blocks = []
            for image in images:
                upload_id = upload_image(token, image)
                image_blocks.append({
                    "object": "block",
                    "type": "image",
                    "image": {
                        "type": "file_upload",
                        "file_upload": {"id": upload_id},
                    },
                })
            blocks.extend([
                {
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {"rich_text": [{"type": "text", "text": {
                        "content": "장면 대표 이미지"
                    }}]},
                },
                *image_blocks,
            ])
        insert_blocks_near_top(page_id, blocks, headers)
        properties = {
            "Git 경로": {"rich_text": [{"text": {"content": rel_book}}]},
            "대표 이미지 수": {"number": len(images)},
        }
        if not args.images_only:
            properties.update({
                "상태": {"select": {"name": "완료"}},
                "요약 상태": {"select": {"name": "완료"}},
            })
        response = requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers,
            json={"properties": properties},
            timeout=20,
        )
        response.raise_for_status()
        if not images_already_synced:
            manifest["notion_images_synced"] = True
            manifest["image_status"] = "Notion 파일 직접 업로드 완료"
        if not args.images_only:
            manifest["notion_summary_synced"] = True
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(manifest["page_url"])


if __name__ == "__main__":
    main()
