import unittest
from xml.etree import ElementTree

import build_readaloud_epub as builder


class StudyCardAudioTest(unittest.TestCase):
    def setUp(self):
        self.card = {
            "vocabulary": [{"ja": "進行", "reading": "しんこう", "ko": "진행"}],
            "expressions": [{"ja": "進行は早い", "reading": "しんこうははやい", "ko": "진행은 빠르다"}],
        }

    def test_study_xhtml_has_audio_control_and_item_targets(self):
        xhtml = builder.make_study_xhtml("1편 장면 1", self.card, "학습 카드", "study0001")
        self.assertIn("▶ 단어·표현 듣기", xhtml)
        self.assertIn('id="study0001-vocab-01"', xhtml)
        self.assertIn('id="study0001-expression-01"', xhtml)
        ElementTree.fromstring(xhtml)

    def test_study_smil_links_each_spoken_item(self):
        entries = [
            {"target_id": "study0001-vocab-01", "filename": "word.m4a", "duration": 1.2},
            {"target_id": "study0001-expression-01", "filename": "expression.m4a", "duration": 3.4},
        ]
        smil = builder.make_study_smil("study0001", entries)
        self.assertIn("#study0001-vocab-01", smil)
        self.assertIn("../audio/word.m4a", smil)
        self.assertIn("#study0001-expression-01", smil)
        self.assertNotIn("study-silence.m4a", smil)
        ElementTree.fromstring(smil)

    def test_opf_declares_study_audio_and_real_duration(self):
        study_pages = [{
            "id": "study0001", "href": "study/study0001.xhtml",
            "smil_id": "study0001-smil", "smil_href": "overlays/study0001.smil",
            "before_page": 1, "duration": 4.6,
            "audio_entries": [{
                "target_id": "study0001-vocab-01", "filename": "word.m4a", "duration": 4.6,
            }],
        }]
        pages = [{"number": 1, "title": "1편 장면 1", "duration": 2.0}]
        opf = builder.make_opf("책", pages, [], False, "urn:test", [], study_pages)
        self.assertIn('href="audio/word.m4a"', opf)
        self.assertIn(builder.clock(4.6), opf)
        self.assertNotIn('id="study-silence"', opf)
        ElementTree.fromstring(opf)


if __name__ == "__main__":
    unittest.main()
