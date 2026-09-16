"""★ 2026-09-16: "일본어선생님이 채팅방에서 작품올리고 설명할때 epub
작품링크랑 미연시 링크도 같이 올리면좋겠어" 요청 — EPUB 읽기 링크와 같은
book_id로 미연시 링크를 만드는 _jp_dating_sim_url()을 검증한다."""
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

import persona_worker as pw


class JpDatingSimLinkTest(unittest.TestCase):
    def test_dating_sim_url_uses_the_same_book_id_as_the_epub_reader(self):
        with patch.object(pw, "JP_EPUB_FINAL_DIR", Path("/tmp/nonexistent-jp-epub-dir")):
            with patch("pathlib.Path.exists", return_value=True), \
                 patch("pathlib.Path.glob") as mock_glob:
                epub_path = Path("/tmp/nonexistent-jp-epub-dir/ABF-161_J 낭독판.epub")
                mock_glob.return_value = [epub_path]
                expected_id = hashlib.sha256(str(epub_path.resolve()).encode()).hexdigest()[:20]
                epub_url = pw._jp_epub_read_url("ABF-161_J")
                dating_sim_url = pw._jp_dating_sim_url("ABF-161_J")
        self.assertIn(expected_id, epub_url)
        self.assertIn(expected_id, dating_sim_url)
        self.assertIn("/dating-sim", dating_sim_url)
        self.assertIn("/epub", epub_url)

    def test_dating_sim_url_is_empty_when_epub_is_missing(self):
        with patch.object(pw, "JP_EPUB_FINAL_DIR", Path("/tmp/nonexistent-jp-epub-dir")):
            with patch("pathlib.Path.exists", return_value=False):
                self.assertEqual(pw._jp_dating_sim_url("어떤-회차"), "")

    def test_dating_sim_url_is_empty_when_public_url_unset(self):
        with patch.object(pw, "JP_DATING_SIM_WEB_PUBLIC_URL", ""):
            self.assertEqual(pw._jp_dating_sim_url("아무거나"), "")


if __name__ == "__main__":
    unittest.main()
