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
import hashlib
import os
import re
import secrets
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from server import auth, oauth
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
PUBLIC_PATHS = {
    "/", "/api/whoami", "/api/auth/signup", "/api/auth/login", "/api/auth/logout",
    # ★ 2026-08-26: 구글/카카오 로그인 — 이 네 경로는 아직 세션이 없는 상태에서
    # 오는 요청(로그인 시작·프로바이더가 돌려보내는 콜백)이라 공개로 열어둔다.
    "/api/auth/google/login", "/api/auth/google/callback",
    "/api/auth/kakao/login", "/api/auth/kakao/callback",
}
OAUTH_STATE_COOKIE = "tulpa_oauth_state"

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


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    """★ 2026-08-26 실측 문제: FastAPI StaticFiles가 Cache-Control 헤더를 아예
    안 보내서, 브라우저가 자체 판단(Last-Modified 기준 휴리스틱)으로 정적
    파일(특히 chat.js)을 몇 분씩 재검증 없이 그대로 재사용했다 — Cloudflare
    캐시를 퍼지하고 우회 규칙까지 만들어도 브라우저 로컬 캐시는 그걸로 전혀
    안 고쳐졌다(서로 다른 계층). /static/·/uploads/ 요청에는 "no-cache"를
    강제해 매번 서버에 재검증(ETag)하게 한다 — 완전히 캐시를 끄는 게
    아니라 "쓰기 전에 항상 물어보라"는 지시라 대역폭 낭비는 크지 않다."""
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/") or request.url.path.startswith("/uploads/"):
            response.headers["Cache-Control"] = "no-cache"
        return response


app = FastAPI(title="툴파시스템 채팅앱")
app.add_middleware(SessionAuthMiddleware)
app.add_middleware(NoCacheStaticMiddleware)
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


# ★ 2026-08-26: "사용자가 자기만의 페르소나를 만들 수 있게 해달라" 요청 —
# Notion 동기화 페르소나(owner_username=NULL)의 1:1 방은 기존처럼 소유자만
# 쓸 수 있고, 사용자가 직접 만든 페르소나(owner_username=계정)의 1:1 방은
# 그 계정 본인 + 소유자만 쓸 수 있다.
def _can_access_persona_room(owner_username, requesting_username, is_owner_request):
    if is_owner_request:
        return True
    return owner_username is not None and owner_username == requesting_username


PERSONA_NAME_RE = re.compile(r"^[A-Za-z0-9_ 가-힣]{1,20}$")
USER_PERSONA_DESC_MAX_CHARS = 2000


def _build_user_persona_prompt(name, owner_username, description):
    return (
        f'당신은 "{name}"이라는 이름의 가상 페르소나입니다. 사용자 계정 "{owner_username}"이(가) '
        "직접 만든 캐릭터입니다. 아래는 그 사용자가 적어준 설정입니다 — 이 설정에 따라 자연스럽게 "
        "대화하세요(설정에 명시되지 않은 사실을 지어내 단정하지 말고, 대화 중 자연스럽게 드러나는 "
        "성격·반응 정도만 보완하세요).\n\n"
        f"--- 캐릭터 설정 ---\n{description}"
    )


def _with_sender_type(rows, persona_names, persona_avatars=None):
    """메시지 발신자 종류와 페르소나 프로필 이미지를 함께 내려준다."""
    persona_avatars = persona_avatars or {}
    return [
        {
            **dict(r),
            "is_persona": r["sender"] in persona_names,
            "avatar_url": persona_avatars.get(r["sender"]),
        }
        for r in rows
    ]


REACTION_EMOJIS = {"❤️", "👍", "✅", "😄", "😮", "😢"}


def _message_reactions(conn, message_ids, username):
    """메시지별 반응 수와 현재 사용자의 선택 여부를 한 번의 쿼리로 묶는다."""
    if not message_ids:
        return {}
    marks = ",".join("?" for _ in message_ids)
    rows = conn.execute(
        f"""SELECT message_id, emoji, COUNT(*) AS reaction_count,
                   MAX(CASE WHEN username = ? THEN 1 ELSE 0 END) AS mine
              FROM message_reactions
             WHERE message_id IN ({marks})
             GROUP BY message_id, emoji
             ORDER BY MIN(created_at)""",
        (username, *message_ids),
    ).fetchall()
    result = {}
    for row in rows:
        result.setdefault(row["message_id"], []).append(
            {"emoji": row["emoji"], "count": row["reaction_count"], "mine": bool(row["mine"])}
        )
    return result


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


def _unique_username_from(conn, display_name):
    """소셜 로그인 최초 가입 시 프로필 이름으로 로컬 계정명을 만든다.
    이미 있는 이름이면 뒤에 숫자를 붙여 유일하게 만든다."""
    base = re.sub(r"[^A-Za-z0-9_가-힣]", "", display_name)[:16] or "user"
    candidate = base
    n = 1
    while conn.execute("SELECT 1 FROM users WHERE username = ?", (candidate,)).fetchone():
        n += 1
        candidate = f"{base}{n}"
    return candidate


def _finish_oauth_login(provider, external_id, display_name):
    """구글/카카오 로그인 콜백의 공통 마무리 — 이미 연결된 계정이면 그대로
    로그인, 처음이면 새 로컬 계정을 만들어 연결한다(비밀번호는 무작위로
    채워두고 실제로 쓰이지 않음 — 이 계정은 소셜 로그인으로만 들어옴)."""
    column = "google_sub" if provider == "google" else "kakao_id"
    conn = get_conn()
    try:
        row = conn.execute(f"SELECT id, is_owner FROM users WHERE {column} = ?", (external_id,)).fetchone()
        if row:
            user_id = row["id"]
        else:
            username = _unique_username_from(conn, display_name)
            salt, digest = auth.hash_password(secrets.token_urlsafe(24))
            cur = conn.execute(
                f"INSERT INTO users (username, password_hash, salt, is_owner, created_at, {column}) "
                "VALUES (?, ?, ?, 0, ?, ?)",
                (username, digest, salt, _now(), external_id),
            )
            conn.commit()
            user_id = cur.lastrowid
        token = auth.create_session(conn, user_id)
    finally:
        conn.close()
    response = RedirectResponse("/")
    response.set_cookie(SESSION_COOKIE_NAME, token, max_age=SESSION_COOKIE_MAX_AGE, httponly=True, samesite="lax")
    response.delete_cookie(OAUTH_STATE_COOKIE)
    return response


@app.get("/api/auth/google/login")
def google_login():
    if not oauth.google_enabled():
        raise HTTPException(status_code=503, detail="Google 로그인이 아직 설정되지 않았습니다")
    state = secrets.token_urlsafe(16)
    response = RedirectResponse(oauth.google_auth_url(state))
    response.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax")
    return response


@app.get("/api/auth/google/callback")
def google_callback(request: Request, code: str = "", state: str = ""):
    if not code or not state or state != request.cookies.get(OAUTH_STATE_COOKIE):
        raise HTTPException(status_code=400, detail="잘못된 요청입니다")
    try:
        profile = oauth.google_exchange(code)
    except oauth.OAuthError:
        raise HTTPException(status_code=502, detail="Google 인증에 실패했습니다")
    return _finish_oauth_login("google", profile["external_id"], profile["name"])


@app.get("/api/auth/kakao/login")
def kakao_login():
    if not oauth.kakao_enabled():
        raise HTTPException(status_code=503, detail="카카오 로그인이 아직 설정되지 않았습니다")
    state = secrets.token_urlsafe(16)
    response = RedirectResponse(oauth.kakao_auth_url(state))
    response.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax")
    return response


