"""툴파시스템 채팅앱 서버 (이 Mac에서 실행, Cloudflare Tunnel로 노출).

이 서버는 채팅 UI를 제공하고 메시지·대기열을 SQLite에 저장할 뿐, 실제 AI 응답은
절대 생성하지 않는다 — Claude/Codex CLI 인증 정보를 공개 인터넷에 노출된
프로세스로 옮기지 않기 위해서다. 응답 생성은 항상 사용자의 Mac에서 도는
worker/persona_worker.py가 이 서버를 폴링해서 처리한다(자세한 이유는
../README.md 참고).

/api/worker/* 엔드포인트는 WORKER_TOKEN 환경변수가 설정돼 있으면 그 토큰을
요구한다(배포 시 반드시 설정 — 안 그러면 누구나 페르소나 프로필을 덮어쓰거나
가짜 응답을 주입할 수 있다).

★ 2026-08-24: 처음엔 앱 전체가 인증 없이 열려 있었는데, 실제로 URL을 아는
지인이 들어와서 "나"인 척 메시지를 보내는 사고가 났다. 그래서 처음엔 소유자
1계정만 쓰기 가능하고 나머지는 전부 읽기 전용으로 통일하는 Basic Auth를
붙였었다.

★ 2026-08-26: "다른 사용자들도 메시지를 남길 수 있으면 좋겠다"는 요청으로
로그인/회원가입 기반 다중 계정으로 확장했다. 이제 계정만 있으면 누구나 쓸 수
있다 — 대신 "다른 사용자가 페르소나를 조종해서 내 파일/프로젝트에 실제 행동을
시키면 안 된다"는 요청에 따라, 실제 부작용이 있는 동작(손동주의 파일 정리
등)은 worker/persona_worker.py 쪽에서 세션의 실제 사용자명이 소유자 계정과
정확히 일치할 때만 실행되도록 별도로 게이트한다(이 파일은 "누가 로그인했는지"
정보만 정확히 넘겨주면 됨 — 승인 판단 자체는 여기서 하지 않는다).

기존 Basic Auth(APP_USERNAME/APP_PASSWORD)는 shift_alarm.py가 소유자 자격으로
/api/all_messages를 폴링할 때 여전히 쓰므로(브라우저 로그인 세션이 없는
백그라운드 프로세스라 쿠키를 못 씀) 소유자 전용 대체 인증 경로로 남겨뒀다."""
import base64
import datetime
import os
import re
import secrets
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from server import auth
from server.db import get_conn, init_db

BASE_DIR = Path(__file__).resolve().parent.parent
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")
APP_USERNAME = os.environ.get("APP_USERNAME", "")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
MAX_CONTEXT_MESSAGES = 20

SESSION_COOKIE_NAME = "tulpa_session"
SESSION_COOKIE_MAX_AGE = auth.SESSION_MAX_AGE_SECONDS  # 180일
USERNAME_RE = re.compile(r"^[A-Za-z0-9_가-힣]{2,20}$")

# ★ 인증 없이 접근 가능한 경로 — 로그인 자체를 하려면 "/"와 정적 파일, 그리고
# 회원가입/로그인 API는 인증 이전에 열려 있어야 한다. /api/whoami는 로그인
# 여부를 프론트가 확인하는 용도라 항상 응답한다(그 자체로 정보 노출 없음).
PUBLIC_PATHS = {"/", "/api/whoami", "/api/auth/signup", "/api/auth/login", "/api/auth/logout"}

# ★ "링크로 공유해서 다른 사람이 채팅을 읽기만(쓰기는 못하게) 할 수 있게
# 해달라" 요청(2026-08-25) — 계정 없이도 쿼리스트링(?share=...)의 토큰이
# 맞으면 읽기 전용으로 통과시키고 쿠키에 저장해 재방문에도 유지한다.
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


