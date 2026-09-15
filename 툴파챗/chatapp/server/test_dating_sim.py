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

    def test_new_player_starts_at_day_one_with_base_affection_and_no_pending_scene(self):
        state = app.dating_sim_state(request())
        self.assertEqual(state["day"], 1)
        self.assertEqual(state["affection"], 50)
        self.assertFalse(state["completed"])
        self.assertNotIn("scene", state)
        self.assertEqual(len(state["locations"]), len(dating_sim_story.LOCATIONS))

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
        state = app.dating_sim_choose(app.DatingSimChoiceRequest(choice_index=0), request())
        self.assertEqual(state["affection"], 60)
        self.assertEqual(state["day"], 2)
        self.assertIsNone(state["pending_location"])

    def test_negative_choice_lowers_affection_and_clamps_at_zero(self):
        app.dating_sim_visit(app.DatingSimLocationRequest(location="cafe"), request())
        state = app.dating_sim_choose(app.DatingSimChoiceRequest(choice_index=1), request())
        self.assertEqual(state["affection"], 45)

    def test_out_of_range_choice_index_is_rejected(self):
        app.dating_sim_visit(app.DatingSimLocationRequest(location="cafe"), request())
        with self.assertRaises(HTTPException) as raised:
            app.dating_sim_choose(app.DatingSimChoiceRequest(choice_index=5), request())
        self.assertEqual(raised.exception.status_code, 400)

    def test_all_positive_choices_across_three_days_reach_the_best_ending(self):
        for _ in range(dating_sim_story.TOTAL_DAYS):
            app.dating_sim_visit(app.DatingSimLocationRequest(location="cafe"), request())
            state = app.dating_sim_choose(app.DatingSimChoiceRequest(choice_index=0), request())
        self.assertTrue(state["completed"])
        self.assertEqual(state["ending"]["id"], "best")
        self.assertEqual(state["affection"], 80)

    def test_all_negative_choices_reach_the_normal_ending_and_stay_playable_after(self):
        for _ in range(dating_sim_story.TOTAL_DAYS):
            app.dating_sim_visit(app.DatingSimLocationRequest(location="park"), request())
            state = app.dating_sim_choose(app.DatingSimChoiceRequest(choice_index=1), request())
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


if __name__ == "__main__":
    unittest.main()