@app.get("/api/auth/kakao/callback")
def kakao_callback(request: Request, code: str = "", state: str = ""):
    if not code or not state or state != request.cookies.get(OAUTH_STATE_COOKIE):
        raise HTTPException(status_code=400, detail="잘못된 요청입니다")
    try:
        profile = oauth.kakao_exchange(code)
    except oauth.OAuthError:
        raise HTTPException(status_code=502, detail="카카오 인증에 실패했습니다")
    return _finish_oauth_login("kakao", profile["external_id"], profile["name"])


class PersonaCreate(BaseModel):
    name: str
    description: str


class PersonaUpdate(BaseModel):
    description: str


class AdminPersonaUpdate(BaseModel):
    description: str


class AdminPersonaGroupUpdate(BaseModel):
    group_name: Optional[str] = None


ADMIN_OVERRIDE_MARKER = "\n\n--- 관리자 설정 덮어쓰기 ---\n"


def _with_admin_override(prompt, description):
    base = prompt.split(ADMIN_OVERRIDE_MARKER, 1)[0]
    return base + (ADMIN_OVERRIDE_MARKER + description if description else "")


def _persona_avatar_prompt(name, description):
    """사용자 설정만 끼워 넣는 결정론적 프로필 이미지 프롬프트."""
    clean = " ".join((description or "").split())[:USER_PERSONA_DESC_MAX_CHARS]
    return (
        "Create a square 1:1 premium editorial semi-realistic avatar portrait for a fictional persona. "
        f"Persona name: {name}. Personality and role: {clean}. "
        "Interpret the personality through expression, clothing, lighting, and a subtle abstract background. "
        "Centered close-up face and shoulders, distinctive silhouette, polished high detail, suitable for a chat profile. "
        "Do not imitate a real person's exact likeness. No text, no letters, no logos, no watermark."
    )


