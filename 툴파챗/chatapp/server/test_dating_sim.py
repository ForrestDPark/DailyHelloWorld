"""★ 2026-09-15: "미연시 시스템 하나 만들어봤으면 좋겠어" 요청으로 만든
선택지+호감도+멀티 엔딩 미니게임의 엔진(상태 저장·전환) 테스트."""
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
        self.assertEqual(state["affection"], 58)
        self.assertEqual(state["day"], 2)
        self.assertIsNone(state["pending_location"])
        self.assertEqual(state["choice_result"]["affection_delta"], 8)

    def test_negative_choice_lowers_affection_and_clamps_at_zero(self):
        app.dating_sim_visit(app.DatingSimLocationRequest(location="cafe"), request())
        index = self.choice_index("reader", "cafe", False)
        state = app.dating_sim_choose(app.DatingSimChoiceRequest(choice_index=index), request())
        self.assertEqual(state["affection"], 46)

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
                self.assertEqual(len(scene["lines"]), 3)
                self.assertEqual(len(scene["choices"]), 2)

    def test_replaying_the_same_slot_can_surface_different_variants(self):
        dating_sim_story.seed_dating_sim_content(self.conn)
        seen = set()
        for _ in range(40):
            story = dating_sim_story.load_story_from_db(self.conn, dating_sim_story.CHARACTER_ID)
            seen.add(story["scenes"][1]["cafe"]["lines"][1])
        self.assertGreater(len(seen), 1, "40번을 다시 골라도 항상 같은 대사만 나오면 다양성이 없는 것")

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


if __name__ == "__main__":
    unittest.main()
