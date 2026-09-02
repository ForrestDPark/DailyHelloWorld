import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("notify_tulpachat.py")
SPEC = importlib.util.spec_from_file_location("notify_tulpachat", SCRIPT_PATH)
notify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notify)


class NotifyTulpaChatTest(unittest.TestCase):
    def test_images_are_separated_from_commander_opening(self):
        page = Path(__file__).with_name("jiudi21_full_page.md")
        markdown = page.read_text(encoding="utf-8")
        _number, original, _subtitle = notify.read_page(page)

        commanders = notify.victorious_commanders(markdown, original)

        self.assertTrue(commanders)
        self.assertTrue(any(item["image_url"] for item in commanders))
        for item in commanders:
            self.assertNotIn("![", item["opening"])
            self.assertNotIn("raw.githubusercontent.com", item["opening"])
            if item["image_url"]:
                self.assertTrue(item["image_url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
