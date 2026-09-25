import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from server import app, db


def request(username="reader", is_owner=False):
    return SimpleNamespace(state=SimpleNamespace(
        user={"username": username, "is_owner": is_owner}, can_write=True, share_guest=False
    ))


class MemoApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(db, "DB_PATH", str(Path(self.temp.name) / "chat.db"))
        self.patch.start(); db.init_db()
        conn = db.get_conn()
        conn.execute("INSERT INTO users(username,password_hash,salt,is_owner,created_at) VALUES('reader','x','x',0,'now')")
        conn.execute("INSERT INTO users(username,password_hash,salt,is_owner,created_at) VALUES('other','x','x',0,'now')")
        conn.execute("INSERT INTO messages(sender,content,created_at,room_id) VALUES('유이','중요한 설계 메모','now','group')")
        self.message_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        conn.commit(); conn.close()

    def tearDown(self):
        self.patch.stop(); self.temp.cleanup()

    def test_message_capture_is_deduplicated_per_account(self):
        first = app.create_memo_from_message(self.message_id, request())
        second = app.create_memo_from_message(self.message_id, request())
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(app.list_memos(request())), 1)

    def test_nodes_are_nested_and_account_scoped(self):
        memo = app.create_memo(app.MemoDocumentCreate(title="아이디어"), request())
        parent = app.create_memo_node(memo["id"], app.MemoNodeCreate(content="첫 가지"), request())
        app.create_memo_node(memo["id"], app.MemoNodeCreate(parent_id=parent["id"], content="하위 가지"), request())
        self.assertEqual(len(app.list_memos(request())[0]["nodes"]), 2)
        with self.assertRaises(HTTPException):
            app.update_memo_node(parent["id"], app.MemoNodeUpdate(content="침범"), request("other"))
        deleted = app.delete_memo_node(parent["id"], request())
        self.assertEqual(deleted["deleted"], 2)


if __name__ == "__main__": unittest.main()
