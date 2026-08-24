"""툴파시스템 메인 Notion 페이지 아래 하위 페이지(페르소나)들을 찾아서, 각
페르소나 페이지의 본문을 읽어 대화용 시스템 프롬프트 텍스트로 변환한다.

Notion 통합 토큰은 이직시스템/일본어자막추출과 동일한 키체인 항목
(jp_subtitle_notion_token)을 재사용한다 — 이미 그 페이지에 통합이 공유돼
있어야 한다. 이직시스템/job_collector.py의 _notion_request 패턴과 동일하게
표준 라이브러리(urllib)만 쓴다."""
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request

NOTION_VERSION = "2026-03-11"
TULPA_ROOT_PAGE_ID = "3c632a1eae8080a581eed393294c097a"
DIARY_PAGE_TITLE = "일기"  # 페르소나 목록에서 제외


def notion_token():
    result = subprocess.run(
        ["security", "find-generic-password", "-a", os.environ.get("USER", ""),
         "-s", "jp_subtitle_notion_token", "-w"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _request(path, token, params=None):
    url = f"https://api.notion.com/v1/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _fetch_all_blocks(page_id, token):
    blocks = []
    cursor = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        data = _request(f"blocks/{page_id}/children", token, params)
        blocks.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return blocks


def _block_text(block):
    block_type = block.get("type")
    payload = block.get(block_type, {})
    rich_text = payload.get("rich_text")
    if rich_text is None:
        return None
    text = "".join(rt.get("plain_text", "") for rt in rich_text)
    if block_type == "heading_1":
        return f"# {text}"
    if block_type == "heading_2":
        return f"## {text}"
    if block_type == "heading_3":
        return f"### {text}"
    if block_type in ("bulleted_list_item", "numbered_list_item"):
        return f"- {text}"
    return text


def fetch_page_text(page_id, token):
    """페이지 본문 전체를 마크다운 비슷한 평문으로 이어붙인다.
    heading/paragraph/list 정도만 지원 — 페르소나 페이지엔 이 타입들만 쓴다."""
    lines = []
    for block in _fetch_all_blocks(page_id, token):
        text = _block_text(block)
        if text:
            lines.append(text)
    return "\n".join(lines)


def list_personas(token):
    """메인 페이지 바로 아래 하위 페이지(child_page) 중 '일기'를 제외한 전부를
    페르소나로 취급한다. [{"id":..., "title":...}, ...] 반환."""
    personas = []
    for block in _fetch_all_blocks(TULPA_ROOT_PAGE_ID, token):
        if block.get("type") != "child_page":
            continue
        title = block["child_page"]["title"]
        if title == DIARY_PAGE_TITLE:
            continue
        personas.append({"id": block["id"], "title": title})
    return personas


def build_system_prompt(persona_title, page_text):
    return (
        f'당신은 지금부터 "{persona_title}"이라는 인물이 되어 대화합니다.\n'
        "아래는 이 인물에 대해 누적된 프로필·기록·지금까지 함께 만든 이야기입니다.\n"
        "이 내용에 기반해서, 이 인물의 성격과 말투를 유지한 채 1인칭으로 대화하세요.\n"
        "실존 인물이면 알려진 사실 범위를 벗어난 추측을 사실처럼 말하지 말고, "
        "모르는 건 모른다고 자연스럽게 넘기세요. 답변은 채팅 메시지처럼 짧고 "
        "자연스럽게 하세요(장황한 설명 금지).\n\n"
        f"--- {persona_title} 기록 ---\n{page_text}\n--- 기록 끝 ---"
    )
