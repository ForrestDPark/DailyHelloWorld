import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from server import app as module


def owner_request():
    return SimpleNamespace(state=SimpleNamespace(user=None, can_write=True, share_guest=False))


class ShiftAlarmApiTests(unittest.TestCase):
    def pipeline_conn(self, path=":memory:"):
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE personas (name TEXT PRIMARY KEY);
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, room_id TEXT, sender TEXT,
                content TEXT, created_at TEXT, is_system INTEGER DEFAULT 0
            );
            CREATE TABLE pending_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT, persona_name TEXT, room_id TEXT,
                status TEXT, created_at TEXT, source_message_id INTEGER
            );
            INSERT INTO personas(name) VALUES ('손무');
        """)
        return conn

    def test_status_reads_the_existing_icloud_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            status_file = Path(directory) / "status.json"
            status_file.write_text(json.dumps({"shift": "D", "reminders": []}), encoding="utf-8")
            with patch.object(module, "SHIFT_ALARM_STATUS_FILE", status_file):
                self.assertEqual(module.shift_alarm_status(owner_request())["shift"], "D")

    def test_invalid_time_is_rejected_before_notion_access(self):
        with self.assertRaises(HTTPException) as raised:
            module.update_shift_alarm_reminder_time(
                module.ReminderTimeUpdate(label="리마인더", time="25:00"), owner_request()
            )
        self.assertEqual(raised.exception.status_code, 422)

    def test_check_all_only_patches_unchecked_allowlisted_routines(self):
        status = {"routine_date": "2026-09-07", "daily_routine": [
            {"label": "완료", "checked": True}, {"label": "남음", "checked": False},
        ]}
        calls = []

        def notion(_token, path, method="GET", payload=None):
            calls.append((path, method, payload))
            if path.startswith("blocks/3b532"):
                return {"results": [{"id": "toggle", "type": "toggle", "toggle": {
                    "rich_text": [{"plain_text": "🌅 오늘의 일일 루틴 — 2026-09-07"}]
                }}]}
            if path == "blocks/toggle/children?page_size=100":
                return {"results": [{"id": "todo", "type": "to_do", "to_do": {
                    "rich_text": [{"plain_text": "남음"}], "checked": False,
                }}]}
            return {}

        with patch.object(module, "_read_shift_alarm_status", return_value=status), \
             patch.object(module, "_shift_alarm_notion_token", return_value="hidden"), \
             patch.object(module, "_notion_request", side_effect=notion):
            result = module.check_all_shift_alarm_routine(owner_request())
        self.assertEqual(result, {"ok": True, "updated": 1})
        patches = [call for call in calls if call[1] == "PATCH"]
        self.assertEqual(len(patches), 1)
        self.assertTrue(patches[0][2]["to_do"]["checked"])

    def test_sunzi_button_queues_one_light_pipeline_turn(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "chat.db"
            conn = self.pipeline_conn(db_path)
            with patch.object(module, "get_conn", return_value=conn), \
                 patch.object(module, "SUNZI_PIPELINE_LOCK_DIR", Path(directory) / "no-lock"):
                result = module.start_shift_alarm_sunzi_analysis(owner_request())
            self.assertEqual(result["mode"], "light")
            check = sqlite3.connect(db_path)
            message = check.execute("SELECT sender,content,is_system FROM messages").fetchone()
            turn = check.execute("SELECT persona_name,room_id,status FROM pending_turns").fetchone()
            check.close()
        self.assertEqual(message, ("system", module.SUNZI_LIGHT_PIPELINE_REQUEST, 1))
        self.assertEqual(turn, ("손무", module.SUNZI_DISCUSSION_ROOM_ID, "pending"))

    def test_sunzi_button_rejects_an_existing_pipeline(self):
        conn = self.pipeline_conn()
        conn.execute(
            "INSERT INTO pending_turns(persona_name,room_id,status,created_at,source_message_id) "
            "VALUES ('손무','room','pending','now',1)"
        )
        with patch.object(module, "get_conn", return_value=conn), \
             patch.object(module, "SUNZI_PIPELINE_LOCK_DIR", Path("/tmp/no-sunzi-test-lock")), \
             self.assertRaises(HTTPException) as raised:
            module.start_shift_alarm_sunzi_analysis(owner_request())
        self.assertEqual(raised.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
