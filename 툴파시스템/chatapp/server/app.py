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
import re
import secrets
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
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

# ★ 2026-08-25: "링크로 공유해서 다른 사람이 채팅을 읽기만(쓰기는 못하게) 할
# 수 있게 해달라" 요청 — Basic Auth 로그인 팝업 없이 URL 하나로 바로 보이게
# 하려고, 쿼리스트링에 이 토큰을 실어 보내면(?share=...) 로그인 없이 읽기
# 전용으로 통과시키고, 이후 요청을 위해 쿠키에도 저장해둔다(같은 브라우저로
# 다시 들어올 때 쿼리스트링 없이도 유지). 소유자 계정(Authorization 헤더)이
# 있으면 항상 그게 우선한다 — 소유자가 같은 브라우저로 공유 링크를 먼저
# 열어봤다고 자기 계정 쓰기 권한이 막히는 일은 없어야 하므로.
READ_SHARE_TOKEN = os.environ.get("READ_SHARE_TOKEN", "")
SHARE_COOKIE_NAME = "tulpa_share"
SHARE_COOKIE_MAX_AGE = 60 * 60 * 24 * 180  # 180일

# ★ 2026-08-25: "채팅창에 이미지 업로드해서 서로 분석하면 좋겠다"는 요청.
# 서버와 워커가 이제 같은 Mac에서 도니까(더 이상 클라우드 분리 구조가 아님),
# 업로드된 이미지를 로컬 디스크에 두면 워커가 그대로 파일 경로로 읽어
# claude/codex의 이미지 첨부 기능에 넘길 수 있다 — 별도 다운로드·스토리지
# 서비스가 필요 없다. server/db.py의 CHATAPP_DB_PATH와 같은 패턴으로
# ~/.tulpachat/ 아래에 둔다.
UPLOADS_DIR = Path(os.path.expanduser("~/.tulpachat/uploads"))
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}
IMAGE_MARKER_RE = re.compile(r"!\[\]\(/uploads/[^)]+\)")


def _preview_text(content):
    """방 목록 미리보기용 — 이미지 마커는 사람이 읽을 문구로 바꾼다."""
    if IMAGE_MARKER_RE.search(content):
        stripped = IMAGE_MARKER_RE.sub("", content).strip()
        return "📷 사진" + (f" {stripped}" if stripped else "")
    return content


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
        if not auth and READ_SHARE_TOKEN:
            shared_token = request.query_params.get("share") or request.cookies.get(SHARE_COOKIE_NAME)
            if shared_token and secrets.compare_digest(
                shared_token.encode("utf-8"), READ_SHARE_TOKEN.encode("utf-8")
            ):
                request.state.can_write = False
                response = await call_next(request)
                if request.query_params.get("share"):
                    response.set_cookie(
                        SHARE_COOKIE_NAME, READ_SHARE_TOKEN,
                        max_age=SHARE_COOKIE_MAX_AGE, httponly=True, samesite="lax",
                    )
                return response
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
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


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


@app.get("/api/whoami")
def whoami(request: Request):
    """프론트엔드가 쓰기 가능 여부를 미리 알아서, 읽기 전용 방문자에겐 아예
    입력창을 숨길 수 있게 한다(2026-08-25 — 공유 링크 요청과 함께 추가)."""
    return {"can_write": getattr(request.state, "can_write", True)}


@app.get("/api/personas")
def list_personas():
    conn = get_conn()
    rows = conn.execute("SELECT name FROM personas ORDER BY name").fetchall()
    conn.close()
    return [r["name"] for r in rows]


def _group_members(conn, room_id, persona_rows):
    """그룹 회의방의 실제 참여자 = Notion "그룹" 필드가 이 방과 같은
    페르소나(기본 멤버) + 이 방에 초대된 페르소나(room_invites, 2026-08-25
    "프로젝트하다가 관련 인물 추가하는 식으로 초대하고 싶다" 요청). 순서는
    기본 멤버 먼저, dict.fromkeys로 중복 제거."""
    base = [r["name"] for r in persona_rows if r["group_name"] == room_id]
    invited = [
        row["persona_name"] for row in conn.execute(
            "SELECT persona_name FROM room_invites WHERE room_id = ?", (room_id,)
        ).fetchall()
    ]
    return list(dict.fromkeys(base + invited))


