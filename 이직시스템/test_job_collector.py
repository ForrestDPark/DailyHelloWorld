import json
import tempfile
import unittest
from pathlib import Path

import job_collector as jc
import contest_collector as cc


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
        self.assertEqual(job.score, 70)

    def test_upsert_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            conn = jc.connect(Path(directory) / "jobs.db")
            job = jc.Job(source_id="1", title="개발자", company="A", url="https://example.com/1")
            self.assertEqual(jc.upsert_jobs(conn, [job]), (1, 0))
            job.deadline = "2026-09-01"
            self.assertEqual(jc.upsert_jobs(conn, [job]), (0, 1))
            count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            self.assertEqual(count, 1)

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

        self.assertIn("경진대회 주제 맞춤 출품 아이디어 3개", prompt)
        self.assertIn("주제 적합성", prompt)
        self.assertIn("1인이 짧게 만들 최소", prompt)
        self.assertIn("최우선 추천", prompt)

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
        self.assertIn("비식별 후보자 근거 프로필", prompt)
        self.assertIn("맞춤 포트폴리오 구성", prompt)
        self.assertIn("맞춤 자기소개서 초안", prompt)


if __name__ == "__main__":
    unittest.main()
