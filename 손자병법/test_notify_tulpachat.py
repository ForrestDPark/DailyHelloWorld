import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("notify_tulpachat.py")
SPEC = importlib.util.spec_from_file_location("notify_tulpachat", SCRIPT_PATH)
notify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notify)


class NotifyTulpaChatTest(unittest.TestCase):
    def test_hanja_lesson_prepares_reading_literal_and_glosses(self):
        page = Path(__file__).with_name("jiudi22_full_page.md")
        markdown = page.read_text(encoding="utf-8")
        _number, original, subtitle = notify.read_page(page)

        lesson = notify.build_hanja_lesson(markdown, original, subtitle)

        self.assertTrue(lesson.startswith("📚 한자선생님입니다"))
        self.assertIn("독음\n\n역기거", lesson)
        self.assertIn("직역\n\n", lesson)
        self.assertIn("易居(역기거)", lesson)
        self.assertIn("梯", lesson)
        self.assertIn("易 — 바꿀 역\n\n其 — 그 기", lesson)
        self.assertIn("梯 — 사다리 제", lesson)

    def test_all_images_are_separated_and_preserved_in_order(self):
        page = Path(__file__).with_name("jiudi22_full_page.md")
        markdown = page.read_text(encoding="utf-8")
        _number, original, _subtitle = notify.read_page(page)

        commanders = notify.victorious_commanders(markdown, original)

        self.assertTrue(commanders)
        section = markdown.split("## 4.", 1)[1].split("## 5.", 1)[0]
        expected_urls = [match.group(2) for match in notify.MARKDOWN_IMAGE_RE.finditer(section)]
        actual_urls = [image["url"] for item in commanders for image in item["images"]]
        self.assertEqual(actual_urls, expected_urls)
        self.assertGreater(len(actual_urls), 2)
        for item in commanders:
            self.assertNotIn("![", item["opening"])
            self.assertNotIn("raw.githubusercontent.com", item["opening"])
            self.assertIn("공유된 도판도 차례대로", item["opening"])
            self.assertIn("\n1. 누가 누구를 속였는가?", item["opening"])
            self.assertIn("\n2. 어떤 사실이 거짓이었는가?", item["opening"])
            self.assertNotIn("뒤에서 반복될 지형을 먼저 잡아두기", item["opening"])
            for image in item["images"]:
                self.assertTrue(image["url"].startswith("https://"))
                self.assertTrue(image["comment"].startswith("🖼️ 도판 해설"))
                self.assertNotIn("사료 원본은 아닙니다", image["comment"])


if __name__ == "__main__":
    unittest.main()
