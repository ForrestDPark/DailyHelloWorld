import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("validate_full_modernization.py")
SPEC = importlib.util.spec_from_file_location("validate_full_modernization", SCRIPT_PATH)
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class DeceptionBundleValidationTest(unittest.TestCase):
    def test_partial_deception_heading_cannot_bypass_required_bundle(self):
        source = Path(__file__).with_name("jiudi24_full_page.md").read_text(encoding="utf-8")
        broken = source.replace(
            "#### 속임수 일곱 질문",
            "#### 속임수의 경계와 작동 구조",
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".md",
            dir=SCRIPT_PATH.parent,
            encoding="utf-8",
        ) as fixture:
            fixture.write(broken)
            fixture.flush()
            errors, _warnings = validator.validate_page(Path(fixture.name))

        self.assertTrue(
            any("속임수 일곱 질문 제목이 0개" in error for error in errors),
            errors,
        )


if __name__ == "__main__":
    unittest.main()
