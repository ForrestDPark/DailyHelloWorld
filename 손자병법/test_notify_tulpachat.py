import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("notify_tulpachat.py")
SPEC = importlib.util.spec_from_file_location("notify_tulpachat", SCRIPT_PATH)
notify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notify)


class NotifyTulpaChatTest(unittest.TestCase):
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
            self.assertIn("공유된 모든 도판", item["opening"])
            for image in item["images"]:
                self.assertTrue(image["url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
