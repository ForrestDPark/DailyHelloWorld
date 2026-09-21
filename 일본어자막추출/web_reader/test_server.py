import tempfile
import unittest
import zipfile
import datetime
import sqlite3
import json
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
            store = server.Store(Path(td) / "state.db"); store.save("book", 3, 42.5, "alpha")
            self.assertEqual(store.get("book", "alpha")["spine_index"], 3)
            self.assertEqual(store.get("book", "beta")["spine_index"], 0)

    def test_owner_progress_syncs_with_morning_reader_sidecar(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); epub_path = root / "book.epub"; make_epub(epub_path)
            book = server.parse_book(epub_path)
            app = object.__new__(server.App); app.store = server.Store(root / "reader.db")
            app.save_progress(book, 0, 100, "owner", True)
            shared = json.loads(book.path.with_suffix(".reader-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(shared["source"], "web")
            self.assertEqual(app.progress_for(book, "owner", True)["spine_index"], 0)
            self.assertEqual(app.progress_for(book, "other", False)["spine_index"], 0)

    def test_morning_reader_sidecar_uses_sentence_ratio_not_chapter_ratio(self):
        """★ 2026-09-22 실제 버그: 장(spine)이 몇 개뿐이고 분량이 들쭉날쭉한
        책(예: 6장 중 3장이 전체의 25~60% 구간)에서 "(장 번호+1)/전체 장 수"
        식은 실제 위치와 크게 어긋난다(66.7%로 보였지만 실제로는 59%).
        아침 리더가 문장 단위 진행률(sentence_idx/sentence_total)을 준
        sidecar가 있으면 그걸로 정확한 퍼센트를 계산해야 한다."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); epub_path = root / "book.epub"; make_epub(epub_path)
            book = server.parse_book(epub_path)
            app = object.__new__(server.App); app.store = server.Store(root / "reader.db")
            sidecar = book.path.with_suffix(".reader-progress.json")
            sidecar.write_text(json.dumps({
                "book_file": str(book.path), "spine_index": 0, "spine_total": 1,
                "sentence_idx": 1144, "sentence_total": 1934,
                "percent": 28.2, "updated_at": 99999999999, "source": "morning-reader",
                "resume_text": "Behind the Scenes",
            }), encoding="utf-8")
            progress = app.progress_for(book, "owner", True)
            self.assertAlmostEqual(progress["percent"], 1144 / 1934 * 100, places=3)
            self.assertEqual(progress["resume_text"], "Behind the Scenes")

    def test_viewing_the_same_chapter_does_not_downgrade_morning_reader_precision(self):
        """★ 2026-09-22 실제 버그: 웹 리더는 페이지를 "보기만" 해도(실제로
        더 읽지 않아도) display()가 진행률 PUT을 매번 보낸다. 이게 그대로
        sidecar를 "web" 소스·장 단위 근사치로 덮어써서, 아침 리더로 정밀하게
        복원한 위치를 여는 순간 다시 부정확해지는 사고가 있었다. 같은 장을
        보는 동안은(spine_index 불변) 아침 리더의 문장 단위 정보를 지켜야
        한다 — 실제로 다른 장으로 넘어갈 때만 web 소스로 갈아탄다."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); epub_path = root / "book.epub"; make_epub(epub_path)
            book = server.parse_book(epub_path)
            app = object.__new__(server.App); app.store = server.Store(root / "reader.db")
            sidecar = book.path.with_suffix(".reader-progress.json")
            sidecar.write_text(json.dumps({
                "book_file": str(book.path), "spine_index": 0, "spine_total": 1,
                "sentence_idx": 1144, "sentence_total": 1934,
                "percent": 59.15, "updated_at": 100, "source": "morning-reader",
                "resume_text": "Behind the Scenes",
            }), encoding="utf-8")
            # display()가 같은 장(0)을 다시 "보기만" 하며 PUT을 보낸 상황을 재현.
            app.save_progress(book, 0, ((0 + 1) / 1) * 100, "owner", True)
            shared = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(shared["source"], "morning-reader")
            self.assertEqual(shared["sentence_idx"], 1144)
            progress = app.progress_for(book, "owner", True)
            self.assertAlmostEqual(progress["percent"], 1144 / 1934 * 100, places=3)

    def test_signed_session_expires(self):
        secret = b"secret"; self.assertTrue(server.valid_session(secret, server.sign_session(secret)))
        with patch.object(server.time, "time", return_value=0): token = server.sign_session(secret)
        self.assertFalse(server.valid_session(secret, token))

    def test_chatapp_session_allows_any_signed_in_user(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "chat.db"
            with sqlite3.connect(db_path) as db:
                db.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY,is_owner INTEGER,username TEXT); CREATE TABLE sessions(token TEXT,user_id INTEGER,expires_at TEXT);")
                future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()
                db.execute("INSERT INTO users VALUES(1,1,'owner'),(2,0,'reader')")
                db.execute("INSERT INTO sessions VALUES('owner',1,?),('user',2,?)", (future, future))
            app = object.__new__(server.App); app.chatapp_db = db_path
            self.assertEqual(app.chat_session_user("owner"), ("owner", True))
            self.assertEqual(app.chat_session_user("user"), ("reader", False))
            self.assertIsNone(app.chat_session_user("missing"))

    def test_edge_tts_uses_one_fixed_voice_per_language_and_caches(self):
        class FakeCommunicate:
            calls = []
            def __init__(self, text, voice):
                self.text, self.voice = text, voice
                self.calls.append((text, voice))
            async def save(self, path):
                Path(path).write_bytes(b"mp3" * 300)

        with tempfile.TemporaryDirectory() as td, patch.object(server.edge_tts, "Communicate", FakeCommunicate):
            app = object.__new__(server.App)
            app.tts_cache = Path(td)
            first = app.edge_tts("こんにちは", "ja-JP")
            second = app.edge_tts("こんにちは", "ja-JP")
            korean = app.edge_tts("안녕하세요", "ko-KR")
        self.assertEqual(first, second)
        self.assertNotEqual(first, korean)
        self.assertEqual(FakeCommunicate.calls.count(("こんにちは", "ja-JP-NanamiNeural")), 1)
        self.assertIn(("안녕하세요", "ko-KR-SunHiNeural"), FakeCommunicate.calls)


if __name__ == "__main__": unittest.main()