def _queue_persona_image(conn, name, description, requested_by, status, reason):
    conn.execute(
        """INSERT INTO persona_image_jobs
           (persona_name, prompt, requested_by, reason, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, _persona_avatar_prompt(name, description), requested_by, reason, status, _now()),
    )


@app.get("/api/admin/personas")
def admin_list_personas(request: Request):
    _require_owner(request)
    conn = get_conn()
    rows = conn.execute(
        """SELECT p.name, p.owner_username, p.description, p.profile_summary,
                  p.admin_description, p.avatar_url, p.group_name,
                  (SELECT j.status FROM persona_image_jobs j WHERE j.persona_name=p.name ORDER BY j.id DESC LIMIT 1) AS image_job_status,
                  (SELECT j.error FROM persona_image_jobs j WHERE j.persona_name=p.name ORDER BY j.id DESC LIMIT 1) AS image_job_error
             FROM personas p ORDER BY p.name"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.put("/api/admin/personas/{name}")
def admin_update_persona(name: str, body: AdminPersonaUpdate, request: Request):
    _require_owner(request)
    description = body.description.strip()
    if not description or len(description) > USER_PERSONA_DESC_MAX_CHARS:
        raise HTTPException(status_code=400, detail=f"설정은 1~{USER_PERSONA_DESC_MAX_CHARS}자로 입력하세요")
    conn = get_conn()
    row = conn.execute("SELECT system_prompt FROM personas WHERE name = ?", (name,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    conn.execute(
        "UPDATE personas SET admin_description = ?, profile_summary = ?, system_prompt = ?, synced_at = ? WHERE name = ?",
        (description, description, _with_admin_override(row["system_prompt"], description), _now(), name),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.put("/api/admin/personas/{name}/group")
def admin_update_persona_group(name: str, body: AdminPersonaGroupUpdate, request: Request):
    _require_owner(request)
    raw_group_name = (body.group_name or "").strip()
    group_name = raw_group_name or None
    if group_name and len(group_name) > 40:
        raise HTTPException(status_code=400, detail="그룹 이름은 40자 이내로 입력하세요")
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM personas WHERE name = ?", (name,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    conn.execute("UPDATE personas SET admin_group_name = ?, group_name = ? WHERE name = ?", (raw_group_name, group_name, name))
    conn.commit()
    conn.close()
    return {"ok": True, "group_name": group_name}


@app.post("/api/admin/personas/{name}/avatar")
async def admin_upload_persona_avatar(name: str, request: Request, file: UploadFile = File(...)):
    _require_owner(request)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="지원하지 않는 이미지 형식입니다")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다(10MB 제한)")
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM personas WHERE name = ?", (name,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    filename = f"persona_{uuid.uuid4().hex}{ext}"
    (UPLOADS_DIR / filename).write_bytes(data)
    url = f"/uploads/{filename}"
    conn.execute("UPDATE personas SET avatar_url = ? WHERE name = ?", (url, name))
    conn.commit()
    conn.close()
    return {"ok": True, "avatar_url": url}


@app.delete("/api/admin/personas/{name}/avatar")
def admin_delete_persona_avatar(name: str, request: Request):
    _require_owner(request)
    conn = get_conn()
    conn.execute("UPDATE personas SET avatar_url = NULL WHERE name = ?", (name,))
    conn.commit()
    conn.close()
    return {"ok": True}


class PersonaImageGenerateRequest(BaseModel):
    description: Optional[str] = None


@app.post("/api/admin/personas/{name}/avatar/generate")
def admin_generate_persona_avatar(name: str, body: PersonaImageGenerateRequest, request: Request):
    """관리자 버튼 클릭을 명시 승인으로 삼아 유료 Images API 작업을 큐에 넣는다."""
    _require_owner(request)
    conn = get_conn()
    row = conn.execute(
        "SELECT description, profile_summary, admin_description FROM personas WHERE name = ?", (name,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    description = (body.description or row["admin_description"] or row["description"] or row["profile_summary"] or "").strip()
    if not description or len(description) > USER_PERSONA_DESC_MAX_CHARS:
        conn.close()
        raise HTTPException(status_code=400, detail="이미지 생성을 위한 프로필 설정이 필요합니다")
    active = conn.execute(
        "SELECT 1 FROM persona_image_jobs WHERE persona_name = ? AND status IN ('pending','processing')",
        (name,),
    ).fetchone()
    if active:
        conn.close()
        raise HTTPException(status_code=409, detail="이미 생성 중인 작업이 있습니다")
    user = request.state.user
    _queue_persona_image(conn, name, description, user["username"], "pending", "admin_regenerate")
    job_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return {"ok": True, "job_id": job_id, "status": "pending"}


@app.get("/api/my_personas")
def list_my_personas(request: Request):
    """내가 만든 페르소나 목록 — 방 목록이 아니라 "관리" 화면(생성·수정·삭제)에서
    쓴다. description을 그대로 돌려줘서 수정 폼에 원문을 채워 넣을 수 있게 한다."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    conn = get_conn()
    rows = conn.execute(
        "SELECT name, description, synced_at FROM personas WHERE owner_username = ? ORDER BY name",
        (user["username"],),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/my_personas")
def create_my_persona(body: PersonaCreate, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    name = body.name.strip()
    if not PERSONA_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="이름은 한글/영문/숫자/공백/밑줄 1~20자로 입력하세요")
    description = body.description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="캐릭터 설정을 입력하세요")
    if len(description) > USER_PERSONA_DESC_MAX_CHARS:
        raise HTTPException(status_code=400, detail=f"설정은 {USER_PERSONA_DESC_MAX_CHARS}자 이내로 입력하세요")
    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM personas WHERE name = ?", (name,)).fetchone():
            raise HTTPException(status_code=409, detail="이미 사용 중인 이름입니다")
        prompt = _build_user_persona_prompt(name, user["username"], description)
        conn.execute(
            "INSERT INTO personas (name, notion_page_id, system_prompt, group_name, owner_username, description, synced_at) "
            "VALUES (?, '', ?, NULL, ?, ?, ?)",
            (name, prompt, user["username"], description, _now()),
        )
        # 소유자의 생성 클릭은 곧 유료 생성 승인이다. 일반 계정은 비용·시스템
        # 영향을 직접 일으키지 못하고 관리자가 재생성 버튼을 눌러야 진행된다.
        image_status = "pending" if user["is_owner"] else "awaiting_approval"
        _queue_persona_image(conn, name, description, user["username"], image_status, "persona_created")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "name": name, "image_status": image_status}


@app.put("/api/my_personas/{name}")
def update_my_persona(name: str, body: PersonaUpdate, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    description = body.description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="캐릭터 설정을 입력하세요")
    if len(description) > USER_PERSONA_DESC_MAX_CHARS:
        raise HTTPException(status_code=400, detail=f"설정은 {USER_PERSONA_DESC_MAX_CHARS}자 이내로 입력하세요")
    conn = get_conn()
    try:
        row = conn.execute("SELECT owner_username FROM personas WHERE name = ?", (name,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
        if row["owner_username"] != user["username"]:
            raise HTTPException(status_code=403, detail="본인이 만든 페르소나만 수정할 수 있습니다")
        prompt = _build_user_persona_prompt(name, user["username"], description)
        conn.execute(
            "UPDATE personas SET system_prompt = ?, description = ?, synced_at = ? WHERE name = ?",
            (prompt, description, _now(), name),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@app.delete("/api/my_personas/{name}")
def delete_my_persona(name: str, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    conn = get_conn()
    try:
        row = conn.execute("SELECT owner_username FROM personas WHERE name = ?", (name,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
        if row["owner_username"] != user["username"]:
            raise HTTPException(status_code=403, detail="본인이 만든 페르소나만 삭제할 수 있습니다")
        conn.execute("DELETE FROM personas WHERE name = ?", (name,))
        conn.execute("DELETE FROM messages WHERE room_id = ?", (name,))
        conn.execute("DELETE FROM pending_turns WHERE room_id = ?", (name,))
        conn.execute("DELETE FROM room_invites WHERE persona_name = ?", (name,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


# ★ 2026-08-26: "사용자가 단체톡방 만들기가 가능하게 해달라"는 요청 — Notion
# "그룹" 필드에서 자동으로 생기는 그룹 회의방과 달리, 계정이 직접 임의의
# 이름으로 만드는 방이다. 멤버 관리는 기존 room_invites 테이블/엔드포인트를
# 그대로 재사용한다(_group_members가 room_id로만 조회하므로 출처를 안 가림).
CUSTOM_ROOM_ID_PREFIX = "custom_"


class CustomRoomCreate(BaseModel):
    label: str


@app.post("/api/rooms")
def create_custom_room(body: CustomRoomCreate, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    label = body.label.strip()
    if not label or len(label) > 30:
        raise HTTPException(status_code=400, detail="방 이름은 1~30자로 입력하세요")
    room_id = f"{CUSTOM_ROOM_ID_PREFIX}{uuid.uuid4().hex[:10]}"
    conn = get_conn()
    conn.execute(
        "INSERT INTO custom_rooms (room_id, label, owner_username, created_at) VALUES (?, ?, ?, ?)",
        (room_id, label, user["username"], _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "room_id": room_id, "label": label}


@app.post("/api/rooms/{room_id}/thumbnail")
async def upload_room_thumbnail(room_id: str, request: Request, file: UploadFile = File(...)):
    """토론방 대표사진(2026-08-26 요청) — 커스텀 방 주인 또는 소유자만 바꿀 수
    있다. 저장·검증 로직은 /api/upload와 동일(같은 UPLOADS_DIR·확장자·용량
    제한 재사용)."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = user["is_owner"] if user else True
    conn = get_conn()
    row = conn.execute("SELECT owner_username FROM custom_rooms WHERE room_id = ?", (room_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="내가 만든 채팅방이 아닙니다")
    if not (is_owner_request or row["owner_username"] == username):
        conn.close()
        raise HTTPException(status_code=403, detail="이 채팅방의 대표사진은 방 주인만 바꿀 수 있습니다")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        conn.close()
        raise HTTPException(status_code=400, detail=f"지원하지 않는 이미지 형식입니다: {ext or '(확장자 없음)'}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        conn.close()
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다(10MB 제한)")
    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOADS_DIR / filename).write_bytes(data)
    url = f"/uploads/{filename}"
    conn.execute("UPDATE custom_rooms SET thumbnail_url = ? WHERE room_id = ?", (url, room_id))
    conn.commit()
    conn.close()
    return {"ok": True, "thumbnail_url": url}


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

# ★ 2026-08-26: "모든 사람한테 유이(UI 개발자 페르소나) 꾸밀 권한을 주지는
# 말고, 내 허락하에 그 사람에게만 권한을 줄 수 있게 해달라" 요청 — 손동주처럼
# 아예 소유자 전용으로 막는 게 아니라, 소유자가 ui_dev_grants 테이블에 특정
# 계정을 등록해두면 그 계정만 "유이"에게 말을 걸어 응답을 받을 수 있다(그 외
# 비소유자는 OWNER_ONLY_PERSONAS와 동일하게 취급 — 응답 대기열에 안 들어감).
# worker/persona_worker.py의 UI_DEV_PERSONA_NAME과 이름이 같아야 한다.
UI_DEV_PERSONAS = {"유이"}

# ★ 2026-08-26: "다른 사람들의 요구·요청사항·개선사항을 모아서 나한테
# 보고하는 에이전틱 툴파" 요청 — worker/persona_worker.py의 ADMIN_PERSONA_NAME과
# 이름이 같아야 한다. 아직은 "수집·보고"만 하고 실제 코드 수정 권한은 없다
# (유이처럼 파일 수정 권한을 줄지는 소유자와 상의 후 결정 예정).
ADMIN_PERSONA_NAME = "툴파관리자"


def _require_owner(request):
    user = getattr(request.state, "user", None)
    if user:
        is_owner_request = user["is_owner"]
    else:
        # user가 없는 경우가 둘 있다 — ①로컬 개발(무인증, can_write=True)은
        # 소유자로 간주(기존 관례) ②공유 링크 읽기 전용 방문자(share_guest=True,
        # can_write=False)는 소유자가 아니다. share_guest를 따로 확인해야
        # 한다 — can_write만 보면 나중에 다른 읽기전용 경로가 늘었을 때
        # 실수로 뚫릴 수 있어서 명시적으로 뺐다.
        is_owner_request = bool(getattr(request.state, "can_write", False)) and not getattr(
            request.state, "share_guest", False
        )
    if not is_owner_request:
        raise HTTPException(status_code=403, detail="소유자만 할 수 있습니다")


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
        # ★ 2026-08-26: 구글/카카오 로그인 버튼은 실제로 설정(도메인+클라이언트
        # ID/시크릿)이 끝났을 때만 보여준다 — 로그인 화면이 아직 안 될 버튼을
        # 미리 보여주지 않게.
        "google_login_enabled": oauth.google_enabled(),
        "kakao_login_enabled": oauth.kakao_enabled(),
    }


@app.get("/api/personas")
def list_personas():
    conn = get_conn()
    rows = conn.execute("SELECT name FROM personas ORDER BY name").fetchall()
    conn.close()
    return [r["name"] for r in rows]


@app.get("/api/persona_profiles")
def list_persona_profiles(request: Request):
    """"툴파들의 성격을 간단히 확인할 수 있는 페이지" 요청(2026-08-26) —
    공개 페르소나(Notion 동기화분) 전부 + 내가 만든 개인 페르소나만 보여준다
    (다른 사람의 개인 페르소나는 그 사람 1:1 방처럼 비공개 유지)."""
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = bool(user and user["is_owner"])
    conn = get_conn()
    rows = conn.execute(
        "SELECT name, owner_username, description, profile_summary, avatar_url FROM personas ORDER BY name"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        if r["owner_username"] is not None and r["owner_username"] != username and not is_owner_request:
            continue
        summary = r["profile_summary"] or r["description"] or "(아직 프로필 정보가 없습니다)"
        result.append({
            "name": r["name"],
            "is_mine": bool(username) and r["owner_username"] == username,
            "summary": summary,
            "avatar_url": r["avatar_url"],
        })
    return result


def _given_name(persona_name):
    """"한경호 선생님" → "경호", "박정민" → "정민"처럼 성(1글자)과 뒤에 붙는
    호칭(선생님 등)을 뗀 "부르는 이름"만 뽑는다. 2026-08-26: "정민씨", "경호쌤"
    처럼 자연스럽게 이름만 불렀는데 전원이 다 대답하는 문제 — @정확한 전체
    이름만 인식하던 걸 이걸로 보강한다."""
    first_word = persona_name.split()[0]
    return first_word[1:] if len(first_word) >= 3 else first_word


def _last_persona_speaker(conn, room_id, candidates):
    if not candidates:
        return None
    placeholders = ",".join("?" * len(candidates))
    row = conn.execute(
        f"SELECT sender FROM messages WHERE room_id = ? AND sender IN ({placeholders}) ORDER BY id DESC LIMIT 1",
        (room_id, *candidates),
    ).fetchone()
    return row["sender"] if row else None


_BROADCAST_INVITE_RE = re.compile(r"다른\s*(분|사람|병법가)|다들|여러분")


def _is_broadcast_invite(content):
    """"다른분들은 할말 없으십니까", "매요신님 같은 다른 병법가들도 말씀해
    보시지요"처럼, 특정 한 명이 아니라 방에 있는 여러/전원에게 발언을
    요청하는 문구인지 본다. ★ 2026-08-26: 이런 문구를 쓴 뒤에도 직전
    발화자나 문장 속에 걸린 이름 한 명만 계속 대답해서 "다른 사람들은
    말을 안 한다"는 버그 신고 — 이 경우엔 전원에게 보낸다."""
    return bool(_BROADCAST_INVITE_RE.search(content))


def _default_targets(conn, room_id, candidates, mentioned, reply_to, content=""):
    """이름/호칭으로 아무도 안 지목했을 때 누구에게 보낼지 정한다.

    ★ 2026-08-26: "너 솔직히 말해봐"처럼 대명사로만 말하면 방에 있는 페르소나
    전원이 반응해서 대화가 이상하게 흘러가는 문제 — 이전엔 "멘션 없으면
    전원 응답"이었는데, 그 방에서 누군가 이미 말을 섞고 있었다면(직전 발화자가
    있다면) 자연스러운 대화 흐름상 그 사람에게 이어서 말하는 것으로 보고
    그 한 명에게만 보낸다. 아직 아무도 말을 안 한 방(막 만들었거나 막
    초대한 직후)에서는 기존처럼 전원이 한 번씩 반응해 "인사 라운드"를 연다.

    ★ 2026-08-26: "다른 분들은 할 말 없으십니까", "매요신님 같은 다른
    병법가들도"처럼 여러/전원에게 말을 거는 문구는 위 "직전 발화자 1인에게만
    이어짐"/"멘션된 1명만" 규칙보다 우선한다 — 명시적으로 여러 명을 부른
    것이므로 전원에게 보낸다."""
    if reply_to and reply_to in candidates:
        return [reply_to]
    if _is_broadcast_invite(content):
        return candidates
    if mentioned:
        return mentioned
    last_speaker = _last_persona_speaker(conn, room_id, candidates)
    return [last_speaker] if last_speaker else candidates


def _mentioned_personas(content, candidates):
    """@정확한 이름 또는 "이름씨"/"이름쌤"/"이름아" 같은 자연스러운 호칭까지
    잡아서 지목된 페르소나를 찾는다. 아무도 안 걸리면 빈 리스트(전원 응답)."""
    mentioned = []
    for name in candidates:
        given = _given_name(name)
        if f"@{name}" in content or (len(given) >= 2 and given in content):
            mentioned.append(name)
    return mentioned


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


def _custom_room_access(conn, room_id, username, is_owner_request):
    """room_id가 사용자 커스텀 방이면 (그 방인지 여부, 접근 가능 여부, 방
    소유 계정)을 반환한다. Notion 그룹 회의방이면 (False, True, None) —
    그쪽은 기존처럼 로그인만 하면 누구나 볼 수 있다(단, 초대는 아래에서
    소유자로 별도 제한)."""
    row = conn.execute("SELECT owner_username FROM custom_rooms WHERE room_id = ?", (room_id,)).fetchone()
    if not row:
        return False, True, None
    allowed = is_owner_request or row["owner_username"] == username
    return True, allowed, row["owner_username"]


@app.get("/api/rooms/{room_id}/notice")
def get_room_notice(room_id: str, request: Request):
    """"카카오톡처럼 채팅방에 공지사항이 보였으면 좋겠다, 그 방 대화를 토대로
    업데이트 내용을 하루하루 요약해서 공지해달라"는 요청(2026-08-26). 워커가
    `sync_room_notices()`로 채워둔 최신 공지를 그대로 돌려준다 — 커스텀
    방이면 그 방 접근 권한과 동일하게 제한한다."""
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = user["is_owner"] if user else True
    conn = get_conn()
    is_custom, allowed, _room_owner = _custom_room_access(conn, room_id, username, is_owner_request)
    if is_custom and not allowed:
        conn.close()
        raise HTTPException(status_code=403, detail="이 채팅방 공지를 볼 수 없습니다")
    row = conn.execute("SELECT content, updated_at FROM room_notices WHERE room_id = ?", (room_id,)).fetchone()
    conn.close()
    if not row or not row["content"]:
        return None
    return {"content": row["content"], "updated_at": row["updated_at"]}


@app.get("/api/rooms/{room_id}/members")
def get_room_members(room_id: str, request: Request):
    """이 그룹 회의방의 현재 참여자 목록과, 아직 초대 안 된 나머지 페르소나
    목록을 같이 준다 — 프론트의 초대 패널이 "누굴 더 부를 수 있는지" 보여줄 때 씀.

    ★ 2026-08-26: "단체톡방 만들기 + 초대" 요청으로 사용자 커스텀 방도 지원.
    커스텀 방은 방 주인 + 소유자만 조회 가능, 초대 후보는 공개 페르소나(Notion) +
    그 방 주인이 직접 만든 페르소나로 제한한다(다른 사람의 개인 페르소나가
    남의 방에 노출되지 않게)."""
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = user["is_owner"] if user else True
    conn = get_conn()
    is_custom, allowed, room_owner = _custom_room_access(conn, room_id, username, is_owner_request)
    if is_custom and not allowed:
        conn.close()
        raise HTTPException(status_code=403, detail="이 채팅방에 접근할 수 없습니다")
    persona_rows = conn.execute("SELECT name, group_name, owner_username FROM personas ORDER BY name").fetchall()
    members = _group_members(conn, room_id, persona_rows)
    conn.close()
    if is_custom:
        candidates = [r["name"] for r in persona_rows if r["owner_username"] is None or r["owner_username"] == room_owner]
    else:
        candidates = [r["name"] for r in persona_rows if r["owner_username"] is None]
    available = [n for n in candidates if n not in members]
    return {"members": members, "available": available}


class InviteRequest(BaseModel):
    persona_name: str


@app.post("/api/rooms/{room_id}/invite")
def invite_to_room(room_id: str, body: InviteRequest, request: Request):
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = user["is_owner"] if user else True
    conn = get_conn()
    is_custom, allowed, room_owner = _custom_room_access(conn, room_id, username, is_owner_request)
    if is_custom and not allowed:
        conn.close()
        raise HTTPException(status_code=403, detail="이 채팅방에 초대할 수 없습니다")
    persona_rows = conn.execute("SELECT name, group_name, owner_username FROM personas ORDER BY name").fetchall()
    persona_map = {r["name"]: r["owner_username"] for r in persona_rows}
    if body.persona_name not in persona_map:
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    if is_custom:
        is_known_room = True
    else:
        is_known_room = any(r["group_name"] == room_id for r in persona_rows)
        if is_known_room and not is_owner_request:
            # ★ Notion 그룹 회의방(모두가 공유하는 방)에 누구든 다른 사람을
            # 부를 수 있으면 위험하니, 소유자만 초대할 수 있게 좁힌다.
            conn.close()
            raise HTTPException(status_code=403, detail="이 회의방은 소유자만 초대할 수 있습니다")
    if not is_known_room:
        conn.close()
        raise HTTPException(status_code=404, detail="그룹 회의방이 아닙니다")
    persona_owner = persona_map[body.persona_name]
    if persona_owner is not None and persona_owner != room_owner:
        conn.close()
        raise HTTPException(status_code=403, detail="이 페르소나는 초대할 수 없습니다")
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
    URL 해시를 직접 편집해도 못 들어간다. 단, "내가 만든 페르소나"는 예외 —
    본인의 1:1 방은 본인에게 보인다(_can_access_persona_room).

    ★ 같은 날 추가: "단체톡방 만들기" 요청 — 계정이 직접 만든 커스텀 방도
    본인/소유자에게만 노출한다."""
    conn = get_conn()
    persona_rows = conn.execute(
        "SELECT name, group_name, owner_username, avatar_url FROM personas ORDER BY name"
    ).fetchall()
    user = getattr(request.state, "user", None)
    is_owner_request = user["is_owner"] if user else True
    username = user["username"] if user else None
    rooms = [{"room_id": GROUP_ROOM_ID, "label": "전체 채팅방", "group_name": None, "is_group_room": False, "is_mine": False}] if GROUP_ROOM_ENABLED else []

    seen_groups = []
    for r in persona_rows:
        if r["group_name"] and r["group_name"] not in seen_groups:
            seen_groups.append(r["group_name"])
    for group_name in seen_groups:
        rooms.append({
            "room_id": group_name, "label": f"👥 {group_name}",
            "group_name": None, "is_group_room": True, "is_mine": False,
        })

    custom_rows = conn.execute(
        "SELECT room_id, label, owner_username, thumbnail_url FROM custom_rooms ORDER BY created_at"
    ).fetchall()
    for cr in custom_rows:
        if is_owner_request or cr["owner_username"] == username:
            rooms.append({
                "room_id": cr["room_id"], "label": f"👥 {cr['label']}",
                "group_name": None, "is_group_room": True, "is_mine": cr["owner_username"] == username,
                "thumbnail_url": cr["thumbnail_url"],
            })

    rooms += [
        {
            "room_id": r["name"], "label": r["name"], "group_name": r["group_name"], "is_group_room": False,
            "is_mine": r["owner_username"] == username if username else False,
            "thumbnail_url": r["avatar_url"],
        }
        for r in persona_rows
        if _can_access_persona_room(r["owner_username"], username, is_owner_request)
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
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = user["is_owner"] if user else True
    # ★ 2026-08-26: list_rooms()와 같은 기준 — 소유자/본인이 아니면 페르소나
    # 1:1 방은 목록뿐 아니라 직접 조회도 막는다(해시를 직접 편집해서 들어오는
    # 우회 방지). 내가 만든 페르소나는 본인에게 허용.
    persona_owner_rows = conn.execute(
        "SELECT name, owner_username, avatar_url FROM personas"
    ).fetchall()
    persona_owner = {r["name"]: r["owner_username"] for r in persona_owner_rows}
    persona_avatars = {r["name"]: r["avatar_url"] for r in persona_owner_rows}
    persona_names = set(persona_owner)
    if room_id in persona_names:
        if not _can_access_persona_room(persona_owner[room_id], username, is_owner_request):
            conn.close()
            raise HTTPException(status_code=403, detail="다른 계정은 이 1:1 대화를 볼 수 없습니다")
    else:
        is_custom, allowed, _room_owner = _custom_room_access(conn, room_id, username, is_owner_request)
        if is_custom and not allowed:
            conn.close()
            raise HTTPException(status_code=403, detail="이 채팅방을 볼 수 없습니다")
    rows = conn.execute(
        """SELECT m.id, m.sender, m.content, m.created_at, m.reply_message_id,
                  parent.sender AS reply_sender, parent.content AS reply_content
             FROM messages m
             LEFT JOIN messages parent ON parent.id = m.reply_message_id
            WHERE m.room_id = ? AND m.id > ? ORDER BY m.id""",
        (room_id, since_id),
    ).fetchall()
    reactions = _message_reactions(conn, [r["id"] for r in rows], username)
    conn.close()
    messages = _with_sender_type(rows, persona_names, persona_avatars)
    for message in messages:
        message["reactions"] = reactions.get(message["id"], [])
    return messages


class MessageEdit(BaseModel):
    content: str


@app.put("/api/messages/{message_id}")
def edit_message(message_id: int, body: MessageEdit, request: Request):
    """"각 이용자들도 자기 메시지는 수정·삭제할 수 있게 해달라" 요청(2026-08-27)
    — 본인이 직접 보낸 메시지(페르소나 발화 제외)만 수정할 수 있다. 관리자도
    다른 사람 말을 대신 고쳐 쓸 수는 없다(삭제와 달리 수정은 "그 사람이 실제로
    한 말"을 바꾸는 것이라 본인 전용으로 좁힌다)."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="내용을 입력하세요")
    conn = get_conn()
    row = conn.execute("SELECT sender FROM messages WHERE id = ?", (message_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")
    persona_names = _persona_name_set(conn)
    if row["sender"] in persona_names or not username or row["sender"] != username:
        conn.close()
        raise HTTPException(status_code=403, detail="본인이 보낸 메시지만 수정할 수 있습니다")
    conn.execute("UPDATE messages SET content = ? WHERE id = ?", (content, message_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/messages/{message_id}")
def delete_message(message_id: int, request: Request):
    """"관리자는 메시지 삭제 권한이 있게, 각 이용자도 자기 메시지는 삭제할 수
    있게 해달라" 요청(2026-08-27) — 소유자는 아무 메시지나, 일반 사용자는
    본인이 보낸 메시지만 지울 수 있다(페르소나 발화 포함 — 소유자 전용)."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = bool(user and user["is_owner"])
    conn = get_conn()
    row = conn.execute("SELECT sender FROM messages WHERE id = ?", (message_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")
    if not (is_owner_request or (username and row["sender"] == username)):
        conn.close()
        raise HTTPException(status_code=403, detail="본인이 보낸 메시지이거나 관리자만 삭제할 수 있습니다")
    conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


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
    persona_avatars = {
        r["name"]: r["avatar_url"]
        for r in conn.execute("SELECT name, avatar_url FROM personas").fetchall()
    }
    rows = conn.execute(
        "SELECT id, room_id, sender, content, created_at FROM messages WHERE id > ? ORDER BY id",
        (since_id,),
    ).fetchall()
    conn.close()
    return _with_sender_type(rows, persona_names, persona_avatars)


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
    reply_message_id: Optional[int] = None


class MessageReactionRequest(BaseModel):
    emoji: str


@app.post("/api/messages/{message_id}/reactions")
def toggle_message_reaction(message_id: int, body: MessageReactionRequest, request: Request):
    """허용된 반응 하나를 토글한다. AI나 워커에는 어떤 실행 권한도 주지 않는다."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    if body.emoji not in REACTION_EMOJIS:
        raise HTTPException(status_code=400, detail="지원하지 않는 반응입니다")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else "user"
    is_owner_request = user["is_owner"] if user else True
    conn = get_conn()
    message = conn.execute("SELECT room_id FROM messages WHERE id = ?", (message_id,)).fetchone()
    if not message:
        conn.close()
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")
    room_id = message["room_id"]
    persona = conn.execute(
        "SELECT owner_username FROM personas WHERE name = ?", (room_id,)
    ).fetchone()
    if persona and not _can_access_persona_room(persona["owner_username"], username, is_owner_request):
        conn.close()
        raise HTTPException(status_code=403, detail="이 대화에 반응할 수 없습니다")
    if not persona and room_id != GROUP_ROOM_ID:
        is_custom, allowed, _owner = _custom_room_access(conn, room_id, username, is_owner_request)
        if is_custom and not allowed:
            conn.close()
            raise HTTPException(status_code=403, detail="이 대화에 반응할 수 없습니다")
    existing = conn.execute(
        "SELECT 1 FROM message_reactions WHERE message_id = ? AND username = ? AND emoji = ?",
        (message_id, username, body.emoji),
    ).fetchone()
    if existing:
        conn.execute(
            "DELETE FROM message_reactions WHERE message_id = ? AND username = ? AND emoji = ?",
            (message_id, username, body.emoji),
        )
    else:
        conn.execute(
            "INSERT INTO message_reactions (message_id, username, emoji, created_at) VALUES (?, ?, ?, ?)",
            (message_id, username, body.emoji, _now()),
        )
    conn.commit()
    reactions = _message_reactions(conn, [message_id], username).get(message_id, [])
    conn.close()
    return {"ok": True, "reactions": reactions}


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
    persona_rows = conn.execute("SELECT name, group_name, owner_username FROM personas").fetchall()
    all_personas = [r["name"] for r in persona_rows]
    persona_owner = {r["name"]: r["owner_username"] for r in persona_rows}
    # ★ 2026-08-26: "나 말고 다른 사람은 페르소나들과 개인 메시지 못 하게
    # 막고 단체 채팅방에서만 메시지 입력이 가능하게 해달라"는 요청 — 1:1
    # 방(room_id가 페르소나 이름과 정확히 같음)은 소유자만 쓸 수 있고, 다른
    # 계정은 전체 채팅방/그룹 회의방에서만 메시지를 보낼 수 있다. 읽기는
    # 그대로 전부 허용(공유 방 정책 유지) — 막는 건 "쓰기"뿐이다. 단, 내가
    # 만든 페르소나는 예외로 본인에게 허용한다.
    if room_id in all_personas and not _can_access_persona_room(persona_owner[room_id], sender, is_owner_request):
        conn.close()
        raise HTTPException(status_code=403, detail="이 1:1 대화를 이용할 수 없습니다")
    # ★ "단체톡방 만들기" 요청 — 커스텀 방도 방 주인/소유자만 메시지를 보낼 수 있다.
    if room_id not in all_personas and room_id != GROUP_ROOM_ID:
        is_custom, allowed, _room_owner = _custom_room_access(conn, room_id, sender, is_owner_request)
        if is_custom and not allowed:
            conn.close()
            raise HTTPException(status_code=403, detail="이 채팅방에 메시지를 보낼 수 없습니다")
    reply_message_id = None
    if msg.reply_message_id is not None:
        replied = conn.execute(
            "SELECT id FROM messages WHERE id = ? AND room_id = ?",
            (msg.reply_message_id, room_id),
        ).fetchone()
        if not replied:
            conn.close()
            raise HTTPException(status_code=400, detail="답장할 메시지를 찾을 수 없습니다")
        reply_message_id = replied["id"]
    conn.execute(
        "INSERT INTO messages (room_id, sender, content, created_at, reply_message_id) VALUES (?, ?, ?, ?, ?)",
        (room_id, sender, content, now, reply_message_id),
    )
    if room_id == GROUP_ROOM_ID:
        # ★ "@이름"으로 특정 인물을 지목하면 그 인물만 응답, 아무도 안 부르면
        # 방에 있는 페르소나 전원이 한 번씩 응답한다(서로 이어서 계속 대화하는
        # 자동 체이닝은 폭주 방지를 위해 하지 않음 — README 로드맵 참고).
        # ★ 2026-08-25: reply_to(메시지 탭해서 답장)가 있으면 @멘션보다 우선해서
        # 그 한 명만 응답 — "한명한테 말하는데 모든 인물이 다 답변해서 정신없다"
        # 는 요청.
        mentioned = _mentioned_personas(content, all_personas)
        targets = _default_targets(conn, room_id, all_personas, mentioned, msg.reply_to, content)
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
        mentioned = _mentioned_personas(content, group_members)
        targets = _default_targets(conn, room_id, group_members, mentioned, msg.reply_to, content)
    if not is_owner_request:
        # 1:1 방은 이미 위에서 막았지만, 단체/그룹 회의방에서는 다른 계정도
        # 메시지를 보낼 수 있다 — 그 경우에도 손동주는 응답 대상에서 뺀다.
        targets = [t for t in targets if t not in OWNER_ONLY_PERSONAS]
        # ★ 유이(UI_DEV_PERSONAS)는 손동주처럼 무조건 막지는 않는다 — 소유자가
        # ui_dev_grants에 등록해준 계정만 예외적으로 응답을 받을 수 있다.
        if any(t in UI_DEV_PERSONAS for t in targets):
            granted = conn.execute(
                "SELECT 1 FROM ui_dev_grants WHERE username = ?", (sender,)
            ).fetchone()
            if not granted:
                targets = [t for t in targets if t not in UI_DEV_PERSONAS]
    for persona_name in targets:
        conn.execute(
            "INSERT INTO pending_turns (persona_name, room_id, status, created_at) VALUES (?, ?, 'pending', ?)",
            (persona_name, room_id, now),
        )
    conn.commit()
    conn.close()
    return {"ok": True, "notified": targets}


@app.get("/api/admin/users")
def admin_list_users(request: Request):
    """소유자 전용 — 계정 목록과 각자의 유이(UI 개발자) 권한 부여 여부, 가입
    정보(가입일·로그인 방식·메시지 수)를 같이 내려준다. 프론트의 권한 관리
    패널(owner에게만 보임)이 쓴다.
    ★ "관리자가 사용자권한관리 버튼 누르면 가입한 사람들 정보를 볼 수 있게
    해달라" 요청(2026-08-26)."""
    _require_owner(request)
    conn = get_conn()
    users = conn.execute(
        "SELECT username, is_owner, created_at, google_sub, kakao_id FROM users ORDER BY username"
    ).fetchall()
    granted = {r["username"] for r in conn.execute("SELECT username FROM ui_dev_grants").fetchall()}
    message_counts = {
        r["sender"]: r["cnt"]
        for r in conn.execute("SELECT sender, COUNT(*) AS cnt FROM messages GROUP BY sender").fetchall()
    }
    conn.close()
    result = []
    for r in users:
        login_method = "구글" if r["google_sub"] else "카카오" if r["kakao_id"] else "아이디/비밀번호"
        result.append({
            "username": r["username"], "is_owner": bool(r["is_owner"]),
            "ui_dev_granted": r["username"] in granted,
            "created_at": r["created_at"], "login_method": login_method,
            "message_count": message_counts.get(r["username"], 0),
        })
    return result


@app.post("/api/admin/ui_dev_grants/{username}")
def admin_grant_ui_dev(username: str, request: Request):
    _require_owner(request)
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 계정입니다")
    conn.execute(
        "INSERT OR IGNORE INTO ui_dev_grants (username, granted_at) VALUES (?, ?)",
        (username, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/admin/ui_dev_grants/{username}")
def admin_revoke_ui_dev(username: str, request: Request):
    _require_owner(request)
    conn = get_conn()
    conn.execute("DELETE FROM ui_dev_grants WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/worker/pending")
def worker_pending(authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    conn = get_conn()
    row = conn.execute(
        "SELECT id, persona_name, room_id, rerouted FROM pending_turns WHERE status = 'pending' ORDER BY id LIMIT 1"
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
        "rerouted": bool(row["rerouted"]),
        "context": [dict(r) for r in reversed(context_rows)],
    }


@app.get("/api/worker/room_candidates")
def worker_room_candidates(room_id: str, authorization: Optional[str] = Header(None)):
    """이 room_id에서 응답 가능한 페르소나 후보 전원을 준다 — post_message()가
    targets를 정할 때 쓰는 것과 같은 세 갈래(전체 채팅방/1:1 방/그룹·커스텀
    방)를 그대로 따른다. ★ "담당 아닌 페르소나가 답하는 버그" 요청(2026-08-26)
    — 워커가 "이 방에 누가 더 있는지" 알아야 담당자 재검토를 할 수 있다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    persona_rows = conn.execute("SELECT name, group_name, owner_username FROM personas ORDER BY name").fetchall()
    persona_names = {r["name"] for r in persona_rows}
    if room_id == GROUP_ROOM_ID:
        candidates = sorted(persona_names)
    elif room_id in persona_names:
        candidates = [room_id]
    else:
        candidates = _group_members(conn, room_id, persona_rows)
    conn.close()
    return {"candidates": candidates}


class RedirectTurn(BaseModel):
    turn_id: int
    persona_name: str


class WorkerAnnouncement(BaseModel):
    room_id: str
    content: str
    dedupe_key: str


@app.post("/api/worker/announcements")
def worker_announcement(body: WorkerAnnouncement, authorization: Optional[str] = Header(None)):
    """주석가 한 명이 분석을 소개하고 나머지 그룹원의 토론을 시작한다."""
    _check_worker_auth(authorization)
    room_id = body.room_id.strip()
    content = body.content.strip()
    dedupe_key = body.dedupe_key.strip()
    if not room_id or not content or not dedupe_key:
        raise HTTPException(status_code=400, detail="방·내용·중복 방지 키가 필요합니다")

    conn = get_conn()
    persona_rows = conn.execute(
        "SELECT name, group_name, owner_username FROM personas ORDER BY name"
    ).fetchall()
    targets = _group_members(conn, room_id, persona_rows)
    if not targets:
        conn.close()
        raise HTTPException(status_code=404, detail="구성원이 있는 그룹방을 찾지 못했습니다")

    conn.execute(
        """CREATE TABLE IF NOT EXISTS automation_announcements (
               dedupe_key TEXT PRIMARY KEY,
               message_id INTEGER NOT NULL,
               created_at TEXT NOT NULL
           )"""
    )
    commentators = [name for name in targets if name != "손무"]
    if not commentators:
        conn.close()
        raise HTTPException(status_code=409, detail="분석을 소개할 전통 주석가가 없습니다")
    digest = hashlib.sha256(dedupe_key.encode("utf-8")).digest()
    sender = commentators[int.from_bytes(digest[:4], "big") % len(commentators)]
    existing = conn.execute(
        "SELECT message_id FROM automation_announcements WHERE dedupe_key = ?", (dedupe_key,)
    ).fetchone()
    marker = f"[automation:{dedupe_key}]"
    if not existing:
        legacy = conn.execute(
            "SELECT id, content FROM messages WHERE room_id = ? AND content LIKE ? ORDER BY id DESC LIMIT 1",
            (room_id, f"%{marker}%"),
        ).fetchone()
        if legacy:
            cleaned = legacy["content"].replace(f"\n\n{marker}", "").replace(marker, "").strip()
            conn.execute(
                "UPDATE messages SET content = ?, sender = ? WHERE id = ?",
                (cleaned, sender, legacy["id"]),
            )
            conn.execute(
                "INSERT OR IGNORE INTO automation_announcements (dedupe_key, message_id, created_at) VALUES (?, ?, ?)",
                (dedupe_key, legacy["id"], _now()),
            )
            conn.commit()
            existing = {"message_id": legacy["id"]}
    if existing:
        conn.execute(
            "UPDATE messages SET sender = ? WHERE id = ? AND sender = ?",
            (sender, existing["message_id"], APP_USERNAME),
        )
        conn.commit()
        conn.close()
        return {
            "ok": True, "duplicate": True, "message_id": existing["message_id"],
            "announcer": sender, "notified": [],
        }

    now = _now()
    cursor = conn.execute(
        "INSERT INTO messages (room_id, sender, content, created_at) VALUES (?, ?, ?, ?)",
        (room_id, sender, content, now),
    )
    message_id = cursor.lastrowid
    conn.execute(
        "INSERT INTO automation_announcements (dedupe_key, message_id, created_at) VALUES (?, ?, ?)",
        (dedupe_key, message_id, now),
    )
    notified = [persona_name for persona_name in targets if persona_name != sender]
    for persona_name in notified:
        conn.execute(
            "INSERT INTO pending_turns (persona_name, room_id, status, created_at) VALUES (?, ?, 'pending', ?)",
            (persona_name, room_id, now),
        )
    conn.commit()
    conn.close()
    return {
        "ok": True, "duplicate": False, "message_id": message_id,
        "announcer": sender, "notified": notified,
    }


@app.post("/api/worker/redirect_turn")
def worker_redirect_turn(body: RedirectTurn, authorization: Optional[str] = Header(None)):
    """대기 중인 턴의 담당자를 바꾼다 — 워커가 "이름이 안 불렸을 때 직전
    화자로 이어감" 판단이 이번엔 틀렸다고 재검토한 경우에만 부른다.
    rerouted=1로 표시해 같은 턴이 다시 왕복하지 않게 한다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    row = conn.execute("SELECT status FROM pending_turns WHERE id = ?", (body.turn_id,)).fetchone()
    if not row or row["status"] != "pending":
        conn.close()
        raise HTTPException(status_code=404, detail="이미 처리됐거나 없는 턴입니다")
    conn.execute(
        "UPDATE pending_turns SET persona_name = ?, rerouted = 1 WHERE id = ?",
        (body.persona_name, body.turn_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


class WorkerResult(BaseModel):
    turn_id: int
    reply: Optional[str] = None
    error: Optional[str] = None


class WorkerMediaApply(BaseModel):
    target_type: str
    target_id: str
    url: str


class WorkerImageJobResult(BaseModel):
    job_id: int
    url: Optional[str] = None
    error: Optional[str] = None


@app.get("/api/worker/image_jobs/pending")
def worker_pending_image_job(authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    conn = get_conn()
    # 워커가 API 호출 도중 종료되면 processing에 영구 고정되지 않도록 15분 지난
    # 작업은 재시도한다. 같은 프롬프트라 결과 품질은 유지되고 기존 avatar는
    # 완료 전까지 덮어쓰지 않는다.
    stale_before = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=15)
    ).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE persona_image_jobs SET status='pending', started_at=NULL WHERE status='processing' AND started_at < ?",
        (stale_before,),
    )
    row = conn.execute(
        "SELECT id, persona_name, prompt FROM persona_image_jobs WHERE status = 'pending' ORDER BY id LIMIT 1"
    ).fetchone()
    if not row:
        conn.close()
        return None
    changed = conn.execute(
        "UPDATE persona_image_jobs SET status='processing', started_at=? WHERE id=? AND status='pending'",
        (_now(), row["id"]),
    ).rowcount
    conn.commit()
    conn.close()
    return dict(row) if changed else None


@app.post("/api/worker/image_jobs/complete")
def worker_complete_image_job(body: WorkerImageJobResult, authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    if body.url and not re.fullmatch(r"/uploads/[A-Za-z0-9_.-]+", body.url):
        raise HTTPException(status_code=400, detail="허용되지 않은 이미지 URL입니다")
    if body.url and not (UPLOADS_DIR / Path(body.url).name).is_file():
        raise HTTPException(status_code=400, detail="생성 이미지 파일을 찾을 수 없습니다")
    conn = get_conn()
    row = conn.execute(
        "SELECT persona_name, status FROM persona_image_jobs WHERE id = ?", (body.job_id,)
    ).fetchone()
    if not row or row["status"] != "processing":
        conn.close()
        raise HTTPException(status_code=404, detail="처리 중인 이미지 작업이 아닙니다")
    if body.url:
        conn.execute("UPDATE personas SET avatar_url = ? WHERE name = ?", (body.url, row["persona_name"]))
        conn.execute(
            "UPDATE persona_image_jobs SET status='done', result_url=?, completed_at=? WHERE id=?",
            (body.url, _now(), body.job_id),
        )
    else:
        conn.execute(
            "UPDATE persona_image_jobs SET status='failed', error=?, completed_at=? WHERE id=?",
            ((body.error or "이미지 생성 실패")[:1000], _now(), body.job_id),
        )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/worker/apply_media")
def worker_apply_media(body: WorkerMediaApply, authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    if not re.fullmatch(r"/uploads/[A-Za-z0-9_.-]+", body.url):
        raise HTTPException(status_code=400, detail="허용되지 않은 이미지 URL입니다")
    conn = get_conn()
    if body.target_type == "persona":
        conn.execute("UPDATE personas SET avatar_url = ? WHERE name = ?", (body.url, body.target_id))
    elif body.target_type == "room":
        conn.execute("UPDATE custom_rooms SET thumbnail_url = ? WHERE room_id = ?", (body.url, body.target_id))
    else:
        conn.close()
        raise HTTPException(status_code=400, detail="허용되지 않은 적용 대상입니다")
    conn.commit()
    conn.close()
    return {"ok": True}


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
    profile_summary: Optional[str] = None


@app.post("/api/worker/sync_persona")
def sync_persona(persona: PersonaSync, authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    conn = get_conn()
    existing = conn.execute("SELECT admin_description, admin_group_name FROM personas WHERE name = ?", (persona.name,)).fetchone()
    admin_description = existing["admin_description"] if existing else None
    admin_group_name = existing["admin_group_name"] if existing else None
    effective_prompt = _with_admin_override(persona.system_prompt, admin_description)
    effective_summary = admin_description or persona.profile_summary
    effective_group = (admin_group_name or None) if admin_group_name is not None else persona.group_name
    conn.execute(
        """
        INSERT INTO personas (name, notion_page_id, system_prompt, group_name, profile_summary, synced_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            notion_page_id = excluded.notion_page_id,
            system_prompt = excluded.system_prompt,
            group_name = excluded.group_name,
            profile_summary = excluded.profile_summary,
            synced_at = excluded.synced_at
        """,
        (persona.name, persona.notion_page_id, effective_prompt, effective_group,
         effective_summary, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/worker/user_personas")
def worker_user_personas(authorization: Optional[str] = Header(None)):
    """워커가 사용자가 직접 만든 페르소나(owner_username IS NOT NULL)의
    system_prompt를 가져가 자기 캐시에 합칠 때 쓴다(2026-08-26 — Notion을
    거치지 않는 페르소나이므로 별도 엔드포인트가 필요)."""
    _check_worker_auth(authorization)
    conn = get_conn()
    rows = conn.execute(
        "SELECT name, system_prompt FROM personas WHERE owner_username IS NOT NULL"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


class AdminReportPost(BaseModel):
    content: str


@app.post("/api/worker/post_admin_report")
def worker_post_admin_report(body: AdminReportPost, authorization: Optional[str] = Header(None)):
    """워커가 다른 사용자들의 피드백을 훑어 정리한 보고를 툴파관리자 명의로
    소유자에게 보낸다(2026-08-26). 사용자 메시지에 대한 응답이 아니라 워커가
    스스로 먼저 말을 거는 경우라 pending_turns를 안 거치고 바로 메시지만
    쌓는다 — 툴파관리자 1:1 방은 다른 Notion 페르소나와 동일하게 소유자만
    볼 수 있어(owner_username이 NULL이라 _can_access_persona_room이 그렇게
    처리) 자동으로 소유자 전용 알림함이 된다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (room_id, sender, content, created_at) VALUES (?, ?, ?, ?)",
        (ADMIN_PERSONA_NAME, ADMIN_PERSONA_NAME, body.content, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/worker/group_rooms")
def worker_group_rooms(authorization: Optional[str] = Header(None)):
    """공지사항 동기화(`sync_room_notices`)가 훑어야 할 "여러 사람이 보는 방"
    전체 목록 — Notion 그룹 회의방 + 모든 커스텀 방(2026-08-26)."""
    _check_worker_auth(authorization)
    conn = get_conn()
    group_rows = conn.execute(
        "SELECT DISTINCT group_name FROM personas WHERE group_name IS NOT NULL"
    ).fetchall()
    custom_rows = conn.execute("SELECT room_id, label FROM custom_rooms").fetchall()
    conn.close()
    rooms = [{"room_id": r["group_name"], "label": r["group_name"]} for r in group_rows]
    rooms += [{"room_id": r["room_id"], "label": r["label"]} for r in custom_rows]
    return rooms


@app.get("/api/worker/room_messages")
def worker_room_messages(room_id: str, since_id: int = 0, authorization: Optional[str] = Header(None)):
    _check_worker_auth(authorization)
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, sender, content, created_at FROM messages WHERE room_id = ? AND id > ? ORDER BY id",
        (room_id, since_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/worker/room_notice")
def worker_get_room_notice_watermark(room_id: str, authorization: Optional[str] = Header(None)):
    """공지 워터마크 조회 — "이 방은 어느 메시지까지 이미 공지 요약에
    반영했는지" 알아야 다음 동기화에서 그 이후 메시지만 본다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    row = conn.execute("SELECT last_message_id FROM room_notices WHERE room_id = ?", (room_id,)).fetchone()
    conn.close()
    return {"last_message_id": row["last_message_id"] if row else 0}


class RoomNoticePost(BaseModel):
    room_id: str
    content: Optional[str] = None
    last_message_id: int


@app.post("/api/worker/room_notice")
def worker_post_room_notice(body: RoomNoticePost, authorization: Optional[str] = Header(None)):
    """워커가 요약한 공지를 저장한다. content가 없으면(그 구간이 잡담뿐이라
    "업데이트 없음"으로 판단된 경우) 기존 공지는 그대로 두고 워터마크만
    전진시킨다 — 카톡 공지가 조용한 날이라고 사라지지 않는 것과 같다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    if body.content:
        conn.execute(
            """
            INSERT INTO room_notices (room_id, content, last_message_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(room_id) DO UPDATE SET
                content = excluded.content,
                last_message_id = excluded.last_message_id,
                updated_at = excluded.updated_at
            """,
            (body.room_id, body.content, body.last_message_id, _now()),
        )
    else:
        conn.execute(
            """
            INSERT INTO room_notices (room_id, content, last_message_id, updated_at)
            VALUES (?, NULL, ?, ?)
            ON CONFLICT(room_id) DO UPDATE SET last_message_id = excluded.last_message_id
            """,
            (body.room_id, body.last_message_id, _now()),
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
