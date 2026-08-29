"""툴파챗의 SQLite 저장소.

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
        CREATE TABLE IF NOT EXISTS room_persona_exclusions (
            room_id TEXT NOT NULL,
            persona_name TEXT NOT NULL,
            excluded_at TEXT NOT NULL,
            PRIMARY KEY (room_id, persona_name)
        );
        CREATE TABLE IF NOT EXISTS room_user_invites (
            room_id TEXT NOT NULL,
            username TEXT NOT NULL,
            invited_at TEXT NOT NULL,
            PRIMARY KEY (room_id, username)
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
        CREATE TABLE IF NOT EXISTS room_read_state (
            username TEXT NOT NULL,
            room_id TEXT NOT NULL,
            last_message_id INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (username, room_id)
        );
        CREATE TABLE IF NOT EXISTS user_room_backgrounds (
            username TEXT NOT NULL,
            room_id TEXT NOT NULL,
            image_url TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (username, room_id)
        );
        CREATE TABLE IF NOT EXISTS friend_favorites (
            username TEXT NOT NULL,
            friend_username TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (username, friend_username),
            FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE,
            FOREIGN KEY (friend_username) REFERENCES users(username) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS user_ai_credentials (
            username TEXT NOT NULL,
            provider TEXT NOT NULL,
            encrypted_key TEXT NOT NULL,
            key_hint TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (username, provider)
        );
        CREATE TABLE IF NOT EXISTS qa_feedback_reports (
            source_message_id INTEGER PRIMARY KEY,
            report_message_id INTEGER,
            reported_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS persona_image_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_name TEXT NOT NULL,
            prompt TEXT NOT NULL,
            requested_by TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL,
            result_url TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            FOREIGN KEY (persona_name) REFERENCES personas(name) ON DELETE CASCADE
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
    # 친구 목록에서 만든 사람/페르소나 1:1 방을 중복 생성하지 않기 위한 키.
    # 누군가를 더 초대해 그룹방이 되면 서버가 이 값을 NULL로 바꾼다.
    _ensure_column(conn, "custom_rooms", "direct_key", "TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_rooms_direct_key "
        "ON custom_rooms(direct_key) WHERE direct_key IS NOT NULL"
    )
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
    # 같은 사용자 메시지에서 생긴 여러 응답을 한 묶음으로 식별하고, 병렬
    # 워커가 한 턴을 중복 점유하지 않게 한다(2026-08-28).
    _ensure_column(conn, "pending_turns", "source_message_id", "INTEGER")
    _ensure_column(conn, "pending_turns", "started_at", "TEXT")
    # ★ "서버 업데이트로 껐다 켜는 도중에 메시지 보내면 반응이 끊긴다" 요청
    # (2026-08-27) — 워커가 재시작 공백 안내를 보냈는지 서버가 기억해둔다.
    # 워커 프로세스 자체가 짧은 시간에 여러 번 재시작되면(배포 중 연속
    # kickstart 등) 같은 pending_turn을 매번 다시 집어 들어 안내를 중복
    # 전송하는 문제가 실제로 있었다 — 워커 메모리가 아니라 서버 DB에
    # 플래그를 둬야 재시작 횟수와 무관하게 딱 한 번만 보낸다.
    _ensure_column(conn, "pending_turns", "restart_notice_sent", "INTEGER NOT NULL DEFAULT 0")
    # ★ "메시지 인물마다 다 띄우니까 정신없다, 방에 있는 툴파 중 대표로
    # 한 사람이 서버 업데이트 중입니다 라고만 알려주자" 요청(2026-08-28) —
    # 위 restart_notice_sent는 pending_turn(=페르소나 1명의 발화 1건)마다
    # 붙어서 같은 방의 여러 페르소나가 각자 안내를 보내는 게 문제였다.
    # 방 단위로 "이미 대표가 안내를 보냈는지"를 별도 테이블에 기억해서
    # 방마다 딱 한 번만 보내고, 밀린 턴이 다 처리되면 이 행을 지우면서
    # "완료" 안내도 한 번 보낸다.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS room_restart_notice (
            room_id TEXT PRIMARY KEY,
            persona_name TEXT NOT NULL,
            notified_at TEXT NOT NULL
        )
    """)
    # ★ "초대가 되면 그 톡방에 '누가 초대되었습니다'라고 구분선 같은 걸
    # 만들어달라" 요청(2026-08-28) — 페르소나/사용자 발화가 아니라 서버가
    # 직접 남기는 시스템 알림. 프론트가 이 플래그로 말풍선이 아니라 가운데
    # 구분선 스타일로 다르게 그린다(static/chat.js의 renderSystemMessage).
    _ensure_column(conn, "messages", "is_system", "INTEGER NOT NULL DEFAULT 0")
    # ★ "채팅방에 새 메시지 있으면 사용자들한테도 알람이 가게 해달라"
    # 요청(2026-08-27) — 브라우저 Web Push 구독 정보(방마다가 아니라
    # 계정마다 — 여러 기기에서 구독하면 여러 행이 쌓인다). endpoint가
    # 곧 그 기기·브라우저의 유일 식별자라 UNIQUE로 중복 구독을 막는다.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            endpoint TEXT NOT NULL UNIQUE,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    # ★ 같은 요청, 카카오로 로그인한 사람에게는 카톡 "나에게 보내기"로 대신
    # 보내달라는 후속 요청(2026-08-27) — 카카오 로그인 시 받은 access/refresh
    # 토큰을 계정에 저장해둔다(talk_message 동의를 받은 경우에만 실제로
    # 채워짐). 액세스 토큰은 몇 시간 뒤 만료되므로 refresh_token으로 갱신.
    _ensure_column(conn, "users", "kakao_access_token", "TEXT")
    _ensure_column(conn, "users", "kakao_refresh_token", "TEXT")
    _ensure_column(conn, "users", "kakao_token_expires_at", "TEXT")
    # ★ "카톡이나 구글로 로그인한 사람은 자기 이름 수정할 수 있게, 프로필
    # 사진도 바꿀 수 있게 해달라" 요청(2026-08-28) — 소셜 로그인은 자동 생성된
    # 아이디(예: kakao_5060403120)라 보기 좋은 이름으로 바꾸고 싶을 만하다.
    # username(로그인·메시지 sender·소유권에 쓰이는 안정적 식별자)은 그대로
    # 두고, 화면에 보여줄 이름/사진만 별도 컬럼으로 둔다 — 없으면(NULL)
    # username으로 대체 표시.
    _ensure_column(conn, "users", "display_name", "TEXT")
    _ensure_column(conn, "users", "avatar_url", "TEXT")
    _ensure_column(conn, "users", "ai_provider", "TEXT")
    # ★ "권민석 프로필설정이 너무 적나라한데 일반 사용자도 다 보이는 거야?
    # 실제 친군데 실친이 들어와서 봤을 때 오해의 소지가 있을 것 같다" 요청
    # (2026-08-28) — 관리자가 만든 페르소나(owner_username=NULL)는 실제
    # 지인을 본뜬 경우가 많아 프로필 문구가 노출되면 곤란할 수 있다. 이제
    # 기본적으로 관리자만 프로필을 볼 수 있고, 이 표에 명시적으로 등록된
    # 사용자만 예외적으로 볼 수 있다(ui_dev_grants와 같은 패턴 — 소유자가
    # 사용자별로 직접 켜고 끔).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS persona_view_grants (
            persona_name TEXT NOT NULL,
            username TEXT NOT NULL,
            granted_at TEXT NOT NULL,
            PRIMARY KEY (persona_name, username)
        )
    """)
    conn.commit()
    conn.close()


# ★ 2026-08-26: "채팅창에 카카오톡처럼 공지사항이 보였으면 좋겠다, 그 방
# 대화 내용을 토대로 업데이트되는 내용을 하루하루 요약해서 공지해달라"는
# 요청. room_notices — 그룹 회의방/커스텀 방마다 최신 공지 하나씩만 들고
# 있는다(마치 카톡 공지처럼 이전 공지를 덮어씀). last_message_id는 워커가
# "여기까지는 이미 요약에 반영했다"를 아는 워터마크.