@app.get("/api/rooms/{room_id}/members")
def get_room_members(room_id: str):
    """이 그룹 회의방의 현재 참여자 목록과, 아직 초대 안 된 나머지 페르소나
    목록을 같이 준다 — 프론트의 초대 패널이 "누굴 더 부를 수 있는지" 보여줄 때 씀."""
    conn = get_conn()
    persona_rows = conn.execute("SELECT name, group_name FROM personas ORDER BY name").fetchall()
    members = _group_members(conn, room_id, persona_rows)
    conn.close()
    all_names = [r["name"] for r in persona_rows]
    available = [n for n in all_names if n not in members]
    return {"members": members, "available": available}


class InviteRequest(BaseModel):
    persona_name: str


@app.post("/api/rooms/{room_id}/invite")
def invite_to_room(room_id: str, body: InviteRequest, request: Request):
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    conn = get_conn()
    persona_rows = conn.execute("SELECT name, group_name FROM personas ORDER BY name").fetchall()
    if body.persona_name not in [r["name"] for r in persona_rows]:
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    is_known_group = any(r["group_name"] == room_id for r in persona_rows)
    if not is_known_group:
        conn.close()
        raise HTTPException(status_code=404, detail="그룹 회의방이 아닙니다")
    conn.execute(
        "INSERT OR IGNORE INTO room_invites (room_id, persona_name, invited_at) VALUES (?, ?, ?)",
        (room_id, body.persona_name, _now()),
    )
    conn.commit()
    members = _group_members(conn, room_id, persona_rows)
    conn.close()
    return {"ok": True, "members": members}


@app.get("/api/rooms")
def list_rooms():
    """방 목록 — 카카오톡 채팅 목록처럼 전체 채팅방 1개 + 그룹 회의방 +
    페르소나별 1:1 방. 각 방의 마지막 메시지 미리보기도 같이 준다.

    ★ 2026-08-25: "페르소나 목록도 그룹화하는 게 좋을거같아" 요청 — 각 1:1
    방에 Notion 프로필의 "그룹" 필드(group_name, 없으면 None)를 실어서
    반환한다. 실제 그룹 헤더로 묶어 보여주는 건 프론트엔드(static/chat.js)가
    한다.

    ★ 같은 날 추가: "동찬이형+양승윤 묶어서 그 안에서 회의하는 식으로"
    요청 — 그룹명 자체를 방 하나로도 노출한다(room_id=그룹명). 이 방에
    메시지를 보내면 그 그룹 소속 페르소나 전원이 순서대로 응답한다(폴링
    큐가 한 번에 하나씩 처리되므로, 뒤 순서 페르소나는 앞선 페르소나의
    답까지 컨텍스트에 포함돼 자연스럽게 "회의"처럼 이어진다). is_group_room
    플래그로 1:1 방과 구분해서 프론트가 그룹 헤더 없이 맨 위에 따로 보여준다
    (그룹 회의방 자신을 그 그룹의 "구성원"처럼 묶어버리는 걸 방지)."""
    conn = get_conn()
    persona_rows = conn.execute(
        "SELECT name, group_name FROM personas ORDER BY name"
    ).fetchall()
    rooms = [{"room_id": GROUP_ROOM_ID, "label": "전체 채팅방", "group_name": None, "is_group_room": False}] if GROUP_ROOM_ENABLED else []

    seen_groups = []
    for r in persona_rows:
        if r["group_name"] and r["group_name"] not in seen_groups:
            seen_groups.append(r["group_name"])
    for group_name in seen_groups:
        rooms.append({
            "room_id": group_name, "label": f"👥 {group_name}",
            "group_name": None, "is_group_room": True,
        })

    rooms += [
        {"room_id": r["name"], "label": r["name"], "group_name": r["group_name"], "is_group_room": False}
        for r in persona_rows
    ]
    for room in rooms:
        # ★ 2026-08-25: "안 읽은 메시지 있으면 안읽음 표시해달라" 요청 —
        # last_message_id를 같이 내려주면 프론트가 로컬(localStorage)에 저장한
        # "이 방에서 마지막으로 읽은 id"와 비교해서 배지를 띄울 수 있다.
        # 읽음 상태 자체는 서버에 저장하지 않는다(단일 사용자 개인 앱이라
        # 기기별 localStorage로 충분 — 여러 기기 동기화는 범위 밖).
        last = conn.execute(
            "SELECT id, content, created_at FROM messages WHERE room_id = ? ORDER BY id DESC LIMIT 1",
            (room["room_id"],),
        ).fetchone()
        room["last_message_id"] = last["id"] if last else None
        room["last_message"] = _preview_text(last["content"]) if last else None
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


