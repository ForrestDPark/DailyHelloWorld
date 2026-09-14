import json
import sqlite3
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import mock_open, patch

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

    def test_video_download_requires_explicit_owner_approval(self):
        with self.assertRaises(HTTPException) as raised:
            module.start_shift_alarm_video_download(
                module.ShiftAlarmVideoDownloadRequest(url="https://example.com/video.m3u8"),
                owner_request(),
            )
        self.assertEqual(raised.exception.status_code, 422)

    def test_video_download_is_owner_only(self):
        with self.assertRaises(HTTPException) as raised:
            module.start_shift_alarm_video_download(
                module.ShiftAlarmVideoDownloadRequest(
                    url="https://example.com/video.m3u8", approved=True,
                ), signed_in_request("other-user"),
            )
        self.assertEqual(raised.exception.status_code, 403)

    def test_video_download_rejects_private_network_targets(self):
        private_dns = [(2, 1, 6, "", ("127.0.0.1", 443))]
        with patch("socket.getaddrinfo", return_value=private_dns), \
             self.assertRaises(HTTPException) as raised:
            module._validate_stream_download_url("https://example.test/video.m3u8")
        self.assertEqual(raised.exception.status_code, 422)

    def test_video_download_starts_only_the_fixed_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory)
            worker = state_dir / "worker.py"
            worker.write_text("pass", encoding="utf-8")
            public_dns = [(2, 1, 6, "", ("93.184.216.34", 443))]
            with patch.object(module, "SHIFT_ALARM_VIDEO_DIR", state_dir), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_STATUS_FILE", state_dir / "status.json"), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_WORKER", worker), \
                 patch.object(module, "_shift_alarm_video_status", return_value={"state": "idle"}), \
                 patch("socket.getaddrinfo", return_value=public_dns), \
                 patch("subprocess.Popen") as popen:
                result = module.start_shift_alarm_video_download(
                    module.ShiftAlarmVideoDownloadRequest(
                        url="https://example.com/video.m3u8", approved=True,
                    ), owner_request(),
                )
            request_path = Path(popen.call_args.args[0][-1])
            saved = json.loads(request_path.read_text(encoding="utf-8"))
        self.assertTrue(result["ok"])
        self.assertEqual(saved["url"], "https://example.com/video.m3u8")
        self.assertEqual(saved["owner_username"], "local-owner")
        self.assertEqual(popen.call_args.args[0][1], str(worker))

    def test_video_file_supports_authenticated_range_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = root / "files"
            files.mkdir()
            video = files / "job_video.mp4"
            video.write_bytes(b"0123456789")
            db = root / "downloads.db"
            with patch.object(module, "SHIFT_ALARM_VIDEO_DIR", root), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_FILES", files), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_DB", db):
                with module._shift_alarm_video_db() as conn:
                    conn.execute(
                        "INSERT INTO video_downloads "
                        "(job_id,owner_username,filename,file_path,size_bytes,created_at,completed_at,expires_at) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        ("job", "local-owner", "영상.mp4", str(video), 10, module._now(),
                         module._now(), "2999-01-01T00:00:00+00:00"),
                    )
                response = module.download_shift_alarm_video("job", owner_request(), "bytes=2-5")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.headers["content-range"], "bytes 2-5/10")
        self.assertEqual(response.headers["content-length"], "4")

    def test_video_file_is_owner_only(self):
        with self.assertRaises(HTTPException) as raised:
            module.download_shift_alarm_video("job", signed_in_request("other-user"), None)
        self.assertEqual(raised.exception.status_code, 403)

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

    # ── ★ 2026-09-14: 대시보드 음량·미디어 버튼 (채팅 대신 직접 클릭) ──────

    def test_get_volume_returns_current_percent(self):
        with patch.object(module, "_shift_alarm_get_volume", return_value=42):
            self.assertEqual(module.get_shift_alarm_volume(owner_request()), {"percent": 42})

    def test_get_volume_503_when_unreadable(self):
        with patch.object(module, "_shift_alarm_get_volume", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                module.get_shift_alarm_volume(owner_request())
        self.assertEqual(raised.exception.status_code, 503)

    def test_set_volume_by_absolute_percent(self):
        with patch.object(module, "_shift_alarm_set_volume", return_value=70) as mock_set:
            result = module.set_shift_alarm_volume(
                module.ShiftAlarmVolumeRequest(percent=70), owner_request()
            )
        mock_set.assert_called_once_with(70)
        self.assertEqual(result, {"ok": True, "percent": 70})

    def test_set_volume_by_delta_reads_current_first(self):
        with patch.object(module, "_shift_alarm_get_volume", return_value=40), \
             patch.object(module, "_shift_alarm_set_volume", return_value=55) as mock_set:
            result = module.set_shift_alarm_volume(
                module.ShiftAlarmVolumeRequest(delta=15), owner_request()
            )
        mock_set.assert_called_once_with(55)
        self.assertEqual(result["percent"], 55)

    def test_set_volume_requires_percent_or_delta(self):
        with self.assertRaises(HTTPException) as raised:
            module.set_shift_alarm_volume(module.ShiftAlarmVolumeRequest(), owner_request())
        self.assertEqual(raised.exception.status_code, 400)

    def test_set_volume_delta_503_when_current_unknown(self):
        with patch.object(module, "_shift_alarm_get_volume", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                module.set_shift_alarm_volume(module.ShiftAlarmVolumeRequest(delta=10), owner_request())
        self.assertEqual(raised.exception.status_code, 503)

    def test_play_favorites_uses_favorites_folder(self):
        with patch.object(module, "_shift_alarm_play_folder", return_value=(True, "3곡을 새로 열었습니다.")) as mock_play:
            result = module.play_shift_alarm_media(
                module.ShiftAlarmPlayRequest(playlist="favorites"), owner_request()
            )
        mock_play.assert_called_once_with(module.SHIFT_ALARM_FAVORITES_FOLDER)
        self.assertTrue(result["ok"])

    def test_play_folder_opens_elmedia_directly(self):
        """★ 2026-09-14 도입 → 같은 날 되돌림: ElmediaOpenHelper.app(open -na
        --args) 경유는 on run 핸들러 자체가 트리거되지 않아 재생이 완전히
        죽는 실제 회귀를 냈다(실측 확인). 원래대로 open -a 직접 호출이어야
        한다 — 이 호출 자체는 터미널에서 항상 정상 동작함을 확인했다."""
        with patch.object(module, "_shift_alarm_list_audio_tracks", return_value=["/a.mp3"]), \
             patch.object(module, "_shift_alarm_reset_elmedia_playlist", return_value=True), \
             patch.object(module, "subprocess") as mock_subprocess, \
             patch("os.path.isdir", return_value=True):
            module._shift_alarm_play_folder(module.SHIFT_ALARM_FAVORITES_FOLDER)
        args = mock_subprocess.Popen.call_args.args[0]
        self.assertEqual(args, ["open", "-a", "Elmedia Video Player", "/a.mp3"])

    def test_play_folder_records_which_playlist_for_now_playing(self):
        with patch.object(module, "_shift_alarm_list_audio_tracks", return_value=["/a.mp3"]), \
             patch.object(module, "_shift_alarm_reset_elmedia_playlist", return_value=True), \
             patch.object(module, "subprocess"), \
             patch.object(module, "_shift_alarm_save_now_playing") as mock_save, \
             patch("os.path.isdir", return_value=True):
            module._shift_alarm_play_folder(module.SHIFT_ALARM_CLASSIC_FOLDER)
            mock_save.assert_called_once_with("classical")
            mock_save.reset_mock()
            module._shift_alarm_play_folder(module.SHIFT_ALARM_FAVORITES_FOLDER)
            mock_save.assert_called_once_with("favorites")

    def test_play_classical_uses_classic_folder(self):
        with patch.object(module, "_shift_alarm_play_folder", return_value=(True, "5곡을 새로 열었습니다.")) as mock_play:
            module.play_shift_alarm_media(module.ShiftAlarmPlayRequest(playlist="classical"), owner_request())
        mock_play.assert_called_once_with(module.SHIFT_ALARM_CLASSIC_FOLDER)

    def test_play_rejects_unknown_playlist(self):
        with self.assertRaises(HTTPException) as raised:
            module.play_shift_alarm_media(module.ShiftAlarmPlayRequest(playlist="podcast"), owner_request())
        self.assertEqual(raised.exception.status_code, 400)

    def test_play_failure_becomes_409(self):
        with patch.object(module, "_shift_alarm_play_folder", return_value=(False, "재생 가능한 음원 파일이 없습니다.")):
            with self.assertRaises(HTTPException) as raised:
                module.play_shift_alarm_media(module.ShiftAlarmPlayRequest(playlist="favorites"), owner_request())
        self.assertEqual(raised.exception.status_code, 409)

    def test_now_playing_reports_running_playlist(self):
        with patch.object(module, "_shift_alarm_elmedia_running", return_value=True), \
             patch.object(module, "_shift_alarm_load_now_playing", return_value="classical"):
            result = module.shift_alarm_now_playing(owner_request())
        self.assertEqual(result, {"running": True, "playlist": "classical"})

    def test_now_playing_hides_playlist_when_not_running(self):
        """Elmedia가 안 떠 있으면 예전에 재생했던 기록이 남아 있어도 무시한다 —
        꺼진 뒤에도 "재생 중"으로 표시되는 걸 막기 위함."""
        with patch.object(module, "_shift_alarm_elmedia_running", return_value=False), \
             patch.object(module, "_shift_alarm_load_now_playing", return_value="favorites"):
            result = module.shift_alarm_now_playing(owner_request())
        self.assertEqual(result, {"running": False, "playlist": None})

    def test_open_random_sites_returns_urls(self):
        """★ 2026-09-14: 서버(Mac)에서 직접 여는 대신 URL만 돌려주고, 여는
        동작은 요청을 보낸 브라우저(app.js) 쪽에서 하게 바꿨다 — 대시보드를
        폰으로 보고 있으면 폰 크롬에서 열려야 하는데, Mac에서 열어봐야 그
        화면을 보고 있지 않으니 무의미했다."""
        with patch.object(module, "_shift_alarm_pick_random_bookmarks", return_value=["https://a.example", "https://b.example"]):
            result = module.open_shift_alarm_random_sites(owner_request())
        self.assertEqual(result["urls"], ["https://a.example", "https://b.example"])
        self.assertIn("2개", result["message"])

    def test_open_random_sites_409_when_no_bookmarks(self):
        with patch.object(module, "_shift_alarm_pick_random_bookmarks", return_value=[]):
            with self.assertRaises(HTTPException) as raised:
                module.open_shift_alarm_random_sites(owner_request())
        self.assertEqual(raised.exception.status_code, 409)

    def test_open_random_sites_does_not_open_chrome_on_server(self):
        """서버 프로세스가 subprocess로 Chrome을 여는 부작용이 없어야 한다 — URL 선택은
        _shift_alarm_pick_random_bookmarks만 호출하고, 여는 건 클라이언트 몫이다."""
        bookmarks_payload = {"roots": {"bookmark_bar": {"type": "folder", "name": "天", "children": [
            {"type": "url", "url": "https://example.com/1"},
        ]}}}
        with patch("builtins.open", mock_open(read_data=json.dumps(bookmarks_payload))), \
             patch.object(module, "_shift_alarm_load_random_bookmark_history", return_value=[]), \
             patch.object(module, "_shift_alarm_save_random_bookmark_history"), \
             patch.object(module, "subprocess") as mock_subprocess:
            result = module.open_shift_alarm_random_sites(owner_request())
        self.assertEqual(result["urls"], ["https://example.com/1"])
        mock_subprocess.Popen.assert_not_called()

    def test_transport_sends_media_key_when_elmedia_running(self):
        with patch.object(module, "_shift_alarm_elmedia_running", return_value=True), \
             patch.object(module, "_shift_alarm_send_media_key") as mock_send:
            result = module.shift_alarm_media_transport(
                module.ShiftAlarmTransportRequest(action="next"), owner_request()
            )
        mock_send.assert_called_once_with("next")
        self.assertEqual(result, {"ok": True})

    def test_transport_uses_shift_alarm_python_identity_not_server_venv(self):
        """★ 2026-09-14: Quartz.CGEventPost는 Accessibility 권한이 필요한데,
        서버 venv가 아니라 shift_alarm.py와 같은 /opt/anaconda3/bin/python3
        신원을 빌려 써야 새 권한 승인을 또 요구하지 않는다."""
        with patch.object(module, "subprocess") as mock_subprocess:
            module._shift_alarm_send_media_key("playpause")
        args = mock_subprocess.run.call_args.args[0]
        self.assertEqual(args[0], module.SHIFT_ALARM_MEDIA_KEY_PYTHON)
        self.assertEqual(args[1], module.SHIFT_ALARM_MEDIA_KEY_SCRIPT)
        self.assertEqual(args[2], "playpause")

    def test_transport_409_when_elmedia_not_running(self):
        with patch.object(module, "_shift_alarm_elmedia_running", return_value=False):
            with self.assertRaises(HTTPException) as raised:
                module.shift_alarm_media_transport(module.ShiftAlarmTransportRequest(action="next"), owner_request())
        self.assertEqual(raised.exception.status_code, 409)

    def test_transport_rejects_unknown_action(self):
        with self.assertRaises(HTTPException) as raised:
            module.shift_alarm_media_transport(module.ShiftAlarmTransportRequest(action="shuffle"), owner_request())
        self.assertEqual(raised.exception.status_code, 400)

    def test_non_owner_cannot_control_volume_or_playback(self):
        with self.assertRaises(HTTPException) as raised:
            module.get_shift_alarm_volume(signed_in_request())
        self.assertEqual(raised.exception.status_code, 403)
        with self.assertRaises(HTTPException) as raised:
            module.set_shift_alarm_volume(module.ShiftAlarmVolumeRequest(percent=50), signed_in_request())
        self.assertEqual(raised.exception.status_code, 403)
        with self.assertRaises(HTTPException) as raised:
            module.play_shift_alarm_media(module.ShiftAlarmPlayRequest(playlist="favorites"), signed_in_request())
        self.assertEqual(raised.exception.status_code, 403)
        with self.assertRaises(HTTPException) as raised:
            module.shift_alarm_media_transport(module.ShiftAlarmTransportRequest(action="next"), signed_in_request())
        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
