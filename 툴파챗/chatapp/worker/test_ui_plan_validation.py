"""★ 2026-09-12: "같은 문제가 앞으로 일어나지 않게 파이프라인 검증 개선해줘"
요청 — 유이(UI 개발 페르소나)가 static/index.html·chat.js·style.css 전체를
다시 써서 적용하는 _execute_ui_plan이 결과를 검증 없이 그대로 덮어써서
실제로 "이미 지운 함수를 여전히 호출"하는 코드가 실서비스에 배포됐었다
(하단 채팅 탭이 완전히 빈 화면으로 죽은 사고). 이 테스트는 그 정확한
버그 패턴을 다시 넣었을 때 검증이 막고, 정상적인 변경은 통과시키는지
확인한다."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import persona_worker

VALID_JS = "function greet(name) {\n  return 'hi ' + name;\n}\ndocument.getElementById('greeting');\n"
VALID_HTML = "<!doctype html><html><body><div id=\"greeting\"></div></body></html>"
VALID_CSS = ".foo { color: red; }"


class UiPlanValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        static_dir = Path(self.tmpdir.name) / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text(VALID_HTML, encoding="utf-8")
        (static_dir / "chat.js").write_text(VALID_JS, encoding="utf-8")
        (static_dir / "style.css").write_text(VALID_CSS, encoding="utf-8")
        self.static_dir = static_dir
        self.backup_dir = Path(self.tmpdir.name) / "backups"
        patcher1 = patch.object(persona_worker, "STATIC_DIR", static_dir)
        patcher2 = patch.object(persona_worker, "UI_BACKUP_DIR", self.backup_dir)
        patcher1.start(); self.addCleanup(patcher1.stop)
        patcher2.start(); self.addCleanup(patcher2.stop)

    def test_undefined_function_call_is_rejected_and_not_written(self):
        """실제 사고 재현: 정의는 없는 함수를 호출부만 새로 추가."""
        broken_js = VALID_JS + "\nremovedHelper();\n"
        actions = [{"file": "chat.js", "content": broken_js}]
        problems = persona_worker._validate_ui_plan(actions)
        self.assertTrue(problems, "no-undef가 removedHelper 참조를 잡아내야 한다")
        self.assertTrue(any("removedHelper" in p for p in problems))

        results = persona_worker._execute_ui_plan(actions)
        self.assertTrue(any("검증 실패" in r for r in results))
        self.assertEqual((self.static_dir / "chat.js").read_text(encoding="utf-8"), VALID_JS)

    def test_valid_change_is_accepted_and_written(self):
        new_js = VALID_JS + "\nfunction farewell(name) { return 'bye ' + name; }\n"
        actions = [{"file": "chat.js", "content": new_js}]
        problems = persona_worker._validate_ui_plan(actions)
        self.assertEqual(problems, [])

        results = persona_worker._execute_ui_plan(actions)
        self.assertTrue(any("✅ 적용" in r for r in results), results)
        self.assertEqual((self.static_dir / "chat.js").read_text(encoding="utf-8"), new_js)

    def test_css_brace_mismatch_is_rejected(self):
        broken_css = ".foo { color: red; "  # 닫는 중괄호 누락
        actions = [{"file": "style.css", "content": broken_css}]
        problems = persona_worker._validate_ui_plan(actions)
        self.assertTrue(any("중괄호" in p for p in problems))
        results = persona_worker._execute_ui_plan(actions)
        self.assertEqual((self.static_dir / "style.css").read_text(encoding="utf-8"), VALID_CSS)

    def test_js_referencing_missing_html_id_is_rejected(self):
        """id를 지웠는데 chat.js가 여전히 그 id를 찾는 경우도 같은 계열의
        "런타임에만 드러나는" 사고라 함께 잡는다."""
        js_wants_missing_id = VALID_JS + "\ndocument.getElementById('does-not-exist');\n"
        actions = [{"file": "chat.js", "content": js_wants_missing_id}]
        problems = persona_worker._validate_ui_plan(actions)
        self.assertTrue(any("does-not-exist" in p for p in problems))

    def test_plan_touching_only_html_still_cross_checks_against_existing_js(self):
        """이번 계획에 chat.js가 없어도, index.html에서 id를 지우면 디스크에
        남아있는 기존 chat.js와 교차검증해 걸러야 한다."""
        html_without_id = "<!doctype html><html><body></body></html>"
        actions = [{"file": "index.html", "content": html_without_id}]
        problems = persona_worker._validate_ui_plan(actions)
        self.assertTrue(any("greeting" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
