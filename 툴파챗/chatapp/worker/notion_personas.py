"""툴파챗 메인 Notion 페이지 아래 하위 페이지(페르소나)들을 찾아서, 각
페르소나 페이지의 본문을 읽어 대화용 시스템 프롬프트 텍스트로 변환한다.

Notion 통합 토큰은 이직시스템/일본어자막추출과 동일한 키체인 항목
(jp_subtitle_notion_token)을 재사용한다 — 이미 그 페이지에 통합이 공유돼
있어야 한다. 이직시스템/job_collector.py의 _notion_request 패턴과 동일하게
표준 라이브러리(urllib)만 쓴다."""
import json
import os
import re
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


def _request(path, token, params=None, method="GET", payload=None):
    url = f"https://api.notion.com/v1/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url, data=body, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
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


_GROUP_LINE_RE = re.compile(r"^-\s*그룹\s*:\s*(.+?)\s*$", re.MULTILINE)


def extract_group(page_text):
    """페르소나 페이지의 프로필 섹션에서 "- 그룹: OOO" 줄을 찾아 그룹명을
    반환한다 (★ 2026-08-25, "페르소나 목록도 그룹화하는 게 좋을거같아" 요청).
    fetch_page_text()가 Notion의 rich_text plain_text를 그대로 이어붙이므로
    "**그룹**"처럼 마크다운 굵게 표시가 리터럴 별표로 남지 않는다(굵게는
    rich_text의 annotation일 뿐 텍스트 자체가 아님) — 그래서 별표 없이 매칭한다.
    없으면 None — 방 목록에서 "그룹 없음"으로 묶인다."""
    match = _GROUP_LINE_RE.search(page_text)
    return match.group(1) if match else None


_PROJECTS_LINE_RE = re.compile(r"^-\s*담당\s*프로젝트\s*:\s*(.+?)\s*$", re.MULTILINE)


def extract_projects(page_text):
    """페르소나 페이지의 프로필 섹션에서 "- 담당 프로젝트: A, B" 줄을 찾아
    프로젝트(레포 폴더) 이름 목록을 반환한다 (★ 2026-08-25, "동찬이형이 실제
    프로젝트 현재 상태를 알고 개발 얘기를 할 수 있지 않을까"라는 아이디어를
    일반화 — 페르소나 페이지에 관련 프로젝트를 걸어두면 워커가 그 프로젝트
    상태를 자동으로 끌어와 대화 컨텍스트에 포함시킨다). 없으면 빈 리스트."""
    match = _PROJECTS_LINE_RE.search(page_text)
    if not match:
        return []
    return [name.strip() for name in match.group(1).split(",") if name.strip()]


_PROFILE_SECTION_RE = re.compile(r"^## 프로필\n(.*?)(?=\n## |\Z)", re.DOTALL | re.MULTILINE)
_PROFILE_FIELD_RE = re.compile(r"^-\s*(유형|정체성/관계|성격|말투|배경)\s*:\s*(.+?)\s*$", re.MULTILINE)


def extract_profile_summary(page_text):
    """"## 프로필" 섹션에서 성격 파악에 필요한 필드(유형·정체성/관계·성격·
    말투·배경)만 뽑아 사람이 읽기 좋은 짧은 요약으로 만든다. 그룹·담당
    프로젝트 같은 내부 운영용 필드는 뺀다(2026-08-26 "채팅앱에서 페르소나
    프로필을 간단히 볼 수 있는 페이지" 요청). "(아직 기록 없음)" 값은
    빈 프로필이나 마찬가지라 제외."""
    section_match = _PROFILE_SECTION_RE.search(page_text)
    if not section_match:
        return ""
    lines = []
    for label, value in _PROFILE_FIELD_RE.findall(section_match.group(1)):
        if "아직 기록 없음" in value:
            continue
        lines.append(f"{label}: {value}")
    return "\n".join(lines)


def build_system_prompt(persona_title, page_text, project_context=""):
    prompt = (
        f'당신은 지금부터 "{persona_title}"이라는 인물이 되어 대화합니다.\n'
        "아래는 이 인물에 대해 누적된 프로필·기록·지금까지 함께 만든 이야기입니다.\n"
        "이 내용에 기반해서, 이 인물의 성격과 말투를 유지한 채 1인칭으로 대화하세요.\n"
        "실존 인물이면 알려진 사실 범위를 벗어난 추측을 사실처럼 말하지 말고, "
        "모르는 건 모른다고 자연스럽게 넘기세요. 답변은 채팅 메시지처럼 짧고 "
        "자연스럽게 하세요(장황한 설명 금지).\n\n"
        f"--- {persona_title} 기록 ---\n{page_text}\n--- 기록 끝 ---"
    )
    if project_context:
        prompt += (
            "\n\n--- 담당 프로젝트 현재 상태(README 발췌, 최신이 아닐 수 있음) ---\n"
            f"{project_context}\n--- 프로젝트 정보 끝 ---\n"
            "이 정보를 근거로, 대화 흐름에 자연스럽게 프로젝트의 개선점·기술적 "
            "다음 단계·이어서 해볼 만한 과제(숙제)를 언급하거나 물어보세요. "
            "README에 없는 내용을 지어내지 말고, 모르면 모른다고 하세요."
        )
    return prompt


def append_story_summary(page_id, token, date_label, summary_text):
    """페르소나 페이지 맨 끝(="함께 만든 이야기" 섹션, 템플릿상 언제나 마지막
    섹션이라 페이지 끝에 추가하면 자연히 그 아래에 들어간다)에 날짜 소제목과
    요약 문단을 추가한다. children append는 항상 페이지 맨 끝에 붙는 것만
    지원하므로, 이 함수는 "함께 만든 이야기"가 마지막 섹션이라는 페이지
    구조를 전제한다(README 템플릿과 일치)."""
    children = [
        {
            "object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": date_label}}]},
        },
        {
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": summary_text[:2000]}}]},
        },
    ]
    _request(f"blocks/{page_id}/children", token, method="PATCH", payload={"children": children})
