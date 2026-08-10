import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import job_collector as jc
import contest_collector as cc
import company_profile as cp


class JobCollectorTest(unittest.TestCase):
    def setUp(self):
        self.config = {
            "include_keywords": ["Python", "SQL", "AI"],
            "exclude_keywords": ["영업"],
        }

    def test_parse_and_score(self):
        raw = {
            "id": "123",
            "url": "https://example.com/123",
            "company": {"detail": {"name": "테스트사"}},
            "position": {
                "title": "Python AI 백엔드 개발자",
                "location": {"name": "서울"},
                "experience-level": {"name": "경력 3년"},
                "required-education-level": {"name": "대졸"},
                "job-type": {"name": "정규직"},
                "job-code": {"name": "Python, SQL"},
            },
            "expiration-date": "2026-08-31",
        }
        job = jc.parse_saramin_job(raw, "Python", self.config)
        self.assertEqual(job.company, "테스트사")
        self.assertIn("Python", job.skills)
        self.assertIn("SQL", job.skills)
        self.assertEqual(job.score, 30)

    def _job_row(self, **overrides):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        conn = jc.connect(Path(directory.name) / "jobs.db")
        self.addCleanup(conn.close)
        values = {
            "source_id": "score-1", "title": "Python AI 자동화 개발자", "company": "테스트사",
            "url": "https://example.com/score-1", "source": "사람인", "location": "서울",
            "experience": "경력 2년", "education": "대졸", "employment_type": "정규직",
            "salary": "연봉 협의", "posted_at": "2026-08-07", "deadline": "2026-08-31",
            "keywords": "SQL 데이터 LLM", "skills": "Python, SQL, FastAPI", "matched_query": "Python 백엔드",
        }
        values.update(overrides)
        jc.upsert_jobs(conn, [jc.Job(**values)])
        return conn.execute("SELECT * FROM jobs").fetchone()

    def test_career_score_is_100_point_explainable_model(self):
        row = self._job_row()
        detail = jc.score_recommendation_candidate(
            row, self.config, "career",
            {"dart_registered": False, "financial_years": 0, "news_count": 0, "related_jobs": 0},
            today=datetime(2026, 8, 9),
        )
        self.assertGreater(detail["total"], 0)
        self.assertLessEqual(detail["total"], 100)
        self.assertEqual(sum(item["max"] for item in detail["dimensions"]), 100)
        self.assertEqual(next(item for item in detail["dimensions"] if item["label"] == "회사 정보 신뢰도")["score"], 0)

    def test_dart_and_financials_are_bonus_not_filter(self):
        without_dart = self._job_row(source_id="no-dart", company="비상장사")
        with_dart = self._job_row(source_id="with-dart", company="공시기업")
        with mock.patch("company_profile._dart_api_key", return_value="key"), \
             mock.patch("company_profile.fetch_dart_corp_code_map", return_value={"공시기업": "001"}), \
             mock.patch("company_profile.find_dart_corp_code", side_effect=lambda name, _: "001" if name == "공시기업" else None), \
             mock.patch("company_profile.fetch_dart_financial_summary", return_value=[{"year": "2025"}]), \
             mock.patch("company_profile.fetch_company_news", return_value=[]), \
             mock.patch("company_profile.search_related_jobs", return_value=[]):
            ranked, info = jc._rank_candidates_by_analyzability([without_dart, with_dart], self.config, "career")
        self.assertEqual(len(ranked), 2)
        self.assertGreater(info["사람인:with-dart"]["total"], info["사람인:no-dart"]["total"])

    def test_parttime_prioritizes_location_and_pay_over_dart(self):
        config = {**self.config, "parttime_locations": ["서울"]}
        practical = self._job_row(
            source="알바몬", source_id="practical", title="Python 데이터 주 3일 오후 알바",
            employment_type="파트타임", salary="시급 15,000원", location="서울",
        )
        opaque = self._job_row(
            source="알바몬", source_id="opaque", title="Python 데이터 보조",
            employment_type="", salary="", location="부산",
        )
        practical_score = jc.score_recommendation_candidate(practical, config, "parttime")["total"]
        opaque_score = jc.score_recommendation_candidate(
            opaque, config, "parttime", {"dart_registered": True, "financial_years": 3, "news_count": 3, "related_jobs": 3},
        )["total"]
        self.assertGreater(practical_score, opaque_score)

    def test_expired_and_duplicate_jobs_do_not_enter_daily_pool(self):
        first = self._job_row(source_id="dup-1", company="중복 회사", title="Python 개발자", deadline="2026-08-31")
        duplicate = self._job_row(source_id="dup-2", company="중복회사", title="Python  개발자", deadline="2026-08-31")
        expired = self._job_row(source_id="expired", company="마감 회사", title="AI 개발자", deadline="2026-08-08")
        eligible = jc._eligible_unique_candidates([first, duplicate, expired], today=datetime(2026, 8, 9))
        self.assertEqual(len(eligible), 1)
        self.assertIn(eligible[0]["source_id"], {"dup-1", "dup-2"})

    def test_job_detail_connection_failure_falls_back_to_next_candidate(self):
        row = self._job_row()
        with mock.patch.object(jc, "fetch_job_detail_text", side_effect=RuntimeError("network down")):
            self.assertIsNone(jc.run_job_analysis(row))

    def test_company_prompt_requires_inline_source_links(self):
        prompt = cp.build_company_prompt(
            "테스트사", {"ceo_nm": "홍길동", "induty_code": "62010"}, [], [], [],
            "회사 소개", [{"title": "내부거래 증가 보도", "url": "https://news.example/article"}],
            "https://company.example",
        )
        self.assertIn("[기업 홈페이지 바로가기](https://company.example)", prompt)
        self.assertIn("[내부거래 증가 보도](https://news.example/article)", prompt)
        self.assertIn("문장 끝에 반드시", prompt)
        self.assertIn("별도의 `참고 링크`, `출처 지도`", prompt)
        self.assertIn("(출처: [기사 제목](URL))", prompt)
        self.assertIn("내부거래·승계·계열분리", prompt)

    def test_company_overview_links_are_injected_after_heading(self):
        text = cp.ensure_company_overview_links(
            "## 1. **기업 개황**\n확인된 내용이다.\n다음 내용", "테스트사", "https://company.example", "001",
        )
        heading_pos = text.index("기업 개황")
        homepage_pos = text.index("기업 홈페이지 바로가기")
        body_pos = text.index("확인된 내용")
        self.assertLess(heading_pos, body_pos)
        self.assertLess(body_pos, homepage_pos)
        self.assertIn("(출처:", text)
        self.assertIn("DART 기업개황 바로가기", text)

    def test_upsert_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            conn = jc.connect(Path(directory) / "jobs.db")
            job = jc.Job(source_id="1", title="개발자", company="A", url="https://example.com/1")
            self.assertEqual(jc.upsert_jobs(conn, [job]), (1, 0))
            job.deadline = "2026-09-01"
            self.assertEqual(jc.upsert_jobs(conn, [job]), (0, 1))
            count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            self.assertEqual(count, 1)
            conn.close()

    def test_contest_prompt_requires_theme_specific_ideas(self):
        with tempfile.TemporaryDirectory() as directory:
            conn = cc.connect(Path(directory) / "contests.db")
            contest = cc.Contest(
                source="테스트",
                source_id="contest-1",
                title="지역 교통 데이터 활용 경진대회",
                organizer="테스트기관",
                url="https://example.com/contest-1",
            )
            cc.upsert_contests(conn, [contest])
            row = conn.execute("SELECT * FROM contests").fetchone()
            prompt = cc.build_contest_prompt(row, "공모분야: 지역 교통 문제 해결")
            conn.close()

        self.assertIn("경진대회 주제 맞춤 출품 아이디어 3개", prompt)
        self.assertIn("주제 적합성", prompt)
        self.assertIn("1인이 짧게 만들 최소", prompt)
        self.assertIn("최우선 추천", prompt)

    def test_contest_analysis_rejects_agent_tool_trace(self):
        leaked = """**Bash**: Check memory index for relevant prior guidance
```\ncat \"/Users/example/.claude/MEMORY.md\"\n```"""
        self.assertFalse(cc._valid_contest_analysis(leaked))

    def test_contest_analysis_accepts_complete_answer(self):
        sections = "\n".join([
            "1. 경진대회 주제 맞춤 출품 아이디어 3개",
            "2. 참여자격/공모분야/평가기준 요약",
            "3. 이 대회가 검증하려는 역량 추론",
            "4. 참가 시 접근 전략",
            "5. 1인 사업자 관점 상품화",
        ])
        self.assertTrue(cc._valid_contest_analysis(sections + "\n" + "구체적 분석 " * 250))

    def test_organization_only_contest_is_excluded(self):
        detail = "참가 대상: ALIO 공시 기준 전체 공공기관. 단독 또는 컨소시엄 참가 가능."
        self.assertTrue(cc._looks_organization_only(detail))
        self.assertFalse(cc._looks_organization_only("공공기관이 주최하며 국민 누구나 참가 가능"))

    def test_candidate_profile_is_sanitized_and_used_in_job_prompt(self):
        profile = jc.load_candidate_profile()
        self.assertTrue(profile["projects"])
        serialized = json.dumps(profile, ensure_ascii=False)
        self.assertNotRegex(serialized, r"01[016789][ -]?\d{3,4}[ -]?\d{4}")
        self.assertNotRegex(serialized, r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

        with tempfile.TemporaryDirectory() as directory:
            conn = jc.connect(Path(directory) / "jobs.db")
            job = jc.Job(source_id="2", title="Python 자동화 개발자", company="B", url="https://example.com/2")
            jc.upsert_jobs(conn, [job])
            row = conn.execute("SELECT * FROM jobs").fetchone()
            prompt = jc.build_analysis_prompt(row, "주요업무 Python 자동화 자격요건 SQL 우대사항 AI")
            conn.close()
        self.assertIn("비식별 후보자 근거 프로필", prompt)
        self.assertIn("맞춤 포트폴리오 구성", prompt)
        self.assertIn("맞춤 자기소개서 초안", prompt)


if __name__ == "__main__":
    unittest.main()
