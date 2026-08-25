"""툴파시스템 채팅앱의 SQLite 저장소.

표준 라이브러리 sqlite3만 쓴다 — 클라우드에 배포되는 부분이라 의존성을 최소로
유지한다. 스키마 네 개: personas(페르소나 캐시), messages(채팅 로그, room_id로
방 구분 — "group"은 전체 채팅방, 그 외엔 해당 페르소나 이름의 1:1 방),
pending_turns(워커가 처리할 응답 대기열), story_sync(대화 내용을 Notion
"함께 만든 이야기"에 어디까지 반영했는지 워터마크)."""
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
        """
    )
    _ensure_column(conn, "messages", "room_id", "TEXT NOT NULL DEFAULT 'group'")
    _ensure_column(conn, "pending_turns", "room_id", "TEXT NOT NULL DEFAULT 'group'")
    _ensure_column(conn, "personas", "group_name", "TEXT")
    conn.commit()
    conn.close()
