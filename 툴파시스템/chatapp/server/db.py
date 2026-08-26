"""툴파시스템 채팅앱의 SQLite 저장소.

표준 라이브러리 sqlite3만 쓴다 — 클라우드에 배포되는 부분이라 의존성을 최소로
유지한다. 스키마: personas(페르소나 캐시), messages(채팅 로그, room_id로
방 구분 — "group"은 전체 채팅방, 그 외엔 해당 페르소나 이름의 1:1 방),
pending_turns(워커가 처리할 응답 대기열), story_sync(대화 내용을 Notion
"함께 만든 이야기"에 어디까지 반영했는지 워터마크), users/sessions(로그인
계정·세션 — 2026-08-26, 아래 참고), ui_dev_grants(소유자가 UI 개발자
페르소나 "유이"에게 말 걸 권한을 선별 부여한 계정 목록 — 2026-08-26)."""
import os
import sqlite3

DB_PATH = os.environ.get("CHATAPP_DB_PATH", "chatapp.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn, table, column, coldef):
    """이미 배포된 DB에 새 컬럼을 추가한다(있으면 그대로 둠) — 볼륨에 데이터가
    남아있는 실제 배포본을 CREATE TABLE IF NOT EXISTS만으로는 마이그레이션할
    수 없어서(기존 테이블은 그대로 남음) 필요."""
    cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}")


def init_db():
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS personas (
            name TEXT PRIMARY KEY,
            notion_page_id TEXT NOT NULL,
            system_prompt TEXT NOT NULL,
            synced_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pending_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            reply TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS story_sync (
            persona_name TEXT PRIMARY KEY,
            last_message_id INTEGER NOT NULL DEFAULT 0,
            synced_at TEXT
        );
        CREATE TABLE IF NOT EXISTS room_invites (
            room_id TEXT NOT NULL,
            persona_name TEXT NOT NULL,
            invited_at TEXT NOT NULL,
            PRIMARY KEY (room_id, persona_name)
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            is_owner INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ui_dev_grants (
            username TEXT PRIMARY KEY,
            granted_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS custom_rooms (
            room_id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS room_notices (
            room_id TEXT PRIMARY KEY,
            content TEXT,
            last_message_id INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS message_reactions (
            message_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            emoji TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (message_id, username, emoji),
            FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
        );
        """
    )
    _ensure_column(conn, "messages", "room_id", "TEXT NOT NULL DEFAULT 'group'")
    _ensure_column(conn, "messages", "reply_message_id", "INTEGER")
    _ensure_column(conn, "pending_turns", "room_id", "TEXT NOT NULL DEFAULT 'group'")
    _ensure_column(conn, "personas", "group_name", "TEXT")
    # ★ 2026-08-26: "사용자가 자기만의 페르소나를 만들고 수정·대화할 수 있게
    # 해달라" 요청 — owner_username이 NULL이면 Notion에서 동기화된 기존
    # 페르소나(모두가 공유), 값이 있으면 그 계정이 직접 만든 개인 페르소나.
    # description은 사용자가 입력한 원문(수정 화면에 그대로 보여주기 위함) —
    # 실제 AI에 넘기는 system_prompt는 이걸 감싸서 별도로 만든다.
    _ensure_column(conn, "personas", "owner_username", "TEXT")
    _ensure_column(conn, "personas", "description", "TEXT")
    # ★ 2026-08-26: "구글/카카오 로그인 연동" 요청 — 소셜 로그인으로 처음
    # 들어온 계정은 비밀번호 없이 이 외부 ID로만 로그인한다(로그인 시
    # google_sub/kakao_id로 기존 계정을 찾고, 없으면 새로 만듦). UNIQUE
    # 제약은 SQLite ALTER TABLE로 못 걸어서(테이블 재생성 필요) 애플리케이션
    # 코드(server/app.py)에서 중복 여부를 직접 확인한다.
    _ensure_column(conn, "users", "google_sub", "TEXT")
    _ensure_column(conn, "users", "kakao_id", "TEXT")
    # ★ 2026-08-26: "토론방 대표사진을 썸네일로 보이게 해달라" 요청 —
    # 커스텀 방(custom_rooms)에만 해당. 업로드 안 하면 NULL(방 목록에서
    # 기존처럼 글자 아바타로 표시).
    _ensure_column(conn, "custom_rooms", "thumbnail_url", "TEXT")
    # ★ 2026-08-26: "페르소나 프로필을 간단히 확인할 수 있는 페이지" 요청 —
    # Notion 페르소나는 워커가 "## 프로필" 섹션(유형·정체성/관계·성격·말투·
    # 배경)만 추려서 채워준다(worker/notion_personas.py extract_profile_summary).
    # 사용자 개인 페르소나는 이미 있는 description을 그대로 프로필로 쓴다.
    _ensure_column(conn, "personas", "profile_summary", "TEXT")
    _ensure_column(conn, "personas", "avatar_url", "TEXT")
    _ensure_column(conn, "personas", "admin_description", "TEXT")
    _ensure_column(conn, "personas", "admin_group_name", "TEXT")
    # ★ "담당이 아닌 페르소나가 엉뚱하게 대답하는 버그" 요청(2026-08-26) —
    # 이름이 안 불렸을 때 "직전 발화자"로 고른 턴을 워커가 한 번 재검토해서
    # 더 알맞은 담당자로 돌려보낼 수 있다(rerouted=1이면 재검토 끝, 무한
    # 왕복 방지).
    _ensure_column(conn, "pending_turns", "rerouted", "INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    conn.close()


# ★ 2026-08-26: "채팅창에 카카오톡처럼 공지사항이 보였으면 좋겠다, 그 방
# 대화 내용을 토대로 업데이트되는 내용을 하루하루 요약해서 공지해달라"는
# 요청. room_notices — 그룹 회의방/커스텀 방마다 최신 공지 하나씩만 들고
# 있는다(마치 카톡 공지처럼 이전 공지를 덮어씀). last_message_id는 워커가
# "여기까지는 이미 요약에 반영했다"를 아는 워터마크.
