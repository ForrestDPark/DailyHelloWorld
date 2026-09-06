import tempfile
import unittest
import zipfile
import datetime
import sqlite3
from pathlib import Path
from unittest.mock import patch

import server


def make_epub(path: Path, title="테스트 책", readaloud=False):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
        overlay = ' media-overlay="s1"' if readaloud else ''
        smil = '<item id="s1" href="overlays/1.smil" media-type="application/smil+xml"/><item id="a1" href="audio/1.m4a" media-type="audio/mp4"/>' if readaloud else ''
        z.writestr("OEBPS/content.opf", f'''<package xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{title}</dc:title></metadata><manifest><item id="cover" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/><item id="p1" href="pages/1.xhtml" media-type="application/xhtml+xml"{overlay}/>{smil}</manifest><spine><itemref idref="p1"/></spine></package>''')
        z.writestr("OEBPS/images/cover.jpg", b"jpeg")
        z.writestr("OEBPS/pages/1.xhtml", "<html>본문</html>")
        if readaloud:
            z.writestr("OEBPS/overlays/1.smil", '<smil xmlns="http://www.w3.org/ns/SMIL"><body><seq><par><text src="../pages/1.xhtml#line-1"/><audio src="../audio/1.m4a" clipBegin="00:00:01.250" clipEnd="00:00:02.500"/></par></seq></body></smil>')
            z.writestr("OEBPS/audio/1.m4a", b"audio")


class ReaderTests(unittest.TestCase):
    def test_parse_and_scan(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); make_epub(root / "ABC-001_낭독판.epub")
            book = server.parse_book(root / "ABC-001_낭독판.epub")
            self.assertEqual(book.title, "테스트 책"); self.assertEqual(book.spine, ("OEBPS/pages/1.xhtml",)); self.assertEqual(book.cover, "OEBPS/images/cover.jpg")
            self.assertEqual(len(server.Library([root]).books), 1)

    def test_readaloud_alias_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "old").mkdir()
            make_epub(root / "ABC-001 — 제목_낭독판.epub")
            make_epub(root / "old" / "ABC-001_읽어주기.epub")
            self.assertEqual(len(server.Library([root]).books), 1)

    def test_smil_audio_is_connected_to_spine_page(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); make_epub(root / "ABC-001_낭독판.epub", readaloud=True)
            book = server.parse_book(root / "ABC-001_낭독판.epub")
            self.assertTrue(book.public()["has_audio"])
            self.assertEqual(book.audio[0][0]["member"], "OEBPS/audio/1.m4a")
            self.assertEqual(book.audio[0][0]["begin"], 1.25)
            self.assertEqual(book.audio[0][0]["end"], 2.5)
            self.assertEqual(book.audio[0][0]["target"], "line-1")

    def test_rejects_traversal(self):
        for value in ("../secret", "%2e%2e/secret", ""):
            with self.assertRaises(ValueError): server._safe_member(value)

    def test_progress_is_persisted(self):
        with tempfile.TemporaryDirectory() as td:
            store = server.Store(Path(td) / "state.db"); store.save("book", 3, 42.5)
            self.assertEqual(store.get("book")["spine_index"], 3)

    def test_signed_session_expires(self):
        secret = b"secret"; self.assertTrue(server.valid_session(secret, server.sign_session(secret)))
        with patch.object(server.time, "time", return_value=0): token = server.sign_session(secret)
        self.assertFalse(server.valid_session(secret, token))

    def test_chatapp_session_allows_only_owner(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "chat.db"
            with sqlite3.connect(db_path) as db:
                db.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY,is_owner INTEGER); CREATE TABLE sessions(token TEXT,user_id INTEGER,expires_at TEXT);")
                future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()
                db.execute("INSERT INTO users VALUES(1,1),(2,0)")
                db.execute("INSERT INTO sessions VALUES('owner',1,?),('user',2,?)", (future, future))
            app = object.__new__(server.App); app.chatapp_db = db_path
            self.assertTrue(app.valid_chat_owner_session("owner"))
            self.assertFalse(app.valid_chat_owner_session("user"))


if __name__ == "__main__": unittest.main()
