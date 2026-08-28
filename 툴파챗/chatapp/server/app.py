"""툴파챗 서버 (이 Mac에서 실행, Cloudflare Tunnel로 노출).

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
import json
import os
import re
import secrets
import sqlite3
import urllib.parse
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from pywebpush import WebPushException, webpush

from server import auth, oauth
from server.db import get_conn, init_db

BASE_DIR = Path(__file__).resolve().parent.parent
# ★ "업데이트할 때마다 페이지를 재시작(새로고침)해야 하는 게 맞냐" 요청
# (2026-08-28) — 서버 프로세스(app.py 등 백엔드 코드)가 바뀌면 재시작 시
# 이 값이 새로 생성돼서 바뀐다. static/*(프론트 HTML·JS·CSS)는 서버를
# 재시작하지 않아도 디스크에서 매 요청 새로 읽히므로(StaticFiles가 자체
# 캐시를 안 함, Cache-Control: no-cache까지 강제) 파일을 고치기만 해도
# 즉시 반영된다 — 다만 이미 열려 있는 브라우저 탭은 그 사실을 스스로 알
# 방법이 없어서 새로고침 전까진 예전 JS를 계속 쓴다. GET /api/version이
# "서버 부팅 id + 정적 파일 중 가장 최근 수정 시각"을 합쳐서 내려주면,
# 프론트가 주기적으로 이 값을 확인해 바뀌었을 때만 "새 버전이 있어요"
# 배너를 띄워 사용자가 놓치지 않고 새로고침할 수 있다.
SERVER_BOOT_ID = os.urandom(4).hex()
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")
APP_USERNAME = os.environ.get("APP_USERNAME", "")
# ★ "채팅방에 새 메시지 있으면 사용자들한테도 알람이 가게 해달라" 요청
# (2026-08-27) — 브라우저 Web Push. 서버(server/.venv)에 pywebpush를 따로
# 설치했다(공용 anaconda 환경에 설치했다가 cryptography 버전 충돌로
# pyopenssl이 깨진 적이 있어, 이후 이 서버만 독립 venv로 분리함 — README
# 참고). 개인키는 리포에 커밋하지 않고 파일 경로로만 읽는다.
VAPID_PRIVATE_KEY_FILE = os.environ.get("VAPID_PRIVATE_KEY_FILE", "")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "")


def push_enabled():
    # ★ pywebpush의 webpush(vapid_private_key=...)는 PEM 텍스트가 아니라
    # "파일 경로 문자열"을 받아야 한다(os.path.isfile로 직접 판별해서 내부적
    # 으로 Vapid.from_file을 호출함) — PEM을 미리 읽어서 넘기면
    # Vapid.from_string이 그 텍스트를 DER로 오인해 파싱 에러가 난다.
    return bool(
        VAPID_PRIVATE_KEY_FILE and os.path.exists(VAPID_PRIVATE_KEY_FILE)
        and VAPID_PUBLIC_KEY and VAPID_CLAIM_EMAIL
    )
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
MAX_CONTEXT_MESSAGES = 20

SESSION_COOKIE_NAME = "tulpa_session"
SESSION_COOKIE_MAX_AGE = auth.SESSION_MAX_AGE_SECONDS  # 180일
USERNAME_RE = re.compile(r"^[A-Za-z0-9_가-힣]{2,20}$")

# ★ 인증 없이 접근 가능한 경로 — 로그인 자체를 하려면 "/"와 정적 파일, 그리고
# 회원가입/로그인 API는 인증 이전에 열려 있어야 한다. /api/whoami는 로그인
# 여부를 프론트가 확인하는 용도라 항상 응답한다(그 자체로 정보 노출 없음).
PUBLIC_PATHS = {
    "/", "/api/whoami", "/api/auth/signup", "/api/auth/login", "/api/auth/logout", "/api/version",
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
BACKGROUND_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
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


app = FastAPI(title="툴파챗")
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


# ★ "처음 일반 사용자 입장에서 프로그램개발그룹이랑 병법가그룹이 보이는데,
# 처음 사용자한테는 아무 채팅방도 안 보이는 게 맞는 것 같다" 요청
# (2026-08-28). Notion 페르소나의 group_name으로 자동 생성되는 "그룹
# 회의방"은 기본적으로 관리자가 큐레이션한 콘텐츠라 기본 접근은 전체
# 관리자로 제한한다.
def _is_notion_group_room(conn, room_id):
    return bool(conn.execute(
        "SELECT 1 FROM personas WHERE group_name = ? LIMIT 1", (room_id,)
    ).fetchone())


# ★ 같은 날 후속 요청: "그룹 회의방에서 사람 초대하려는데 왜 일반 사용자는
# 목록에 없지" — 관리자만 보이게 막고 나니, 관리자가 그 방에 특정 사람을
# 데려오고 싶어도 방법이 없었다. 커스텀 방과 똑같이 room_user_invites를
# 재사용해서(스키마에 room_id에 대한 FK 제약이 없어 커스텀 방이 아닌
# room_id로도 그냥 저장된다) 관리자가 초대한 사람은 그 그룹 회의방에도
# 들어올 수 있게 한다 — 방 "주인"이 없는 콘텐츠라 초대는 관리자만 할 수
# 있다(커스텀 방처럼 "방 주인"이 따로 초대하는 경우가 없음).
def _group_room_allowed(conn, room_id, username, is_owner_request):
    if is_owner_request:
        return True
    if not username:
        return False
    return bool(conn.execute(
        "SELECT 1 FROM room_user_invites WHERE room_id = ? AND username = ?", (room_id, username)
    ).fetchone())


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


def _with_sender_type(rows, persona_names, persona_avatars=None, human_profiles=None):
    """메시지 발신자 종류와 프로필 이미지·표시 이름을 함께 내려준다.
    페르소나는 avatar_url만(이름은 프론트 displayName()이 "(가상)"을 붙여
    표시), 사람은 avatar_url·display_name 둘 다(2026-08-28 — "자기 이름·
    프로필사진 바꿀 수 있게 해달라" 요청. display_name이 없으면 프론트가
    sender(아이디)로 대체 표시)."""
    persona_avatars = persona_avatars or {}
    human_profiles = human_profiles or {}
    result = []
    for r in rows:
        sender = r["sender"]
        is_persona = sender in persona_names
        human = human_profiles.get(sender, {}) if not is_persona else {}
        result.append({
            **dict(r),
            "is_persona": is_persona,
            "avatar_url": persona_avatars.get(sender) if is_persona else human.get("avatar_url"),
            "display_name": human.get("display_name"),
            # ★ 2026-08-28: row에 is_system 컬럼이 없는 옛 쿼리에서도 안전하게
            # 기본값 False로 떨어지게 dict.get 사용(SELECT에 안 넣은 곳도 있음).
            "is_system": bool(dict(r).get("is_system", 0)),
        })
    return result


def _human_profiles(conn):
    return {
        r["username"]: {"display_name": r["display_name"], "avatar_url": r["avatar_url"]}
        for r in conn.execute("SELECT username, display_name, avatar_url FROM users").fetchall()
    }


def _insert_system_notice(conn, room_id, content):
    """★ "초대가 되면 그 톡방에 '누가 초대되었습니다'라고 구분선 같은 걸
    만들어달라" 요청(2026-08-28) — 사람/페르소나 발화가 아닌 서버 알림
    메시지를 남긴다. sender는 화면에 안 쓰이지만(프론트가 is_system이면
    content만 가운데 구분선으로 그림) 그래도 사람이 알아볼 수 있는 값을
    넣어둔다."""
    conn.execute(
        "INSERT INTO messages (room_id, sender, content, created_at, is_system) VALUES (?, 'system', ?, ?, 1)",
        (room_id, content, _now()),
    )


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
            "SELECT id, username, password_hash, salt, is_owner, display_name, avatar_url FROM users WHERE username = ?",
            (body.username.strip(),),
        ).fetchone()
        if not row or not auth.verify_password(body.password, row["salt"], row["password_hash"]):
            raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다")
        token = auth.create_session(conn, row["id"])
    finally:
        conn.close()
    response.set_cookie(SESSION_COOKIE_NAME, token, max_age=SESSION_COOKIE_MAX_AGE, httponly=True, samesite="lax")
    return {
        "ok": True, "username": row["username"], "is_owner": bool(row["is_owner"]),
        "display_name": row["display_name"], "avatar_url": row["avatar_url"],
    }


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


def _finish_oauth_login(provider, external_id, display_name, kakao_tokens=None):
    """구글/카카오 로그인 콜백의 공통 마무리 — 이미 연결된 계정이면 그대로
    로그인, 처음이면 새 로컬 계정을 만들어 연결한다(비밀번호는 무작위로
    채워두고 실제로 쓰이지 않음 — 이 계정은 소셜 로그인으로만 들어옴).

    kakao_tokens: talk_message 동의를 받았을 때만 실제 값이 들어있는
    {"access_token","refresh_token","expires_in"} — "카톡으로 로그인한
    사람한테는 카톡 알람이 가게" 요청(2026-08-27). 매 로그인마다 최신
    토큰으로 갱신 저장한다."""
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
        if kakao_tokens and kakao_tokens.get("access_token"):
            expires_at = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(seconds=kakao_tokens.get("expires_in") or 0)
            ).isoformat()
            conn.execute(
                "UPDATE users SET kakao_access_token = ?, "
                "kakao_refresh_token = COALESCE(?, kakao_refresh_token), "
                "kakao_token_expires_at = ? WHERE id = ?",
                (kakao_tokens["access_token"], kakao_tokens.get("refresh_token"), expires_at, user_id),
            )
            conn.commit()
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
    return _finish_oauth_login("kakao", profile["external_id"], profile["name"], kakao_tokens=profile)


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
    # ★ "페르소나 프로필 보기 권한" 요청(2026-08-28) — 관리 패널이 페르소나별로
    # 누가 프로필을 볼 수 있는지 렌더할 수 있게 같이 내려준다.
    grants_by_persona = {}
    for r in conn.execute("SELECT persona_name, username FROM persona_view_grants").fetchall():
        grants_by_persona.setdefault(r["persona_name"], []).append(r["username"])
    conn.close()
    result = [dict(r) for r in rows]
    for r in result:
        r["view_grants"] = grants_by_persona.get(r["name"], [])
    return result


@app.delete("/api/admin/personas/{name}")
def admin_delete_persona(name: str, request: Request):
    """"관리자가 툴파 삭제도 가능하게 해달라" 요청(2026-08-28). 사용자가
    직접 만든 페르소나는 이미 본인이 지울 수 있었지만(delete_my_persona),
    공용 Notion 페르소나를 포함해 아무 페르소나나 지우는 건 관리자만 할 수
    있다. delete_my_persona와 같은 cascade 목록에 persona_image_jobs만
    더한다(그쪽은 이미지 생성 이력이라 지금까진 안 지웠는데, 관리자
    삭제에서는 실수 요청도 아니므로 깔끔하게 정리한다)."""
    _require_owner(request)
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM personas WHERE name = ?", (name,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    conn.execute("DELETE FROM personas WHERE name = ?", (name,))
    conn.execute("DELETE FROM messages WHERE room_id = ?", (name,))
    conn.execute("DELETE FROM pending_turns WHERE room_id = ?", (name,))
    conn.execute("DELETE FROM room_invites WHERE persona_name = ?", (name,))
    conn.execute("DELETE FROM persona_image_jobs WHERE persona_name = ?", (name,))
    conn.execute("DELETE FROM persona_view_grants WHERE persona_name = ?", (name,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/admin/personas/{name}/view_grants/{username}")
def admin_grant_persona_view(name: str, username: str, request: Request):
    """"권민석 프로필설정이 너무 적나라한데 일반 사용자도 다 보이는 거야"
    요청(2026-08-28) — 관리자가 특정 사용자에게 특정(관리자 소유) 페르소나
    프로필 열람을 예외적으로 허용한다(ui_dev_grants와 같은 패턴)."""
    _require_owner(request)
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM personas WHERE name = ?", (name,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
    if not conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 계정입니다")
    conn.execute(
        "INSERT OR IGNORE INTO persona_view_grants (persona_name, username, granted_at) VALUES (?, ?, ?)",
        (name, username, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/admin/personas/{name}/view_grants/{username}")
def admin_revoke_persona_view(name: str, username: str, request: Request):
    _require_owner(request)
    conn = get_conn()
    conn.execute(
        "DELETE FROM persona_view_grants WHERE persona_name = ? AND username = ?", (name, username)
    )
    conn.commit()
    conn.close()
    return {"ok": True}


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


class DirectRoomCreate(BaseModel):
    target_type: str
    target_id: str


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


@app.post("/api/direct-rooms")
def create_or_get_direct_room(body: DirectRoomCreate, request: Request):
    """친구 목록에서 사람 또는 페르소나와 시작하는 확장 가능한 1:1 방.
    처음에는 둘만 참여하지만 custom_rooms를 사용하므로 방 주인이 다른 사람이나
    페르소나를 초대하면 같은 대화 기록을 유지한 채 그룹방으로 발전한다."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    requester = user["username"]
    target_type = body.target_type.strip().lower()
    target_id = body.target_id.strip()
    if target_type not in {"user", "persona"} or not target_id:
        raise HTTPException(status_code=400, detail="대화 상대가 올바르지 않습니다")
    conn = get_conn()
    if target_type == "user":
        if target_id == requester:
            conn.close()
            raise HTTPException(status_code=400, detail="자기 자신과는 1:1 방을 만들 수 없습니다")
        target = conn.execute(
            "SELECT username, display_name FROM users WHERE username=?", (target_id,)
        ).fetchone()
        if not target:
            conn.close()
            raise HTTPException(status_code=404, detail="존재하지 않는 사용자입니다")
        pair = sorted((requester, target_id))
        direct_key = f"user:{pair[0]}:{pair[1]}"
        label = target["display_name"] or target_id
    else:
        target = conn.execute(
            "SELECT name, owner_username FROM personas WHERE name=?", (target_id,)
        ).fetchone()
        if not target:
            conn.close()
            raise HTTPException(status_code=404, detail="존재하지 않는 페르소나입니다")
        if target["owner_username"] not in (None, requester) and not user["is_owner"]:
            conn.close()
            raise HTTPException(status_code=403, detail="이 페르소나와 대화할 수 없습니다")
        direct_key = f"persona:{requester}:{target_id}"
        label = target_id
    existing = conn.execute(
        "SELECT room_id, label FROM custom_rooms WHERE direct_key=?", (direct_key,)
    ).fetchone()
    if existing:
        conn.close()
        return {"ok": True, "room_id": existing["room_id"], "label": existing["label"], "created": False}
    room_id = f"{CUSTOM_ROOM_ID_PREFIX}{uuid.uuid4().hex[:10]}"
    try:
        conn.execute(
            "INSERT INTO custom_rooms(room_id,label,owner_username,created_at,direct_key) VALUES (?,?,?,?,?)",
            (room_id, label, requester, _now(), direct_key),
        )
        if target_type == "user":
            conn.execute(
                "INSERT INTO room_user_invites(room_id,username,invited_at) VALUES (?,?,?)",
                (room_id, target_id, _now()),
            )
        else:
            conn.execute(
                "INSERT INTO room_invites(room_id,persona_name,invited_at) VALUES (?,?,?)",
                (room_id, target_id, _now()),
            )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        existing = conn.execute(
            "SELECT room_id, label FROM custom_rooms WHERE direct_key=?", (direct_key,)
        ).fetchone()
        conn.close()
        if existing:
            return {"ok": True, "room_id": existing["room_id"], "label": existing["label"], "created": False}
        raise
    conn.close()
    return {"ok": True, "room_id": room_id, "label": label, "created": True}


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