def _resolve_auth(request):
    """세션 쿠키 → 소유자 Basic Auth(하위 호환) → 공유 링크 순서로 확인해
    request.state.user/can_write/share_guest를 채운다. 어디에도 해당 없으면
    user=None, can_write=False, share_guest=False로 남고 False를 반환한다
    (보호된 경로면 이때 401).

    ★ share_guest를 user/can_write와 별도로 두는 이유: 공유 링크 읽기 전용
    방문자와 완전 비로그인(차단 대상) 방문자가 둘 다 user=None,
    can_write=False라 이 둘을 구분할 방법이 없으면 프론트가 "로그인 필요"와
    "읽기 전용으로 정상 접속"을 구분 못 한다(/api/whoami가 이 필드로 알려줌)."""
    request.state.user = None
    request.state.can_write = False
    request.state.share_guest = False
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        conn = get_conn()
        try:
            user = auth.get_session_user(conn, token)
        finally:
            conn.close()
        if user:
            request.state.user = user
            request.state.can_write = True
            return True
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Basic ") and APP_USERNAME and APP_PASSWORD:
        try:
            username, _, password = base64.b64decode(auth_header[6:]).decode("utf-8").partition(":")
        except (ValueError, UnicodeDecodeError):
            username, password = "", ""
        if username and _credentials_match(username, password, APP_USERNAME, APP_PASSWORD):
            request.state.user = {"id": None, "username": APP_USERNAME, "is_owner": True}
            request.state.can_write = True
            return True
    if READ_SHARE_TOKEN:
        shared_token = request.query_params.get("share") or request.cookies.get(SHARE_COOKIE_NAME)
        if shared_token and secrets.compare_digest(
            shared_token.encode("utf-8"), READ_SHARE_TOKEN.encode("utf-8")
        ):
            request.state.can_write = False
            request.state.share_guest = True
            return True
    return False


class SessionAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if path.startswith("/api/worker/"):
            request.state.user = None
            request.state.can_write = True  # 워커는 WORKER_TOKEN으로 각 라우트에서 별도 인증
            request.state.share_guest = False
            return await call_next(request)
        if not APP_USERNAME or not APP_PASSWORD:
            request.state.user = None
            request.state.can_write = True  # 로컬 개발용 — 둘 다 미설정 시 인증 생략
            request.state.share_guest = False
            return await call_next(request)
        allowed = _resolve_auth(request)
        is_public = path in PUBLIC_PATHS or path.startswith("/static/")
        if not (allowed or is_public):
            return JSONResponse(status_code=401, content={"detail": "로그인이 필요합니다"})
        response = await call_next(request)
        share_param = request.query_params.get("share")
        if READ_SHARE_TOKEN and share_param and not request.state.user and secrets.compare_digest(
            share_param.encode("utf-8"), READ_SHARE_TOKEN.encode("utf-8")
        ):
            response.set_cookie(
                SHARE_COOKIE_NAME, READ_SHARE_TOKEN,
                max_age=SHARE_COOKIE_MAX_AGE, httponly=True, samesite="lax",
            )
        return response


app = FastAPI(title="툴파시스템 채팅앱")
app.add_middleware(SessionAuthMiddleware)
init_db()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _bootstrap_owner():
    """서버가 뜰 때 APP_USERNAME/APP_PASSWORD를 users 테이블의 is_owner=1
    계정으로 만들어둔다(이미 있으면 아무것도 안 함).

    ★ 2026-08-26: 이걸 안 하면 서버 시작 직후 "다른 누군가가 소유자 아이디를
    먼저 가입해서 선점"하는 경쟁 상태가 생긴다 — worker/persona_worker.py의
    파일 정리 승인 게이트는 로그인 세션의 실제 sender 문자열이
    CHATAPP_OWNER_USERNAME과 일치하는지만 보므로, 그 아이디를 다른 사람이
    먼저 계정으로 가지면 그 사람이 "소유자 승인"을 위조할 수 있게 된다.
    서버 시작 시점(첫 요청을 받기도 전)에 동기적으로 미리 만들어두면 이
    경쟁 자체가 없다."""
    if not APP_USERNAME or not APP_PASSWORD:
        return
    conn = get_conn()
    try:
        if conn.execute("SELECT id FROM users WHERE username = ?", (APP_USERNAME,)).fetchone():
            return
        salt, digest = auth.hash_password(APP_PASSWORD)
        conn.execute(
            "INSERT INTO users (username, password_hash, salt, is_owner, created_at) VALUES (?, ?, ?, 1, ?)",
            (APP_USERNAME, digest, salt, _now()),
        )
        conn.commit()
    finally:
        conn.close()


