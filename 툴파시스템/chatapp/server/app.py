"""툴파시스템 채팅앱 서버 (클라우드에 배포).

이 서버는 채팅 UI를 제공하고 메시지·대기열을 SQLite에 저장할 뿐, 실제 AI 응답은
절대 생성하지 않는다 — Claude/Codex CLI 인증 정보를 이 서버(공개 인터넷에
노출됨)로 옮기지 않기 위해서다. 응답 생성은 항상 사용자의 Mac에서 도는
worker/persona_worker.py가 이 서버를 폴링해서 처리한다(자세한 이유는
../README.md 참고).

/api/worker/* 엔드포인트는 WORKER_TOKEN 환경변수가 설정돼 있으면 그 토큰을
요구한다(배포 시 반드시 설정 — 안 그러면 누구나 페르소나 프로필을 덮어쓰거나
가짜 응답을 주입할 수 있다).

★ 2026-08-24: 처음엔 앱 전체가 인증 없이 열려 있었는데, 실제로 URL을 아는
지인이 들어와서 "나"인 척 메시지를 보내는 사고가 났다(전체 채팅방에서 발견,
1:1 방도 구조상 똑같이 뚫려 있었음). /api/worker/*를 제외한 모든 요청에
HTTP Basic 인증을 건다 — APP_USERNAME/APP_PASSWORD 둘 다 설정된 경우에만
강제되고, 로컬 개발(둘 다 미설정)에서는 그대로 인증 없이 쓸 수 있다.

★ 같은 날 추가: "pulpilisory(APP_USERNAME/APP_PASSWORD)는 내 전용 쓰기
계정이고, 이외의 계정은 그냥 읽기 계정으로 하라"는 요청 — 별도 뷰어 계정을
미리 정해둘 필요 없이, 소유자 계정과 정확히 일치하지 않는 다른 아이디/
비밀번호는(무엇을 입력하든) 전부 읽기 전용으로 통과된다. 읽기 전용 요청이
POST /api/messages를 시도하면 403으로 막힌다."""
import base64
import datetime
import os
import secrets
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from server.db import get_conn, init_db

BASE_DIR = Path(__file__).resolve().parent.parent
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")
APP_USERNAME = os.environ.get("APP_USERNAME", "")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
MAX_CONTEXT_MESSAGES = 20


def _credentials_match(username, password, expected_username, expected_password):
    # ★ 2026-08-24 실측 버그: secrets.compare_digest(str, str)는 둘 중 하나라도
    # ASCII가 아닌 문자가 있으면 TypeError를 던진다(문서화된 CPython 제약) —
    # 다른 아이디로 로그인 시도하는 사람이 실수로건 의도적이건 비ASCII 문자가
    # 든 아이디/비밀번호를 넣으면 500 에러가 났다. bytes로 인코딩해서
    # 비교하면 이 제약이 없다.
    return (
        secrets.compare_digest(username.encode("utf-8"), expected_username.encode("utf-8"))
        and secrets.compare_digest(password.encode("utf-8"), expected_password.encode("utf-8"))
    )


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not APP_USERNAME or not APP_PASSWORD:
            request.state.can_write = True
            return await call_next(request)  # 로컬 개발용 — 둘 다 미설정 시 인증 생략
        if request.url.path.startswith("/api/worker/"):
            request.state.can_write = True
            return await call_next(request)  # 워커는 WORKER_TOKEN으로 별도 인증
        auth = request.headers.get("authorization", "")
        if auth.startswith("Basic "):
            try:
                username, _, password = base64.b64decode(auth[6:]).decode("utf-8").partition(":")
            except (ValueError, UnicodeDecodeError):
                username, password = "", ""
            if username or password:
                # ★ 2026-08-24: "pulpilisory는 내 전용 쓰기 계정이고 이외의
                # 계정은 그냥 읽기 계정으로 하라"는 요청 — 별도 뷰어 계정을
                # 미리 등록해둘 필요 없이, 소유자 계정과 정확히 일치하지 않는
                # 다른 아이디/비밀번호는(무엇이든) 전부 읽기 전용으로 통과시킨다.
                # 빈 문자열(=인증 헤더 없음/빈 시도)만 걸러서 브라우저가 처음엔
                # 로그인 창을 띄우게 한다.
                request.state.can_write = _credentials_match(username, password, APP_USERNAME, APP_PASSWORD)
                return await call_next(request)
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="tulpa"'})


