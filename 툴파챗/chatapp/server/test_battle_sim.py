"""손자병법 전쟁 시뮬레이션 상태 전이 테스트."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from server import app, db


def request(username="general"):
    return SimpleNamespace(state=SimpleNamespace(user={"username": username, "is_owner": False}, can_write=True, share_guest=False))


class BattleSimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(db, "DB_PATH", str(Path(self.temp.name) / "chat.db"))
        self.patch.start()
        db.init_db()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_regular_user_can_complete_jingxing(self):
        state = app.battle_sim_state(request(), "jingxing")
        self.assertEqual(state["phase"], 0)
        for _ in range(3):
            state = app.battle_sim_choose(app.BattleSimChoiceRequest(battle_id="jingxing", choice_index=0), request())
        self.assertTrue(state["completed"])
        self.assertEqual(state["score"], 6)
        self.assertEqual(state["summary"]["rank"], "대승")

    def test_progress_isolated_by_account_and_battle(self):
        app.battle_sim_choose(app.BattleSimChoiceRequest(battle_id="cannae", choice_index=1), request("a"))
        self.assertEqual(app.battle_sim_state(request("b"), "cannae")["phase"], 0)
        self.assertEqual(app.battle_sim_state(request("a"), "austerlitz")["phase"], 0)


if __name__ == "__main__":
    unittest.main()
