import unittest

from server.audio_editor import ffmpeg_filter, kept_segments, normalize_cuts


class AudioEditorTests(unittest.TestCase):
    def test_overlapping_cuts_are_clamped_and_merged(self):
        cuts = normalize_cuts([
            {"start": -2, "end": 3}, {"start": 2.5, "end": 5},
            {"start": 9, "end": 15}, {"start": 7, "end": 7.01},
        ], 10)
        self.assertEqual(cuts, [[0.0, 5.0], [9.0, 10]])

    def test_kept_segments_are_the_cut_complement(self):
        self.assertEqual(kept_segments([
            {"start": 2, "end": 4}, {"start": 6, "end": 7},
        ], 10), [(0.0, 2.0), (4.0, 6.0), (7.0, 10)])

    def test_filter_only_references_fixed_audio_graph(self):
        value = ffmpeg_filter([(0, 2), (4, 6)])
        self.assertIn("atrim=start=0.000000:end=2.000000", value)
        self.assertTrue(value.endswith("[a0][a1]concat=n=2:v=0:a=1[out]"))


if __name__ == "__main__":
    unittest.main()