app = FastAPI(title="툴파시스템 채팅앱")
app.add_middleware(BasicAuthMiddleware)
init_db()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _check_worker_auth(authorization: Optional[str]) -> None:
    if not WORKER_TOKEN:
        return  # 로컬 개발용 — 토큰 미설정 시 인증 생략
    if authorization != f"Bearer {WORKER_TOKEN}":
        raise HTTPException(status_code=401, detail="워커 인증 실패")


@app.get("/")
def index():
    return FileResponse(str(BASE_DIR / "static" / "index.html"))


GROUP_ROOM_ID = "group"
# ★ 2026-08-24: 그룹방은 아무도 안 부르면 페르소나 전원이 매번 동시에 반응하는
# 구조라 거의 똑같은 답이 몇 개씩 쏟아지고, 서로 일면식 없어야 할 인물들이
# Notion에 없는 친분·약속을 지어내는 문제가 실사용 중 확인됐다("이 채팅방은
# 당분간 폐쇄한다"는 요청). 코드/데이터는 그대로 두고 노출만 끈다 — "당분간"
# 이라 나중에 그룹 대화 로직을 고친 뒤 다시 켤 수 있게. GROUP_ROOM_ENABLED
# 환경변수(fly.toml [env])로 제어.
GROUP_ROOM_ENABLED = os.environ.get("GROUP_ROOM_ENABLED", "true").lower() == "true"


@app.get("/api/personas")
def list_personas():
    conn = get_conn()
    rows = conn.execute("SELECT name FROM personas ORDER BY name").fetchall()
    conn.close()
    return [r["name"] for r in rows]


@app.get("/api/rooms")
def list_rooms():
    """방 목록 — 카카오톡 채팅 목록처럼 전체 채팅방 1개 + 페르소나별 1:1 방.
    각 방의 마지막 메시지 미리보기도 같이 준다."""
    conn = get_conn()
    persona_names = [r["name"] for r in conn.execute("SELECT name FROM personas ORDER BY name").fetchall()]
    rooms = [{"room_id": GROUP_ROOM_ID, "label": "전체 채팅방"}] if GROUP_ROOM_ENABLED else []
    rooms += [{"room_id": name, "label": name} for name in persona_names]
    for room in rooms:
        last = conn.execute(
            "SELECT content, created_at FROM messages WHERE room_id = ? ORDER BY id DESC LIMIT 1",
            (room["room_id"],),
        ).fetchone()
        room["last_message"] = last["content"] if last else None
        room["last_message_at"] = last["created_at"] if last else None
    conn.close()
    return rooms


@app.get("/api/messages")
def get_messages(room_id: str = GROUP_ROOM_ID, since_id: int = 0):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, sender, content, created_at FROM messages WHERE room_id = ? AND id > ? ORDER BY id",
        (room_id, since_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


class NewMessage(BaseModel):
    content: str
    room_id: str = GROUP_ROOM_ID


@app.post("/api/messages")
def post_message(msg: NewMessage, request: Request):
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    content = msg.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="빈 메시지는 보낼 수 없습니다")
    room_id = msg.room_id or GROUP_ROOM_ID
    if room_id == GROUP_ROOM_ID and not GROUP_ROOM_ENABLED:
        raise HTTPException(status_code=403, detail="전체 채팅방은 당분간 닫혀 있습니다")
    conn = get_conn()
    now = _now()
    conn.execute(
        "INSERT INTO messages (room_id, sender, content, created_at) VALUES (?, 'user', ?, ?)",
        (room_id, content, now),
    )
    all_personas = [r["name"] for r in conn.execute("SELECT name FROM personas").fetchall()]
    if room_id == GROUP_ROOM_ID:
        # ★ "@이름"으로 특정 인물을 지목하면 그 인물만 응답, 아무도 안 부르면
        # 방에 있는 페르소나 전원이 한 번씩 응답한다(서로 이어서 계속 대화하는
        # 자동 체이닝은 폭주 방지를 위해 하지 않음 — README 로드맵 참고).
        mentioned = [p for p in all_personas if f"@{p}" in content]
        targets = mentioned if mentioned else all_personas
    else:
        # 1:1 방은 방 이름 = 그 페르소나 이름이므로 항상 그 한 명만 응답한다.
        targets = [room_id] if room_id in all_personas else []
    for persona_name in targets:
        conn.execute(
            "INSERT INTO pending_turns (persona_name, room_id, status, created_at) VALUES (?, ?, 'pending', ?)",
            (persona_name, room_id, now),
        )
    conn.commit()
    conn.close()
    return {"ok": True, "notified": targets}


