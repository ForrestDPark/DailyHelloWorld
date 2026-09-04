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
HANJA_HUN_EUM = {
    "易": "바꿀 역", "其": "그 기", "居": "살 거", "迂": "멀 우", "途": "길 도",
    "使": "하여금 사", "人": "사람 인", "不": "아닐 불", "得": "얻을 득", "慮": "생각할 려",
    "帥": "장수 수", "與": "더불 여", "之": "갈 지", "期": "기약할 기", "如": "같을 여",
    "登": "오를 등", "高": "높을 고", "而": "말 이을 이", "去": "버릴 거", "梯": "사다리 제",
    "深": "깊을 심", "入": "들 입", "諸": "모두 제", "侯": "제후 후", "地": "땅 지",
    "發": "필 발", "機": "틀 기", "焚": "사를 분", "舟": "배 주", "破": "깨뜨릴 파",
    "釜": "가마 부", "若": "같을 약", "驅": "몰 구", "群": "무리 군", "羊": "양 양",
    "往": "갈 왕", "來": "올 래", "莫": "없을 막", "知": "알 지", "所": "바 소",
}


def plain(value: str) -> str:
    # 이미지 Markdown이 전장 설명에 합쳐지면 채팅에서 URL이 문장 중간에
    # 잘려 보인다. 이미지는 별도 필드로 보내므로 일반 문장에서는 제거한다.
    value = MARKDOWN_IMAGE_RE.sub("", value)
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"(?m)^\s*#{1,6}\s*", "", value)
    value = re.sub(r"\*\*|__|`", "", value)
    return " ".join(html.unescape(value).split())


def chat_format(value: str) -> str:
    """Notion 원고를 채팅용 문단과 목록으로 정리한다."""
    value = MARKDOWN_IMAGE_RE.sub("", value)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"(?m)^\s*#{1,6}\s*", "", value)
    value = re.sub(r"\*\*|__|`", "", value)
    lines = [re.sub(r"[ \t]+", " ", html.unescape(line)).strip() for line in value.splitlines()]
    return "\n".join(line for i, line in enumerate(lines) if line or (i and lines[i - 1])).strip()


def image_comment(alt: str, battle: str) -> str:
    """도판이 맥락 없는 그림으로 게시되지 않도록 읽을 초점을 함께 보낸다."""
    guides = (
        (("인물", "장수"), "주요 지휘관의 역할과 승패 판단이 어디서 갈렸는지 보십시오."),
        (("병사", "무기", "생활"), "당시 병사의 무장·방호·식량과 대형의 강점·취약점을 함께 보십시오."),
        (("지휘", "편제"), "명령 계통과 부대 간 연결이 정보 전달과 대응 속도에 미친 영향을 보십시오."),
        (("세력", "시대"), "전장이 더 큰 전쟁에서 차지한 위치와 각 세력의 접근축을 보십시오."),
        (("전략지형", "지형도"), "강·도로·도시·산맥 등 기동을 제한하거나 은폐한 핵심 지형을 보십시오."),
        (("단계", "흐름"), "시간순 기동과 전환점, 상대가 뒤늦게 알아챈 신호를 화살표 순서로 보십시오."),
    )
    focus = next((guide for keys, guide in guides if any(key in alt for key in keys)),
                 "도판의 배치와 기동 표시를 전투 서사와 대조해 보십시오.")
    return f"🖼️ 도판 해설 — {battle}: {focus}"