def _require_personal_background_room_access(conn, room_id, username, is_owner_request):
    """개인 배경을 설정하려는 방이 실제로 이 계정에 보이는 방인지 확인한다.
    메시지 조회와 같은 접근 규칙을 적용해 임의 room_id에 파일 설정을 쌓거나
    초대받지 않은 방의 존재를 확인하지 못하게 한다."""
    if room_id == GROUP_ROOM_ID:
        return
    persona = conn.execute(
        "SELECT owner_username FROM personas WHERE name=?", (room_id,)
    ).fetchone()
    if persona:
        if not _can_access_persona_room(persona["owner_username"], username, is_owner_request):
            raise HTTPException(status_code=403, detail="이 채팅방을 볼 수 없습니다")
        return
    is_custom, allowed, _room_owner = _custom_room_access(conn, room_id, username, is_owner_request)
    if is_custom:
        if not allowed:
            raise HTTPException(status_code=403, detail="이 채팅방을 볼 수 없습니다")
        return
    if _is_notion_group_room(conn, room_id):
        if not _group_room_allowed(conn, room_id, username, is_owner_request):
            raise HTTPException(status_code=403, detail="이 채팅방을 볼 수 없습니다")
        return
    raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없습니다")


@app.get("/api/rooms/{room_id}/my-background")
def get_my_room_background(room_id: str, request: Request):
    """현재 로그인 계정의 이 방 배경만 반환한다. 방 공용 정보에는 섞지 않는다."""
    user = getattr(request.state, "user", None)
    if not user:
        return {"image_url": None}
    conn = get_conn()
    _require_personal_background_room_access(conn, room_id, user["username"], user["is_owner"])
    row = conn.execute(
        "SELECT image_url FROM user_room_backgrounds WHERE username=? AND room_id=?",
        (user["username"], room_id),
    ).fetchone()
    conn.close()
    return {"image_url": row["image_url"] if row else None}