@app.get("/api/worker/pending")
def worker_pending(authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    conn = get_conn()
    row = conn.execute(
        "SELECT id, persona_name, room_id FROM pending_turns WHERE status = 'pending' ORDER BY id LIMIT 1"
    ).fetchone()
    if not row:
        conn.close()
        return None
    context_rows = conn.execute(
        "SELECT sender, content FROM messages WHERE room_id = ? ORDER BY id DESC LIMIT ?",
        (row["room_id"], MAX_CONTEXT_MESSAGES),
    ).fetchall()
    conn.close()
    return {
        "turn_id": row["id"],
        "persona_name": row["persona_name"],
        "room_id": row["room_id"],
        "context": [dict(r) for r in reversed(context_rows)],
    }


class WorkerResult(BaseModel):
    turn_id: int
    reply: Optional[str] = None
    error: Optional[str] = None


@app.post("/api/worker/complete")
def worker_complete(result: WorkerResult, authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    conn = get_conn()
    row = conn.execute(
        "SELECT persona_name, room_id FROM pending_turns WHERE id = ?", (result.turn_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="해당 turn_id 없음")
    now = _now()
    if result.reply:
        conn.execute(
            "INSERT INTO messages (room_id, sender, content, created_at) VALUES (?, ?, ?, ?)",
            (row["room_id"], row["persona_name"], result.reply, now),
        )
        conn.execute(
            "UPDATE pending_turns SET status = 'done', reply = ?, completed_at = ? WHERE id = ?",
            (result.reply, now, result.turn_id),
        )
    else:
        conn.execute(
            "UPDATE pending_turns SET status = 'failed', error = ?, completed_at = ? WHERE id = ?",
            (result.error or "unknown error", now, result.turn_id),
        )
    conn.commit()
    conn.close()
    return {"ok": True}


class PersonaSync(BaseModel):
    name: str
    notion_page_id: str
    system_prompt: str


@app.post("/api/worker/sync_persona")
def sync_persona(persona: PersonaSync, authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO personas (name, notion_page_id, system_prompt, synced_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            notion_page_id = excluded.notion_page_id,
            system_prompt = excluded.system_prompt,
            synced_at = excluded.synced_at
        """,
        (persona.name, persona.notion_page_id, persona.system_prompt, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/worker/all_messages")
def worker_all_messages(since_id: int = 0, authorization: Optional[str] = Header(None)):
    """방 구분 없이(전체 채팅방 + 모든 1:1 방) 새 메시지를 전부 반환한다.
    /api/messages는 방 하나만 보므로, 이야기 동기화처럼 "이 인물이 어느
    방에서든 등장한 모든 대목"을 봐야 하는 용도로 워커만 쓴다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, room_id, sender, content, created_at FROM messages WHERE id > ? ORDER BY id",
        (since_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/worker/story_sync")
def get_story_sync(authorization: Optional[str] = Header(None)):
    """워커가 각 페르소나별로 "함께 만든 이야기"에 어디까지(message id) 반영했는지
    조회한다. 워커를 재시작해도 이 서버가 워터마크를 들고 있어 중복·누락 없이
    이어서 처리할 수 있다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    rows = conn.execute("SELECT persona_name, last_message_id FROM story_sync").fetchall()
    conn.close()
    return {r["persona_name"]: r["last_message_id"] for r in rows}


class StorySyncUpdate(BaseModel):
    persona_name: str
    last_message_id: int


@app.post("/api/worker/story_sync")
def set_story_sync(update: StorySyncUpdate, authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO story_sync (persona_name, last_message_id, synced_at)
        VALUES (?, ?, ?)
        ON CONFLICT(persona_name) DO UPDATE SET
            last_message_id = excluded.last_message_id,
            synced_at = excluded.synced_at
        """,
        (update.persona_name, update.last_message_id, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}