_bootstrap_owner()


def _check_worker_auth(authorization: Optional[str]) -> None:
    if not WORKER_TOKEN:
        return  # 로컬 개발용 — 토큰 미설정 시 인증 생략
    if authorization != f"Bearer {WORKER_TOKEN}":
        raise HTTPException(status_code=401, detail="워커 인증 실패")


def _persona_name_set(conn):
    return {r["name"] for r in conn.execute("SELECT name FROM personas").fetchall()}


def _with_sender_type(rows, persona_names):
    return [{**dict(r), "is_persona": r["sender"] in persona_names} for r in rows]


@app.get("/")
def index():
    return FileResponse(str(BASE_DIR / "static" / "index.html"))


class SignupRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/signup")
def signup(body: SignupRequest, response: Response):
    username = body.username.strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="아이디는 한글/영문/숫자/밑줄 2~20자로 입력하세요")
    if len(body.password) < 4:
        raise HTTPException(status_code=400, detail="비밀번호는 4자 이상이어야 합니다")
    # ★ _bootstrap_owner()가 서버 시작 시 APP_USERNAME을 이미 선점해두므로
    # 정상 흐름에서는 아래 UNIQUE 체크에서 걸러진다. 그래도 혹시 순서가
    # 꼬이는 경우(예: 서버 재기동 사이 잠깐)를 대비해 명시적으로 한 번 더 막는다.
    if APP_USERNAME and username == APP_USERNAME:
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다")
    conn = get_conn()
    try:
        if conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
            raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다")
        salt, digest = auth.hash_password(body.password)
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, salt, is_owner, created_at) VALUES (?, ?, ?, 0, ?)",
            (username, digest, salt, _now()),
        )
        conn.commit()
        token = auth.create_session(conn, cur.lastrowid)
    finally:
        conn.close()
    response.set_cookie(SESSION_COOKIE_NAME, token, max_age=SESSION_COOKIE_MAX_AGE, httponly=True, samesite="lax")
    return {"ok": True, "username": username, "is_owner": False}


@app.post("/api/auth/login")
def login(body: LoginRequest, response: Response):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, salt, is_owner FROM users WHERE username = ?",
            (body.username.strip(),),
        ).fetchone()
        if not row or not auth.verify_password(body.password, row["salt"], row["password_hash"]):
            raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다")
        token = auth.create_session(conn, row["id"])
    finally:
        conn.close()
    response.set_cookie(SESSION_COOKIE_NAME, token, max_age=SESSION_COOKIE_MAX_AGE, httponly=True, samesite="lax")
    return {"ok": True, "username": row["username"], "is_owner": bool(row["is_owner"])}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        conn = get_conn()
        auth.delete_session(conn, token)
        conn.close()
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"ok": True}


GROUP_ROOM_ID = "group"
# ★ 2026-08-24: 그룹방은 아무도 안 부르면 페르소나 전원이 매번 동시에 반응하는
# 구조라 거의 똑같은 답이 몇 개씩 쏟아지고, 서로 일면식 없어야 할 인물들이
# Notion에 없는 친분·약속을 지어내는 문제가 실사용 중 확인됐다("이 채팅방은
# 당분간 폐쇄한다"는 요청). 코드/데이터는 그대로 두고 노출만 끈다 — "당분간"
# 이라 나중에 그룹 대화 로직을 고친 뒤 다시 켤 수 있게. GROUP_ROOM_ENABLED
# 환경변수로 제어.
GROUP_ROOM_ENABLED = os.environ.get("GROUP_ROOM_ENABLED", "true").lower() == "true"

