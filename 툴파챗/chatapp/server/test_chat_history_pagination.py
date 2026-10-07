"""손자병법 토론방의 최근 7일 우선 로딩과 커서 페이지 테스트."""

import datetime
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from server import app, db


def owner_request():
    return SimpleNamespace(state=SimpleNamespace(user=None, can_write=True, share_guest=False))


class ChatHistoryPaginationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(db, "DB_PATH", str(Path(self.temp.name) / "chat.db"))
        self.patch.start()
        db.init_db()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def _insert(self, room_id, content, created_at):
        conn = db.get_conn()
        cursor = conn.execute(
            "INSERT INTO messages(room_id,sender,content,created_at) VALUES(?,?,?,?)",
            (room_id, "tester", content, created_at),
        )
        conn.commit()
        message_id = cursor.lastrowid
        conn.close()
        return message_id

    def test_sunzi_initial_load_only_returns_recent_week_then_before_cursor_returns_old(self):
        now = datetime.datetime.now().astimezone()
        old_id = self._insert(app.SUNZI_DISCUSSION_ROOM_ID, "old", (now - datetime.timedelta(days=8)).isoformat(timespec="seconds"))
        recent_id = self._insert(app.SUNZI_DISCUSSION_ROOM_ID, "recent", (now - datetime.timedelta(days=2)).isoformat(timespec="seconds"))
        initial = app.get_messages(owner_request(), room_id=app.SUNZI_DISCUSSION_ROOM_ID)
        self.assertEqual([message["id"] for message in initial], [recent_id])
        older = app.get_messages(owner_request(), room_id=app.SUNZI_DISCUSSION_ROOM_ID, before_id=recent_id, limit=100)
        self.assertEqual([message["id"] for message in older], [old_id])

    def test_other_rooms_keep_existing_initial_history_behavior(self):
        now = datetime.datetime.now().astimezone()
        old_id = self._insert("another-room", "old", (now - datetime.timedelta(days=30)).isoformat(timespec="seconds"))
        recent_id = self._insert("another-room", "recent", now.isoformat(timespec="seconds"))
        messages = app.get_messages(owner_request(), room_id="another-room")
        self.assertEqual([message["id"] for message in messages], [old_id, recent_id])


if __name__ == "__main__":
    unittest.main()
