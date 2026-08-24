#!/usr/bin/env python3
"""툴파시스템 채팅앱의 Mac쪽 워커.

클라우드에 배포된 chatapp 서버가 큐에 쌓아 둔 "페르소나가 응답할 차례"를
폴링해서 가져오고, 이 Mac에 이미 로그인된 claude/codex CLI(ai_exec.py)로 응답을
생성한 뒤 서버에 결과를 돌려보낸다.

★ 설계 원칙: Claude/Codex CLI 인증 정보는 이 Mac 밖으로 나가지 않는다 — 클라우드
서버는 채팅 UI·메시지 저장·페르소나 프로필 캐시만 맡고, 실제 AI 응답 생성은
항상 이 Mac에서 일어난다(이직시스템 등에서 이미 쓰는 ai_exec.py 패턴 재사용,
추가 API 키·과금 없음). shift_alarm이 iCloud 쓰기를 launchd 대신 Launch
Services 앱에 위임하는 것과 같은 이유로, "민감한 작업은 신뢰된 로컬 프로세스가
전담"하는 이 저장소의 기존 패턴을 그대로 따른다."""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_exec import run_ai_exec  # noqa: E402
from notion_personas import build_system_prompt, fetch_page_text, list_personas, notion_token  # noqa: E402

SERVER_URL = os.environ.get("CHATAPP_SERVER_URL", "http://localhost:8000")
WORKER_TOKEN = os.environ.get("CHATAPP_WORKER_TOKEN", "")
POLL_INTERVAL_SECONDS = 3
PERSONA_SYNC_INTERVAL_SECONDS = 300
AI_TIMEOUT_SECONDS = 120
WORK_DIR = Path(__file__).resolve().parent


def _api(path, method="GET", body=None):
    url = f"{SERVER_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if WORKER_TOKEN:
        headers["Authorization"] = f"Bearer {WORKER_TOKEN}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def sync_personas():
    """Notion에서 페르소나 목록·본문을 읽어 (이름→system_prompt) 캐시를 만들고,
    서버에도 참고용으로 올려둔다(서버가 /api/personas로 목록을 보여줄 수 있게).
    실패해도 워커는 멈추지 않고 이전 캐시를 그대로 쓴다."""
    token = notion_token()
    if not token:
        print("⚠️ Notion 토큰을 못 찾음 — 이전 캐시 유지", flush=True)
        return None
    cache = {}
    try:
        personas = list_personas(token)
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"⚠️ Notion 페르소나 목록 조회 실패: {exc}", flush=True)
        return None
    for persona in personas:
        try:
            page_text = fetch_page_text(persona["id"], token)
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            print(f"⚠️ '{persona['title']}' 페이지 조회 실패: {exc}", flush=True)
            continue
        system_prompt = build_system_prompt(persona["title"], page_text)
        cache[persona["title"]] = system_prompt
        try:
            _api("/api/worker/sync_persona", "POST", {
                "name": persona["title"],
                "notion_page_id": persona["id"],
                "system_prompt": system_prompt,
            })
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            print(f"⚠️ '{persona['title']}' 서버 동기화 실패: {exc}", flush=True)
    print(f"✅ 페르소나 {len(cache)}명 동기화: {', '.join(cache) or '(없음)'}", flush=True)
    return cache


def build_prompt(persona_name, system_prompt, context):
    lines = [system_prompt, "", "--- 최근 대화 ---"]
    for msg in context:
        speaker = "나" if msg["sender"] == "user" else msg["sender"]
        lines.append(f"{speaker}: {msg['content']}")
    lines.append("")
    lines.append(
        f'위 대화 흐름에 이어서 "{persona_name}"으로서 다음 메시지 하나만 답하세요. '
        f'"{persona_name}:" 같은 이름표는 붙이지 말고 대사만 쓰세요.'
    )
    return "\n".join(lines)


def process_turn(turn, persona_cache):
    persona_name = turn["persona_name"]
    system_prompt = persona_cache.get(persona_name)
    if not system_prompt:
        print(f"⚠️ 페르소나 '{persona_name}' 프로필 캐시 없음 — 다음 동기화 주기까지 대기", flush=True)
        return
    prompt = build_prompt(persona_name, system_prompt, turn["context"])
    try:
        reply, engine = run_ai_exec(prompt, WORK_DIR, timeout=AI_TIMEOUT_SECONDS)
        reply = reply.strip()
        _api("/api/worker/complete", "POST", {"turn_id": turn["turn_id"], "reply": reply})
        print(f"💬 {persona_name} ({engine}): {reply[:60]}", flush=True)
    except Exception as exc:  # noqa: BLE001 — 이 턴만 실패 처리하고 워커는 계속 돈다
        try:
            _api("/api/worker/complete", "POST", {"turn_id": turn["turn_id"], "error": str(exc)})
        except (urllib.error.URLError, urllib.error.HTTPError):
            pass
        print(f"⚠️ {persona_name} 응답 생성 실패: {exc}", flush=True)


def main():
    print(f"툴파시스템 워커 시작 — 서버: {SERVER_URL}", flush=True)
    persona_cache = sync_personas() or {}
    last_sync = time.time()
    while True:
        if time.time() - last_sync > PERSONA_SYNC_INTERVAL_SECONDS:
            new_cache = sync_personas()
            if new_cache is not None:
                persona_cache = new_cache
            last_sync = time.time()
        try:
            turn = _api("/api/worker/pending")
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            print(f"⚠️ 서버 연결 실패: {exc}", flush=True)
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        if turn:
            process_turn(turn, persona_cache)
        else:
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