# ★ 2026-08-26: "손동주는 내 말에만 응답하게 해달라" 요청 — 1:1 방은 이미
# 소유자만 쓸 수 있게 막았으니(위 post_message) 이 목록은 단체 채팅방/그룹
# 회의방에서 다른 계정이 손동주를 부르거나 @멘션해도 응답 대기열에 아예
# 안 들어가게 거르는 용도다. worker/persona_worker.py의
# FILE_ORGANIZER_PERSONA_NAME과 같은 이름을 가리켜야 한다(두 파일은 서로
# import하지 않는 독립 프로세스라 값을 맞춰서 손으로 동기화해야 함).
OWNER_ONLY_PERSONAS = {"손동주"}


@app.get("/api/whoami")
def whoami(request: Request):
    """프론트엔드가 로그인 여부·쓰기 가능 여부를 미리 알아서, 비로그인
    방문자에겐 로그인/가입 화면을, 공유 링크 읽기 전용 방문자·로그인은
    했지만 읽기 전용인 방문자에겐 입력창을 숨긴 채팅 화면을 보여줄 수 있게
    한다. share_guest=False, logged_in=False인 조합만 진짜 "로그인이
    필요한" 상태다(공유 링크 방문자는 share_guest=True라 로그인 없이도
    채팅 화면을 그대로 봄)."""
    user = getattr(request.state, "user", None)
    return {
        "can_write": getattr(request.state, "can_write", True),
        "logged_in": user is not None,
        "username": user["username"] if user else None,
        "is_owner": bool(user["is_owner"]) if user else False,
        "share_guest": getattr(request.state, "share_guest", False),
    }


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
def list_rooms(request: Request):
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
    (그룹 회의방 자신을 그 그룹의 "구성원"처럼 묶어버리는 걸 방지).

    ★ 2026-08-26: "1:1 방은 다른 참여자들에게 아예 안 보이게 해달라" 요청 —
    소유자가 아니면 페르소나 1:1 방 자체를 목록에서 뺀다(전체 채팅방·그룹
    회의방만 보임). /api/messages도 같은 기준으로 직접 접근을 막으므로,
    URL 해시를 직접 편집해도 못 들어간다."""
    conn = get_conn()
    persona_rows = conn.execute(
        "SELECT name, group_name FROM personas ORDER BY name"
    ).fetchall()
    user = getattr(request.state, "user", None)
    is_owner_request = user["is_owner"] if user else True
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

    if is_owner_request:
        rooms += [
            {"room_id": r["name"], "label": r["name"], "group_name": r["group_name"], "is_group_room": False}
            for r in persona_rows
        ]
    for room in rooms:
        # ★ 2026-08-25: "안 읽은 메시지 있으면 안읽음 표시해달라" 요청 —
        # last_message_id를 같이 내려주면 프론트가 로컬(localStorage)에 저장한
        # "이 방에서 마지막으로 읽은 id"와 비교해서 배지를 띄울 수 있다.
        # 읽음 상태 자체는 서버에 저장하지 않는다(기기별 localStorage로 충분).
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
def get_messages(request: Request, room_id: str = GROUP_ROOM_ID, since_id: int = 0):
    conn = get_conn()
    persona_names = _persona_name_set(conn)
    # ★ 2026-08-26: list_rooms()와 같은 기준 — 소유자가 아니면 페르소나 1:1
    # 방은 목록뿐 아니라 직접 조회도 막는다(해시를 직접 편집해서 들어오는
    # 우회 방지).
    if room_id in persona_names:
        user = getattr(request.state, "user", None)
        is_owner_request = user["is_owner"] if user else True
        if not is_owner_request:
            conn.close()
            raise HTTPException(status_code=403, detail="다른 계정은 이 1:1 대화를 볼 수 없습니다")
    rows = conn.execute(
        "SELECT id, sender, content, created_at FROM messages WHERE room_id = ? AND id > ? ORDER BY id",
        (room_id, since_id),
    ).fetchall()
    conn.close()
    return _with_sender_type(rows, persona_names)


@app.get("/api/all_messages")
def all_messages(since_id: int = 0):
    """방 구분 없이 새 메시지를 전부 반환한다 — /api/worker/all_messages와 같은
    조회지만 워커 토큰이 아니라 일반 세션 인증(읽기 전용 계정도 가능)으로
    쓴다. ★ 2026-08-25: shift_alarm이 "새 메시지 있으면 알람 띄워달라"는
    요청으로 로컬에서 이 엔드포인트를 주기적으로 폴링한다(소유자 Basic Auth로
    인증 — 브라우저 세션 쿠키가 없는 백그라운드 프로세스라서). 방 하나씩은
    /api/messages로 이미 누구나 볼 수 있으므로, 여러 방을 합쳐서 보여주는
    것 자체는 새로운 노출이 아니다."""
    conn = get_conn()
    persona_names = _persona_name_set(conn)
    rows = conn.execute(
        "SELECT id, room_id, sender, content, created_at FROM messages WHERE id > ? ORDER BY id",
        (since_id,),
    ).fetchall()
    conn.close()
    return _with_sender_type(rows, persona_names)


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
    user = getattr(request.state, "user", None)
    # ★ 2026-08-26: 예전엔 sender가 항상 'user' 리터럴이었다(단일 사용자
    # 전제). 다중 계정으로 바뀌면서 실제 로그인 아이디를 그대로 저장한다 —
    # 페르소나가 "누가 말하는지" 구분할 수 있어야 하고(worker/persona_worker.py
    # build_prompt), 손동주의 파일 정리 승인도 "소유자 본인의 메시지인지"를
    # 이 값으로 판단하기 때문에 정확해야 한다. 인증이 꺼진 로컬 개발에서는
    # user가 없으므로 예전 그대로 'user'로 남겨 하위 호환한다.
    sender = user["username"] if user else "user"
    # ★ 로컬 개발(무인증)에서는 user 자체가 없다 — 이 경우 예전처럼 제약 없이
    # 다 허용한다(단일 사용자 전제이므로 "소유자 아님" 개념이 의미가 없음).
    is_owner_request = user["is_owner"] if user else True
    conn = get_conn()
    now = _now()
    persona_rows = conn.execute("SELECT name, group_name FROM personas").fetchall()
    all_personas = [r["name"] for r in persona_rows]
    # ★ 2026-08-26: "나 말고 다른 사람은 페르소나들과 개인 메시지 못 하게
    # 막고 단체 채팅방에서만 메시지 입력이 가능하게 해달라"는 요청 — 1:1
    # 방(room_id가 페르소나 이름과 정확히 같음)은 소유자만 쓸 수 있고, 다른
    # 계정은 전체 채팅방/그룹 회의방에서만 메시지를 보낼 수 있다. 읽기는
    # 그대로 전부 허용(공유 방 정책 유지) — 막는 건 "쓰기"뿐이다.
    if room_id in all_personas and not is_owner_request:
        conn.close()
        raise HTTPException(status_code=403, detail="다른 계정은 1:1 대화를 보낼 수 없습니다 — 단체 채팅방을 이용해주세요")
    conn.execute(
        "INSERT INTO messages (room_id, sender, content, created_at) VALUES (?, ?, ?, ?)",
        (room_id, sender, content, now),
    )
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
    if not is_owner_request:
        # 1:1 방은 이미 위에서 막았지만, 단체/그룹 회의방에서는 다른 계정도
        # 메시지를 보낼 수 있다 — 그 경우에도 손동주는 응답 대상에서 뺀다.
        targets = [t for t in targets if t not in OWNER_ONLY_PERSONAS]
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
