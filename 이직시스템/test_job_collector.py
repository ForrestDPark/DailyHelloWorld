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
        # related_jobs=2(자기 자신 + 다른 공고 1건 이상)라 information_void 조건에는
        # 안 걸린다 — DART 미등록 자체는 여전히 감점일 뿐 총점을 0으로 만들지 않는다.
        detail = jc.score_recommendation_candidate(
            row, self.config, "career",
            {"dart_registered": False, "financial_years": 0, "news_count": 0, "related_jobs": 2},
            today=datetime(2026, 8, 9),
        )
        self.assertGreater(detail["total"], 0)
        self.assertLessEqual(detail["total"], 100)
        self.assertEqual(sum(item["max"] for item in detail["dimensions"]), 100)
        # DART 미등록이라 만점(10점)은 못 받지만, 다른 공고도 있어 정보 공백은
        # 아니므로 완전 0점 처리(information_void)까지는 가지 않는다.
        self.assertLess(next(item for item in detail["dimensions"] if item["label"] == "회사 정보 신뢰도")["score"], 10)

    def test_information_void_forces_total_to_zero(self):
        """★ 2026-08-18: DART 미등록+재무 0개년+관련 공고 1건 이하(=지금 채점 중인
        공고 자기 자신 외에 다른 공고 없음)가 모두 겹치면(실제 사례: 한중에스에스 —
        뉴스도 이 회사와 무관한 노이즈뿐이었음) 직무 적합도가 아무리 높아도 총점을
        0으로 강제한다 — 사용자가 "분석할 정보 없음이면 점수도 빵점 처리해"라고
        명시적으로 요청한 정책. related_jobs는 search_related_jobs()가 jobs 테이블을
        회사명으로만 조회해 자기 자신도 포함하므로 "0건"이 아니라 "1건 이하"가
        현실적인 기준이다."""
        row = self._job_row()
        detail = jc.score_recommendation_candidate(
            row, self.config, "career",
            {"dart_registered": False, "financial_years": 0, "news_count": 8, "related_jobs": 1},
            today=datetime(2026, 8, 9),
        )
        self.assertTrue(detail["information_void"])
        self.assertEqual(detail["total"], 0)
        self.assertGreater(detail["subtotal"], 0)  # 다른 항목은 정상 채점됐으나 총점만 0으로 덮임
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
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["company"], "공시기업")
        self.assertEqual(info["사람인:no-dart"]["total"], 0)
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

    def test_parttime_rejects_remote_store_job_outside_asan_commute_area(self):
        row = self._job_row(
            source="알바천국(크롤링)", source_id="gumi-lotteria",
            company="롯데리아 구미원평", title="롯데리아 아르바이트 모집",
            location="경북 구미시", keywords="매장 서빙", skills="", matched_query="",
        )
        accepted, reasons = jc._parttime_recommendation_eligibility(row, self.config)
        self.assertFalse(accepted)
        self.assertIn("활용 근거 없음", reasons[0])

    def test_parttime_accepts_remote_ai_or_asan_coding_job(self):
        remote = self._job_row(
            source="알바몬(크롤링)", source_id="remote-ai", title="재택 AI 데이터 라벨링",
            location="전국", keywords="온라인 원격", skills="AI",
        )
        asan = self._job_row(
            source="알바몬(크롤링)", source_id="asan-code", title="Python 코딩 보조 알바",
            location="충남 아산시", keywords="데이터", skills="Python",
        )
        self.assertTrue(jc._parttime_recommendation_eligibility(remote, self.config)[0])
        self.assertTrue(jc._parttime_recommendation_eligibility(asan, self.config)[0])

    def test_parttime_low_score_still_ranked_not_hidden(self):
        """★ 2026-08-19: 예전엔 50점 미만이면 후보군을 통째로 비워 "적합한 후보가
        없는 날은 갱신을 건너뛴다"는 뜻이었는데, 이게 며칠씩 이어지면 훨씬 예전
        결과가 그대로 남아 "매일 똑같은 것만 보인다"는 문제로 이어졌다("점수 낮아도
        매일 다른 게 보이면 좋겠다"는 요청). 주제 적합성(코딩·AI·온라인)은 별도
        eligibility 필터가 걸러주므로, 점수 자체로는 더 이상 후보를 비우지 않는다."""
        low = self._job_row(
            source="알바몬(크롤링)", source_id="low", title="재택 AI 보조",
            location="전국", employment_type="", salary="", keywords="", skills="AI",
            posted_at="", deadline="", matched_query="",
        )
        with mock.patch("company_profile._dart_api_key", return_value=""), \
             mock.patch("company_profile.fetch_company_news", return_value=[]), \
             mock.patch("company_profile.search_related_jobs", return_value=[]):
            ranked, info = jc._rank_candidates_by_analyzability([low], self.config, "parttime")
        self.assertLess(info["알바몬(크롤링):low"]["total"], jc.PARTTIME_RECOMMENDATION_MIN_SCORE)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["source_id"], "low")

    def test_score_breakdown_lists_each_news_source_link(self):
        row = self._job_row()
        detail = jc.score_recommendation_candidate(
            row, self.config, "career",
            {"dart_registered": True, "financial_years": 0, "news_count": 2, "related_jobs": 1},
            today=datetime(2026, 8, 9),
        )
        text = jc._format_score_breakdown(row, self.config, {
            "score_detail": detail,
            "news_items": [
                {"title": "첫 번째 기사", "url": "https://news.example/1"},
                {"title": "두 번째 기사", "url": "https://news.example/2"},
            ],
        })
        self.assertIn("뉴스 2건", text)
        self.assertIn("뉴스 1: [첫 번째 기사](https://news.example/1)", text)
        self.assertIn("뉴스 2: [두 번째 기사](https://news.example/2)", text)
        blocks = jc._markdown_to_notion_blocks(text)
        company_block = next(
            block for block in blocks
            if block["type"] == "bulleted_list_item"
            and "회사 정보 신뢰도" in block["bulleted_list_item"]["rich_text"][0]["text"]["content"]
        )
        self.assertEqual(len(company_block["bulleted_list_item"]["children"]), 2)

    def test_homepage_sources_are_linked_subitems(self):
        text = cp.homepage_sources_markdown([
            {"category": "공식 홈페이지", "url": "https://company.example", "text": "대표"},
            {"category": "공식 채용공고", "url": "https://company.example/jobs", "text": "개발자 채용"},
            {"category": "복리후생", "url": "https://company.example/benefits", "text": "기숙사와 교육 지원"},
        ])
        self.assertIn("[공식 채용공고 바로가기](https://company.example/jobs)", text)
        self.assertIn("[복리후생 바로가기](https://company.example/benefits)", text)
        self.assertTrue(all(line.startswith("  - ") for line in text.splitlines()))

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

    def test_job_analysis_rejects_internal_agent_chatter(self):
        leaked = "jobs-analyst 에이전트에 위임하여 작업을 진행하겠습니다. " * 100
        self.assertFalse(jc._valid_job_analysis(leaked))

    def test_job_analysis_accepts_complete_answer(self):
        sections = "\n".join((
            "1. 이 회사가 지금 만들려는/겪고 있는 것 추론",
            "2. 연습 프로젝트 추천 1~2개",
            "3. 요구사항/우대사항 요약",
        ))
        self.assertTrue(jc._valid_job_analysis(sections + "\n" + "구체적 근거 " * 100))

    def test_recommendation_status_and_expiry(self):
        self.assertEqual(jc._recommendation_status(0), "분석 제외")
        self.assertEqual(jc._recommendation_status(50), "준비 후 지원")
        self.assertTrue(jc._entry_expired(
            {"deadline": "2026-08-01"}, datetime(2026, 8, 27),
        ))

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
