#!/usr/bin/env python3
"""Claude·Codex 공용 작업 인계장("클로드코덱스 이력정리" Notion 페이지) 자동화.

지금까지는 각 에이전트가 세션이 끝날 때마다 손으로 이 페이지에 항목을 적었다
(이직시스템/AGENTS.md 5단계, 콜아웃의 "클로드-코덱스 세션 연동 운영 규칙" 참고).
이 스크립트는 그 과정을 자동화한다 — 커밋 직후 `add`를 호출하면 구조화된
항목이 Notion에 그대로 반영되고, 새 세션 시작 시 `check`를 호출하면 마지막
기록과 실제 Git 상태를 자동으로 대조해서 알려준다.

Notion 페이지: https://app.notion.com/p/3b532a1eae8080d6b6edda0d0afba7a1
페이지 안의 기존 콜아웃(운영 규칙)과 날짜별 토글(예: "## 2026-08-10 {toggle=true}")
구조를 그대로 따른다 — 새 포맷을 만들지 않는다.

★ 중요한 제약(2026-08-09~12 세션에서 실측 확인): 이 워크스페이스의 Notion API
버전은 블록 추가 요청의 `after` 파라미터를 지원하지 않는다(HTTP 400
"body.after should be not present"). 그래서 "페이지 맨 위" 순서를 유지하려면
전체 페이지 최상위 자식 블록을 통째로 지우고 다시 쓰는 방법밖에 없다 — 이때
GET으로 받은 블록을 그대로 다시 PATCH에 넣으면 `icon: null` 같은 필드 때문에
validation_error가 난다(실측 확인). 그래서 이 스크립트는 블록을 읽을 때 필요한
필드만 화이트리스트로 뽑아 자체 구조로 변환하고(`_read_block_tree`), 쓸 때도
그 구조에서 새로 유효한 블록만 만든다(`_block_to_payload`) — GET 응답을 절대
그대로 재사용하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REPO_DIR = SCRIPT_DIR.parent

NOTION_VERSION = "2026-03-11"
JOURNAL_PAGE_ID = "3b532a1e-ae80-80d6-b6ed-da0d0afba7a1"
KST = timezone(timedelta(hours=9))

STATUS_CHOICES = ["완료", "진행 중", "대기"]
AGENT_CHOICES = ["Claude", "Codex"]


# ════════════════════════════════════════════════════════════
# Notion 저수준 API (이직시스템/job_collector.py와 동일 패턴)
# ════════════════════════════════════════════════════════════

def _notion_token() -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-a", os.environ.get("USER", ""),
         "-s", "jp_subtitle_notion_token", "-w"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SystemExit("Notion 토큰(jp_subtitle_notion_token)이 키체인에 없습니다.")
    return result.stdout.strip()


def _notion_request(method: str, path: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"https://api.notion.com/v1/{path}", data=body, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", "replace")
        raise RuntimeError(f"Notion API {method} {path} HTTP {exc.code}: {detail}") from exc


def _list_children(block_id: str, token: str) -> list[dict[str, Any]]:
    results, cursor = [], None
    while True:
        path = f"blocks/{block_id}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        resp = _notion_request("GET", path, token)
        results.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return results


# ════════════════════════════════════════════════════════════
# 리치 텍스트 인라인 서식 — **볼드**, `코드`, [라벨](URL), raw URL 지원
# ════════════════════════════════════════════════════════════

_INLINE_RE = re.compile(
    r"\*\*(.+?)\*\*|`([^`]+)`|\[([^\]]+)\]\((https?://[^\s)]+)\)|(https?://[^\s]+)"
)


def _rich_text(content: str) -> list[dict[str, Any]]:
    segments, pos = [], 0
    for m in _INLINE_RE.finditer(content):
        if m.start() > pos:
            segments.append(_plain_segment(content[pos:m.start()]))
        if m.group(1) is not None:
            segments.append(_plain_segment(m.group(1), bold=True))
        elif m.group(2) is not None:
            segments.append(_plain_segment(m.group(2), code=True))
        elif m.group(3) is not None:
            segments.append(_plain_segment(m.group(3), link=m.group(4)))
        else:
            url = m.group(5)
            trail = ""
            while url and url[-1] in ".,)]}":
                trail = url[-1] + trail
                url = url[:-1]
            segments.append(_plain_segment(url, link=url))
            if trail:
                segments.append(_plain_segment(trail))
        pos = m.end()
    if pos < len(content):
        segments.append(_plain_segment(content[pos:]))
    return segments or [_plain_segment("")]


def _plain_segment(text: str, bold: bool = False, code: bool = False, link: str | None = None) -> dict[str, Any]:
    seg: dict[str, Any] = {"type": "text", "text": {"content": text[:1900]}}
    if link:
        seg["text"]["link"] = {"url": link}
    annotations = {}
    if bold:
        annotations["bold"] = True
    if code:
        annotations["code"] = True
    if annotations:
        seg["annotations"] = annotations
    return seg


def _plain_text_of(rich_text: list[dict[str, Any]]) -> str:
    return "".join(seg.get("plain_text") or seg.get("text", {}).get("content", "") for seg in rich_text)


# ════════════════════════════════════════════════════════════
# 블록 트리 읽기/쓰기 — GET 응답을 절대 그대로 재사용하지 않고
# 화이트리스트 필드만 뽑아 자체 구조로 변환한다.
# ════════════════════════════════════════════════════════════

def _read_block_tree(block_id: str, token: str) -> list[dict[str, Any]]:
    """block_id의 자식들을 재귀적으로 읽어 최소 구조로 변환한다.
    반환: [{"type": ..., "rich_text": [...], "children": [...], (기타 type별 필드)}]"""
    nodes = []
    for child in _list_children(block_id, token):
        btype = child["type"]
        data = child.get(btype, {})
        node: dict[str, Any] = {"type": btype}
        if "rich_text" in data:
            node["rich_text"] = data["rich_text"]
        if btype == "callout":
            node["icon"] = data.get("icon")
            node["color"] = data.get("color", "default")
        if btype in ("heading_1", "heading_2", "heading_3"):
            node["is_toggleable"] = bool(data.get("is_toggleable"))
        if child.get("has_children"):
            node["children"] = _read_block_tree(child["id"], token)
        nodes.append(node)
    return nodes


def _block_to_payload(node: dict[str, Any]) -> dict[str, Any]:
    """_read_block_tree()가 만든 노드를 새 블록 생성 payload로 바꾼다.
    GET 응답 필드를 그대로 쓰지 않고 알려진 필드만 명시적으로 채운다
    (icon: null 같은 값 때문에 validation_error 났던 사고 재발 방지)."""
    btype = node["type"]
    inner: dict[str, Any] = {}
    if "rich_text" in node:
        inner["rich_text"] = node["rich_text"]
    if btype == "callout":
        if node.get("icon"):
            inner["icon"] = node["icon"]
        inner["color"] = node.get("color", "default")
    if btype in ("heading_1", "heading_2", "heading_3") and node.get("is_toggleable"):
        inner["is_toggleable"] = True
    payload: dict[str, Any] = {"object": "block", "type": btype, btype: inner}
    children = node.get("children") or []
    if children:
        # Notion 블록 생성 API는 한 요청 안에서 자손까지 함께 만들 수 있다(2단계까지).
        # 우리 구조는 toggle 헤딩 → 그 밑 항목들 정도의 얕은 depth라 문제없다.
        payload[btype]["children"] = [_block_to_payload(c) for c in children]
    return payload


def _append_children(parent_id: str, payloads: list[dict[str, Any]], token: str) -> None:
    for start in range(0, len(payloads), 50):
        _notion_request("PATCH", f"blocks/{parent_id}/children", token, {"children": payloads[start:start + 50]})


def _delete_all_children(parent_id: str, token: str) -> None:
    while True:
        existing = _list_children(parent_id, token)
        if not existing:
            break
        for child in existing:
            _notion_request("DELETE", f"blocks/{child['id']}", token)


# ════════════════════════════════════════════════════════════
# 날짜 토글 파싱 헬퍼
# ════════════════════════════════════════════════════════════

_DATE_HEADING_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _date_of(node: dict[str, Any]) -> str | None:
    if node["type"] != "heading_2":
        return None
    text = _plain_text_of(node.get("rich_text", []))
    m = _DATE_HEADING_RE.match(text.strip())
    return m.group(1) if m else None


# ════════════════════════════════════════════════════════════
# 항목 빌드
# ════════════════════════════════════════════════════════════

def _kst_now() -> datetime:
    return datetime.now(KST)


def _git(repo_dir: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo_dir), *args], capture_output=True, text=True)
    return result.stdout.strip()


def _git_head_info(repo_dir: Path) -> dict[str, Any] | None:
    head = _git(repo_dir, "rev-parse", "HEAD")
    if not head:
        return None
    subject = _git(repo_dir, "log", "-1", "--format=%s")
    changed = _git(repo_dir, "show", "--stat", "--format=", "HEAD")
    changed_files = [
        line.split("|")[0].strip() for line in changed.splitlines() if "|" in line
    ]
    upstream = _git(repo_dir, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    pushed = False
    if upstream:
        upstream_hash = _git(repo_dir, "rev-parse", upstream)
        pushed = upstream_hash == head
    return {
        "hash": head[:7], "full_hash": head, "subject": subject,
        "changed_files": changed_files, "pushed": pushed,
    }


def _target_systems(changed_files: list[str]) -> str:
    tops = sorted({f.split("/")[0] for f in changed_files if "/" in f})
    return ", ".join(tops) if tops else "(루트)"


def _build_entry_nodes(args: argparse.Namespace, git_info: dict[str, Any] | None) -> list[dict[str, Any]]:
    """헤딩 하나 + 불릿 여러 개를 "형제(flat sibling)"로 반환한다 — 기존 페이지의
    실제 구조를 그대로 읽어보니(★ 2026-08-12 확인) 불릿이 heading_3의 자식으로
    중첩된 게 아니라 날짜 토글 바로 밑에 나란히 있었다(마크다운으로 만들 때
    헤딩 다음 줄을 탭으로 들여쓰지 않으면 이렇게 된다). 기존 관례를 그대로
    따른다."""
    now = _kst_now()
    title = f"{now:%H:%M} KST · {args.agent} · {args.title}"
    bullets = [f"**상태:** {args.status}"]
    if args.request:
        bullets.append(f"**요청:** {args.request}")
    if args.changes:
        bullets.append(f"**변경:** {args.changes}")
    if args.verification:
        bullets.append(f"**검증:** {args.verification}")
    if git_info:
        push_note = "`main` 푸시 완료" if git_info["pushed"] else "⚠️ 아직 푸시 안 됨"
        subject = f" ({git_info['subject']})" if git_info["subject"] else ""
        bullets.append(f"**Git:** `{git_info['hash']}`{subject}, {push_note}")
        if git_info["changed_files"]:
            files_preview = ", ".join(git_info["changed_files"][:12])
            if len(git_info["changed_files"]) > 12:
                files_preview += f" 외 {len(git_info['changed_files']) - 12}개"
            bullets.append(f"**변경 파일:** {files_preview}")
    elif args.no_git:
        pass
    else:
        bullets.append("**Git:** 아직 커밋 전(진행 중 작업)")
    if args.risks:
        bullets.append(f"**남은 일·위험:** {args.risks}")
    if args.next_prompt:
        bullets.append(f"**다음 세션용 프롬프트:** {args.next_prompt}")

    heading = {"type": "heading_3", "rich_text": _rich_text(title), "is_toggleable": False}
    return [heading] + [{"type": "bulleted_list_item", "rich_text": _rich_text(b)} for b in bullets]


# ════════════════════════════════════════════════════════════
# add — 새 항목을 페이지에 반영
# ════════════════════════════════════════════════════════════

def cmd_add(args: argparse.Namespace) -> None:
    repo_dir = Path(args.repo).resolve()
    token = _notion_token()

    git_info = None if args.no_git else _git_head_info(repo_dir)
    entry_nodes = _build_entry_nodes(args, git_info)

    print("📖 기존 페이지 구조를 읽는 중...")
    top_nodes = _read_block_tree(JOURNAL_PAGE_ID, token)

    callout = None
    date_groups: list[dict[str, Any]] = []
    for node in top_nodes:
        if node["type"] == "callout" and callout is None:
            callout = node
            continue
        date_groups.append(node)

    today = _kst_now().strftime("%Y-%m-%d")
    target_group = None
    for group in date_groups:
        if _date_of(group) == today:
            target_group = group
            break

    if target_group is not None:
        target_group.setdefault("children", [])[0:0] = entry_nodes
        print(f"➕ 기존 {today} 토글에 항목 추가")
    else:
        new_group = {
            "type": "heading_2",
            "rich_text": _rich_text(today),
            "is_toggleable": True,
            "children": entry_nodes,
        }
        date_groups.insert(0, new_group)
        print(f"🆕 새 날짜 토글 {today} 생성")

    if args.dry_run:
        print("\n--- DRY RUN: 실제로 쓰지 않음 ---")
        preview = [callout] if callout else []
        preview += date_groups
        for node in preview:
            _print_node(node)
        return

    ordered = ([callout] if callout else []) + date_groups
    payloads = [_block_to_payload(n) for n in ordered]

    print("🗑️  기존 최상위 블록 전체 삭제 중...")
    _delete_all_children(JOURNAL_PAGE_ID, token)
    print("✍️  새 구조로 재작성 중...")
    _append_children(JOURNAL_PAGE_ID, payloads, token)
    print(f"✅ 완료 — https://www.notion.so/{JOURNAL_PAGE_ID.replace('-', '')}")


def _print_node(node: dict[str, Any], depth: int = 0) -> None:
    prefix = "  " * depth
    text = _plain_text_of(node.get("rich_text", [])) if "rich_text" in node else ""
    print(f"{prefix}[{node['type']}] {text[:80]}")
    for child in node.get("children", []):
        _print_node(child, depth + 1)


# ════════════════════════════════════════════════════════════
# check — 세션 시작 시 점검
# ════════════════════════════════════════════════════════════

# ★ 2026-08-12: Notion 리치 텍스트는 **볼드**/`코드` 서식이 annotations로 들어가고
# _plain_text_of()로 뽑으면 별표·백틱 같은 마크다운 기호가 안 남는다("Git: 07cd530
# (커밋메시지), main 푸시 완료"처럼 평문만 남음) — 그래서 정규식도 그 평문 형태로
# 맞춘다.
_COMMIT_HASH_RE = re.compile(r"\bGit:\s*([0-9a-f]{7,40})\b")
_PROCESS_PATTERNS = [
    "shift_alarm.py", "job_collector.py", "contest_collector.py",
    "company_profile.py", "contest_tracker.py", "extract_high_pitch_video.py",
]


def _find_latest_logged_commit(token: str) -> str | None:
    """★ 2026-08-12: 기존 페이지 실측 결과, heading_3(시간·에이전트·제목) 다음의
    불릿들은 heading_3의 자식이 아니라 날짜 토글 밑에 나란히(flat) 있다 — 중첩
    구조를 가정하지 않고 날짜 토글의 모든 자식을 그대로 훑는다."""
    top_nodes = _read_block_tree(JOURNAL_PAGE_ID, token)
    for node in top_nodes:
        if node["type"] != "heading_2" or not _date_of(node):
            continue
        for child in node.get("children", []):
            if child["type"] != "bulleted_list_item":
                continue
            text = _plain_text_of(child.get("rich_text", []))
            m = _COMMIT_HASH_RE.search(text)
            if m:
                return m.group(1)
        # 이 날짜 토글에 Git 기록이 하나도 없으면(전부 진행 중) 다음 날짜로 계속 찾음
    return None


def cmd_check(args: argparse.Namespace) -> None:
    repo_dir = Path(args.repo).resolve()
    token = _notion_token()

    print("📖 공용 일지 최신 기록 조회 중...")
    logged_hash = _find_latest_logged_commit(token)
    local_head = _git(repo_dir, "rev-parse", "HEAD")
    local_head_short = local_head[:7] if local_head else "(없음)"

    print(f"\n{'=' * 60}")
    print("📋 세션 시작 점검")
    print(f"{'=' * 60}")
    print(f"일지에 마지막으로 기록된 커밋: {logged_hash or '(없음)'}")
    print(f"로컬 HEAD:                    {local_head_short}")

    if logged_hash and local_head and not local_head.startswith(logged_hash):
        log = _git(repo_dir, "log", f"{logged_hash}..HEAD", "--oneline")
        if log:
            print("\n⚠️  일지에 없는 커밋이 있습니다:")
            for line in log.splitlines():
                print(f"   {line}")
        else:
            print("\nℹ️  로컬 HEAD가 일지 기록보다 오래됐거나 다른 브랜치입니다(직접 확인 필요).")
    elif logged_hash:
        print("✅ 일지가 최신 커밋과 일치합니다.")

    dirty = _git(repo_dir, "status", "--short")
    print(f"\n{'─' * 60}")
    if dirty:
        print(f"⚠️  커밋되지 않은 변경사항:\n{dirty}")
    else:
        print("✅ dirty 파일 없음(작업 트리 깨끗함).")

    print(f"\n{'─' * 60}")
    print("🔍 관련 프로세스 실행 상태:")
    ps_output = subprocess.run(["ps", "aux"], capture_output=True, text=True).stdout
    found_any = False
    for pattern in _PROCESS_PATTERNS:
        matches = [line for line in ps_output.splitlines() if pattern in line and "grep" not in line]
        for line in matches:
            found_any = True
            parts = line.split(None, 10)
            pid = parts[1] if len(parts) > 1 else "?"
            print(f"   [{pattern}] PID {pid}")
    if not found_any:
        print("   (관련 스크립트가 현재 실행 중이지 않음)")
    print(f"{'=' * 60}")


# ════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Claude·Codex 공용 작업 인계장 자동화")
    p.add_argument("--repo", default=str(DEFAULT_REPO_DIR), help="Git 저장소 경로(기본: DailyHelloWorld_)")
    sub = p.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="새 작업 항목을 일지에 추가")
    add.add_argument("--agent", choices=AGENT_CHOICES, required=True)
    add.add_argument("--status", choices=STATUS_CHOICES, required=True)
    add.add_argument("--title", required=True, help="항목 제목(짧게)")
    add.add_argument("--request", default="", help="사용자 요청 요약")
    add.add_argument("--changes", default="", help="실제 변경 내용")
    add.add_argument("--verification", default="", help="실행한 검증")
    add.add_argument("--risks", default="", help="남은 일·위험")
    add.add_argument("--next-prompt", default="", help="다음 세션용 인계 프롬프트")
    add.add_argument("--no-git", action="store_true", help="Git 커밋 정보를 자동으로 붙이지 않음")
    add.add_argument("--dry-run", action="store_true", help="실제로 쓰지 않고 결과만 미리 출력")
    add.set_defaults(func=cmd_add)

    check = sub.add_parser("check", help="세션 시작 시 일지·Git·프로세스 상태 점검")
    check.set_defaults(func=cmd_check)

    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