@app.get("/api/all_messages")
def all_messages(since_id: int = 0):
    """방 구분 없이 새 메시지를 전부 반환한다 — /api/worker/all_messages와 같은
    조회지만 워커 토큰이 아니라 일반 Basic 인증(읽기 전용 계정도 가능)으로
    쓴다. ★ 2026-08-25: shift_alarm이 "새 메시지 있으면 알람 띄워달라"는
    요청으로 로컬에서 이 엔드포인트를 주기적으로 폴링한다. 방 하나씩은
    /api/messages로 이미 누구나 볼 수 있으므로, 여러 방을 합쳐서 보여주는
    것 자체는 새로운 노출이 아니다."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, room_id, sender, content, created_at FROM messages WHERE id > ? ORDER BY id",
        (since_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/upload")
async def upload_image(request: Request, file: UploadFile = File(...)):
    """이미지를 ~/.tulpachat/uploads/에 저장하고 접근 URL을 반환한다. 채팅
    메시지 본문에는 이 URL을 `![](url)` 마크다운 이미지 문법으로 넣는다 —
    프론트는 그대로 렌더링하고, 워커는 같은 마커를 정규식으로 찾아 로컬
    파일 경로로 바꿔서 AI에게 직접 이미지로 넘긴다(server/app.py의
    IMAGE_MARKER_RE와 worker 쪽이 같은 정규식을 씀)."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 이미지 형식입니다: {ext or '(확장자 없음)'}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다(10MB 제한)")
    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOADS_DIR / filename).write_bytes(data)
    return {"url": f"/uploads/{filename}"}


class NewMessage(BaseModel):
    content: str
    room_id: str = GROUP_ROOM_ID
    # ★ 2026-08-25: "한명한테 답장하는 기능" 요청 — 그룹/회의방에서 특정
    # 페르소나 메시지를 탭해서 답장하면 그 사람만 응답하게 한다. @멘션을
    # 직접 타이핑하지 않아도 되는 UI 단축 경로(static/chat.js가 채워서 보냄).
    reply_to: Optional[str] = None


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
    persona_rows = conn.execute("SELECT name, group_name FROM personas").fetchall()
    all_personas = [r["name"] for r in persona_rows]
    if room_id == GROUP_ROOM_ID:
        # ★ "@이름"으로 특정 인물을 지목하면 그 인물만 응답, 아무도 안 부르면
        # 방에 있는 페르소나 전원이 한 번씩 응답한다(서로 이어서 계속 대화하는
        # 자동 체이닝은 폭주 방지를 위해 하지 않음 — README 로드맵 참고).
        # ★ 2026-08-25: reply_to(메시지 탭해서 답장)가 있으면 @멘션보다 우선해서
        # 그 한 명만 응답 — "한명한테 말하는데 모든 인물이 다 답변해서 정신없다"
        # 는 요청.
        mentioned = [p for p in all_personas if f"@{p}" in content]
        if msg.reply_to and msg.reply_to in all_personas:
            targets = [msg.reply_to]
        else:
            targets = mentioned if mentioned else all_personas
    elif room_id in all_personas:
        # 1:1 방은 방 이름 = 그 페르소나 이름이므로 항상 그 한 명만 응답한다.
        targets = [room_id]
    else:
        # ★ 2026-08-25: "그룹 안에서 회의하는 식으로" 요청 — room_id가
        # 그룹명이면 그 그룹 소속 페르소나 전원(또는 @멘션된 사람만)이
        # 응답한다. 워커 폴링 큐는 한 번에 하나씩 처리되므로, 뒤 순서
        # 페르소나는 앞서 답한 페르소나의 메시지까지 컨텍스트에 포함된
        # 상태로 응답하게 되어 자연스럽게 순서대로 이어지는 회의가 된다.
        # ★ 2026-08-25: 기본 그룹 멤버 외에 room_invites로 초대된 페르소나도
        # 포함한다("프로젝트하다가 관련 인물 추가" 요청).
        group_members = _group_members(conn, room_id, persona_rows)
        mentioned = [p for p in group_members if f"@{p}" in content]
        if msg.reply_to and msg.reply_to in group_members:
            targets = [msg.reply_to]
        else:
            targets = mentioned if mentioned else group_members
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
    group_name: Optional[str] = None


@app.post("/api/worker/sync_persona")
def sync_persona(persona: PersonaSync, authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO personas (name, notion_page_id, system_prompt, group_name, synced_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            notion_page_id = excluded.notion_page_id,
            system_prompt = excluded.system_prompt,
            group_name = excluded.group_name,
            synced_at = excluded.synced_at
        """,
        (persona.name, persona.notion_page_id, persona.system_prompt, persona.group_name, _now()),
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
