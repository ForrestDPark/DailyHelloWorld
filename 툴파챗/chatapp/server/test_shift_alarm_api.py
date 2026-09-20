import asyncio
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


async def _never_disconnected():
    return False


def owner_request():
    return SimpleNamespace(
        state=SimpleNamespace(user=None, can_write=True, share_guest=False),
        is_disconnected=_never_disconnected,
    )


def signed_in_request(username="tester"):
    return SimpleNamespace(
        state=SimpleNamespace(
            user={"username": username, "is_owner": False}, can_write=True, share_guest=False
        ),
        is_disconnected=_never_disconnected,
    )


class ShiftAlarmApiTests(unittest.TestCase):
    def test_read_only_subapps_allow_signed_in_users(self):
        module._require_signed_in_user(signed_in_request())
        with self.assertRaises(HTTPException) as raised:
            module._require_signed_in_user(SimpleNamespace(state=SimpleNamespace(user=None, can_write=False, share_guest=True)))
        self.assertEqual(raised.exception.status_code, 401)

    def test_owner_only_actions_stay_closed_to_regular_users(self):
        with self.assertRaises(HTTPException) as raised:
            module._require_owner(signed_in_request())
        self.assertEqual(raised.exception.status_code, 403)

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

    def test_reminder_definition_crud_uses_owner_editor_file(self):
        status = {"reminder_schedule": [{"key": "laundry", "label": "빨래", "time": "11:30"}]}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(module, "SHIFT_ALARM_REMINDER_EDITOR_FILE", Path(directory) / "editor.json"), \
             patch.object(module, "_read_shift_alarm_status", return_value=status):
            created = module.create_shift_alarm_reminder(module.ReminderDefinitionUpdate(
                label="물 마시기", time="09:10", recurrence_unit="days",
                recurrence_interval=2, recurrence_anchor="2026-09-20",
            ), owner_request())
            payload = module._read_reminder_editor()
            self.assertTrue(payload["items"][created["key"]]["custom"])
            updated = module.update_shift_alarm_reminder("laundry", module.ReminderDefinitionUpdate(
                label="빨래 돌리기", time="12:00", recurrence_unit="weeks",
                recurrence_interval=1, recurrence_anchor="2026-09-20",
            ), owner_request())
            self.assertTrue(updated["ok"])
            module.delete_shift_alarm_reminder_definition("laundry", owner_request())
            self.assertTrue(module._read_reminder_editor()["items"]["laundry"]["deleted"])

    def test_automatic_schedule_saves_profile_time_without_deleting_rule(self):
        status = {"reminder_schedule": [{
            "key": "wake_shift", "label": "기상 알람", "auto_schedule": True,
            "default_recurrence_text": "선택한 근무 유형의 근무일마다",
            "times": {"Day": "02:55"}, "editable": True,
        }]}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(module, "SHIFT_ALARM_REMINDER_EDITOR_FILE", Path(directory) / "editor.json"), \
             patch.object(module, "_read_shift_alarm_status", return_value=status):
            result = module.update_shift_alarm_reminder("wake_shift", module.ReminderDefinitionUpdate(
                label="기상 알람", time="03:10", profile="Day",
            ), owner_request())
            self.assertEqual(result["profile"], "Day")
            saved = module._read_reminder_editor()["items"]["wake_shift"]
            self.assertEqual(saved["profile_times"]["Day"], {"hour": 3, "minute": 10})

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

    def test_wake_alarm_worker_endpoint_queues_the_same_light_pipeline_turn(self):
        """★ 2026-09-16: ShiftAlarm이 기상 알람 시각에 세션 쿠키 없이도 손무의
        라이트 분석을 트리거할 수 있어야 한다 — WORKER_TOKEN 인증 엔드포인트가
        소유자 버튼(start_shift_alarm_sunzi_analysis)과 같은 결과를 내는지 확인."""
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "chat.db"
            conn = self.pipeline_conn(db_path)
            with patch.object(module, "get_conn", return_value=conn), \
                 patch.object(module, "WORKER_TOKEN", "secret-token"), \
                 patch.object(module, "SUNZI_PIPELINE_LOCK_DIR", Path(directory) / "no-lock"):
                result = module.worker_start_sunzi_light_analysis(authorization="Bearer secret-token")
            self.assertEqual(result["mode"], "light")
            check = sqlite3.connect(db_path)
            turn = check.execute("SELECT persona_name,room_id,status FROM pending_turns").fetchone()
            check.close()
        self.assertEqual(turn, ("손무", module.SUNZI_DISCUSSION_ROOM_ID, "pending"))

    def test_wake_alarm_worker_endpoint_rejects_a_bad_token(self):
        with patch.object(module, "WORKER_TOKEN", "secret-token"), \
             self.assertRaises(HTTPException) as raised:
            module.worker_start_sunzi_light_analysis(authorization="Bearer wrong-token")
        self.assertEqual(raised.exception.status_code, 401)

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

    def test_running_video_reports_real_staging_bytes_for_legacy_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job_dir = root / "staging" / "job"
            job_dir.mkdir(parents=True)
            (job_dir / "video.mp4").write_bytes(b"1234567")
            status_file = root / "status.json"
            status_file.write_text(json.dumps({
                "job_id": "job", "state": "running", "stage": "영상 정보를 확인하는 중",
                "progress": 1, "pid": 123,
            }), encoding="utf-8")
            with patch.object(module, "SHIFT_ALARM_VIDEO_DIR", root), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_STATUS_FILE", status_file), \
                 patch("os.kill", return_value=None):
                status = module._shift_alarm_video_status()
        self.assertEqual(status["downloaded_bytes"], 7)

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
                async def consume():
                    return b"".join([chunk async for chunk in response.body_iterator])
                body = asyncio.run(consume())
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.headers["content-range"], "bytes 2-5/10")
        self.assertEqual(response.headers["content-length"], "4")
        self.assertEqual(response.media_type, "application/octet-stream")
        self.assertIn('attachment; filename="video-', response.headers["content-disposition"])
        self.assertEqual(body, b"2345")

    def test_safari_download_page_explains_the_external_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            files = Path(directory)
            video = files / "KSBJ-108_긴제목.mp4"
            video.write_bytes(b"video")
            with patch.object(module, "SHIFT_ALARM_VIDEO_FILES", files):
                file_id = module._shift_alarm_av4_id(video)
                response = module.shift_alarm_safari_download_page(file_id, owner_request())
        body = response.body.decode("utf-8")
        self.assertIn("오른쪽 아래 나침반 아이콘", body)
        self.assertIn(f'/api/shift-alarm/video-library/{file_id}/file', body)
        self.assertIn("KSBJ-108.mp4", body)

    def test_disconnect_mid_stream_is_reported_as_interrupted_not_complete(self):
        """★ 2026-09-14: "백그라운드로 넘어가면 몇 분 뒤 다운로드 실패가
        뜨는데 앱에는 성공으로 뜬다" — 클라이언트가 이미 연결을 끊었는데도
        읽기 루프가 그걸 모르고 파일을 끝까지 읽어 completed=True로 잘못
        보고했다(서버가 OS 소켓 버퍼에 쓰는 것과 클라이언트가 실제로 받는
        것은 별개). request.is_disconnected()를 매 청크마다 확인해서
        끊기면 즉시 멈추고 interrupted로 정직하게 기록해야 한다."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = root / "av4"
            files.mkdir()
            video = files / "큰파일.mp4"
            video.write_bytes(b"0" * (3 * 1024 * 1024))
            db = root / "downloads.db"
            with patch.object(module, "SHIFT_ALARM_VIDEO_DIR", root), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_FILES", files), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_DB", db):
                file_id = module._shift_alarm_av4_id(video)
                calls = {"n": 0}

                async def is_disconnected():
                    calls["n"] += 1
                    return calls["n"] > 1

                request = SimpleNamespace(
                    state=SimpleNamespace(user=None, can_write=True, share_guest=False),
                    is_disconnected=is_disconnected,
                )
                response = module.download_shift_alarm_library_video(file_id, request, None)

                async def consume():
                    return b"".join([chunk async for chunk in response.body_iterator])

                body = asyncio.run(consume())
                state = module._shift_alarm_transfer_states()[file_id]
        self.assertLess(len(body), 3 * 1024 * 1024, "연결이 끊긴 뒤에는 더 읽으면 안 된다")
        self.assertEqual(state["state"], "interrupted")

    def test_ios_download_filename_uses_short_title_code(self):
        path = Path("KSBJ-108-아주 긴 한글 제목과 출연자 이름.mp4")
        self.assertEqual(module._shift_alarm_ios_filename(path), "KSBJ-108.mp4")
        fallback = module._shift_alarm_ios_filename(Path("작품 코드 없는 긴 제목.mp4"))
        self.assertRegex(fallback, r"^video-[a-f0-9]{10}\.mp4$")

    def test_video_file_is_owner_only(self):
        with self.assertRaises(HTTPException) as raised:
            module.download_shift_alarm_video("job", signed_in_request("other-user"), None)
        self.assertEqual(raised.exception.status_code, 403)

    def test_av4_library_lists_only_direct_mp4_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "첫째.mp4").write_bytes(b"123")
            (root / "제외.mkv").write_bytes(b"456")
            (root / "nested").mkdir()
            (root / "nested" / "제외.mp4").write_bytes(b"789")
            with patch.object(module, "SHIFT_ALARM_VIDEO_FILES", root):
                files = module._shift_alarm_av4_files()
                file_id = module._shift_alarm_av4_id(files[0])
                resolved = module._shift_alarm_av4_file(file_id)
        self.assertEqual([path.name for path in files], ["첫째.mp4"])
        self.assertEqual(resolved.name, "첫째.mp4")

    def test_video_processing_history_table_migrates_missing_columns(self):
        """★ 2026-09-15: "영상가져오기가 다운로드 파일이 하나도 안보이는데
        왜 그렇지" 신고의 실제 원인 — safari_completed_at 컬럼이 코드에
        추가되기 전에 이미 video_processing_history 테이블이 있던 환경에서는
        `CREATE TABLE IF NOT EXISTS`가 조용히 아무것도 안 해서 그 컬럼이
        영원히 안 생기고, SELECT * 결과를 history["safari_completed_at"]로
        읽던 상태 API가 KeyError로 통째로 500이 나 목록이 비어 보였다."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db_path = root / "downloads.db"
            # safari_completed_at 컬럼이 없는 옛 스키마를 그대로 재현한다.
            legacy = sqlite3.connect(db_path)
            legacy.execute("""
                CREATE TABLE video_processing_history (
                    file_id TEXT PRIMARY KEY, filename TEXT NOT NULL,
                    subtitle_state TEXT, subtitle_progress REAL, subtitle_stage TEXT,
                    subtitle_started_at TEXT, subtitle_completed_at TEXT,
                    photo_shortcut_at TEXT, updated_at TEXT NOT NULL
                )
            """)
            legacy.execute(
                "INSERT INTO video_processing_history (file_id,filename,updated_at) VALUES (?,?,?)",
                ("abc123", "영상.mp4", module._now()),
            )
            legacy.commit()
            legacy.close()
            with patch.object(module, "SHIFT_ALARM_VIDEO_DIR", root), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_DB", db_path):
                history = module._shift_alarm_processing_history()
        self.assertIn("abc123", history)
        self.assertIsNone(history["abc123"]["safari_completed_at"])

    def test_video_status_survives_legacy_processing_history_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = root / "av4"
            files.mkdir()
            video = files / "영상.mp4"
            video.write_bytes(b"1234")
            db_path = root / "downloads.db"
            legacy = sqlite3.connect(db_path)
            legacy.execute("""
                CREATE TABLE video_processing_history (
                    file_id TEXT PRIMARY KEY, filename TEXT NOT NULL,
                    subtitle_state TEXT, subtitle_progress REAL, subtitle_stage TEXT,
                    subtitle_started_at TEXT, subtitle_completed_at TEXT,
                    photo_shortcut_at TEXT, updated_at TEXT NOT NULL
                )
            """)
            file_id = module._shift_alarm_av4_id(video)
            legacy.execute(
                "INSERT INTO video_processing_history (file_id,filename,subtitle_state,updated_at) "
                "VALUES (?,?,?,?)", (file_id, video.name, "running", module._now()),
            )
            legacy.commit()
            legacy.close()
            with patch.object(module, "SHIFT_ALARM_VIDEO_DIR", root), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_FILES", files), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_DB", db_path), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_STATUS_FILE", root / "status.json"):
                result = module.shift_alarm_video_download_status(owner_request())
        self.assertEqual(len(result["downloads"]), 1)
        self.assertEqual(result["downloads"][0]["subtitle_state"], "running")
        self.assertIsNone(result["downloads"][0]["safari_completed_at"])

    def test_av4_library_download_is_owner_only(self):
        with self.assertRaises(HTTPException) as raised:
            module.download_shift_alarm_library_video(
                "a" * 24, signed_in_request("other-user"), None
            )
        self.assertEqual(raised.exception.status_code, 403)

    def test_extract_subtitle_copies_only_the_selected_file_into_an_isolated_folder(self):
        """subtitle_notion_epub_only.sh는 폴더 안 영상을 전부 처리하므로, av4에
        다른 파일이 더 있어도 고른 영상 하나만 격리된 작업 폴더에 복사돼
        넘어가야 한다(원본은 그대로 남아 iPhone 전송 기능과 안 부딪힘)."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            av4 = root / "av4"
            av4.mkdir()
            (av4 / "다른영상.mp4").write_bytes(b"other")
            selected = av4 / "선택한영상.mp4"
            selected.write_bytes(b"selected-bytes")
            script = root / "subtitle_notion_epub_only.sh"
            script.write_text("#!/bin/zsh\n", encoding="utf-8")
            subtitle_dir = root / "subtitle_extract"
            file_id = module._shift_alarm_av4_id(selected)
            with patch.object(module, "SHIFT_ALARM_VIDEO_FILES", av4), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_DIR", root), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_DB", root / "downloads.db"), \
                 patch.object(module, "JP_SUBTITLE_STAGE2_SCRIPT", script), \
                 patch.object(module, "SHIFT_ALARM_SUBTITLE_DIR", subtitle_dir), \
                 patch.object(module, "SHIFT_ALARM_SUBTITLE_STATUS_FILE", subtitle_dir / "status.json"), \
                 patch("subprocess.Popen") as popen:
                result = module.act_on_shift_alarm_library_video(
                    file_id, module.ShiftAlarmVideoActionRequest(action="extract_subtitle"),
                    owner_request(),
                )
            popen_args = popen.call_args.args[0]
            work_dir = Path(popen_args[-1])
            work_dir_entries = [path.name for path in work_dir.iterdir()]
            copied_bytes = (work_dir / "선택한영상.mp4").read_bytes()
            original_survives = selected.is_file()
            status = json.loads((subtitle_dir / "status.json").read_text(encoding="utf-8"))
        self.assertTrue(result["ok"])
        self.assertEqual(popen_args[:2], ["zsh", str(script)])
        self.assertEqual(work_dir_entries, ["선택한영상.mp4"])
        self.assertEqual(copied_bytes, b"selected-bytes")
        self.assertTrue(original_survives, "원본 av4 파일은 그대로 남아 있어야 한다")
        self.assertEqual(status["state"], "running")
        self.assertEqual(status["filename"], "선택한영상.mp4")

    def test_extract_subtitle_rejects_when_another_extraction_is_running(self):
        with tempfile.TemporaryDirectory() as directory:
            av4 = Path(directory)
            video = av4 / "영상.mp4"
            video.write_bytes(b"1234")
            file_id = module._shift_alarm_av4_id(video)
            with patch.object(module, "SHIFT_ALARM_VIDEO_FILES", av4), \
                 patch.object(module, "_shift_alarm_subtitle_status", return_value={"state": "running"}), \
                 self.assertRaises(HTTPException) as raised:
                module.act_on_shift_alarm_library_video(
                    file_id, module.ShiftAlarmVideoActionRequest(action="extract_subtitle"),
                    owner_request(),
                )
        self.assertEqual(raised.exception.status_code, 409)

    def test_subtitle_progress_takes_the_furthest_marker_and_never_regresses_across_parts(self):
        """긴 영상은 여러 구간(파트)으로 나뉘어 처리되므로 1~2번 마커가 파트마다
        반복된다 — 로그 전체에서 가장 앞선 마커만 골라야 진행률이 뒤로 가지 않는다."""
        with tempfile.TemporaryDirectory() as directory:
            log_dir = Path(directory)
            (log_dir / "20260915_110421_job123.log").write_text(
                "📝 Whisper 자막 분석 중...\n⏱ Whisper 자막 생성 소요: 20초\n"
                "📚 EPUB 생성 중...\n"
                "📺 2편 / 2편\n📝 Whisper 자막 분석 중...\n",  # 2편에서 마커가 다시 나와도 역행 금지
                encoding="utf-8",
            )
            with patch.object(module, "JP_SUBTITLE_LOG_DIR", log_dir):
                result = module._shift_alarm_subtitle_log_progress("job123")
        self.assertEqual(result[0], 60)

    def test_subtitle_progress_is_none_before_the_log_file_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(module, "JP_SUBTITLE_LOG_DIR", Path(directory)):
                result = module._shift_alarm_subtitle_log_progress("no-such-job")
        self.assertIsNone(result)

    def test_video_status_includes_ios_filename_for_finding_the_download_later(self):
        """★ 2026-09-14: "폰에서 아무리 찾아도 파일이 없다"는 신고의 실제 원인 —
        '파일명 복사' 버튼이 원래 긴 파일명(item.filename)을 복사했는데, 정작
        Safari는 짧은 작품 코드(_shift_alarm_ios_filename)로 저장하니 그
        이름으로는 Files 앱에서 절대 못 찾는다. 목록 응답에 실제 저장될
        이름을 포함시켜 화면에 항상 보이게 하고, 복사 버튼도 이 값을 쓰도록
        고쳤다(app.js)."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = root / "av4"
            files.mkdir()
            video = files / "KSBJ-108-아주 긴 한글 제목과 출연자 이름.mp4"
            video.write_bytes(b"1234")
            with patch.object(module, "SHIFT_ALARM_VIDEO_DIR", root), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_FILES", files), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_DB", root / "downloads.db"), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_STATUS_FILE", root / "status.json"):
                (root / "status.json").write_text(json.dumps({"state": "idle", "progress": 0}), encoding="utf-8")
                result = module.shift_alarm_video_download_status(owner_request())
        self.assertEqual(result["downloads"][0]["ios_filename"], "KSBJ-108.mp4")

    def test_video_status_matches_managed_db_row_to_av4_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = root / "av4"
            files.mkdir()
            video = files / "완성.mp4"
            video.write_bytes(b"1234")
            db = root / "downloads.db"
            status_file = root / "status.json"
            status_file.write_text(json.dumps({"state": "idle", "progress": 0}), encoding="utf-8")
            with patch.object(module, "SHIFT_ALARM_VIDEO_DIR", root), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_FILES", files), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_DB", db), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_STATUS_FILE", status_file):
                with module._shift_alarm_video_db() as conn:
                    conn.execute(
                        "INSERT INTO video_downloads "
                        "(job_id,owner_username,filename,file_path,size_bytes,created_at,completed_at,expires_at) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        ("job", "local-owner", video.name, str(video), 4, module._now(),
                         module._now(), "2999-01-01T00:00:00+00:00"),
                    )
                result = module.shift_alarm_video_download_status(owner_request())
        self.assertEqual(len(result["downloads"]), 1)
        self.assertTrue(result["downloads"][0]["temporary"])
        self.assertEqual(result["downloads"][0]["filename"], "완성.mp4")

    def test_iphone_transfer_progress_is_persisted_per_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "downloads.db"
            video = root / "video.mp4"
            video.write_bytes(b"0" * 10)
            with patch.object(module, "SHIFT_ALARM_VIDEO_DIR", root), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_DB", db):
                transfer_id = module._shift_alarm_transfer_start("a" * 24, video, 0, 10)
                module._shift_alarm_transfer_update("a" * 24, transfer_id, "downloading", 6)
                state = module._shift_alarm_transfer_states()["a" * 24]
        self.assertEqual(state["state"], "downloading")
        self.assertEqual(state["sent_bytes"], 6)
        self.assertEqual(state["total_bytes"], 10)

    def test_video_processing_history_is_persisted_per_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "downloads.db"
            with patch.object(module, "SHIFT_ALARM_VIDEO_DIR", root), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_DB", db):
                module._shift_alarm_update_processing(
                    "a" * 24, "영상.mp4", subtitle_state="running",
                    subtitle_progress=35, subtitle_stage="Whisper 자막 분석 중",
                )
                module._shift_alarm_update_processing(
                    "a" * 24, "영상.mp4", subtitle_state="complete",
                    subtitle_progress=100, subtitle_completed_at="2026-09-15T12:00:00+00:00",
                )
                history = module._shift_alarm_processing_history()["a" * 24]
        self.assertEqual(history["subtitle_state"], "complete")
        self.assertEqual(history["subtitle_progress"], 100)
        self.assertEqual(history["subtitle_stage"], "Whisper 자막 분석 중")

    def test_photo_shortcut_action_records_execution_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = root / "av4"
            files.mkdir()
            video = files / "영상.mp4"
            video.write_bytes(b"1234")
            db = root / "downloads.db"
            with patch.object(module, "SHIFT_ALARM_VIDEO_DIR", root), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_FILES", files), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_DB", db):
                file_id = module._shift_alarm_av4_id(video)
                result = module.act_on_shift_alarm_library_video(
                    file_id,
                    module.ShiftAlarmVideoActionRequest(action="mark_photo_shortcut"),
                    owner_request(),
                )
                history = module._shift_alarm_processing_history()[file_id]
        self.assertTrue(result["ok"])
        self.assertEqual(history["photo_shortcut_at"], result["executed_at"])

    def test_completed_iphone_transfer_schedules_owner_web_push(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "downloads.db"
            video = root / "HODV-21738.mp4"
            video.write_bytes(b"0123456789")
            with patch.object(module, "SHIFT_ALARM_VIDEO_DIR", root), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_DB", db), \
                 patch("threading.Thread") as thread:
                response = module._shift_alarm_stream_file(
                    video, None, owner_request(), "a" * 24, "local-owner"
                )

                async def consume():
                    return b"".join([chunk async for chunk in response.body_iterator])

                body = asyncio.run(consume())
                history = module._shift_alarm_processing_history()["a" * 24]
        self.assertEqual(body, b"0123456789")
        self.assertEqual(thread.call_args.kwargs["target"], module._shift_alarm_notify_transfer_complete)
        self.assertEqual(thread.call_args.kwargs["args"], ("local-owner", video.name))
        self.assertIsNotNone(history["safari_completed_at"])
        thread.return_value.start.assert_called_once()

    def test_cancel_transfer_unsticks_a_stalled_downloading_row(self):
        """★ 2026-09-14: "전송중에서 멈춰있는데 어떻게하지" — 터널이 전송 도중
        연결을 끊으면 스트리밍 제너레이터의 finally가 실행되지 않아
        video_transfers 행이 영원히 "downloading"으로 남고, 프런트엔드는 그
        상태를 보고 재생버튼을 계속 비활성화해서 사용자가 재시도할 방법이
        없었다. cancel_transfer 액션으로 강제로 "interrupted"로 돌려
        버튼을 다시 누를 수 있게 한다."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = root / "av4"
            files.mkdir()
            video = files / "완성.mp4"
            video.write_bytes(b"1234")
            db = root / "downloads.db"
            with patch.object(module, "SHIFT_ALARM_VIDEO_DIR", root), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_FILES", files), \
                 patch.object(module, "SHIFT_ALARM_VIDEO_DB", db):
                file_id = module._shift_alarm_av4_id(video)
                module._shift_alarm_transfer_start(file_id, video, 0, 1_000_000)
                result = module.act_on_shift_alarm_library_video(
                    file_id, module.ShiftAlarmVideoActionRequest(action="cancel_transfer"), owner_request()
                )
                state = module._shift_alarm_transfer_states()[file_id]
                file_still_exists = video.exists()
        self.assertTrue(result["ok"])
        self.assertEqual(state["state"], "interrupted")
        self.assertTrue(file_still_exists, "원본 영상 파일은 건드리지 않아야 한다")

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

    def test_random_sites_exclude_non_web_bookmarks(self):
        bookmarks_payload = {"roots": {"bookmark_bar": {"type": "folder", "name": "天", "children": [
            {"type": "url", "url": "javascript:alert(1)"},
            {"type": "url", "url": "file:///private/tmp/example"},
            {"type": "url", "url": "https://safe.example/video"},
        ]}}}
        with patch("builtins.open", mock_open(read_data=json.dumps(bookmarks_payload))), \
             patch.object(module, "_shift_alarm_load_random_bookmark_history", return_value=[]), \
             patch.object(module, "_shift_alarm_save_random_bookmark_history"):
            result = module._shift_alarm_pick_random_bookmarks(3)
        self.assertEqual(result, ["https://safe.example/video"])

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
