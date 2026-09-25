"""★ 2026-09-15: "미연시 시스템 하나 만들어봤으면 좋겠어" 요청으로 만든
선택지+호감도+멀티 엔딩 미니게임의 엔진(상태 저장·전환) 테스트."""
import json
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from server import app, db, dating_sim_story


def request(username="reader"):
    return SimpleNamespace(state=SimpleNamespace(user={"username": username, "is_owner": False}, can_write=True, share_guest=False))


class DatingSimApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(db, "DB_PATH", str(Path(self.temp.name) / "chat.db"))
        self.patch.start()
        db.init_db()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def choice_index(self, username, location, positive):
        state = app.dating_sim_state(request(username))
        story = app._dating_story(None, username)
        choices = story["scenes"][state["day"]][location]["choices"]
        return next(
            index for index, choice in enumerate(choices)
            if (choice["affection"] > 0) is positive
        )

    def test_nested_sone_scene_image_is_served_but_unlisted_path_is_blocked(self):
        response = app.dating_sim_static(
            "static/sone-486/rainy-evening.png", request()
        )
        self.assertTrue(str(response.path).endswith("static/sone-486/rainy-evening.png"))
        with self.assertRaises(HTTPException) as raised:
            app.dating_sim_static("static/sone-486/not-allowed.png", request())
        self.assertEqual(raised.exception.status_code, 404)

    def test_generated_scene_image_route_only_serves_manifest_files(self):
        root = Path(self.temp.name) / "work" / "dating_sim_images"
        root.mkdir(parents=True)
        image = root / "portrait.png"
        image.write_bytes(b"png")
        (root / "manifest.json").write_text(json.dumps({
            "portrait": "portrait.png", "assignments": {"1:first": "portrait.png"}
        }), encoding="utf-8")
        with patch.object(dating_sim_story, "_find_book", return_value=Path("book.epub")), \
             patch.object(dating_sim_story, "_book_title", return_value="TEST"), \
             patch.object(dating_sim_story, "_find_library_folder", return_value=root.parent):
            response = app.dating_sim_generated_image("a" * 20, "portrait.png", request())
            self.assertEqual(Path(response.path), image)
            with self.assertRaises(HTTPException):
                app.dating_sim_generated_image("a" * 20, "../secret.png", request())

    def test_generated_image_history_includes_prompt_and_safe_references(self):
        root = Path(self.temp.name) / "work" / "dating_sim_images"
        root.mkdir(parents=True)
        for filename in ("portrait.png", "scene-123456789abc.png"):
            (root / filename).write_bytes(b"png")
        for filename in ("reference-111111111111.jpg", "reference-222222222222.jpg"):
            (root / filename).write_bytes(b"jpg")
        (root / "manifest.json").write_text(json.dumps({
            "portrait": "portrait.png", "portrait_provider": "comfyui",
            "portrait_prompt": "portrait prompt", "portrait_reference": "reference-111111111111.jpg",
            "assignments": {"1:first": "scene-123456789abc.png"},
            "scenes": {"1:first": {"file": "scene-123456789abc.png",
                "provider": "comfyui", "day": 1, "location": "first",
                "prompt": "scene prompt", "reference_file": "reference-222222222222.jpg",
                "reference_source": "images/part1_scene002.jpg"}},
        }), encoding="utf-8")
        with patch.object(dating_sim_story, "_find_library_folder", return_value=root.parent):
            history = dating_sim_story.load_generated_images("TEST", "a" * 20)
        self.assertEqual(len(history["gallery"]), 2)
        self.assertEqual(history["gallery"][0]["prompt"], "portrait prompt")
        self.assertTrue(history["gallery"][0]["reference_url"].endswith("/reference-111111111111.jpg"))
        self.assertTrue(history["gallery"][1]["reference_url"].endswith("/reference-222222222222.jpg"))
        self.assertEqual(history["gallery"][1]["reference_source"], "images/part1_scene002.jpg")
        self.assertEqual(history["gallery"][1]["prompt"], "scene prompt")
        self.assertIn("photorealistic adult Japanese woman", history["gallery"][1]["effective_prompt"])
        self.assertEqual(history["gallery"][1]["generation_settings"]["steps"], 25)
        self.assertEqual(history["gallery"][1]["generation_settings"]["denoise"], 0.48)
        self.assertEqual(history["gallery"][1]["generation_settings"]["model"], "majicmixRealistic_v7.safetensors")
        self.assertIn("txt2img", history["gallery"][1]["generation_settings"]["composition_pass"])

        with patch.object(dating_sim_story, "_find_book", return_value=Path("book.epub")), \
             patch.object(dating_sim_story, "_book_title", return_value="TEST"), \
             patch.object(dating_sim_story, "_find_library_folder", return_value=root.parent):
            owner = SimpleNamespace(state=SimpleNamespace(
                user={"username": "admin", "is_owner": True}, can_write=True, share_guest=False))
            response = app.dating_sim_generated_image_reference("a" * 20, "reference-222222222222.jpg", owner)
            self.assertEqual(Path(response.path), root / "reference-222222222222.jpg")
            with self.assertRaises(HTTPException) as denied:
                app.dating_sim_generated_image_reference("a" * 20, "reference-222222222222.jpg", request())
            self.assertEqual(denied.exception.status_code, 403)

    def test_resolve_book_work_dir_matches_book_story_id_to_library_folder(self):
        folder = Path(self.temp.name) / "library" / "TEST"
        book_id = "c" * 20
        with patch.object(dating_sim_story, "_find_book", return_value=Path("book.epub")), \
             patch.object(dating_sim_story, "_book_title", return_value="TEST"), \
             patch.object(dating_sim_story, "_find_library_folder", return_value=folder):
            self.assertEqual(dating_sim_story.resolve_book_work_dir(f"book:{book_id}"), (book_id, folder))
        self.assertEqual(dating_sim_story.resolve_book_work_dir(None), (None, None))
        self.assertEqual(dating_sim_story.resolve_book_work_dir("소이"), (None, None))
        with patch.object(dating_sim_story, "_find_book", return_value=None):
            self.assertEqual(dating_sim_story.resolve_book_work_dir(f"book:{book_id}"), (book_id, None))

    def test_generate_images_endpoints_start_track_and_reject_owner_only(self):
        # ★ 2026-09-23: "시나리오트리에 이미지생성하기 버튼 만들어서 이미지만
        # 생성해서 올릴수있게하자" 요청 — 서브프로세스를 실제로 띄우지 않고
        # 가짜 Popen으로 시작→진행 중→완료 상태 전이와 소유자 전용 접근을
        # 검증한다.
        work_dir = Path(self.temp.name) / "work"
        work_dir.mkdir()
        book_id = "d" * 20
        owner = SimpleNamespace(state=SimpleNamespace(
            user={"username": "admin", "is_owner": True}, can_write=True, share_guest=False))

        class FakeProcess:
            def __init__(self):
                self.returncode = None

            def poll(self):
                return self.returncode

        fake_process = FakeProcess()
        with patch.object(dating_sim_story, "resolve_book_work_dir", return_value=(book_id, work_dir)), \
             patch.object(app.subprocess, "Popen", return_value=fake_process) as popen:
            started = app.dating_sim_generate_images_start(owner, f"book:{book_id}")
            self.assertEqual(started, {"status": "started"})
            command = popen.call_args[0][0]
            self.assertEqual(command[0], app.DATING_SIM_IMAGE_PYTHON)
            self.assertEqual(command[1], app.DATING_SIM_IMAGE_SCRIPT)
            self.assertEqual(command[2], str(work_dir))
            self.assertTrue((work_dir / "dating_sim_images" / "generation.log").is_file())

            status = app.dating_sim_generate_images_status(owner, f"book:{book_id}")
            self.assertEqual(status["running"], True)

            with self.assertRaises(HTTPException) as busy:
                app.dating_sim_generate_images_start(owner, f"book:{book_id}")
            self.assertEqual(busy.exception.status_code, 409)

            with self.assertRaises(HTTPException) as denied:
                app.dating_sim_generate_images_status(request(), f"book:{book_id}")
            self.assertEqual(denied.exception.status_code, 403)

            fake_process.returncode = 0
            status = app.dating_sim_generate_images_status(owner, f"book:{book_id}")
            self.assertEqual(status["running"], False)
            self.assertEqual(status["returncode"], 0)
            # 완료 처리된 작업은 다시 시작할 수 있어야 한다(잔여 job 항목이 안 남음).
            started_again = app.dating_sim_generate_images_start(owner, f"book:{book_id}")
            self.assertEqual(started_again, {"status": "started"})

    def test_generate_images_force_and_force_key_build_the_right_command(self):
        # ★ 2026-09-23: "이미지 재생성 버튼... 전체재생성도 있고 사진눌렀을때
        # 이사진만 재생성하기 버튼있게해줘" 요청 — force=true면 --force가,
        # force_key면 --force-key <키>가 서브프로세스 명령에 실제로 실리는지,
        # 그리고 이상한 force_key는 400으로 막히는지 검증한다.
        work_dir = Path(self.temp.name) / "work2"
        work_dir.mkdir()
        book_id = "e" * 20
        owner = SimpleNamespace(state=SimpleNamespace(
            user={"username": "admin", "is_owner": True}, can_write=True, share_guest=False))

        class FakeProcess:
            returncode = 0

            def poll(self):
                return self.returncode

        with patch.object(dating_sim_story, "resolve_book_work_dir", return_value=(book_id, work_dir)), \
             patch.object(app.subprocess, "Popen", return_value=FakeProcess()) as popen:
            app.dating_sim_generate_images_start(owner, f"book:{book_id}", force=True)
            self.assertIn("--force", popen.call_args[0][0])

            app.dating_sim_generate_images_start(owner, f"book:{book_id}", force_key="1:first")
            command = popen.call_args[0][0]
            self.assertIn("--force-key", command)
            self.assertEqual(command[command.index("--force-key") + 1], "1:first")

            app.dating_sim_generate_images_start(owner, f"book:{book_id}", force_key="portrait")
            command = popen.call_args[0][0]
            self.assertEqual(command[command.index("--force-key") + 1], "portrait")

            with self.assertRaises(HTTPException) as bad:
                app.dating_sim_generate_images_start(owner, f"book:{book_id}", force_key="../etc/passwd")
            self.assertEqual(bad.exception.status_code, 400)

    def test_new_player_starts_at_day_one_with_base_affection_and_no_pending_scene(self):
        state = app.dating_sim_state(request())
        self.assertEqual(state["day"], 1)
        self.assertEqual(state["affection"], 50)
        self.assertFalse(state["completed"])
        self.assertNotIn("scene", state)
        self.assertEqual(len(state["locations"]), len(dating_sim_story.LOCATIONS))
        self.assertTrue(state["day_opening"])
        self.assertTrue(all(location["action"] != location["label"] for location in state["locations"]))

    def test_visiting_a_location_returns_that_scene_and_blocks_a_second_visit(self):
        state = app.dating_sim_visit(app.DatingSimLocationRequest(location="cafe"), request())
        self.assertEqual(state["scene"]["location"], "cafe")
        self.assertEqual(len(state["scene"]["choices"]), 2)
        with self.assertRaises(HTTPException) as raised:
            app.dating_sim_visit(app.DatingSimLocationRequest(location="park"), request())
        self.assertEqual(raised.exception.status_code, 409)

    def test_learning_progress_counts_only_after_last_line_is_seen(self):
        story = copy.deepcopy(dating_sim_story.story_for())
        story["id"] = "learning-progress-test"
        story["scenes"][1]["cafe"]["vocab_words"] = [
            {"ja": "約束", "reading": "やくそく", "ko": "약속"}
        ]
        story["scenes"][1]["cafe"]["expressions_used"] = [
            {"ja": "また会いましょう", "reading": "またあいましょう", "ko": "또 만나요"}
        ]
        story["scenes"][1]["cafe"]["grammar_used"] = [
            {"pattern": "～たらいい？", "explanation": "제안을 묻는다.",
             "evidence": "どうしたらいいですか"}
        ]
        with patch.object(app, "_dating_story", return_value=story):
            initial = app.dating_sim_state(request())
            self.assertEqual(initial["learning_progress"], {"seen": 0, "total": 3, "percent": 0})
            visited = app.dating_sim_visit(app.DatingSimLocationRequest(location="cafe"), request())
            self.assertEqual(visited["learning_progress"]["seen"], 0)
            result = app.dating_sim_seen(app.DatingSimRestartRequest(story_id=story["id"]), request())
            self.assertEqual(result["learning_progress"], {"seen": 3, "total": 3, "percent": 100})

    def test_visiting_an_unknown_location_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            app.dating_sim_visit(app.DatingSimLocationRequest(location="space station"), request())
        self.assertEqual(raised.exception.status_code, 400)

    def test_choosing_without_a_pending_scene_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            app.dating_sim_choose(app.DatingSimChoiceRequest(choice_index=0), request())
        self.assertEqual(raised.exception.status_code, 409)

    def test_positive_choice_raises_affection_and_advances_the_day(self):
        app.dating_sim_visit(app.DatingSimLocationRequest(location="cafe"), request())
        index = self.choice_index("reader", "cafe", True)
        state = app.dating_sim_choose(app.DatingSimChoiceRequest(choice_index=index), request())
        self.assertIn(state["choice_result"]["affection_delta"], range(7, 12))
        self.assertEqual(state["affection"], 50 + state["choice_result"]["affection_delta"])
        self.assertEqual(state["day"], 2)
        self.assertIsNone(state["pending_location"])

    def test_negative_choice_lowers_affection_and_clamps_at_zero(self):
        app.dating_sim_visit(app.DatingSimLocationRequest(location="cafe"), request())
        index = self.choice_index("reader", "cafe", False)
        state = app.dating_sim_choose(app.DatingSimChoiceRequest(choice_index=index), request())
        self.assertIn(state["choice_result"]["affection_delta"], range(-6, -1))
        self.assertEqual(state["affection"], 50 + state["choice_result"]["affection_delta"])

    def test_choice_scores_and_reactions_vary_by_scene(self):
        scores = {dating_sim_story.choice_scores(day, location, 1)
                  for day in range(1, 8) for location in ("cafe", "park", "school")}
        reactions = {dating_sim_story.choice_reaction(day, "cafe", 8, "story")
                     for day in range(1, 8)}
        self.assertGreater(len(scores), 3)
        self.assertGreater(len(reactions), 3)

    def test_out_of_range_choice_index_is_rejected(self):
        app.dating_sim_visit(app.DatingSimLocationRequest(location="cafe"), request())
        with self.assertRaises(HTTPException) as raised:
            app.dating_sim_choose(app.DatingSimChoiceRequest(choice_index=5), request())
        self.assertEqual(raised.exception.status_code, 400)

    def test_all_positive_choices_across_three_days_reach_the_best_ending(self):
        for _ in range(dating_sim_story.TOTAL_DAYS):
            app.dating_sim_visit(app.DatingSimLocationRequest(location="cafe"), request())
            index = self.choice_index("reader", "cafe", True)
            state = app.dating_sim_choose(app.DatingSimChoiceRequest(choice_index=index), request())
        self.assertTrue(state["completed"])
        self.assertEqual(state["ending"]["id"], "best")
        self.assertEqual(state["affection"], 100)

    def test_all_negative_choices_reach_the_normal_ending_and_stay_playable_after(self):
        for _ in range(dating_sim_story.TOTAL_DAYS):
            app.dating_sim_visit(app.DatingSimLocationRequest(location="park"), request())
            index = self.choice_index("reader", "park", False)
            state = app.dating_sim_choose(app.DatingSimChoiceRequest(choice_index=index), request())
        self.assertTrue(state["completed"])
        self.assertEqual(state["ending"]["id"], "normal")
        with self.assertRaises(HTTPException) as raised:
            app.dating_sim_visit(app.DatingSimLocationRequest(location="cafe"), request())
        self.assertEqual(raised.exception.status_code, 409)

    def test_restart_resets_progress_even_after_completion(self):
        for _ in range(dating_sim_story.TOTAL_DAYS):
            app.dating_sim_visit(app.DatingSimLocationRequest(location="school"), request())
            app.dating_sim_choose(app.DatingSimChoiceRequest(choice_index=0), request())
        state = app.dating_sim_restart(request())
        self.assertEqual(state["day"], 1)
        self.assertEqual(state["affection"], 50)
        self.assertFalse(state["completed"])

    def test_progress_is_isolated_per_account(self):
        app.dating_sim_visit(app.DatingSimLocationRequest(location="cafe"), request("alice"))
        app.dating_sim_choose(app.DatingSimChoiceRequest(choice_index=0), request("alice"))
        bob_state = app.dating_sim_state(request("bob"))
        self.assertEqual(bob_state["day"], 1)
        self.assertEqual(bob_state["affection"], 50)

    def test_regular_user_receives_character_image_and_numeric_affection(self):
        state = app.dating_sim_state(request("regular-user"))
        self.assertEqual(state["affection"], 50)
        self.assertEqual(state["character_image"], "/dating-sim/static/soi.png")
        self.assertIn("|", state["locations"] and dating_sim_story.SCENES[1]["cafe"]["lines"][0])

    def test_scene_starts_with_protagonist_narration_and_furigana(self):
        state = app.dating_sim_visit(app.DatingSimLocationRequest(location="cafe"), request())
        first_line = state["scene"]["lines"][0]
        self.assertEqual(first_line["speaker"], "narrator")
        self.assertIn("[名前|なまえ]", first_line["text"])
        self.assertNotIn("[約束|やくそく]", first_line["text"])


