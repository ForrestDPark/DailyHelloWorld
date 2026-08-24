"""툴파시스템 채팅앱의 SQLite 저장소.

표준 라이브러리 sqlite3만 쓴다 — 클라우드에 배포되는 부분이라 의존성을 최소로
유지한다. 스키마 세 개: personas(페르소나 캐시), messages(채팅 로그),
pending_turns(워커가 처리할 응답 대기열)."""
import os
import sqlite3

DB_PATH = os.environ.get("CHATAPP_DB_PATH", "chatapp.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
        """
    )
    conn.commit()
    conn.close()
