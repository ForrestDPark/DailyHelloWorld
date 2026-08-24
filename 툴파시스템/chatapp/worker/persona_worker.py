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
from notion_personas import (  # noqa: E402
    append_story_summary, build_system_prompt, fetch_page_text, list_personas, notion_token,
)

SERVER_URL = os.environ.get("CHATAPP_SERVER_URL", "http://localhost:8000")
WORKER_TOKEN = os.environ.get("CHATAPP_WORKER_TOKEN", "")
POLL_INTERVAL_SECONDS = 3
PERSONA_SYNC_INTERVAL_SECONDS = 300
AI_TIMEOUT_SECONDS = 120
WORK_DIR = Path(__file__).resolve().parent

# ★ "채팅 → Notion도 자동으로 동기화되면 좋겠다"는 요청(2026-08-24) — 대화가
# 쌓이면 주기적으로 훑어서 각 페르소나의 "함께 만든 이야기" 섹션에 요약해
# 추가한다. 너무 잦으면 Notion이 자잘한 요약으로 도배되니 두 조건으로
# 묶는다: 시간 간격(STORY_SYNC_INTERVAL_SECONDS)과 최소 메시지 수
# (STORY_SYNC_MIN_NEW_MESSAGES) 둘 다 넘어야 실제로 요약·기록한다.
STORY_SYNC_INTERVAL_SECONDS = 600
STORY_SYNC_MIN_NEW_MESSAGES = 4


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
    """Notion에서 페르소나 목록·본문을 읽어 이름→{system_prompt, page_id} 캐시를
    만들고, 서버에도 참고용으로 올려둔다(서버가 /api/personas로 목록을 보여줄
    수 있게). 실패해도 워커는 멈추지 않고 이전 캐시를 그대로 쓴다."""
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
        cache[persona["title"]] = {"system_prompt": system_prompt, "page_id": persona["id"]}
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
    entry = persona_cache.get(persona_name)
    if not entry:
        print(f"⚠️ 페르소나 '{persona_name}' 프로필 캐시 없음 — 다음 동기화 주기까지 대기", flush=True)
        return
    prompt = build_prompt(persona_name, entry["system_prompt"], turn["context"])
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


def sync_stories(persona_cache):
    """새로 쌓인 대화(전체 채팅방 + 모든 1:1 방 통틀어)를 훑어서, 각 페르소나가
    등장한 대목이 STORY_SYNC_MIN_NEW_MESSAGES개 이상이면 AI로 짧게 요약해
    그 인물의 Notion 페이지 "함께 만든 이야기" 섹션에 추가한다. 워터마크는
    서버(story_sync 테이블)가 들고 있어 워커를 재시작해도 중복·누락이 없다."""
    token = notion_token()
    if not token:
        return
    try:
        watermarks = _api("/api/worker/story_sync") or {}
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"⚠️ 이야기 동기화 상태 조회 실패: {exc}", flush=True)
        return
    try:
        all_messages = _api("/api/worker/all_messages?since_id=0")
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"⚠️ 전체 메시지 조회 실패: {exc}", flush=True)
        return
    if not all_messages:
        return
    max_id = all_messages[-1]["id"]
    for persona_name, entry in persona_cache.items():
        last_id = watermarks.get(persona_name, 0)
        new_msgs = [m for m in all_messages if m["id"] > last_id]
        relevant = [m for m in new_msgs if m["sender"] == persona_name or f"@{persona_name}" in m["content"]]
        if len(relevant) < STORY_SYNC_MIN_NEW_MESSAGES:
            continue
        transcript = "\n".join(
            f"{'나' if m['sender'] == 'user' else m['sender']}: {m['content']}" for m in new_msgs
        )
        prompt = (
            f'다음은 "{persona_name}"이(가) 참여한 채팅 대화의 최근 구간입니다.\n\n'
            f"{transcript}\n\n"
            f'이 대화에서 "{persona_name}"과 관련해 새로 드러나거나 만들어진 설정·사건·'
            "감정선을 2~4문장으로 짧게 요약하세요. 잡담이나 인사만 있었고 새로 쌓인 "
            '설정이 없다면 정확히 "특별한 진전 없음"이라고만 답하세요.'
        )
        try:
            summary, engine = run_ai_exec(prompt, WORK_DIR, timeout=AI_TIMEOUT_SECONDS)
            summary = summary.strip()
        except Exception as exc:  # noqa: BLE001 — 이 인물만 건너뛰고 워커는 계속 돈다
            print(f"⚠️ {persona_name} 이야기 요약 실패: {exc}", flush=True)
            continue
        if not summary.startswith("특별한 진전"):
            try:
                date_label = time.strftime("%Y-%m-%d")
                append_story_summary(entry["page_id"], token, date_label, summary)
                print(f"📝 {persona_name} 이야기 Notion에 기록 ({engine}): {summary[:50]}", flush=True)
            except (urllib.error.URLError, urllib.error.HTTPError) as exc:
                print(f"⚠️ {persona_name} Notion 기록 실패(워터마크는 유지 안 함): {exc}", flush=True)
                continue
        try:
            _api("/api/worker/story_sync", "POST", {"persona_name": persona_name, "last_message_id": max_id})
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            print(f"⚠️ {persona_name} 동기화 상태 저장 실패: {exc}", flush=True)


def main():
    print(f"툴파시스템 워커 시작 — 서버: {SERVER_URL}", flush=True)
    persona_cache = sync_personas() or {}
    last_sync = time.time()
    last_story_sync = time.time()
    while True:
        now = time.time()
        if now - last_sync > PERSONA_SYNC_INTERVAL_SECONDS:
            new_cache = sync_personas()
            if new_cache is not None:
                persona_cache = new_cache
            last_sync = time.time()
        if now - last_story_sync > STORY_SYNC_INTERVAL_SECONDS:
            sync_stories(persona_cache)
            last_story_sync = time.time()
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