class DatingSimContentDatabaseTests(unittest.TestCase):
    """★ 2026-09-15: "스토리 시나리오전개쪽에서 데이터베이스 만들어주고
    ... 재밌는 서사와 스토리 대화 등등 에피소드를 다양하게" 요청 — 요일×장소
    조합마다 활동 대사가 하나뿐이라 장소 선택이 서사에 영향을 안 줬다.
    dating_sim_scenarios 테이블에 변형(variant)을 여러 개 두고 무작위로
    골라 재플레이 다양성을 주는 시딩·로딩 로직을 검증한다."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(db, "DB_PATH", str(Path(self.temp.name) / "chat.db"))
        self.patch.start()
        db.init_db()
        self.conn = db.get_conn()

    def tearDown(self):
        self.conn.close()
        self.patch.stop()
        self.temp.cleanup()

    def test_seed_is_idempotent(self):
        dating_sim_story.seed_dating_sim_content(self.conn)
        before = self.conn.execute("SELECT COUNT(*) AS n FROM dating_sim_scenarios").fetchone()["n"]
        dating_sim_story.seed_dating_sim_content(self.conn)
        after = self.conn.execute("SELECT COUNT(*) AS n FROM dating_sim_scenarios").fetchone()["n"]
        self.assertEqual(before, after)
        self.assertGreater(before, 0)

    def test_old_content_is_migrated_to_first_meeting_story(self):
        dating_sim_story.seed_dating_sim_content(self.conn)
        self.conn.execute(
            "INSERT INTO dating_sim_progress "
            "(username,character_id,day,affection,pending_location,completed,ending_id,"
            "created_at,updated_at,scenario_run) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("legacy-reader", dating_sim_story.CHARACTER_ID, 5, 82, "park", 0, None,
             "2026-09-15", "2026-09-15", 0),
        )
        self.conn.execute(
            "UPDATE dating_sim_characters SET content_version=1 WHERE character_id=?",
            (dating_sim_story.CHARACTER_ID,),
        )
        self.conn.execute(
            "UPDATE dating_sim_scenarios SET activity_line='기존 데이트 장면' "
            "WHERE character_id=? AND day=1",
            (dating_sim_story.CHARACTER_ID,),
        )
        self.conn.commit()
        dating_sim_story.seed_dating_sim_content(self.conn)
        version = self.conn.execute(
            "SELECT content_version FROM dating_sim_characters WHERE character_id=?",
            (dating_sim_story.CHARACTER_ID,),
        ).fetchone()["content_version"]
        first_day = self.conn.execute(
            "SELECT activity_line FROM dating_sim_scenarios "
            "WHERE character_id=? AND day=1 AND location_id='cafe' AND variant=1",
            (dating_sim_story.CHARACTER_ID,),
        ).fetchone()["activity_line"]
        self.assertEqual(version, dating_sim_story.CONTENT_VERSION)
        self.assertNotEqual(first_day, "기존 데이트 장면")
        self.assertIn("[彼女|かのじょ]", first_day)
        progress = self.conn.execute(
            "SELECT day,affection,pending_location,scenario_run FROM dating_sim_progress "
            "WHERE username='legacy-reader' AND character_id=?",
            (dating_sim_story.CHARACTER_ID,),
        ).fetchone()
        self.assertEqual(
            (progress["day"], progress["affection"], progress["pending_location"]),
            (1, 50, None),
        )
        self.assertEqual(progress["scenario_run"], 1)

    def test_day_one_establishes_that_they_are_strangers(self):
        dating_sim_story.seed_dating_sim_content(self.conn)
        story = dating_sim_story.load_story_from_db(
            self.conn, dating_sim_story.CHARACTER_ID, seed_key="first-meeting-check"
        )
        first_scene = "\n".join(story["scenes"][1]["cafe"]["lines"])
        self.assertIn("[初|はじ]めまして", first_scene)
        self.assertIn("[名前|なまえ]", first_scene)

    def test_day_one_explains_the_help_before_thanking_and_exchanges_contact(self):
        dating_sim_story.seed_dating_sim_content(self.conn)
        story = dating_sim_story.load_story_from_db(
            self.conn, dating_sim_story.CHARACTER_ID, seed_key="coherence-check"
        )
        for scene in story["scenes"][1].values():
            self.assertTrue(scene["lines"][0].lstrip().startswith("("))
            self.assertIn("ありがとうございました", scene["lines"][1])
            self.assertIn("[連絡先|れんらくさき]", scene["lines"][2])
            self.assertTrue(all("[連絡先|れんらくさき]" in choice["text"] for choice in scene["choices"]))

    def test_day_six_openings_agree_that_protagonist_missed_her_contact(self):
        openings = dating_sim_story.DAY_OPENINGS[6]
        self.assertTrue(all("ソイの[返事|へんじ]がない" not in opening for opening in openings))
        self.assertTrue(all("メッセージ" in opening for opening in openings))

    def test_difficulty_upgrade_preserves_current_progress(self):
        dating_sim_story.seed_dating_sim_content(self.conn)
        self.conn.execute(
            "INSERT INTO dating_sim_progress "
            "(username,character_id,day,affection,pending_location,completed,ending_id,"
            "created_at,updated_at,scenario_run) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("current-reader", dating_sim_story.CHARACTER_ID, 4, 71, None, 0, None,
             "2026-09-15", "2026-09-15", 2),
        )
        self.conn.execute(
            "UPDATE dating_sim_characters SET content_version=2 WHERE character_id=?",
            (dating_sim_story.CHARACTER_ID,),
        )
        self.conn.commit()
        dating_sim_story.seed_dating_sim_content(self.conn)
        progress = self.conn.execute(
            "SELECT day,affection,scenario_run FROM dating_sim_progress "
            "WHERE username='current-reader' AND character_id=?",
            (dating_sim_story.CHARACTER_ID,),
        ).fetchone()
        self.assertEqual(
            (progress["day"], progress["affection"], progress["scenario_run"]),
            (4, 71, 2),
        )

    def test_loaded_story_matches_story_for_shape(self):
        dating_sim_story.seed_dating_sim_content(self.conn)
        story = dating_sim_story.load_story_from_db(self.conn, dating_sim_story.CHARACTER_ID)
        for key in ("id", "name", "title", "character_image", "character_images",
                    "total_days", "locations", "scenes", "endings"):
            self.assertIn(key, story)
        self.assertEqual(story["total_days"], dating_sim_story.TOTAL_DAYS)
        self.assertEqual(set(story["locations"]), set(dating_sim_story.LOCATIONS))
        self.assertEqual(set(story["scenes"]), set(range(1, dating_sim_story.TOTAL_DAYS + 1)))
        for day_scenes in story["scenes"].values():
            for scene in day_scenes.values():
                # ★ 2026-09-17: "하루에 나누는 대화제한도 풀어버려" 요청으로
                # 일부 요일(중간 대화 턴이 있는 날)은 3줄보다 길어질 수 있다.
                self.assertGreaterEqual(len(scene["lines"]), 3)
                self.assertEqual(len(scene["choices"]), 2)

    def test_replaying_the_same_slot_can_surface_different_variants(self):
        dating_sim_story.seed_dating_sim_content(self.conn)
        # 1일차는 사고(활동 대사)가 먼저 나오도록 순서가 바뀌어 있어 인덱스 0을
        # 본다 — 나머지 요일은 인트로가 먼저라 인덱스 1(활동 대사)을 본다.
        seen = set()
        for _ in range(40):
            story = dating_sim_story.load_story_from_db(self.conn, dating_sim_story.CHARACTER_ID)
            seen.add(story["scenes"][1]["cafe"]["lines"][0])
        self.assertGreater(len(seen), 1, "40번을 다시 골라도 항상 같은 대사만 나오면 다양성이 없는 것")
        seen_other_day = set()
        for _ in range(40):
            story = dating_sim_story.load_story_from_db(self.conn, dating_sim_story.CHARACTER_ID)
            seen_other_day.add(story["scenes"][2]["cafe"]["lines"][1])
        self.assertGreater(len(seen_other_day), 1, "2일차도 40번을 다시 골라도 항상 같은 대사만 나오면 다양성이 없는 것")

    def test_same_account_keeps_the_same_variant_across_api_requests(self):
        first = app.dating_sim_visit(
            app.DatingSimLocationRequest(location="cafe"), request("stable-reader")
        )
        refreshed = app.dating_sim_state(request("stable-reader"))
        self.assertEqual(first["scene"]["lines"], refreshed["scene"]["lines"])
        self.assertEqual(first["scene"]["choices"], refreshed["scene"]["choices"])

    def test_seeded_story_loading_is_stable(self):
        dating_sim_story.seed_dating_sim_content(self.conn)
        first = dating_sim_story.load_story_from_db(
            self.conn, dating_sim_story.CHARACTER_ID, seed_key="reader:run-1"
        )
        second = dating_sim_story.load_story_from_db(
            self.conn, dating_sim_story.CHARACTER_ID, seed_key="reader:run-1"
        )
        self.assertEqual(first["scenes"], second["scenes"])

    def test_positive_choice_is_not_always_in_the_first_position(self):
        dating_sim_story.seed_dating_sim_content(self.conn)
        first_deltas = {
            dating_sim_story.load_story_from_db(
                self.conn, dating_sim_story.CHARACTER_ID, seed_key=f"reader-{number}"
            )["scenes"][1]["cafe"]["choices"][0]["affection"]
            for number in range(40)
        }
        self.assertTrue(any(delta > 0 for delta in first_deltas))
        self.assertTrue(any(delta < 0 for delta in first_deltas))

    def test_day_opening_is_stable_but_varies_between_runs(self):
        first = dating_sim_story._daily_openings("reader:run-1", dating_sim_story.CHARACTER_ID)
        repeated = dating_sim_story._daily_openings("reader:run-1", dating_sim_story.CHARACTER_ID)
        self.assertEqual(first, repeated)
        day_three_variants = {
            dating_sim_story._daily_openings(
                f"reader:run-{number}", dating_sim_story.CHARACTER_ID
            )[3]
            for number in range(20)
        }
        self.assertGreater(len(day_three_variants), 1)

    def test_reopening_before_choosing_a_location_gets_a_different_intro(self):
        """★ 2026-09-16: "미연시 시스템 누를때마다 인트로가 똑같은데 다양하게
        전개시작할수있게 무작위성좀 추가하면 좋겠어" 신고 — 장소를 아직 안 고른
        상태에서 화면을 다시 열면(재시작 없이) 매번 같은 도입부만 나왔다."""
        openings = {app.dating_sim_state(request("intro-variety"))["day_opening"] for _ in range(30)}
        self.assertGreater(len(openings), 1)

    def test_intro_stays_stable_once_a_location_is_chosen(self):
        """장소를 고른 뒤(pending_location 있음)에는 재조회해도 도입부가
        바뀌면 안 된다 — 선택·호감도와 무관한 문구지만 화면 깜빡임을 막는다."""
        app.dating_sim_visit(app.DatingSimLocationRequest(location="cafe"), request("intro-stable"))
        openings = {app.dating_sim_state(request("intro-stable"))["day_opening"] for _ in range(10)}
        self.assertEqual(len(openings), 1)

    def test_restart_advances_the_scenario_run(self):
        app.dating_sim_state(request("replay-reader"))
        app.dating_sim_restart(request("replay-reader"))
        row = self.conn.execute(
            "SELECT scenario_run FROM dating_sim_progress WHERE username=? AND character_id=?",
            ("replay-reader", dating_sim_story.CHARACTER_ID),
        ).fetchone()
        self.assertEqual(row["scenario_run"], 1)

    def test_hidden_event_is_rare_but_reachable(self):
        dating_sim_story.seed_dating_sim_content(self.conn)
        hidden_line = dating_sim_story.HIDDEN_EVENTS[5]
        hits = 0
        trials = 200
        for _ in range(trials):
            story = dating_sim_story.load_story_from_db(self.conn, dating_sim_story.CHARACTER_ID)
            if story["scenes"][5]["cafe"]["lines"][1] == hidden_line:
                hits += 1
        # 가중치 1 : 4 : 4 → 기대 확률 1/9 ≈ 22회/200. 너무 자주 나오면(절반 이상)
        # "히든"이 아니고, 한 번도 안 나오면 도달 불가능한 죽은 콘텐츠다.
        self.assertGreater(hits, 0, "200번 시도해도 히든 이벤트가 한 번도 안 나옴")
        self.assertLess(hits, trials // 2, "히든 이벤트가 너무 자주 나와 '히든'이 아님")

    def test_epub_inspired_story_is_unaffected_by_db_seeding(self):
        """book: 접두 스토리는 여전히 DB를 안 쓰고 그때그때 템플릿으로 만든다
        (원작 성인 콘텐츠를 절대 DB나 게임 대사로 옮기지 않는다는 안전장치)."""
        dating_sim_story.seed_dating_sim_content(self.conn)
        with patch.object(dating_sim_story, "_find_book", return_value=None):
            with self.assertRaises(ValueError):
                dating_sim_story.story_for("book:" + "0" * 20)

    def test_book_story_scene_last_line_is_always_the_outro_the_choices_answer(self):
        """선택지는 항상 마지막 줄(beat_outro)에 답해야 한다 — 표현 나레이션이
        중간에 끼어들어도(아래 vocab 테스트들) 마지막 줄은 그대로여야 한다."""
        with patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", Path("/tmp/no-such-jp-epub-library")), \
             patch.object(dating_sim_story, "_find_book", return_value=Path("/tmp/MATCHME.epub")), \
             patch.object(dating_sim_story, "_book_title", return_value="MATCHME"):
            story = dating_sim_story.story_for("book:" + "1" * 20)
        expected_outro = (
            dating_sim_story.DAY_BEATS[1][0][-1]
            .replace("ソイ", story["character_dialogue_name_jp"])
            .replace("소이", story["character_dialogue_name_ko"])
        )
        self.assertEqual(story["scenes"][1]["first"]["lines"][-1], expected_outro)
        self.assertNotIn("vocab", story["scenes"][1]["first"])

    def test_load_work_vocabulary_only_reads_vocabulary_field_never_expressions(self):
        """expressions(원본 대사 문장 그대로일 수 있음)는 절대 재료로 쓰면
        안 되고, 이미 학습용으로 추출된 개별 단어(vocabulary)만 안전하게
        재사용해야 한다."""
        with tempfile.TemporaryDirectory() as directory:
            library_dir = Path(directory)
            work_dir = library_dir / "TEST-001"
            work_dir.mkdir()
            (work_dir / "scene_study_cards.json").write_text(json.dumps({
                "1-1": {
                    "expressions": [{"ja": "원본 대사 문장이라 절대 쓰면 안 됨", "reading": "x", "ko": "금지"}],
                    "vocabulary": [{"ja": "同棲", "reading": "どうせい", "ko": "동거"}],
                }
            }), encoding="utf-8")
            with patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", library_dir):
                vocab = dating_sim_story._load_work_vocabulary("TEST-001")
        self.assertEqual(vocab, [("同棲", "どうせい", "동거")])
        for _, _, ko in vocab:
            self.assertNotEqual(ko, "금지")

    def test_vocab_situation_line_is_narration_not_a_question_to_the_player(self):
        """★ 2026-09-17: "단어뚝 나오고 그거에대해 말해볼까요 이런식으로
        하눈 컨셉을 버리라는거였지" 요청 — 표현 삽입은 플레이어에게
        화제 전환을 묻는 대사가 아니어야 하고, 실제 단어(한자+읽기)가
        문장에 들어가야 한다.

        ★ 2026-09-18(6차): setup이 (추상적 나레이션이 아니라) 캐릭터가
        직접 들려주는 구체적 사건 대사로 바뀌면서 괄호도 뗐다 — 이제는
        평문 대사 형식이라 괄호 여부는 검사하지 않는다. 무물음표 규칙과
        "실제 단어는 reveal에만"(setup에 단어가 나오면 "뜬금없음"이
        재발한 것) 규칙은 그대로 유지한다.

        ★ 2026-09-18(8차): reveal 뒤에 화제 복귀 줄(transition_back)이
        추가돼 반환값이 세 줄이 됐다."""
        setup, reveal, transition_back = dating_sim_story._vocab_situation_lines(("洗濯", "せんたく", "세탁"), 0)
        for line in (setup, reveal, transition_back):
            self.assertNotIn("?", line)
            self.assertNotIn("？", line)
        self.assertNotIn("[洗濯|せんたく]", setup, "setup 줄에 단어가 이미 나옴 — 뜬금없음 방지 설계 위반")
        self.assertIn("[洗濯|せんたく]", reveal)
        self.assertIn("세탁", reveal)
        self.assertNotIn("[洗濯|せんたく]", transition_back, "화제 복귀 줄은 단어와 무관한 범용 문장이어야 함")

    def test_vocab_situation_line_picks_the_correct_korean_particle(self):
        """받침 있는 단어("고민")는 "이라는", 받침 없는 단어("고마워")는
        "라는"이 붙어야 한다 — 안 그러면 "고민라는 말이"처럼 문법이 깨진다."""
        _, with_batchim, _ = dating_sim_story._vocab_situation_lines(("進行", "しんこう", "진행"), 0)
        self.assertNotIn("진행라는", with_batchim)
        _, without_batchim, _ = dating_sim_story._vocab_situation_lines(("久しぶり", "ひさしぶり", "오랜만"), 0)
        # "오랜만"도 받침(ㄴ)이 있으므로 "이라는"이 붙어야 한다.
        self.assertNotIn("오랜만라는", without_batchim)

    def test_book_story_attaches_vocab_from_day_two_onward_when_library_match_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            library_dir = Path(directory)
            work_dir = library_dir / "MATCHME"
            work_dir.mkdir()
            (work_dir / "scene_study_cards.json").write_text(json.dumps({
                "1-1": {"vocabulary": [{"ja": "本音", "reading": "ほんね", "ko": "본심"}]},
            }), encoding="utf-8")
            with patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", library_dir), \
                 patch.object(dating_sim_story, "_find_book", return_value=Path("/tmp/MATCHME.epub")), \
                 patch.object(dating_sim_story, "_book_title", return_value="MATCHME"):
                story = dating_sim_story.story_for("book:" + "1" * 20)
        self.assertIn("vocab", story["scenes"][2]["first"])
        self.assertEqual(story["scenes"][2]["first"]["vocab"]["ja"], "本音")

    def test_book_story_state_payload_forwards_vocab_for_the_frontend_to_highlight(self):
        """★ 2026-09-18: "쓰여진 그 단어는 대사에서 글자색상을 다르게...
        클릭시에 팝업이 떠서 훈음과 한국어뜻을 보고 단어장 즐겨찾기도
        되면 좋겠어" 요청을 구현하다가 발견 — story_for()가 계산한
        scene["vocab"]이 _dating_sim_state_payload()의 실제 응답에는
        실려 나가지 않고 있었다(프론트가 어떤 단어를 강조할지 알 방법이
        아예 없었음). /api/dating-sim/visit 응답까지 끝까지 확인한다."""
        story_id = "book:" + "9" * 20
        username = "vocab-payload-reader"
        with tempfile.TemporaryDirectory() as directory:
            library_dir = Path(directory)
            work_dir = library_dir / "MATCHME"
            work_dir.mkdir()
            (work_dir / "scene_study_cards.json").write_text(json.dumps({
                "1-1": {"vocabulary": [{"ja": "本音", "reading": "ほんね", "ko": "본심"}]},
            }), encoding="utf-8")
            with patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", library_dir), \
                 patch.object(dating_sim_story, "_find_book", return_value=Path("/tmp/MATCHME.epub")), \
                 patch.object(dating_sim_story, "_book_title", return_value="MATCHME"):
                app.dating_sim_visit(app.DatingSimLocationRequest(location="first", story_id=story_id), request(username))
                story = app._dating_story(story_id, username)
                choices = story["scenes"][1]["first"]["choices"]
                index = next(i for i, choice in enumerate(choices) if choice["affection"] > 0)
                app.dating_sim_choose(app.DatingSimChoiceRequest(choice_index=index, story_id=story_id), request(username))
                state = app.dating_sim_visit(app.DatingSimLocationRequest(location="first", story_id=story_id), request(username))
        self.assertEqual(state["scene"]["vocab"], {"ja": "本音", "reading": "ほんね", "ko": "본심"})

    def test_scenario_tree_reports_vocab_usage_and_flags_injected_lines(self):
        """★ 2026-09-19: "미연시스템 관리자 모드에서는 시나리오트리를 볼수있게...
        학습카드에서 나온 표현들이 어떻게 시나리오상에 작용되었는지 확인" +
        "간단한 보고서도... 항목화해서 테이블로 보고" 요청 — 시나리오 트리가
        요일·장소·대사·선택지 전체 구조와, 학습 단어가 어느 요일에 실제로
        삽입됐는지(report.vocabulary_usage) + 요일별 주제·장소(scenario_
        breakdown) + 원작 규모(corpus)를 함께 실어 주는지 확인한다. 삽입된
        단어 줄은 is_vocab로 표시돼야 하고, 그 단어는 report에서 used로
        잡혀야 한다."""
        with tempfile.TemporaryDirectory() as directory:
            library_dir = Path(directory)
            work_dir = library_dir / "MATCHME"
            work_dir.mkdir()
            (work_dir / "scene_study_cards.json").write_text(json.dumps({
                "1-1": {
                    "vocabulary": [
                        {"ja": "効果", "reading": "こうか", "ko": "효과"},
                        {"ja": "本音", "reading": "ほんね", "ko": "본심"},
                    ],
                    "expressions": [
                        {"ja": "a", "reading": "a", "ko": "사용 안 됨"},
                        {"ja": "初めまして", "reading": "はじめまして", "ko": "처음 뵙겠습니다"},
                    ],
                },
            }), encoding="utf-8")
            (work_dir / "transcript_part1.jsonl").write_text(
                '{"part":1,"scene":1,"ja":"x","ko":"y"}\n{"part":1,"scene":1,"ja":"z","ko":"w"}\n',
                encoding="utf-8",
            )
            with patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", library_dir), \
                 patch.object(dating_sim_story, "_find_book", return_value=Path("/tmp/MATCHME.epub")), \
                 patch.object(dating_sim_story, "_book_title", return_value="MATCHME"):
                tree = dating_sim_story.scenario_tree("book:" + "5" * 20, seed_key="admin")
        # 전체 구조
        self.assertEqual(len(tree["days"]), tree["total_days"])
        self.assertEqual(len(tree["days"][1]["locations"]), 3)
        self.assertTrue(tree["days"][1]["locations"][0]["choices"])
        # 1일차는 단어 삽입이 없어야 하고, 2일차부터 삽입된다.
        self.assertIsNone(tree["days"][0]["vocab"])
        self.assertIsNotNone(tree["days"][1]["vocab"])
        # 삽입된 단어 줄은 is_vocab로 표시된다.
        vocab_flagged = [
            line for loc in tree["days"][1]["locations"]
            for line in loc["lines"] if line["is_vocab"]
        ]
        self.assertTrue(vocab_flagged, "2일차에 is_vocab로 표시된 줄이 없음")
        # 보고서: corpus 규모 + 단어 활용 현황 + 요일별 breakdown
        report = tree["report"]
        self.assertEqual(report["corpus"]["study_card_scenes"], 1)
        self.assertEqual(report["corpus"]["transcript_lines"], 2)
        self.assertEqual(report["vocabulary_pool_count"], 2)
        self.assertGreaterEqual(report["vocabulary_used_count"], 1)
        used = [w for w in report["vocabulary_usage"] if w["used_days"]]
        self.assertTrue(used, "시나리오에 쓰인 단어가 보고서에 하나도 없음")
        self.assertTrue(all("category" in w for w in report["vocabulary_usage"]))
        self.assertEqual(report["expression_pool_count"], 2)
        self.assertEqual(len(report["expression_usage"]), 2)
        self.assertTrue(all("used_days" in entry for entry in report["expression_usage"]))
        self.assertEqual(len(report["scenario_breakdown"]), tree["total_days"])
        self.assertTrue(all(row["topic"] for row in report["scenario_breakdown"]))

    def test_scenario_tree_default_story_has_no_vocab_but_still_reports_topics(self):
        """EPUB 매칭이 없는 기본 소이 이야기는 학습 단어 풀이 비어도 트리·
        보고서 자체는 정상이어야 한다(요일별 주제·장소는 여전히 나옴)."""
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", Path(directory)):
                tree = dating_sim_story.scenario_tree(None, seed_key="admin")
        self.assertEqual(tree["report"]["vocabulary_pool_count"], 0)
        self.assertEqual(tree["report"]["vocabulary_used_count"], 0)
        self.assertEqual(len(tree["report"]["scenario_breakdown"]), tree["total_days"])
        self.assertTrue(all(row["topic"] for row in tree["report"]["scenario_breakdown"]))

    def _fake_generated_scenario(self):
        """★ 2026-09-19: AI 생성 시나리오 캐시(dating_sim_scenario.json)의
        최소 유효 버전을 프로그램으로 만든다 — 14일 × first/walk/quiet,
        장소마다 lines(마지막이 질문) + 선택지 2개(양·음)."""
        days = {}
        for day in range(1, dating_sim_story.TOTAL_DAYS + 1):
            scenes = {}
            for loc in ("first", "walk", "quiet"):
                # 2일차 first 장면에만 학습 단어 태그를 넣어 활용 추적을 확인.
                extra = "[効果|こうか]がありました。\n효과가 있었어요." if (day == 2 and loc == "first") else "오늘도 좋은 하루였어요."
                scenes[loc] = {
                    "lines": [f"D{day} {loc} 도입.\n도입", extra, "오늘 뭐 할까요?\n오늘 뭐 할까요?"],
                    "choices": [
                        {"text": "같이 있고 싶어요.\n같이", "affection": 10},
                        {"text": "글쎄요.\n글쎄", "affection": -4},
                    ],
                }
            days[str(day)] = {"narration": f"DAY{day} 생성 나레이션.\n생성 나레이션", "scenes": scenes}
        return {"content_version": dating_sim_story.GENERATED_SCENARIO_VERSION, "days": days}

    def test_story_uses_generated_scenario_cache_when_present(self):
        """★ 2026-09-19: "학습단어를 토대로 시나리오를 전부 새로 구성" 요청 —
        작품 폴더에 dating_sim_scenario.json이 있으면 story_for가 고정
        템플릿 대신 그 생성 시나리오를 쓰고(scenario_source=generated),
        작품별 나레이션·대사가 반영돼야 한다. 없으면 템플릿으로 폴백."""
        with tempfile.TemporaryDirectory() as directory:
            library_dir = Path(directory)
            work_dir = library_dir / "MATCHME"
            work_dir.mkdir()
            (work_dir / "scene_study_cards.json").write_text(json.dumps({
                "1-1": {"vocabulary": [{"ja": "効果", "reading": "こうか", "ko": "효과"}]},
            }), encoding="utf-8")
            with patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", library_dir), \
                 patch.object(dating_sim_story, "_find_book", return_value=Path("/tmp/MATCHME.epub")), \
                 patch.object(dating_sim_story, "_book_title", return_value="MATCHME"):
                # 캐시 없을 때는 템플릿
                template_story = dating_sim_story.story_for("book:" + "3" * 20)
                self.assertEqual(template_story["scenario_source"], "template")
                # 캐시를 쓰면 생성 시나리오
                (work_dir / "dating_sim_scenario.json").write_text(
                    json.dumps(self._fake_generated_scenario()), encoding="utf-8")
                gen_story = dating_sim_story.story_for("book:" + "3" * 20)
        self.assertEqual(gen_story["scenario_source"], "generated")
        self.assertIn("day_narration", gen_story)
        self.assertIn("생성 나레이션", gen_story["day_narration"][2])
        # 생성 대사에는 ソイ/소이 자리표시자가 실제 이름으로 치환돼 있어야 한다.
        first_scene = gen_story["scenes"][1]["first"]
        self.assertTrue(first_scene["lines"])
        self.assertEqual(len(first_scene["choices"]), 2)

    def test_generated_dialogue_removes_repeated_character_name_prefix(self):
        generated = self._fake_generated_scenario()
        generated["days"]["1"]["scenes"]["first"]["lines"][0] = (
            "ソイ：[今日|きょう]はいい[天気|てんき]ですね。\n소이: 오늘은 날씨가 좋네요."
        )
        scenes, _ = dating_sim_story._scenes_from_generated(
            generated, "사토 하루", "[佐藤|さとう] [春|はる]"
        )
        line = scenes[1]["first"]["lines"][0]
        self.assertNotIn("[佐藤|さとう] [春|はる]", line)
        self.assertNotIn("사토 하루:", line)
        self.assertTrue(line.startswith("[今日|きょう]"))

    def test_generated_scenario_tree_flags_vocab_by_content_and_reports_usage(self):
        """생성 시나리오(한 장면 여러 단어, 대사에 직접 녹음)에서도 트리가
        단어 태그 포함 여부로 is_vocab을 잡고, 보고서 활용 집계가 맞아야 한다."""
        with tempfile.TemporaryDirectory() as directory:
            library_dir = Path(directory)
            work_dir = library_dir / "MATCHME"
            work_dir.mkdir()
            (work_dir / "scene_study_cards.json").write_text(json.dumps({
                "1-1": {"vocabulary": [{"ja": "効果", "reading": "こうか", "ko": "효과"}]},
            }), encoding="utf-8")
            (work_dir / "dating_sim_scenario.json").write_text(
                json.dumps(self._fake_generated_scenario()), encoding="utf-8")
            with patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", library_dir), \
                 patch.object(dating_sim_story, "_find_book", return_value=Path("/tmp/MATCHME.epub")), \
                 patch.object(dating_sim_story, "_book_title", return_value="MATCHME"):
                tree = dating_sim_story.scenario_tree("book:" + "3" * 20, seed_key="admin")
        day2 = tree["days"][1]
        flagged = [ln for loc in day2["locations"] for ln in loc["lines"] if ln["is_vocab"]]
        self.assertTrue(flagged, "생성 대사에 든 학습 단어 줄이 is_vocab로 안 잡힘")
        usage = {w["ja"]: w for w in tree["report"]["vocabulary_usage"]}
        self.assertIn(2, usage["効果"]["used_days"])

    def test_state_payload_marks_owner_as_admin_for_the_scenario_tree_button(self):
        """관리자(is_owner)만 시나리오 트리 버튼을 보게 상태에 is_admin이
        실려야 한다 — 일반 로그인 사용자는 False."""
        owner_req = SimpleNamespace(state=SimpleNamespace(
            user={"username": "boss", "is_owner": True}, can_write=True, share_guest=False))
        owner_state = app.dating_sim_state(owner_req)
        self.assertTrue(owner_state["is_admin"])
        member_state = app.dating_sim_state(request("member"))
        self.assertFalse(member_state["is_admin"])

    def test_book_story_never_attaches_vocab_on_the_first_meeting_day(self):
        """★ 2026-09-18: "이거 두 장면이 개연성이없어" 신고 — 1일차(방금
        처음 만난 사이)에 관계 지속을 전제하는 단어가 나오면 나레이션
        형식이어도 낯선 사이 설정과 부딪힌다. 1일차는 표현 나레이션 자체를
        빼야 한다."""
        with tempfile.TemporaryDirectory() as directory:
            library_dir = Path(directory)
            work_dir = library_dir / "MATCHME"
            work_dir.mkdir()
            (work_dir / "scene_study_cards.json").write_text(json.dumps({
                "1-1": {"vocabulary": [{"ja": "残る", "reading": "のこる", "ko": "남다"}]},
            }), encoding="utf-8")
            with patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", library_dir), \
                 patch.object(dating_sim_story, "_find_book", return_value=Path("/tmp/MATCHME.epub")), \
                 patch.object(dating_sim_story, "_book_title", return_value="MATCHME"):
                story = dating_sim_story.story_for("book:" + "8" * 20)
        for location, scene in story["scenes"][1].items():
            self.assertNotIn("vocab", scene, f"1일차 {location}에 표현 나레이션이 섞임")

    def test_book_story_has_no_vocab_when_no_library_match(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", Path(directory)), \
                 patch.object(dating_sim_story, "_find_book", return_value=Path("/tmp/NOMATCH.epub")), \
                 patch.object(dating_sim_story, "_book_title", return_value="NOMATCH"):
                story = dating_sim_story.story_for("book:" + "2" * 20)
        self.assertNotIn("vocab", story["scenes"][1]["first"])

    def test_random_book_id_excludes_already_started_books(self):
        """★ 2026-09-17: "새로운 만남 시작하기"가 이미 진행 중인 만남을 새
        만남인 척 다시 내놓으면 안 된다."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.epub").write_bytes(b"")
            (root / "b.epub").write_bytes(b"")
            with patch.object(dating_sim_story, "JAPANESE_EPUB_ROOT", root):
                id_a = dating_sim_story._book_id(root / "a.epub")
                id_b = dating_sim_story._book_id(root / "b.epub")
                picked = {dating_sim_story.random_book_id(exclude={id_a}, prepared_only=False) for _ in range(20)}
        self.assertEqual(picked, {id_b})

    def test_new_encounter_rejects_when_no_prepared_story_exists(self):
        with patch.object(dating_sim_story, "random_book_id", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                app.dating_sim_new_encounter(request("fresh-player"))
        self.assertEqual(raised.exception.status_code, 409)

    def test_new_encounter_picks_an_unstarted_book_once_default_is_played(self):
        app.dating_sim_state(request("book-picker"))
        with patch.object(dating_sim_story, "random_book_id", return_value="a" * 20):
            result = app.dating_sim_new_encounter(request("book-picker"))
        self.assertTrue(result["story_id"].startswith("book:"))

    def test_new_encounter_rejects_when_everything_is_already_started(self):
        app.dating_sim_state(request("completionist"))
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(dating_sim_story, "JAPANESE_EPUB_ROOT", Path(directory)):
                with self.assertRaises(HTTPException) as raised:
                    app.dating_sim_new_encounter(request("completionist"))
        self.assertEqual(raised.exception.status_code, 409)

    def test_encounters_hides_legacy_default_story_until_a_prepared_work_exists(self):
        app.dating_sim_state(request("lister"))
        encounters = app.dating_sim_encounters(request("lister"))
        self.assertEqual(encounters, [])

    def test_encounters_keeps_showing_a_book_with_real_progress_even_if_unprepared(self):
        # ★ 2026-09-23: "미연시 이거미완료라고 아무것도 안보이는데 미완료여도
        # 이전에 진행하던거는 계속볼수있게해줘" 요청 — prepared_book()이
        # False(이미지·시나리오 생성이 아직 안 끝남)여도, 실제로 진행한
        # 기록(장소 방문·선택으로 day가 늘어남)이 있으면 "이어하기"에서
        # 사라지면 안 된다.
        story_id = "book:" + "3" * 20
        username = "progressor"
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", Path(directory)), \
             patch.object(dating_sim_story, "_find_book", return_value=Path("/tmp/UNFINISHED.epub")), \
             patch.object(dating_sim_story, "_book_title", return_value="UNFINISHED"), \
             patch.object(dating_sim_story, "prepared_book", return_value=False):
            app.dating_sim_visit(app.DatingSimLocationRequest(location="first", story_id=story_id), request(username))
            story = app._dating_story(story_id, username)
            choices = story["scenes"][1]["first"]["choices"]
            index = next(i for i, choice in enumerate(choices) if choice["affection"] > 0)
            app.dating_sim_choose(app.DatingSimChoiceRequest(choice_index=index, story_id=story_id), request(username))
            encounters = app.dating_sim_encounters(request(username))
        self.assertEqual([e["story_id"] for e in encounters], [story_id])

    def test_encounters_still_hides_an_untouched_unprepared_book(self):
        story_id = "book:" + "3" * 19 + "4"
        username = "glancer"
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", Path(directory)), \
             patch.object(dating_sim_story, "_find_book", return_value=Path("/tmp/UNFINISHED.epub")), \
             patch.object(dating_sim_story, "_book_title", return_value="UNFINISHED"), \
             patch.object(dating_sim_story, "prepared_book", return_value=False):
            app.dating_sim_state(request(username), story_id)
            encounters = app.dating_sim_encounters(request(username))
        self.assertEqual(encounters, [])

    def test_playable_stories_lists_prepared_books_for_owner_only(self):
        owner = SimpleNamespace(state=SimpleNamespace(
            user={"username": "admin", "is_owner": True}, can_write=True, share_guest=False))
        book_id = "5" * 20
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", Path(directory)), \
             patch.object(dating_sim_story, "all_book_ids", return_value=[book_id]), \
             patch.object(dating_sim_story, "book_readiness", return_value=(True, False, 10)), \
             patch.object(dating_sim_story, "_find_book", return_value=Path("/tmp/READY.epub")), \
             patch.object(dating_sim_story, "_book_title", return_value="READY"):
            stories = app.dating_sim_playable_stories(owner)
            with self.assertRaises(HTTPException) as denied:
                app.dating_sim_playable_stories(request("plain"))
        self.assertEqual(denied.exception.status_code, 403)
        self.assertEqual([s["story_id"] for s in stories], [f"book:{book_id}"])
        self.assertFalse(stories[0]["started"])
        self.assertFalse(stories[0]["ready"])  # 미완료도 목록에는 남는다
        self.assertEqual(stories[0]["image_count"], 10)
        self.assertTrue(stories[0]["character_name"])
        self.assertEqual(stories[0]["source_title"], "READY")

    def test_playable_stories_puts_completed_scenarios_first(self):
        owner = SimpleNamespace(state=SimpleNamespace(
            user={"username": "admin", "is_owner": True}, can_write=True, share_guest=False))
        book_ids = ["7" * 20, "8" * 20, "9" * 20]
        readiness = {
            book_ids[0]: (False, False, 0),
            book_ids[1]: (True, False, 10),
            book_ids[2]: (True, True, 42),
        }

        def find_book(book_id):
            return Path(f"/tmp/{book_id}.epub")

        with tempfile.TemporaryDirectory() as directory, \
             patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", Path(directory)), \
             patch.object(dating_sim_story, "all_book_ids", return_value=book_ids), \
             patch.object(dating_sim_story, "book_readiness", side_effect=lambda book_id: readiness[book_id]), \
             patch.object(dating_sim_story, "_find_book", side_effect=find_book), \
             patch.object(dating_sim_story, "_book_title", side_effect=lambda path: path.stem):
            stories = app.dating_sim_playable_stories(owner)

        self.assertEqual([item["story_id"] for item in stories], [
            f"book:{book_ids[2]}", f"book:{book_ids[1]}", f"book:{book_ids[0]}",
        ])

    def test_reference_candidates_list_and_regeneration_passes_selected_references(self):
        owner = SimpleNamespace(state=SimpleNamespace(
            user={"username": "admin", "is_owner": True}, can_write=True, share_guest=False))
        story_id = "book:" + "6" * 20
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "images").mkdir()
            for name in ("part1_scene001.jpg", "part1_scene002.jpg"):
                (work / "images" / name).write_bytes(b"x" * 2048)
            with patch.object(dating_sim_story, "resolve_book_work_dir", return_value=("6" * 20, work)):
                listing = app.dating_sim_reference_candidates(owner, story_id)
                self.assertEqual([c["name"] for c in listing["candidates"]],
                                 ["part1_scene001.jpg", "part1_scene002.jpg"])
                with self.assertRaises(HTTPException) as denied:
                    app.dating_sim_reference_candidates(request("plain"), story_id)
                self.assertEqual(denied.exception.status_code, 403)
                with self.assertRaises(HTTPException) as bad:
                    app.dating_sim_generate_images_start(owner, story_id, reference=["../secret.jpg"])
                self.assertEqual(bad.exception.status_code, 400)
                with patch.object(app.subprocess, "Popen") as popen:
                    popen.return_value.poll.return_value = 0
                    app.dating_sim_generate_images_start(owner, story_id, reference=["part1_scene002.jpg"])
                command = popen.call_args[0][0]
        self.assertIn("--reference", command)
        self.assertIn("part1_scene002.jpg", command)
        self.assertIn("portrait", command)
        app._dating_sim_image_jobs.pop("6" * 20, None)

    def test_book_character_profiles_are_stable_and_varied(self):
        profiles = [dating_sim_story.book_character_profile(f"book:{number:020x}")
                    for number in range(20)]
        self.assertGreater(len({profile["jp"] for profile in profiles}), 3)
        self.assertEqual(
            dating_sim_story.book_character_profile("book:" + "1" * 20),
            dating_sim_story.book_character_profile("book:" + "1" * 20),
        )

    def test_book_character_uses_actual_sone_486_dialogue_name(self):
        """SONE-486 자기소개 ASR 오류는 실제 五条恋(고죠 렌)으로 보정한다."""
        with tempfile.TemporaryDirectory() as directory:
            library_dir = Path(directory)
            work_dir = library_dir / "SONE-486"
            work_dir.mkdir()
            (work_dir / "transcript_part1.jsonl").write_text(
                json.dumps({"ja": "ご乗れんです。お願いします", "ko": "고렌입니다."},
                           ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            with patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", library_dir):
                profile = dating_sim_story.book_character_profile(
                    "book:" + "4" * 20, source_title="SONE-486 — 출장의 밤"
                )
        self.assertEqual(profile["full_jp"], "[五条|ごじょう] [恋|れん]")
        self.assertEqual(profile["ko"], "고죠 렌")
        self.assertFalse(profile["is_alias"])
        self.assertIn("rainy-evening.png", profile["scene_images"]["walk"])

    def test_book_character_name_uses_japanese_reading_not_literal_translation(self):
        # ★ 2026-09-23: "이름이 화장실인건 이상하잖아 이름은 일본어 이름으로
        # 읽어줘" 신고 — 277DCV-298에서 "これお手洗いです"(=이것은 화장실
        # 입니다)라는 무관한 문장이 자기소개로 오인식되면서 이름이 "화장실"
        # 로 떴다. 감지된 일본어 글자는 그대로 두되, 한국어 이름은 번역문이
        # 아니라 발음(음역)으로 채워야 한다.
        with tempfile.TemporaryDirectory() as directory:
            library_dir = Path(directory)
            work_dir = library_dir / "277DCV-298"
            work_dir.mkdir()
            (work_dir / "transcript_part1.jsonl").write_text(
                json.dumps({"ja": "これお手洗いです", "ko": "이것은 화장실입니다.",
                            "furigana": "これお手洗い(てあらい)です"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            with patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", library_dir):
                profile = dating_sim_story.book_character_profile(
                    "book:" + "6" * 20, source_title="277DCV-298"
                )
        self.assertEqual(profile["jp"], "これお手洗い")
        self.assertNotIn("화장실", profile["ko"])
        self.assertNotEqual(profile["ko"], "이것은 화장실")

    def test_japanese_name_romanization_uses_kanji_readings_not_meaning(self):
        self.assertEqual(dating_sim_story._romanize_japanese_name("これお手洗い"), "고레오테아라이")
        self.assertEqual(dating_sim_story._romanize_japanese_name("たかはし"), "다카하시")
        self.assertEqual(dating_sim_story._romanize_japanese_name("さくら"), "사쿠라")

    def test_book_character_marks_generated_name_as_alias(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(dating_sim_story, "JP_SUBTITLE_LIBRARY_DIR", Path(directory)):
            profile = dating_sim_story.book_character_profile(
                "book:" + "5" * 20, source_title="NO-DIALOGUE-NAME"
            )
        self.assertTrue(profile["is_alias"])
        self.assertTrue(profile["display_jp"].endswith("(가명)"))
        self.assertTrue(profile["display_ko"].endswith("(가명)"))


if __name__ == "__main__":
    unittest.main()
