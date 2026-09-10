"""만료된 채용·경진 데이터를 삭제 전에 복구 가능한 SQLite DB에 보관한다."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable


def archive_rows(path: Path, kind: str, rows: Iterable[sqlite3.Row], reason: str) -> int:
    items = list(rows)
    if not items:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expired_items (
                kind TEXT NOT NULL,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                archived_at TEXT NOT NULL,
                reason TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (kind, source, source_id)
            )
        """)
        archived_at = datetime.now().astimezone().isoformat(timespec="seconds")
        conn.executemany(
            """INSERT INTO expired_items
               (kind, source, source_id, archived_at, reason, payload_json)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(kind, source, source_id) DO UPDATE SET
                 archived_at=excluded.archived_at,
                 reason=excluded.reason,
                 payload_json=excluded.payload_json""",
            [
                (kind, row["source"], row["source_id"], archived_at, reason,
                 json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
                for row in items
            ],
        )
        conn.commit()
        return len(items)
    finally:
        conn.close()
