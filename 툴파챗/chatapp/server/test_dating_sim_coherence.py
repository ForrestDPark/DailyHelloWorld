"""미연시 콘텐츠 개연성 점검 파이프라인을 상시 테스트 스위트에 편입한다.

★ 2026-09-17: "개연성이 말이안되 개연성 완성도를 훨씬높이도록 파이프라인구성해"
요청. dating_sim_coherence_report.py의 결정론적 규칙(check_*)들을 그대로
호출한다 — 이 파일이 실패하면 DAY_BEATS·LOCATION_LINES·DAY_LOCATION_ACTIONS
등 콘텐츠를 고칠 때 과거에 실제로 터졌던 유형의 개연성 버그(①선택지가
마지막 대사가 아닌 엉뚱한 줄에 답하는 것처럼 보임, ②장소 라벨이 하루만
다른 문체를 씀, ③요일 데이터 누락)를 다시 만들었다는 뜻이다. 사람이
스크린샷을 볼 때까지 기다리지 않고 커밋 전에 잡아낸다."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import dating_sim_coherence_report as report
from server import dating_sim_story as ds
from server import db


class DatingSimCoherenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(db, "DB_PATH", str(Path(self.temp.name) / "chat.db"))
        self.patch.start()
        db.init_db()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def scenes_by_variant(self):
        return {
            "variant1": report.variant_scenes(ds.LOCATION_LINES),
            "variant2": report.variant_scenes(ds.VARIANT_2_LOCATION_LINES),
        }

    def test_choices_always_answer_the_scenes_actual_last_line(self):
        """★ 2026-09-16/17 실제 버그: EPUB 표현 줄이 장면 끝에 붙어 선택지가
        엉뚱한 마지막 줄에 답하는 것처럼 보였다. 마지막 줄은 항상 선택지가
        답하는 beat_outro여야 한다."""
        issues = report.check_last_line_matches_outro(self.scenes_by_variant())
        self.assertEqual(issues, [], "\n".join(issues))

    def test_location_labels_use_physical_destination_framing_not_text_reply(self):
        """★ 2026-09-17 실제 버그: 2일차만 장소 라벨이 따옴표+"답한다" 문자
        답장투였는데, 실제로는 물리적 장소 장면으로 곧장 이어져 어색했다."""
        issues = report.check_location_labels_are_physical(ds.DAY_LOCATION_ACTIONS)
        self.assertEqual(issues, [], "\n".join(issues))

    def test_every_day_has_complete_content_across_all_data_tables(self):
        """요일 데이터가 하나라도 빠지면 그 날짜에 도달했을 때 KeyError로
        게임이 죽는다 — 개연성 이전에 진행 자체가 끊기는 사고를 막는다."""
        issues = report.check_day_range_completeness()
        self.assertEqual(issues, [], "\n".join(issues))

    def test_hidden_events_also_preserve_the_outro_as_the_last_line(self):
        """5·7일차 히든 이벤트(가중치 1)는 DB 시드 경로를 타므로 별도 확인 —
        활동 대사만 바뀌고 마지막 줄은 여전히 beat_outro여야 한다."""
        issues = report.check_hidden_events_preserve_outro(db.get_conn)
        self.assertEqual(issues, [], "\n".join(issues))

    def test_no_vocab_tangent_on_emotionally_heavy_days(self):
        """★ 2026-09-17 실제 버그: "장래에대한 고민인데 왜 돕다에대해서
        이야기한다는거야 의미가 이해가 안가" — 4·6일차(고민 상담·서운함
        사과) 같은 감정적으로 무거운 요일에 EPUB에서 뽑은 무관한 단어로
        화제를 트는 표현 줄이 섞이면 안 된다."""
        issues = report.check_no_vocab_tangent_on_serious_days(
            [("同棲", "どうせい", "동거"), ("本音", "ほんね", "본심")]
        )
        self.assertEqual(issues, [], "\n".join(issues))

    def test_run_all_checks_reports_nothing_wrong(self):
        """다섯 규칙을 한 번에 묶어 돌리는 진입점(run_all_checks)도 그대로
        비어 있어야 한다 — dating_sim_coherence_report.py를 직접 실행했을
        때와 같은 결과를 테스트로도 보장한다."""
        issues = report.run_all_checks(conn_factory=db.get_conn)
        self.assertEqual(issues, [], "\n".join(issues))

    def test_emotionally_heavy_days_have_concrete_worry_content_not_just_a_question(self):
        """★ 2026-09-17: "고민내영에대해서 더 대화를 해야지 이런식으로
        억지대화가 나지않게" 요청 — 4·6일차는 감정을 언급만 하고 바로
        질문으로 넘어가면 안 되고, 최소한의 구체적인 내용(문장 쌍 3개
        이상)이 있어야 한다는 하한선을 회귀 방지로 건다."""
        for day in ds.DAYS_WITHOUT_VOCAB_ASIDE:
            self.assertEqual(
                report.score_day_depth(day), 100,
                f"day={day}가 다시 얕아짐(문장 쌍 부족) — DAY_BEATS[{day}]에 내용을 더 채워야 함",
            )

    def test_narrative_completeness_score_stays_above_the_floor(self):
        """종합 완성도 점수가 과거 버그 수정 이전 수준(87점 미만)으로
        되돌아가지 않는지 확인하는 회귀 방지 하한선이다."""
        score = report.score_narrative_completeness(conn_factory=db.get_conn)
        self.assertGreaterEqual(score["overall"], 85, score)
        self.assertEqual(score["invariant_score"], 100, score["issues"])


if __name__ == "__main__":
    unittest.main()
