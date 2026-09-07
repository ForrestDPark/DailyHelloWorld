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
            "after_page": 1, "duration": 4.6,
            "audio_entries": [{
                "target_id": "study0001-vocab-01", "filename": "word.m4a", "duration": 4.6,
            }],
        }]
        pages = [{"number": 1, "title": "1편 장면 1", "duration": 2.0}]
        opf = builder.make_opf("책", pages, [], False, "urn:test", [], study_pages)
        self.assertIn('href="audio/word.m4a"', opf)
        self.assertIn(builder.clock(4.6), opf)
        self.assertNotIn('id="study-silence"', opf)
        self.assertLess(
            opf.index('<itemref idref="page0001"/>'),
            opf.index('<itemref idref="study0001"/>'),
        )
        ElementTree.fromstring(opf)


class LegacyFuriganaFallbackTest(unittest.TestCase):
    def test_generates_ruby_when_legacy_record_has_no_furigana_field(self):
        xhtml = builder.make_page_xhtml(
            "1편 장면 3 · 13쪽", 13,
            [{"ja": "これ渡してアウターもらいます", "ko": "이걸 건넵니다."}],
        )
        self.assertIn("<ruby>渡<rt>わた</rt></ruby>して", xhtml)

    def test_same_initial_kana_does_not_drop_ruby(self):
        self.assertEqual(
            builder.generated_furigana_html("今いくつになったの?"),
            "<ruby>今<rt>いま</rt></ruby>いくつになったの?",
        )


if __name__ == "__main__":
    unittest.main()
