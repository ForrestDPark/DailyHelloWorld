import json
import sqlite3
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from server import app as module


def owner_request():
    return SimpleNamespace(state=SimpleNamespace(user=None, can_write=True, share_guest=False))


def signed_in_request(username="tester"):
    return SimpleNamespace(state=SimpleNamespace(
        user={"username": username, "is_owner": False}, can_write=True, share_guest=False
    ))


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

    def test_notifications_combine_system_updates_and_unread_chat(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "notifications.db"
            conn = sqlite3.connect(db_path)
            conn.executescript("""
                CREATE TABLE notification_reads (
                    username TEXT, notification_id TEXT, read_at TEXT,
                    PRIMARY KEY (username, notification_id)
                );
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY, room_id TEXT, sender TEXT,
                    content TEXT, created_at TEXT
                );
                INSERT INTO messages VALUES (2, 'room-a', '친구', '새 소식', '2026-09-09T10:00:00+09:00');
            """)
            conn.commit()
            conn.close()

            def connection():
                opened = sqlite3.connect(db_path)
                opened.row_factory = sqlite3.Row
                return opened

            room = {"room_id": "room-a", "label": "테스트 방", "last_message_id": 2,
                    "last_read_id": 0, "last_message": "새 소식",
                    "last_message_at": "2026-09-09T10:00:00+09:00"}
            with patch.object(module, "get_conn", side_effect=connection), \
                 patch.object(module, "list_rooms", return_value=[room]):
                result = module.get_notifications(signed_in_request())
        self.assertEqual(result["items"][0]["type"], "chat")
        self.assertEqual(result["items"][0]["url"], "/#room=room-a")
        self.assertEqual(result["unread_count"], len(module.SYSTEM_UPDATE_NOTIFICATIONS) + 1)

    def test_system_notification_read_is_account_specific(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "notification-read.db"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE notification_reads (username TEXT, notification_id TEXT, read_at TEXT, PRIMARY KEY (username, notification_id))")
            conn.commit()
            conn.close()

            def connection():
                opened = sqlite3.connect(db_path)
                opened.row_factory = sqlite3.Row
                return opened

            notification_id = module.SYSTEM_UPDATE_NOTIFICATIONS[0]["id"]
            with patch.object(module, "get_conn", side_effect=connection):
                module.mark_notification_read(
                    module.NotificationReadUpdate(notification_id=notification_id),
                    signed_in_request("alice"),
                )
            check = sqlite3.connect(db_path)
            rows = check.execute("SELECT username, notification_id FROM notification_reads").fetchall()
            check.close()
        self.assertEqual(rows, [("alice", notification_id)])

    def test_career_source_analysis_uses_visual_fallback_after_html_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            conn = sqlite3.connect(data_dir / "jobs.db")
            conn.execute("CREATE TABLE jobs (source TEXT, source_id TEXT, title TEXT, url TEXT)")
            conn.execute("INSERT INTO jobs VALUES ('테스트','1','백엔드 개발자','https://example.com/job')")
            conn.commit(); conn.close()
            visual = "주요업무\nPython API 개발\n자격요건\nSQL 경험\n우대사항\nDocker 경험"
            fake_collector = SimpleNamespace(fetch_job_detail_via_screenshot=lambda *_: visual)
            with patch.object(module, "CAREER_DATA_DIR", data_dir), \
                 patch.dict("sys.modules", {"job_collector": fake_collector}), \
                 patch("urllib.request.urlopen", side_effect=urllib.error.URLError("blocked")):
                result = module.career_source_analysis(owner_request(), "job", "테스트", "1")
        self.assertTrue(result["ok"])
        self.assertEqual(result["extraction"], "visual")
        self.assertIn("자격요건", result["preparation"]["sections"])

    def test_source_study_plan_is_specific_without_exposing_match_evidence(self):
        result = module._source_grounded_preparation(
            "주요업무\nPython REST API 개발\n자격요건\nSQL 데이터베이스 경험\n우대사항\nDocker AWS 경험"
        )
        self.assertTrue(result["grounded"])
        self.assertGreaterEqual(len(result["study"]), 3)
        for item in result["study"]:
            self.assertIn("how", item)
            self.assertIn("practice", item)
            self.assertNotIn("evidence", item)
            self.assertGreater(len(item["how"]), 25)

    def test_source_sections_allow_saramin_icon_prefixes(self):
        result = module._source_grounded_preparation(
            "모집분야\nAI 자동화 개발자\n📋 주요업무\nPython FastAPI 개발\n"
            "📋 자격요건\n경력 3년 이상\n✅ 우대사항\nReact 경험"
        )
        self.assertTrue(result["grounded"])
        self.assertIn("주요업무", result["sections"])
        self.assertIn("자격요건", result["sections"])
        self.assertIn("우대사항", result["sections"])

    def test_career_consult_queues_only_hr_persona(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "career"
            data_dir.mkdir()
            jobs = sqlite3.connect(data_dir / "jobs.db")
            jobs.execute("""CREATE TABLE jobs (
                source TEXT, source_id TEXT, title TEXT, company TEXT, url TEXT,
                location TEXT, experience TEXT, education TEXT, employment_type TEXT,
                salary TEXT, deadline TEXT, skills TEXT, keywords TEXT, matched_query TEXT
            )""")
            jobs.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                "사람인(크롤링)", "7", "AI 자동화 개발자", "테스트회사", "https://example.com/job",
                "서울", "3년", "무관", "정규직", "", "", "Python", "AI", "자동화",
            ))
            jobs.commit(); jobs.close()

            chat_path = Path(directory) / "chat.db"
            chat = sqlite3.connect(chat_path)
            chat.executescript("""
                CREATE TABLE personas (name TEXT PRIMARY KEY, notion_page_id TEXT, system_prompt TEXT,
                    group_name TEXT, owner_username TEXT, description TEXT, synced_at TEXT);
                CREATE TABLE room_invites (room_id TEXT, persona_name TEXT, invited_at TEXT,
                    PRIMARY KEY(room_id,persona_name));
                CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, room_id TEXT,
                    sender TEXT, content TEXT, created_at TEXT, is_system INTEGER);
                CREATE TABLE pending_turns (id INTEGER PRIMARY KEY AUTOINCREMENT, persona_name TEXT,
                    room_id TEXT, status TEXT, created_at TEXT, source_message_id INTEGER);
            """)
            chat.commit(); chat.close()

            def connection():
                opened = sqlite3.connect(chat_path)
                opened.row_factory = sqlite3.Row
                return opened

            body = module.CareerConsultRequest(source="사람인(크롤링)", source_id="7")
            with patch.object(module, "CAREER_DATA_DIR", data_dir), patch.object(
                module, "get_conn", side_effect=connection
            ):
                result = module.start_career_consult(body, owner_request())
            check = sqlite3.connect(chat_path)
            turn = check.execute("SELECT persona_name,room_id,status FROM pending_turns").fetchone()
            invite = check.execute("SELECT persona_name FROM room_invites").fetchone()
            check.close()
        self.assertEqual(result["room_id"], module.CAREER_CONSULT_ROOM_ID)
        self.assertEqual(turn, (module.CAREER_HR_PERSONA_NAME, module.CAREER_CONSULT_ROOM_ID, "pending"))
        self.assertEqual(invite, (module.CAREER_HR_PERSONA_NAME,))

    def test_certificates_are_recommended_from_job_signals_and_not_called_required(self):
        result = module._source_grounded_preparation(
            "주요업무\nPython REST API 개발\n자격요건\nSQL 데이터베이스 설계\n우대사항\n데이터 분석 경험"
        )
        names = [item["name"] for item in result["recommended_certificates"]]
        self.assertIn("정보처리기사", names)
        self.assertIn("SQLD", names)
        self.assertTrue(all(item["required"] is False for item in result["recommended_certificates"]))

    def test_explicit_certificate_is_not_repeated_as_recommendation(self):
        result = module._source_grounded_preparation(
            "주요업무\nSQL 데이터베이스 운영\n자격요건\nSQLD 보유자\n우대사항\n데이터 분석"
        )
        self.assertIn("SQLD", result["certificates"])
        self.assertNotIn("SQLD", [item["name"] for item in result["recommended_certificates"]])


if __name__ == "__main__":
    unittest.main()
