import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from server import app, db


def request(username="reader"):
    return SimpleNamespace(state=SimpleNamespace(user={"username": username, "is_owner": False}, can_write=True, share_guest=False))


class VocabularyApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(db, "DB_PATH", str(Path(self.temp.name) / "chat.db"))
        self.patch.start(); db.init_db()
        conn = db.get_conn(); conn.execute("INSERT INTO users(username,password_hash,salt,is_owner,created_at) VALUES('reader','x','x',0,'now')"); conn.commit(); conn.close()

    def tearDown(self):
        self.patch.stop(); self.temp.cleanup()

    def test_english_word_create_list_and_delete_are_account_scoped(self):
        saved = app.save_vocabulary_entry(app.VocabularyEntryUpdate(term="strategy", meaning="전략", note="아침 독서"), request())
        self.assertEqual(saved["term"], "strategy")
        self.assertEqual(len(app.list_vocabulary_entries(request(), "english")), 1)
        with self.assertRaises(HTTPException): app.delete_vocabulary_entry(saved["id"], request("other"))
        self.assertTrue(app.delete_vocabulary_entry(saved["id"], request())["ok"])

    def test_invalid_language_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            app.save_vocabulary_entry(app.VocabularyEntryUpdate(language="unknown", term="word"), request())
        self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__": unittest.main()
