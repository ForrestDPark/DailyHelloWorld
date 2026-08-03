import json
import tempfile
import unittest
from pathlib import Path

import job_collector as jc


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
        job = jc.parse_job(raw, "Python", self.config)
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


if __name__ == "__main__":
    unittest.main()