@app.post("/api/rooms/{room_id}/my-background")
async def upload_my_room_background(room_id: str, request: Request, file: UploadFile = File(...)):
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    conn = get_conn()
    _require_personal_background_room_access(conn, room_id, user["username"], user["is_owner"])
    ext = Path(file.filename or "").suffix.lower()
    if ext not in BACKGROUND_UPLOAD_EXTENSIONS:
        conn.close()
        raise HTTPException(status_code=400, detail="배경은 JPG, PNG, GIF, WebP만 지원합니다")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        conn.close()
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다(10MB 제한)")
    filename = f"room-bg-{uuid.uuid4().hex}{ext}"
    (UPLOADS_DIR / filename).write_bytes(data)
    url = f"/uploads/{filename}"
    conn.execute(
        """INSERT INTO user_room_backgrounds(username,room_id,image_url,updated_at)
           VALUES(?,?,?,?)
           ON CONFLICT(username,room_id) DO UPDATE SET
             image_url=excluded.image_url, updated_at=excluded.updated_at""",
        (user["username"], room_id, url, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "image_url": url}


@app.delete("/api/rooms/{room_id}/my-background")
def reset_my_room_background(room_id: str, request: Request):
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    conn = get_conn()
    _require_personal_background_room_access(conn, room_id, user["username"], user["is_owner"])
    conn.execute(
        "DELETE FROM user_room_backgrounds WHERE username=? AND room_id=?",
        (user["username"], room_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "image_url": None}


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

# 소유자가 채팅에서 이 문구를 직접 보낸 경우에만 기존 손자병법 자동 해석
# 파이프라인을 시작한다. 일반 사용자의 같은 문장은 평범한 대화로만 취급하고
# 실제 작업 큐를 만들지 않는다. 실행 자체는 로컬 워커의 고정 스크립트가 맡고,
# AI가 채팅 내용으로 임의 명령이나 경로를 구성하지 않는다.
SUNZI_PIPELINE_PERSONA_NAME = "손무"
SUNZI_PIPELINE_COMMAND_RE = re.compile(
    r"손자병법.{0,20}다음\s*구절.{0,20}(?:해석|분석|최신화)(?:해|해줘|해주세요|하라|진행)?"
)


def _is_sunzi_pipeline_command(content: str) -> bool:
    return bool(SUNZI_PIPELINE_COMMAND_RE.search(content.replace("_", " ")))

# ★ 2026-08-26: "다른 사람들의 요구·요청사항·개선사항을 모아서 나한테
# 보고하는 에이전틱 툴파" 요청 — worker/persona_worker.py의 ADMIN_PERSONA_NAME과
# 이름이 같아야 한다. 아직은 "수집·보고"만 하고 실제 코드 수정 권한은 없다
# (유이처럼 파일 수정 권한을 줄지는 소유자와 상의 후 결정 예정).
ADMIN_PERSONA_NAME = "툴파관리자"
QA_PERSONA_NAME = "QA요정"
QA_REPORTER_USERNAME = "qqq"


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


@app.get("/api/version")
def get_version():
    """프론트가 폴링해서 배포 이후 값이 바뀌었으면 새로고침을 유도한다
    (SERVER_BOOT_ID 정의부의 설명 참고). 로그인 여부와 무관하게 누구나
    확인할 수 있어도 되는 값이라 인증을 요구하지 않는다."""
    static_dir = BASE_DIR / "static"
    mtimes = [
        f.stat().st_mtime for f in (static_dir / "index.html", static_dir / "chat.js", static_dir / "style.css")
        if f.exists()
    ]
    static_stamp = int(max(mtimes)) if mtimes else 0
    return {"version": f"{SERVER_BOOT_ID}-{static_stamp}"}


@app.get("/api/whoami")
def whoami(request: Request):
    """프론트엔드가 로그인 여부·쓰기 가능 여부를 미리 알아서, 비로그인
    방문자에겐 로그인/가입 화면을, 공유 링크 읽기 전용 방문자·로그인은
    했지만 읽기 전용인 방문자에겐 입력창을 숨긴 채팅 화면을 보여줄 수 있게
    한다. share_guest=False, logged_in=False인 조합만 진짜 "로그인이
    필요한" 상태다(공유 링크 방문자는 share_guest=True라 로그인 없이도
    채팅 화면을 그대로 봄)."""
    user = getattr(request.state, "user", None)
    display_name = None
    avatar_url = None
    if user:
        conn = get_conn()
        row = conn.execute(
            "SELECT display_name, avatar_url FROM users WHERE username = ?", (user["username"],)
        ).fetchone()
        conn.close()
        if row:
            display_name, avatar_url = row["display_name"], row["avatar_url"]
    return {
        "can_write": getattr(request.state, "can_write", True),
        "logged_in": user is not None,
        "username": user["username"] if user else None,
        "is_owner": bool(user["is_owner"]) if user else False,
        "share_guest": getattr(request.state, "share_guest", False),
        # ★ "자기 이름·프로필사진 바꿀 수 있게 해달라" 요청(2026-08-28) —
        # 로그인 직후 프론트가 내 표시 이름/아바타를 바로 알아야 헤더에 반영할
        # 수 있다.
        "display_name": display_name,
        "avatar_url": avatar_url,
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


@app.get("/api/users")
def list_users_public(request: Request):
    """★ "친구 목록에 일반 가입자들도 뜨게 해달라" 요청(2026-08-28) — 페르소나
    말고 실제 가입 계정도 친구 탭에 보여준다. /api/admin/users(소유자 전용,
    유이 권한 부여 여부 등 관리 정보 포함)와 달리 이건 아이디·가입일만 내려주고
    로그인한 계정이면 누구나 볼 수 있다. 공유 링크 읽기 전용 방문자는 실제
    계정이 아니므로 제외한다."""
    user = getattr(request.state, "user", None)
    if user is None and not getattr(request.state, "can_write", False):
        raise HTTPException(status_code=403, detail="로그인이 필요합니다")
    exclude = user["username"] if user else None
    conn = get_conn()
    rows = conn.execute(
        "SELECT username, is_owner, created_at, display_name, avatar_url FROM users ORDER BY created_at"
    ).fetchall()
    favorites = {
        row["friend_username"] for row in conn.execute(
            "SELECT friend_username FROM friend_favorites WHERE username = ?", (exclude,)
        ).fetchall()
    } if exclude else set()
    conn.close()
    return [dict(r) | {"is_favorite": r["username"] in favorites} for r in rows if r["username"] != exclude]


@app.put("/api/friends/{friend_username}/favorite")
def add_friend_favorite(friend_username: str, request: Request):
    """로그인한 사용자 본인에게만 보이는 친구 즐겨찾기를 저장한다."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    if friend_username == user["username"]:
        raise HTTPException(status_code=400, detail="자기 자신은 즐겨찾기할 수 없습니다")
    conn = get_conn()
    exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (friend_username,)).fetchone()
    if not exists:
        conn.close()
        raise HTTPException(status_code=404, detail="친구를 찾을 수 없습니다")
    conn.execute(
        "INSERT OR IGNORE INTO friend_favorites (username, friend_username, created_at) VALUES (?, ?, ?)",
        (user["username"], friend_username, datetime.datetime.now(datetime.timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "is_favorite": True}


@app.delete("/api/friends/{friend_username}/favorite")
def remove_friend_favorite(friend_username: str, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    conn = get_conn()
    conn.execute(
        "DELETE FROM friend_favorites WHERE username = ? AND friend_username = ?",
        (user["username"], friend_username),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "is_favorite": False}


class MyProfileUpdate(BaseModel):
    display_name: str


@app.put("/api/me")
def update_my_profile(body: MyProfileUpdate, request: Request):
    """★ "카톡이나 구글로 로그인한 사람은 자기 이름 수정할 수 있게, 다른
    일반 사용자도 마찬가지로" 요청(2026-08-28) — 로그인한 계정이면 누구나
    (소유자 여부·가입 방식과 무관하게) 자기 표시 이름을 바꿀 수 있다.
    username(로그인 아이디)은 안 바뀐다 — 화면에 보이는 이름만."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    name = body.display_name.strip()
    if not (1 <= len(name) <= 30):
        raise HTTPException(status_code=400, detail="이름은 1~30자로 입력하세요")
    conn = get_conn()
    conn.execute("UPDATE users SET display_name = ? WHERE username = ?", (name, user["username"]))
    conn.commit()
    conn.close()
    return {"ok": True, "display_name": name}


@app.post("/api/me/avatar")
async def upload_my_avatar(request: Request, file: UploadFile = File(...)):
    """내 프로필 사진 변경 — 저장·검증 로직은 /api/upload와 동일(같은
    UPLOADS_DIR·확장자·용량 제한 재사용, /api/admin/personas/{name}/avatar와
    같은 패턴)."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 이미지 형식입니다: {ext or '(확장자 없음)'}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다(10MB 제한)")
    filename = f"user_{uuid.uuid4().hex}{ext}"
    (UPLOADS_DIR / filename).write_bytes(data)
    url = f"/uploads/{filename}"
    conn = get_conn()
    conn.execute("UPDATE users SET avatar_url = ? WHERE username = ?", (url, user["username"]))
    conn.commit()
    conn.close()
    return {"ok": True, "avatar_url": url}


@app.delete("/api/me/avatar")
def delete_my_avatar(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    conn = get_conn()
    conn.execute("UPDATE users SET avatar_url = NULL WHERE username = ?", (user["username"],))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/persona_profiles")
def list_persona_profiles(request: Request):
    """"툴파들의 성격을 간단히 확인할 수 있는 페이지" 요청(2026-08-26) —
    공개 페르소나(Notion 동기화분) 전부 + 내가 만든 개인 페르소나만 보여준다
    (다른 사람의 개인 페르소나는 그 사람 1:1 방처럼 비공개 유지).

    ★ "권민석 프로필설정이 너무 적나라한데 일반 사용자도 다 보이는 거야?
    실제 친군데 실친이 들어와서 봤을 때 오해의 소지가 있을 것 같다" 요청
    (2026-08-28) — 관리자가 만든 페르소나(owner_username=NULL)는 실제
    지인을 본뜬 경우가 많아 기본적으로 관리자만 프로필을 본다.
    persona_view_grants에 명시적으로 등록된 사용자만 예외."""
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = bool(user and user["is_owner"])
    conn = get_conn()
    rows = conn.execute(
        "SELECT name, owner_username, description, profile_summary, avatar_url FROM personas ORDER BY name"
    ).fetchall()
    granted = {
        r["persona_name"] for r in conn.execute(
            "SELECT persona_name FROM persona_view_grants WHERE username = ?", (username,)
        ).fetchall()
    } if username else set()
    conn.close()
    result = []
    for r in rows:
        if r["owner_username"] is not None:
            if r["owner_username"] != username and not is_owner_request:
                continue
        elif not is_owner_request and r["name"] not in granted:
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
    소유자로 별도 제한).

    ★ "가상 인물뿐만 아니라 실제 사용자도 초대할 수 있게 해달라" 요청
    (2026-08-27) — 방 주인·소유자 외에도 room_user_invites에 초대된
    계정이면 접근(읽기·쓰기)을 허용한다."""
    row = conn.execute("SELECT owner_username FROM custom_rooms WHERE room_id = ?", (room_id,)).fetchone()
    if not row:
        return False, True, None
    allowed = is_owner_request or row["owner_username"] == username
    if not allowed and username:
        invited = conn.execute(
            "SELECT 1 FROM room_user_invites WHERE room_id = ? AND username = ?", (room_id, username)
        ).fetchone()
        allowed = bool(invited)
    return True, allowed, row["owner_username"]


def _promote_direct_room(conn, room_id):
    """1:1 방에 세 번째 구성원이 추가되면 중복 방 키를 해제하고 그룹 표시로 바꾼다."""
    row = conn.execute(
        "SELECT label, direct_key FROM custom_rooms WHERE room_id=?", (room_id,)
    ).fetchone()
    if row and row["direct_key"]:
        conn.execute(
            "UPDATE custom_rooms SET direct_key=NULL, label=? WHERE room_id=?",
            (f"{row['label']} 외 그룹", room_id),
        )


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
    cur = conn.execute(
        "INSERT OR IGNORE INTO room_invites (room_id, persona_name, invited_at) VALUES (?, ?, ?)",
        (room_id, body.persona_name, _now()),
    )
    if cur.rowcount:  # 이미 있던 초대면(중복 클릭 등) 알림을 또 남기지 않는다
        _promote_direct_room(conn, room_id)
        _insert_system_notice(conn, room_id, f"{body.persona_name}님이 초대되었습니다")
    conn.commit()
    members = _group_members(conn, room_id, persona_rows)
    conn.close()
    return {"ok": True, "members": members}


def _room_manage_context(conn, room_id, requester, is_owner_request):
    """방 멤버 관리(초대·조회·내보내기)에 필요한 공통 판단 — 커스텀 방과
    그룹 회의방 둘 다 지원한다("그룹 회의방에서 사람 초대하려는데 왜 목록에
    없지" 요청, 2026-08-28). 반환: (관리 가능한 방인가(존재+권한),
    owner_username — 그룹 회의방은 주인이 없어 None)."""
    row = conn.execute("SELECT owner_username FROM custom_rooms WHERE room_id = ?", (room_id,)).fetchone()
    if row:
        owner_username = row["owner_username"]
        return (is_owner_request or owner_username == requester), owner_username
    if _is_notion_group_room(conn, room_id):
        return is_owner_request, None
    return False, None


@app.get("/api/rooms/{room_id}/user_members")
def get_room_user_members(room_id: str, request: Request):
    """이 방에 초대된 실제 사용자 목록과, 초대 가능한 나머지 계정 목록을
    준다. ★ "가상 인물뿐만 아니라 실제 사용자도 초대할 수 있게 해달라"
    요청(2026-08-27) — 커스텀 방은 방 주인(또는 소유자)만 조회할 수 있다.
    그룹 회의방은 "방 주인"이 없는 콘텐츠라 관리자만 관리(조회·초대)할
    수 있다(_room_manage_context)."""
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = bool(user and user["is_owner"])
    conn = get_conn()
    allowed, owner_username = _room_manage_context(conn, room_id, username, is_owner_request)
    if not allowed:
        conn.close()
        raise HTTPException(status_code=403, detail="이 방을 관리할 권한이 없습니다")
    members = [
        r["username"] for r in conn.execute(
            "SELECT username FROM room_user_invites WHERE room_id = ?", (room_id,)
        ).fetchall()
    ]
    if owner_username and owner_username not in members:
        members.insert(0, owner_username)
    user_rows = conn.execute(
        "SELECT username, display_name FROM users ORDER BY username"
    ).fetchall()
    all_users = [r["username"] for r in user_rows]
    user_labels = {r["username"]: (r["display_name"] or r["username"]) for r in user_rows}
    available = [u for u in all_users if u not in members]
    conn.close()
    # ★ "관리자가 채팅방에서 내보내는 기능" 요청(2026-08-28) — 프론트가 방
    # 주인 칩에는 내보내기 버튼을 안 그리도록(방 주인은 내보낼 수 없음,
    # kick_room_member 참고) owner_username을 같이 내려준다. 그룹 회의방은
    # owner_username이 null이라 모든 칩에 내보내기 버튼이 붙는다.
    return {
        "members": members, "available": available, "owner_username": owner_username,
        "user_labels": user_labels,
    }


class InviteUserRequest(BaseModel):
    username: str


@app.post("/api/rooms/{room_id}/invite_user")
def invite_user_to_room(room_id: str, body: InviteUserRequest, request: Request):
    """실제 사용자를 방에 초대한다. ★ 2026-08-27 요청. 커스텀 방은 방 주인
    (또는 소유자)만, 그룹 회의방은 관리자만 초대할 수 있다
    (_room_manage_context) — 초대된 계정은 이후 이 방을 보고, 메시지도
    보낼 수 있다(_custom_room_access/_group_room_allowed가 room_user_invites도
    확인)."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = bool(user and user["is_owner"])
    conn = get_conn()
    allowed, _owner_username = _room_manage_context(conn, room_id, username, is_owner_request)
    if not allowed:
        conn.close()
        raise HTTPException(status_code=403, detail="이 방에 초대할 권한이 없습니다")
    target = conn.execute("SELECT username FROM users WHERE username = ?", (body.username,)).fetchone()
    if not target:
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 계정입니다")
    cur = conn.execute(
        "INSERT OR IGNORE INTO room_user_invites (room_id, username, invited_at) VALUES (?, ?, ?)",
        (room_id, body.username, _now()),
    )
    if cur.rowcount:  # 이미 초대돼 있었으면(중복 클릭 등) 알림을 또 남기지 않는다
        _promote_direct_room(conn, room_id)
        _insert_system_notice(conn, room_id, f"{body.username}님이 초대되었습니다")
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/rooms/{room_id}/members/{username}")
def kick_room_member(room_id: str, username: str, request: Request):
    """"관리자에게 채팅방에서 내보내는 기능이 있으면 좋겠다" 요청
    (2026-08-28). 본인이 스스로 나가는 leave_room과 달리, 대상이 원치
    않아도 관리자(전체) 또는 그 방 주인이 강제로 뺄 수 있다(커스텀 방).
    그룹 회의방은 주인이 없어 관리자만(_room_manage_context). 방 주인은
    room_user_invites에 아예 없으므로(get_room_user_members가 목록엔
    끼워 넣어 보여줄 뿐) 대상이 될 수 없다 — 방을 통째로 없애고 싶으면
    delete_room을 쓰라고 안내한다."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    requester = user["username"] if user else None
    is_owner_request = bool(user and user["is_owner"])
    conn = get_conn()
    allowed, owner_username = _room_manage_context(conn, room_id, requester, is_owner_request)
    if not allowed:
        conn.close()
        raise HTTPException(status_code=403, detail="이 방의 주인이나 관리자만 내보낼 수 있습니다")
    if owner_username and username == owner_username:
        conn.close()
        raise HTTPException(status_code=400, detail="방 주인은 내보낼 수 없습니다 — 방 삭제를 사용하세요")
    cur = conn.execute(
        "DELETE FROM room_user_invites WHERE room_id = ? AND username = ?", (room_id, username)
    )
    if not cur.rowcount:
        conn.close()
        raise HTTPException(status_code=404, detail="이 방의 멤버가 아닙니다")
    _insert_system_notice(conn, room_id, f"{username}님이 방에서 내보내졌습니다")
    conn.commit()
    conn.close()
    return {"ok": True}


def _delete_custom_room(conn, room_id):
    """커스텀 방과 거기 딸린 데이터를 전부 지운다 — 나가기(방 주인이 자기
    방을 나가는 경우)와 관리자 강제 삭제가 이 함수를 공유한다. SQLite는
    이 프로젝트에서 PRAGMA foreign_keys를 켜지 않아서(server/db.py) 스키마의
    ON DELETE CASCADE가 실제로는 동작하지 않는다 — 관련 테이블을 전부
    손으로 나열해서 지워야 한다."""
    conn.execute("DELETE FROM custom_rooms WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM messages WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM pending_turns WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_invites WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_user_invites WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_notices WHERE room_id = ?", (room_id,))
    conn.execute("DELETE FROM room_restart_notice WHERE room_id = ?", (room_id,))


@app.post("/api/rooms/{room_id}/leave")
def leave_room(room_id: str, request: Request):
    """"채팅방 나가기 기능 있게 해달라" 요청(2026-08-28). 내가 만든 방이
    아니라 초대받아 들어간 방만 "나간다"(room_user_invites에서 내 행만
    지움 — 방은 다른 멤버에게 그대로 남는다). 내가 만든 방은 넘겨줄 다음
    주인이 없어서 "나가기"가 곧 "방 폐쇄"와 같다 — 그 경우엔 DELETE
    /api/rooms/{room_id}(관리자 강제 삭제와 같은 함수)를 쓰라고 안내한다."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    username = user["username"]
    conn = get_conn()
    row = conn.execute("SELECT owner_username FROM custom_rooms WHERE room_id = ?", (room_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 채팅방입니다")
    if row["owner_username"] == username:
        conn.close()
        raise HTTPException(status_code=400, detail="내가 만든 방은 나가기 대신 삭제를 사용하세요")
    cur = conn.execute(
        "DELETE FROM room_user_invites WHERE room_id = ? AND username = ?", (room_id, username)
    )
    if not cur.rowcount:
        conn.close()
        raise HTTPException(status_code=403, detail="이 채팅방의 멤버가 아닙니다")
    _insert_system_notice(conn, room_id, f"{username}님이 나갔습니다")
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/rooms/{room_id}")
def delete_room(room_id: str, request: Request):
    """"관리자는 채팅방 삭제할 수 있게 해달라" 요청(2026-08-28). 방 주인
    본인(자기 방을 완전히 없애고 싶을 때) 또는 전체 관리자만 지울 수
    있다 — 초대받은 일반 멤버는 나가기(leave_room)만 가능."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = bool(user and user["is_owner"])
    conn = get_conn()
    row = conn.execute("SELECT owner_username FROM custom_rooms WHERE room_id = ?", (room_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 채팅방입니다")
    if not (is_owner_request or row["owner_username"] == username):
        conn.close()
        raise HTTPException(status_code=403, detail="이 방의 주인이나 관리자만 삭제할 수 있습니다")
    _delete_custom_room(conn, room_id)
    conn.commit()
    conn.close()
    return {"ok": True}


class RoomRename(BaseModel):
    label: str


@app.put("/api/rooms/{room_id}")
def rename_room(room_id: str, body: RoomRename, request: Request):
    """방 이름 수정 — "왼쪽으로 밀면 삭제나 수정 나오는 기능" 요청
    (2026-08-28)의 "수정"에 해당. 방 주인 또는 관리자만 가능."""
    if not getattr(request.state, "can_write", True):
        raise HTTPException(status_code=403, detail="읽기 전용 계정입니다")
    label = body.label.strip()
    if not label or len(label) > 30:
        raise HTTPException(status_code=400, detail="방 이름은 1~30자로 입력하세요")
    user = getattr(request.state, "user", None)
    username = user["username"] if user else None
    is_owner_request = bool(user and user["is_owner"])
    conn = get_conn()
    row = conn.execute("SELECT owner_username FROM custom_rooms WHERE room_id = ?", (room_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 채팅방입니다")
    if not (is_owner_request or row["owner_username"] == username):
        conn.close()
        raise HTTPException(status_code=403, detail="이 방의 주인이나 관리자만 수정할 수 있습니다")
    conn.execute("UPDATE custom_rooms SET label = ? WHERE room_id = ?", (label, room_id))
    conn.commit()
    conn.close()
    return {"ok": True, "label": label}


# ══════════════════════════════════════════════════════════════
# ★ "채팅방에 새 메시지 있으면 사용자들한테도 알람이 가게 해달라" +
# "카카오로 로그인한 사람한테는 카톡 알람이 가게" 요청(2026-08-27).
# 대상은 커스텀 방(방 주인 + room_user_invites로 초대된 계정) — Notion
# 그룹 회의방은 로그인만 하면 전원 공유라 매 메시지마다 전체 알림을 보내면
# 스팸이 되므로 대상에서 뺐다. 카카오 로그인 + talk_message 토큰이 있는
# 계정은 카톡 "나에게 보내기"로, 그 외(또는 카톡 전송 실패)는 웹 푸시로.
# ══════════════════════════════════════════════════════════════

@app.get("/api/push/public_key")
def push_public_key():
    return {"enabled": push_enabled(), "public_key": VAPID_PUBLIC_KEY}


class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: dict


@app.post("/api/push/subscribe")
def push_subscribe(body: PushSubscribeRequest, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    p256dh = body.keys.get("p256dh")
    auth_key = body.keys.get("auth")
    if not p256dh or not auth_key:
        raise HTTPException(status_code=400, detail="구독 정보가 올바르지 않습니다")
    conn = get_conn()
    conn.execute(
        """INSERT INTO push_subscriptions (username, endpoint, p256dh, auth, created_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(endpoint) DO UPDATE SET username = excluded.username,
               p256dh = excluded.p256dh, auth = excluded.auth""",
        (user["username"], body.endpoint, p256dh, auth_key, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


@app.post("/api/push/unsubscribe")
def push_unsubscribe(body: PushUnsubscribeRequest):
    conn = get_conn()
    conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (body.endpoint,))
    conn.commit()
    conn.close()
    return {"ok": True}


def _send_web_push_to_user(conn, username, title, body_text, url):
    if not push_enabled():
        return
    rows = conn.execute(
        "SELECT id, endpoint, p256dh, auth FROM push_subscriptions WHERE username = ?", (username,)
    ).fetchall()
    for row in rows:
        try:
            webpush(
                subscription_info={
                    "endpoint": row["endpoint"],
                    "keys": {"p256dh": row["p256dh"], "auth": row["auth"]},
                },
                data=json.dumps({"title": title, "body": body_text, "url": url}),
                vapid_private_key=VAPID_PRIVATE_KEY_FILE,
                vapid_claims={"sub": VAPID_CLAIM_EMAIL},
            )
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                conn.execute("DELETE FROM push_subscriptions WHERE id = ?", (row["id"],))
            else:
                print(f"⚠️ 웹 푸시 실패({username}): {exc}")


def _send_kakao_alert_to_user(conn, username, title, body_text, url):
    """카톡 "나에게 보내기"로 보낼 수 있으면 보내고 True, 아니면(토큰 없음·
    갱신 실패·전송 실패) False — 호출부가 웹 푸시로 대체할 수 있게."""
    row = conn.execute(
        "SELECT kakao_access_token, kakao_refresh_token, kakao_token_expires_at FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not row or not row["kakao_access_token"]:
        return False
    access_token = row["kakao_access_token"]
    needs_refresh = True
    if row["kakao_token_expires_at"]:
        try:
            needs_refresh = (
                datetime.datetime.fromisoformat(row["kakao_token_expires_at"])
                <= datetime.datetime.now(datetime.timezone.utc)
            )
        except ValueError:
            needs_refresh = True
    if needs_refresh:
        if not row["kakao_refresh_token"]:
            return False
        try:
            refreshed = oauth.kakao_refresh_token(row["kakao_refresh_token"])
            access_token = refreshed["access_token"]
            new_expires_at = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(seconds=refreshed.get("expires_in") or 0)
            ).isoformat()
            conn.execute(
                "UPDATE users SET kakao_access_token = ?, "
                "kakao_refresh_token = COALESCE(?, kakao_refresh_token), "
                "kakao_token_expires_at = ? WHERE username = ?",
                (access_token, refreshed.get("refresh_token"), new_expires_at, username),
            )
            conn.commit()
        except oauth.OAuthError as exc:
            print(f"⚠️ 카카오 토큰 갱신 실패({username}): {exc}")
            return False
    try:
        oauth.send_kakao_memo(access_token, f"{title}\n{body_text}", url)
        return True
    except oauth.OAuthError as exc:
        print(f"⚠️ 카톡 알림 전송 실패({username}): {exc}")
        return False


def notify_room_members_new_message(conn, room_id, sender, title, body_text):
    """방(room_id)의 실제 사용자 멤버(발신자 제외)에게 새 메시지를 알린다.

    ★ 실측(2026-08-28): "일반 사용자들한테는 메시지 알람이 불가능한가?"
    문의로 확인한 버그 — 원래는 커스텀 방만 대상이었는데, 같은 날 앞서
    그룹 회의방에도 실제 사람을 초대할 수 있게 확장(room_user_invites
    재사용)하면서 이 함수를 안 고쳐서, 그룹 회의방에 초대된 사람은
    room_user_invites에 엄연히 들어 있는데도 알림을 하나도 못 받고
    있었다. 커스텀 방이 아니면 그룹 회의방인지 확인해서 초대된 사람만
    챙긴다(관리자는 굳이 알림 대상에 안 넣는다 — 그룹 회의방은 페르소나
    발화가 잦아 관리자에게 매번 알리면 스팸이 된다는 기존 결정 유지,
    room_user_invites에 아무도 없으면 전체 채팅방 등은 여전히 대상이
    아니다)."""
    row = conn.execute("SELECT owner_username FROM custom_rooms WHERE room_id = ?", (room_id,)).fetchone()
    if row:
        members = {row["owner_username"]} if row["owner_username"] else set()
    elif _is_notion_group_room(conn, room_id):
        members = set()
    else:
        return
    members |= {
        r["username"] for r in conn.execute(
            "SELECT username FROM room_user_invites WHERE room_id = ?", (room_id,)
        ).fetchall()
    }
    members.discard(sender)
    if not members:
        return
    base_url = oauth.PUBLIC_BASE_URL or ""
    url = f"{base_url}/#room={urllib.parse.quote(room_id, safe='')}"
    for username in members:
        if not _send_kakao_alert_to_user(conn, username, title, body_text, url):
            _send_web_push_to_user(conn, username, title, body_text, url)


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
    # ★ "실제 사용자도 초대할 수 있게 해달라" 요청(2026-08-27) — 초대된
    # 계정에게도 방 목록에 그 방이 보여야 들어갈 수 있다(직접 URL을 몰라도).
    # room_user_invites는 커스텀 방·그룹 회의방 구분 없이 room_id로만
    # 저장되므로 둘 다 이 집합 하나로 판단한다.
    invited_room_ids = {
        r["room_id"] for r in conn.execute(
            "SELECT room_id FROM room_user_invites WHERE username = ?", (username,)
        ).fetchall()
    } if username else set()
    # ★ "처음 사용자한테는 아무 채팅방도 안 보이는 게 맞다" 요청(2026-08-28)
    # — 그룹 회의방은 기본적으로 관리자만 목록에서 본다(_is_notion_group_room
    # 정의부 설명 참고). ★ 같은 날 후속 요청: "그룹 회의방에서 사람 초대하려는데
    # 왜 목록에 없지" — 관리자가 특정 사람을 그 방에 초대(room_user_invites)
    # 했으면 그 사람에게도 보인다.
    for group_name in seen_groups:
        if is_owner_request or group_name in invited_room_ids:
            rooms.append({
                "room_id": group_name, "label": f"👥 {group_name}",
                "group_name": None, "is_group_room": True, "is_mine": False,
            })

    custom_rows = conn.execute(
        "SELECT room_id, label, owner_username, thumbnail_url, direct_key FROM custom_rooms ORDER BY created_at"
    ).fetchall()
    for cr in custom_rows:
        if is_owner_request or cr["owner_username"] == username or cr["room_id"] in invited_room_ids:
            custom_label = cr["label"]
            if cr["direct_key"] and cr["direct_key"].startswith("user:") and username:
                participants = cr["direct_key"].split(":", 2)[1:]
                if username in participants:
                    other_username = participants[1] if participants[0] == username else participants[0]
                    other = conn.execute(
                        "SELECT display_name FROM users WHERE username=?", (other_username,)
                    ).fetchone()
                    custom_label = (other["display_name"] if other else None) or other_username
            rooms.append({
                "room_id": cr["room_id"], "label": f"👥 {custom_label}",
                "group_name": None, "is_group_room": True, "is_mine": cr["owner_username"] == username,
                "thumbnail_url": cr["thumbnail_url"], "is_direct": bool(cr["direct_key"]),
                "direct_type": cr["direct_key"].split(":", 1)[0] if cr["direct_key"] else None,
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
        read = conn.execute(
            "SELECT last_message_id FROM room_read_state WHERE username=? AND room_id=?",
            (username or "user", room["room_id"]),
        ).fetchone()
        room["last_read_id"] = read["last_message_id"] if read else 0
    conn.close()
    return rooms


@app.get("/api/messages")
def get_messages(request: Request, room_id: str = GROUP_ROOM_ID, since_id: int = 0, count_only: bool = False):
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
        # ★ "처음 사용자한테는 아무 채팅방도 안 보이는 게 맞다" 요청
        # (2026-08-28) — 그룹 회의방은 목록뿐 아니라 직접 조회도 관리자·
        # 초대받은 사람만 되게 막는다(해시 직접 편집 우회 방지, list_rooms와
        # 같은 기준. _group_room_allowed가 관리자 여부까지 판단하므로 이미
        # 위에서 걸러진 is_owner_request와 별개로 초대 여부를 확인).
        if (
            not is_custom and room_id != GROUP_ROOM_ID and _is_notion_group_room(conn, room_id)
            and not _group_room_allowed(conn, room_id, username, is_owner_request)
        ):
            conn.close()
            raise HTTPException(status_code=403, detail="이 채팅방을 볼 수 없습니다")
    # ★ "채팅방에서 안 읽은 메시지 개수를 방 목록에서도 확인되게 해달라"
    # 요청(2026-08-28) — 안읽음 자체는 기존처럼 클라이언트 localStorage가
    # 기준(last_read_id)이지만, "이 방에 그 id 이후 메시지가 몇 개인지"는
    # 서버만 셀 수 있다. 방 목록을 그릴 때마다 방마다 이 엔드포인트를
    # count_only=true로 불러 가벼운 COUNT만 받는다(전체 메시지 본문을
    # 내려받지 않아 오래된 방도 가볍다) — 별도의 "읽음 상태" 테이블을
    # 서버에 새로 두지 않고 기존 접근 제어를 그대로 재사용한다.
    if count_only:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE room_id = ? AND id > ?", (room_id, since_id)
        ).fetchone()["n"]
        conn.close()
        return {"count": count}
    rows = conn.execute(
        """SELECT m.id, m.sender, m.content, m.created_at, m.reply_message_id, m.is_system,
                  parent.sender AS reply_sender, parent.content AS reply_content
             FROM (SELECT * FROM messages
                    WHERE room_id = ? AND id > ? ORDER BY id DESC LIMIT 500) m
             LEFT JOIN messages parent ON parent.id = m.reply_message_id
            ORDER BY m.id""",
        (room_id, since_id),
    ).fetchall()
    reactions = _message_reactions(conn, [r["id"] for r in rows], username)
    human_profiles = _human_profiles(conn)
    conn.close()
    messages = _with_sender_type(rows, persona_names, persona_avatars, human_profiles)
    for message in messages:
        message["reactions"] = reactions.get(message["id"], [])
        if message.get("reply_sender"):
            message["reply_is_persona"] = message["reply_sender"] in persona_names
            reply_profile = human_profiles.get(message["reply_sender"], {})
            message["reply_display_name"] = reply_profile.get("display_name") or message["reply_sender"]
    return messages


class ReadStateUpdate(BaseModel):
    room_id: str
    last_message_id: int


@app.put("/api/read-state")
def update_read_state(body: ReadStateUpdate, request: Request):
    """계정별 읽음 위치를 서버에 저장해 브라우저와 기기가 달라도 동기화한다."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    if body.last_message_id < 0:
        raise HTTPException(status_code=400, detail="잘못된 메시지 ID입니다")
    conn = get_conn()
    conn.execute(
        """INSERT INTO room_read_state(username, room_id, last_message_id, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(username, room_id) DO UPDATE SET
             last_message_id=MAX(room_read_state.last_message_id, excluded.last_message_id),
             updated_at=excluded.updated_at""",
        (user["username"], body.room_id, body.last_message_id, _now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


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
        "SELECT id, room_id, sender, content, created_at, is_system FROM messages WHERE id > ? ORDER BY id",
        (since_id,),
    ).fetchall()
    human_profiles = _human_profiles(conn)
    conn.close()
    return _with_sender_type(rows, persona_names, persona_avatars, human_profiles)


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


class QaResolutionRequest(BaseModel):
    source_message_id: int
    summary: str


@app.post("/api/admin/qa-resolution")
def post_qa_resolution(body: QaResolutionRequest, request: Request):
    """관리자가 QA 제보를 해결한 뒤, 제보가 올라온 방에서 QA요정 명의로
    원 제보자에게 결과를 알린다. AI 실행이나 파일 권한 없이 DB에 정해진
    형식의 메시지만 추가하는 소유자 전용 경로다."""
    user = getattr(request.state, "user", None)
    if not user or not user["is_owner"]:
        raise HTTPException(status_code=403, detail="관리자만 해결 알림을 보낼 수 있습니다")
    summary = body.summary.strip()
    if not summary or len(summary) > 500:
        raise HTTPException(status_code=400, detail="해결 내용을 1~500자로 입력해주세요")
    conn = get_conn()
    source = conn.execute(
        "SELECT id, sender, room_id FROM messages WHERE id=?", (body.source_message_id,)
    ).fetchone()
    if not source:
        conn.close()
        raise HTTPException(status_code=404, detail="원본 QA 메시지를 찾을 수 없습니다")
    content = f"@{source['sender']} 제보해주신 문제를 관리자가 해결했습니다. {summary}"
    cursor = conn.execute(
        "INSERT INTO messages(sender, content, created_at, room_id, reply_message_id) VALUES (?, ?, ?, ?, ?)",
        ("QA요정", content, _now(), source["room_id"], source["id"]),
    )
    conn.commit()
    message_id = cursor.lastrowid
    conn.close()
    return {"ok": True, "message_id": message_id, "room_id": source["room_id"]}


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
        # ★ "처음 사용자한테는 아무 채팅방도 안 보이는 게 맞다" 요청
        # (2026-08-28) — 그룹 회의방은 읽기뿐 아니라 쓰기도 관리자·초대받은
        # 사람만.
        if (
            not is_custom and _is_notion_group_room(conn, room_id)
            and not _group_room_allowed(conn, room_id, sender, is_owner_request)
        ):
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
    message_cursor = conn.execute(
        "INSERT INTO messages (room_id, sender, content, created_at, reply_message_id) VALUES (?, ?, ?, ?, ?)",
        (room_id, sender, content, now, reply_message_id),
    )
    source_message_id = message_cursor.lastrowid
    # qqq가 QA요정과 점검하며 남긴 내용은 AI 분류·30분 배치를 거치지 않고
    # 즉시 관리자 전용 툴파관리자 방으로 원문 전달한다. 요약 누락을 막고,
    # source_message_id UNIQUE 테이블로 같은 원문을 재처리해도 한 번만 보고한다.
    if sender == QA_REPORTER_USERNAME and room_id == QA_PERSONA_NAME:
        relay_claim = conn.execute(
            "INSERT OR IGNORE INTO qa_feedback_reports(source_message_id,reported_at) VALUES (?,?)",
            (source_message_id, now),
        )
        if relay_claim.rowcount:
            relay_content = (
                f"📋 QA요정 전달\n{sender}님이 QA 점검 중 의견을 남겼습니다.\n\n"
                f"{content}\n\n원문: QA요정 방 메시지 #{source_message_id}"
            )
            relay_cursor = conn.execute(
                "INSERT INTO messages(room_id,sender,content,created_at) VALUES (?,?,?,?)",
                (ADMIN_PERSONA_NAME, QA_PERSONA_NAME, relay_content, now),
            )
            conn.execute(
                "UPDATE qa_feedback_reports SET report_message_id=? WHERE source_message_id=?",
                (relay_cursor.lastrowid, source_message_id),
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
    # "손자병법 다음 구절 해석해"는 소유자가 직접 입력한 문장 자체를 이번
    # 한 건의 명시 승인으로 본다. 여러 페르소나가 같은 작업을 중복 시작하지
    # 않도록 손무 한 명에게만 결정론적 실행 턴을 배정한다.
    if is_owner_request and _is_sunzi_pipeline_command(content):
        if SUNZI_PIPELINE_PERSONA_NAME in all_personas:
            targets = [SUNZI_PIPELINE_PERSONA_NAME]
        else:
            targets = []
            conn.execute(
                "INSERT INTO messages (room_id, sender, content, created_at) VALUES (?, ?, ?, ?)",
                (room_id, "system", "손무 페르소나를 찾지 못해 손자병법 파이프라인을 시작하지 못했습니다.", now),
            )
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
            "INSERT INTO pending_turns (persona_name, room_id, status, created_at, source_message_id) VALUES (?, ?, 'pending', ?, ?)",
            (persona_name, room_id, now, source_message_id),
        )
    conn.commit()
    preview = content[:80] + ("…" if len(content) > 80 else "")
    notify_room_members_new_message(conn, room_id, sender, f"{sender}", preview)
    conn.commit()  # notify_room_members_new_message이 만료 구독 정리 등으로 DB에 쓸 수 있음
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
    stale_before = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)
    ).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE pending_turns SET status='pending', started_at=NULL "
        "WHERE status='processing' AND started_at < ?",
        (stale_before,),
    )
    row = conn.execute(
        "SELECT id, persona_name, room_id, rerouted, created_at, restart_notice_sent, source_message_id "
        "FROM pending_turns WHERE status = 'pending' ORDER BY id LIMIT 1"
    ).fetchone()
    if not row:
        conn.close()
        return None
    claimed = conn.execute(
        "UPDATE pending_turns SET status='processing', started_at=? WHERE id=? AND status='pending'",
        (_now(), row["id"]),
    ).rowcount
    if not claimed:
        conn.commit()
        conn.close()
        return None
    context_rows = conn.execute(
        "SELECT sender, content FROM messages WHERE room_id = ? ORDER BY id DESC LIMIT ?",
        (row["room_id"], MAX_CONTEXT_MESSAGES),
    ).fetchall()
    # ★ "메시지 인물마다 다 띄우니까 정신없다, 방에 있는 툴파 중 대표로
    # 한 사람만 알려주자" 요청(2026-08-28) — 페르소나별(pending_turns)이
    # 아니라 방 단위로 이미 안내를 보냈는지를 본다.
    notice_row = conn.execute(
        "SELECT persona_name FROM room_restart_notice WHERE room_id = ?",
        (row["room_id"],),
    ).fetchone()
    if row["source_message_id"] is not None:
        batch_size = conn.execute(
            "SELECT COUNT(*) AS n FROM pending_turns WHERE source_message_id = ?",
            (row["source_message_id"],),
        ).fetchone()["n"]
    else:
        batch_size = 1
    room_active_count = conn.execute(
        "SELECT COUNT(*) AS n FROM pending_turns WHERE room_id=? AND status IN ('pending','processing')",
        (row["room_id"],),
    ).fetchone()["n"]
    conn.commit()
    conn.close()
    return {
        "turn_id": row["id"],
        "persona_name": row["persona_name"],
        "room_id": row["room_id"],
        "rerouted": bool(row["rerouted"]),
        "source_message_id": row["source_message_id"],
        "batch_size": batch_size,
        "room_active_count": room_active_count,
        # ★ "서버 업데이트로 껐다 켜는 도중에 메시지 보내면 반응이 끊긴다"
        # 요청(2026-08-27) — 워커가 이 턴이 얼마나 오래 대기했는지 알아야
        # "재시작 때문에 늦었다"는 안내를 보낼지 판단할 수 있다.
        "created_at": row["created_at"],
        # ★ 방 단위 대표 안내가 이미 나갔는지(room_restart_notice에 행이
        # 있는지). true면 이 턴의 페르소나는 별도 안내를 또 보내지 않는다.
        "room_restart_notice_active": notice_row is not None,
        "room_restart_notice_persona": notice_row["persona_name"] if notice_row else None,
        "context": [dict(r) for r in reversed(context_rows)],
    }


class RestartNoticeMark(BaseModel):
    room_id: str
    persona_name: str


@app.post("/api/worker/mark_restart_notice_sent")
def worker_mark_restart_notice_sent(body: RestartNoticeMark, authorization: Optional[str] = Header(None)):
    """워커가 어떤 방에 재시작 공백 안내(대표 1명분)를 보낸 직후 호출해
    그 방을 "안내 완료"로 표시한다. 방 단위(room_restart_notice)라서 같은
    방의 다른 페르소나 턴들은 이 안내를 또 보내지 않는다. INSERT OR IGNORE라
    워커가 거의 동시에 두 번 호출해도(레이스) 먼저 잡은 대표만 남는다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    cursor = conn.execute(
        "INSERT OR IGNORE INTO room_restart_notice (room_id, persona_name, notified_at) "
        "VALUES (?, ?, datetime('now'))",
        (body.room_id, body.persona_name),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "claimed": cursor.rowcount == 1}


class RestartNoticeClear(BaseModel):
    room_id: str


@app.post("/api/worker/clear_restart_notice")
def worker_clear_restart_notice(body: RestartNoticeClear, authorization: Optional[str] = Header(None)):
    """이 방의 밀린 턴이 다 처리됐는지 확인하고, 다 처리됐으면 그 방의
    room_restart_notice 행을 지운다(=다음에 또 공백이 생기면 새 대표 안내를
    보낼 수 있게 초기화). "시작" 안내를 보냈던 대표 페르소나 이름을 같이
    돌려줘서, 워커가 그 대표 이름으로 "완료" 안내까지 이어서 보낼 수 있게
    한다 — 여전히 밀린 턴이 남아 있으면 아무것도 지우지 않고 null을 준다."""
    _check_worker_auth(authorization)
    conn = get_conn()
    remaining = conn.execute(
        "SELECT COUNT(*) AS n FROM pending_turns WHERE room_id = ? AND status IN ('pending','processing')",
        (body.room_id,),
    ).fetchone()["n"]
    if remaining > 0:
        conn.close()
        return {"cleared": False, "persona_name": None}
    notice_row = conn.execute(
        "SELECT persona_name FROM room_restart_notice WHERE room_id = ?",
        (body.room_id,),
    ).fetchone()
    conn.execute("DELETE FROM room_restart_notice WHERE room_id = ?", (body.room_id,))
    conn.commit()
    conn.close()
    return {
        "cleared": notice_row is not None,
        "persona_name": notice_row["persona_name"] if notice_row else None,
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
    traditional_commentators = {
        "조조", "이전", "두목", "매요신", "장예", "왕석", "가림", "두우", "진호"
    }
    commentators = [name for name in targets if name in traditional_commentators]
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
            "UPDATE messages SET sender = ?, content = ? WHERE id = ?",
            (sender, content, existing["message_id"]),
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
            "INSERT INTO pending_turns (persona_name, room_id, status, created_at, source_message_id) VALUES (?, ?, 'pending', ?, ?)",
            (persona_name, room_id, now, message_id),
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
    if not row or row["status"] not in {"pending", "processing"}:
        conn.close()
        raise HTTPException(status_code=404, detail="이미 처리됐거나 없는 턴입니다")
    conn.execute(
        "UPDATE pending_turns SET persona_name = ?, rerouted = 1, status='pending', started_at=NULL WHERE id = ?",
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
        conn.commit()
        preview = result.reply[:80] + ("…" if len(result.reply) > 80 else "")
        notify_room_members_new_message(conn, row["room_id"], row["persona_name"], row["persona_name"], preview)
        conn.commit()
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


class WorkerPostMessage(BaseModel):
    persona_name: str
    room_id: str
    content: str


@app.post("/api/worker/post_message")
def worker_post_message(body: WorkerPostMessage, authorization: Optional[str] = Header(None)):
    """post_admin_report와 같은 패턴을 일반화한 것 — 워커가 pending_turns
    큐를 거치지 않고 아무 방에나 페르소나 명의로 바로 메시지를 남긴다.
    사용자 메시지에 대한 실시간 응답이 아니라 워커가 스스로 먼저 말을
    거는 경우에 쓴다.

    ★ 2026-08-27: "서버 업데이트로 껐다 켜는 도중에 메시지 보내면 반응이
    끊긴다"는 요청으로 처음 추가 — 워커가 재시작 후 오래 대기한 pending_turn을
    발견하면, 실제 AI 응답 전에 이 엔드포인트로 짧은 복귀 안내를 먼저
    보낸다(worker/persona_worker.py의 RESTART_GAP_NOTICE_SECONDS 참고)."""
    _check_worker_auth(authorization)
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (room_id, sender, content, created_at) VALUES (?, ?, ?, ?)",
        (body.room_id, body.persona_name, body.content, _now()),
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
