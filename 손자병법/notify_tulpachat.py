#!/usr/bin/env python3
"""완료된 손자병법 구절을 Tulpa Chat 손자병법 토론방에 알리고 토론을 시작한다."""

import argparse
import html
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

ROOM_ID = "custom_16ea779e1f"
API_URL = "http://127.0.0.1:8000/api/worker/announcements"
KEYCHAIN_SERVICE = "com.forrest.tulpachat.worker"
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)")


def plain(value: str) -> str:
    # 이미지 Markdown이 전장 설명에 합쳐지면 채팅에서 URL이 문장 중간에
    # 잘려 보인다. 이미지는 별도 필드로 보내므로 일반 문장에서는 제거한다.
    value = MARKDOWN_IMAGE_RE.sub("", value)
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"(?m)^\s*#{1,6}\s*", "", value)
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


def victorious_commanders(markdown: str, original: str) -> list[dict[str, str]]:
    """역사 사례별 승군의 첫 대장급 인물을 골라 토론용 소개를 만든다."""
    section = re.split(r"^##\s+4\.", markdown, maxsplit=1, flags=re.M)
    if len(section) != 2:
        return []
    section = re.split(r"^##\s+5\.", section[1], maxsplit=1, flags=re.M)[0]
    blocks = re.split(r"(?=^\s*###\s+(?:서양|동양)\s*[—-])", section, flags=re.M)
    rejected = ("군", "연합", "제국", "왕국", "공화국", "방진", "함대", "부대", "세력", "지휘부")
    found: list[dict[str, str]] = []
    for block in blocks:
        heading = re.search(r"^\s*###\s+(?:서양|동양)\s*[—-]\s*(.+)$", block, flags=re.M)
        if not heading:
            continue
        heading_text = plain(heading.group(1))
        battle = heading_text.split("│", 1)[-1].strip()
        blue_names = re.findall(
            r'<span\s+color="blue">\s*\*\*([^*<>]+)\*\*\s*</span>', block, flags=re.I
        )
        candidates = [
            plain(name) for name in blue_names
            if 1 < len(plain(name)) <= 20 and not any(word in plain(name) for word in rejected)
            and "·" not in plain(name) and plain(name) not in {"승군 측 결과", "▰"}
        ]
        winning_force = plain(blue_names[0]) if blue_names else ""
        def commander_score(name: str) -> tuple[int, int]:
            short_forms = {name, name.split()[0], name.split()[-1]}
            mentions = sum(block.count(form) for form in short_forms if len(form) >= 2)
            force_bonus = 100 if any(form in winning_force for form in short_forms if len(form) >= 2) else 0
            return force_bonus + mentions, -candidates.index(name)
        commander = max(dict.fromkeys(candidates), key=commander_score, default="")
        if not commander or any(item["name"] == commander for item in found):
            continue
        image_matches = list(MARKDOWN_IMAGE_RE.finditer(block))
        preferred_image = next(
            (match for match in image_matches if "command_structure" in match.group(2)),
            image_matches[0] if image_matches else None,
        )
        narrative = plain(re.split(r"^####\s+", block, maxsplit=1, flags=re.M)[0])
        narrative = narrative[:900].strip()
        profile = (
            f"{battle}의 승군 대장급 지휘관. 이 페르소나는 해당 전투의 검증된 분석 범위에서만 "
            f"자신의 판단과 한계를 설명한다. 분석 근거: {narrative}"
        )
        opening = (
            f"⚔️ 승군 지휘관 전장 토론 — {battle}\n\n"
            f"저는 {commander}입니다. 이 전장에서 제가 지휘한 승군의 선택과 그 한계를 "
            f"『손자』의 ‘{original}’에 비추어 이야기해 보겠습니다. {narrative[:500]}\n\n"
            "이 전투에서 실제로 승패를 가른 조건과, 다른 상황에서는 같은 선택이 실패할 수 있는 "
            "지점을 병법적으로 함께 짚어 보시지요."
        )
        found.append({
            "name": commander,
            "battle": battle,
            "profile": profile,
            "opening": opening,
            "image_url": preferred_image.group(2) if preferred_image else None,
            "image_alt": plain(preferred_image.group(1)) if preferred_image else "",
        })
    return found


def keychain_token() -> str:
    env_token = os.environ.get("CHATAPP_WORKER_TOKEN", "").strip()
    if env_token:
        return env_token
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
    markdown = args.page.read_text(encoding="utf-8")
    commanders = victorious_commanders(markdown, original)
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
        {
            "room_id": ROOM_ID,
            "content": content,
            "dedupe_key": f"{ROOM_ID}:sunzi-jiudi-{number}:commanders-v1",
            "victory_commanders": commanders,
        },
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
