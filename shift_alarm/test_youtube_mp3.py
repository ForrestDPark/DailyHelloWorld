import unittest

from shift_alarm import _normalize_youtube_mp3_url


class YouTubeMp3UrlTests(unittest.TestCase):
    def test_restores_anchor_video_for_radio_mix_id(self):
        url, label, liked = _normalize_youtube_mp3_url(
            "https://www.youtube.com/playlist?list=RDa0fkNdPiIL4"
        )
        self.assertEqual(
            url,
            "https://www.youtube.com/watch?v=a0fkNdPiIL4&list=RDa0fkNdPiIL4",
        )
        self.assertEqual(label, "YouTube 믹스 (RDa0fkNdPiIL4)")
        self.assertFalse(liked)

    def test_preserves_explicit_mix_anchor(self):
        url, _, _ = _normalize_youtube_mp3_url(
            "https://www.youtube.com/watch?v=abcdefghijk&list=RDMMabcdefghijk"
        )
        self.assertEqual(
            url,
            "https://www.youtube.com/watch?v=abcdefghijk&list=RDMMabcdefghijk",
        )

    def test_normalizes_regular_playlist(self):
        url, label, liked = _normalize_youtube_mp3_url(
            "https://www.youtube.com/watch?v=abcdefghijk&list=PL123"
        )
        self.assertEqual(url, "https://www.youtube.com/playlist?list=PL123")
        self.assertEqual(label, "재생목록 전체 (PL123)")
        self.assertFalse(liked)

    def test_liked_playlist_keeps_special_handling(self):
        url, label, liked = _normalize_youtube_mp3_url(
            "https://www.youtube.com/watch?v=abcdefghijk&list=LL"
        )
        self.assertEqual(url, "https://www.youtube.com/playlist?list=LL")
        self.assertEqual(label, "좋아요 표시한 동영상 전체")
        self.assertTrue(liked)


if __name__ == "__main__":
    unittest.main()