def build_hanja_lesson(markdown: str, original: str, subtitle: str) -> str:
    """모든 글자의 훈·음을 먼저 보이고 정본 해설을 말하듯 풀어낸다."""
    section_match = re.search(r"^##\s+1\.[^\n]*\n([\s\S]*?)(?=^---\s*$)", markdown, flags=re.M)
    if not section_match:
        raise ValueError("한자선생님 수업에 필요한 1절 원문 풀이를 찾지 못했습니다")
    section = section_match.group(1)
    reading = subtitle.split("—", 1)[0].strip().rstrip(".")
    literal_match = re.search(r"\*\*직역\*\*\s*\n+([^\n]+)", section)
    literal = plain(literal_match.group(1)) if literal_match else "직역을 정본에서 확인해 주십시오."
    unique_chars = list(dict.fromkeys(re.findall(r"[\u3400-\u9fff]", original)))
    missing = [char for char in unique_chars if char not in HANJA_HUN_EUM]
    if missing:
        raise ValueError("훈·음 사전에 없는 한자: " + ", ".join(missing))
    definitions = [f"{char} — {HANJA_HUN_EUM[char]}" for char in unique_chars]
    explanations = []
    for match in re.finditer(
        r"^####\s+([^\n]+)\n([\s\S]*?)(?=^####\s+|</details>)", section, flags=re.M
    ):
        heading = plain(match.group(1))
        if "글자들이 완성" in heading:
            continue
        explanation = plain(match.group(2))[:420]
        explanations.append(f"먼저 {heading}을 보겠습니다.\n\n{explanation}")
    return (
        "📚 한자선생님입니다. 먼저 글자부터 천천히 살펴보겠습니다.\n\n"
        f"원문\n\n{original}\n\n독음\n\n{reading}\n\n"
        "모든 한자의 훈과 음\n\n" + "\n\n".join(definitions) +
        f"\n\n직역\n\n{literal}\n\n"
        "이제 문장이 실제로 어떤 장면을 만드는지 말씀드리겠습니다.\n\n" +
        "\n\n".join(explanations[:8]) +
        "\n\n정리하면, 이 구절은 글자 하나하나가 이어져 하나의 지휘 장면을 만듭니다. "
        "이 뜻을 바탕으로 이제 전투 사례를 함께 살펴보겠습니다."
    )


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
        images = []
        for match in image_matches:
            alt = plain(match.group(1)) or f"{battle} 전장 자료"
            images.append({"url": match.group(2), "alt": alt, "comment": image_comment(alt, battle)})
        narrative = plain(re.split(r"^####\s+", block, maxsplit=1, flags=re.M)[0])
        narrative = narrative[:900].strip()
        deception_match = re.search(
            r"^####\s+전투에서 사용된 속임수[^\n]*\n([\s\S]*?)(?=^####\s+法 한눈 비교)",
            block,
            flags=re.M,
        )
        deception = chat_format(deception_match.group(0))[:3600] if deception_match else (
            "이 전투에서는 사료로 확인되는 명시적 기만보다 정보 격차·지형·시간차가 "
            "상대의 오판을 키웠다. 기만과 단순 오판을 구분해 설명한다."
        )
        profile = (
            f"{battle}의 승군 대장급 지휘관. 이 페르소나는 해당 전투의 검증된 분석 범위에서만 "
            f"자신의 판단과 한계를 설명한다. 분석 근거: {narrative}"
            f" 속임수·오판 분석: {deception}"
        )
        opening = (
            f"⚔️ 승군 지휘관 전장 토론 — {battle}\n\n"
            f"저는 {commander}입니다. 이 전투에서 상대의 판단이 어디서 어긋났는지부터 "
            f"『손자』의 ‘{original}’에 비추어 말씀드리겠습니다.\n\n"
            f"{deception}\n\n"
            "공유된 도판도 차례대로 보겠습니다. 지형과 병력 배치가 무엇을 가능하게 했는지, "
            "그림만으로 단정할 수 없는 부분은 무엇인지 함께 짚겠습니다."
        )
        found.append({
            "name": commander,
            "battle": battle,
            "profile": profile,
            "opening": opening,
            "images": images,
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
    parser.add_argument(
        "--discussion-run",
        default="commanders-v1",
        help="같은 구절 토론을 의도적으로 다시 시작할 때 쓰는 중복 방지 실행명",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", args.discussion_run):
        parser.error("--discussion-run은 영문 소문자·숫자·밑줄·하이픈만 사용할 수 있습니다")

    number, original, subtitle = read_page(args.page)
    markdown = args.page.read_text(encoding="utf-8")
    commanders = victorious_commanders(markdown, original)
    hanja_lesson = build_hanja_lesson(markdown, original, subtitle)
    content = (
        f"📜 손자병법 새 구절 분석이 완료되었습니다 — 구지편 {number}구절\n\n"
        f"원문: {original}\n"
        f"핵심 해석: {subtitle}\n\n"
        f"Notion 정본: {args.notion_url}\n"
        f"사이트 분석: {args.site_url}\n\n"
        "병법가들은 각자의 주석 관점에서 이 구절의 뜻, 역사 사례에서 놓치기 쉬운 조건, "
        "현대에 옮길 때의 오용 위험 가운데 가장 중요하다고 보는 한 가지를 논합니다."
        " 역사 사례의 전투 도판은 빠짐없이 공유하며, 장수들은 각 도판의 지형·배치·기동·기만 "
        "신호를 설명하고 카너먼은 그 신호가 판단 편향에 미친 영향을 분석합니다."
    )
    payload = json.dumps(
        {
            "room_id": ROOM_ID,
            "content": content,
            "dedupe_key": f"{ROOM_ID}:sunzi-jiudi-{number}:{args.discussion_run}",
            "hanja_lesson": hanja_lesson,
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
    if not result.get("duplicate") and not isinstance(result.get("hanja_lesson_message_id"), int):
        raise RuntimeError("Tulpa Chat 한자선생님 첫 풀이 메시지가 생성되지 않았습니다")
    expected_image_count = sum(len(item["images"]) for item in commanders)
    if not result.get("duplicate") and result.get("posted_image_count") != expected_image_count:
        raise RuntimeError(
            "Tulpa Chat 전투 도판 게시 수 불일치: "
            f"원고 {expected_image_count}장, 게시 {result.get('posted_image_count')}장"
        )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
