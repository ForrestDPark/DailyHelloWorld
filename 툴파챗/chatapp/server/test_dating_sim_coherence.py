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

    def test_vocab_situation_templates_avoid_meta_commentary(self):
        """★ 2026-09-17: "단어뚝 나오고 그거에대해 말해볼까요 이런식으로
        하눈 컨셉을 버리라는거였지" 요청 — 표현 삽입은 물음표로 화제를
        묻지 않아야 하며, 실제 단어가 문장에 들어가야 한다.

        ★ 2026-09-18(10차): 실제 신고에 나왔던 문제 단어들("효과"·"온천"·
        "참음"처럼 어떤 카테고리에도 안 걸려 general/outcome으로 떨어진
        명사, "그립다"처럼 형용사 사전형인 서술어)을 표본에 추가했다."""
        issues = report.check_vocab_templates_avoid_meta_commentary([
            ("洗濯", "せんたく", "세탁"), ("手伝う", "てつだう", "돕다"),
            ("進行", "しんこう", "진행"), ("悩む", "なやむ", "고민"),
            ("好き", "すき", "좋아함"), ("思い出", "おもいで", "추억"),
            ("約束", "やくそく", "약속"), ("嬉しい", "うれしい", "기쁨"),
            ("効果", "こうか", "효과"), ("温泉", "おんせん", "온천"),
            ("我慢", "がまん", "참음"), ("懐かしい", "なつかしい", "그립다"),
        ])
        self.assertEqual(issues, [], "\n".join(issues))

    def test_no_vocab_narration_on_the_first_meeting_day(self):
        """★ 2026-09-18 실제 버그: 1일차(방금 처음 만난 사이)에 "남다"처럼
        관계 지속을 전제하는 단어가 나레이션으로 나오면, 나레이션 형식으로
        바꿔도 여전히 낯선 사이 설정과 부딪힌다. 1일차는 표현 나레이션 자체를
        완전히 빼야 한다(2일차부터는 이미 연락하는 사이라 허용)."""
        issues = report.check_no_vocab_narration_on_first_meeting_day([
            ("残る", "のこる", "남다"), ("同棲", "どうせい", "동거"), ("思い出", "おもいで", "추억"),
        ])
        self.assertEqual(issues, [], "\n".join(issues))

    def test_run_all_checks_reports_nothing_wrong(self):
        """네 규칙을 한 번에 묶어 돌리는 진입점(run_all_checks)도 그대로
        비어 있어야 한다 — dating_sim_coherence_report.py를 직접 실행했을
        때와 같은 결과를 테스트로도 보장한다."""
        issues = report.run_all_checks(conn_factory=db.get_conn)
        self.assertEqual(issues, [], "\n".join(issues))

    def test_days_with_extra_dialogue_turns_have_concrete_content_not_just_a_question(self):
        """★ 2026-09-17: "고민내영에대해서 더 대화를 해야지 이런식으로
        억지대화가 나지않게" 요청 — 대화가 2턴(도입+질문)뿐이라 감정만
        언급하고 바로 질문으로 넘어가면 안 되는 요일(중간 턴이 있는 4·6
        일차)은 최소한의 구체적인 내용(문장 쌍 3개 이상)이 있어야 한다는
        하한선을 회귀 방지로 건다."""
        days_with_middle_turns = [day for day, (lines, _) in ds.DAY_BEATS.items() if len(lines) > 2]
        self.assertGreaterEqual(len(days_with_middle_turns), 1, "중간 대화 턴이 있는 요일이 하나도 없음")
        for day in days_with_middle_turns:
            self.assertEqual(
                report.score_day_depth(day), 100,
                f"day={day}가 다시 얕아짐(문장 쌍 부족) — DAY_BEATS[{day}]에 내용을 더 채워야 함",
            )

    def test_narrative_completeness_score_stays_above_the_floor(self):
        """종합 완성도 점수가 8~14일차 확장·4·6·10·11·12일차 심화 이후
        수준(90점) 밑으로 되돌아가지 않는지 확인하는 회귀 방지 하한선이다."""
        score = report.score_narrative_completeness(conn_factory=db.get_conn)
        self.assertGreaterEqual(score["overall"], 88, score)
        self.assertEqual(score["invariant_score"], 100, score["issues"])

    def test_day_transition_coherence_covers_every_day_and_stays_above_the_floor(self):
        """★ 2026-09-18: "각각의 장면마다 전방면과의 개연성을 점수화해서
        나타내게해" 요청 — 2일차부터 마지막 날까지 전환이 전부 채점돼
        있어야 하고(요일 추가 시 빠뜨리면 이 테스트가 잡는다), 각 전환
        점수가 70점 밑(원인 없는 급반전 수준)으로 떨어지면 안 된다."""
        rows = report.score_day_transitions()
        covered_days = {row["to_day"] for row in rows}
        self.assertEqual(covered_days, set(range(2, ds.TOTAL_DAYS + 1)))
        for row in rows:
            self.assertGreaterEqual(
                row["score"], 70,
                f"DAY {row['from_day']}→{row['to_day']} 개연성 점수가 너무 낮음: {row['note']}",
            )

    def test_day6_transition_no_longer_has_an_unexplained_mood_reversal(self):
        """★ 2026-09-18 실제 버그: 5일차 '시간이 빨리 간다'는 좋은 분위기
        직후 6일차가 설명 없이 '답장이 뜸해졌다'로 급반전했다. 나레이션에
        시간적 연결('즐거웠던 다음 날부터')이 들어갔는지 확인한다."""
        self.assertIn("다음 날", ds.DAY_NARRATION[6])

    def test_day13_transition_bridges_the_family_conversation(self):
        """★ 2026-09-18 실제 버그: 12일차의 무거운 가족 이야기 직후 13일차가
        곧장 '특별한 날'이라는 밝은 화제로 바뀌어 감정이 안 이어졌다."""
        self.assertIn("가족", ds.DAY_NARRATION[13])

    def test_day2_first_line_grounds_itself_in_day_ones_actual_event(self):
        """★ 2026-09-18 실제 버그: "만나고 바로다음날 이전보다더
        잘말하게됫네여가 나오니까 이상해" 신고 — 장소를 고른 뒤 실제로
        나오는 2일차 첫 대사(DAY_BEATS[2][0])가 "어제보다 자연스럽게
        이야기할 수 있게 됐다"며 여러 번의 대화 연습을 전제했는데, 1일차는
        어제 딱 한 번(그것도 사고로) 만난 사이라 앞뒤가 안 맞았다. 채점
        파이프라인(score_day_transitions)이 narration·openings만 보고
        beat_intro는 놓쳤던 사각지대이기도 하다 — 1일차에 실제로 있었던
        일(인사·연락처 교환)에 근거를 맞췄는지 확인한다."""
        day2_first_line = ds.DAY_BEATS[2][0][0]
        self.assertIn("어제", day2_first_line)
        self.assertIn("연락처", day2_first_line)
        self.assertNotIn("자연스럽게 이야기할 수 있게", day2_first_line)

    def test_day2_location_actions_specify_whose_club_it_is(self):
        """★ 2026-09-18 실제 버그: "동아리가 끝나길기다린다는게 려주동아리
        인지 내동아리인지모르겠고" 신고 — 학교 선택지 라벨이 "동아리 끝나길
        기다린다"뿐이라 누구의 동아리인지 알 수 없었다. LOCATION_LINES의
        2일차 school 대사는 그녀 본인이 자기 동아리를 언급하는 대사이므로
        라벨도 "그녀"를 명시해야 한다."""
        self.assertIn("그녀", ds.DAY_LOCATION_ACTIONS[2]["school"])

    def test_vocab_insertion_returns_to_the_days_own_topic_before_the_outro(self):
        """★ 2026-09-18 실제 버그: "그 다음 장면도 좀 이상해 장면이 전혀
        연결되지가 않잖아" 신고 — 표현 삽입(reveal) 바로 다음 줄이 그날
        원래 하려던 질문(beat_outro)이면 화제가 뚝 끊긴다. reveal과
        beat_outro 사이에 화제를 되돌리는 범용 다리 줄이 항상 있는지
        확인한다."""
        sample_pool = [("効果", "こうか", "효과")]
        scenes = ds._seven_day_scenes(ds.LOCATION_LINES, vocab_pool=sample_pool)
        scene = scenes[2]["cafe"]
        self.assertIn("vocab", scene)
        self.assertEqual(scene["lines"][-2], ds.VOCAB_TRANSITION_BACK)
        self.assertNotEqual(scene["lines"][-1], ds.VOCAB_TRANSITION_BACK)

    def test_outcome_words_no_longer_get_the_unrelated_workplace_stress_story(self):
        """★ 2026-09-18 실제 버그: "효과라는 말이 왜 갑자기 생각났냐고"
        신고 — "효과"가 어떤 카테고리에도 안 걸려 general로 떨어졌는데,
        그때의 general 고정 설화(알바 스트레스를 참는 이야기)는 감정
        억누르기 얘기라 "효과"(효능·결과)와 의미가 안 맞았다. "효과"류
        단어는 이제 전용 outcome 카테고리로 분류되고, general 자체도
        특정 감정을 전제하지 않는 내용 중립적인 틀로 바뀌었는지 확인한다."""
        self.assertEqual(ds._classify_vocab_word("효과"), "outcome")
        for category in ("outcome", "general"):
            for setup, _reveal in ds.VOCAB_SITUATION_TEMPLATES[category]:
                self.assertNotIn("억울", setup, f"{category} 카테고리가 여전히 특정 감정(억울함)을 전제함")

    def test_vocab_reveal_never_uses_the_word_came_to_mind_reference_pattern(self):
        """★ 2026-09-18(10차) 실제 버그: "이거 뭐 다짜고짜 무슨 단어가
        생각났네요 이거 똑같은 패턴 계속 반복되는데... 그냥 그 상황에
        그 단어를 끼워 넣어" 신고 — 8차의 general reveal("{단어}라는
        말이 오늘 하루를 잘 나타내는 것 같다")이 문구만 바뀐 "단어가
        생각났다" 재탕이었다. 모든 카테고리·모든 템플릿·명사/서술어 두
        경로 전부에서 "-라는 말이" 참조형이 reveal에 다시는 안 나오는지
        직접 확인한다(카테고리 키워드 표본 하나씩 + 서술어 강제 표본)."""
        samples = [
            ("洗濯", "せんたく", "세탁"), ("悩む", "なやむ", "고민"),
            ("約束", "やくそく", "약속"), ("手伝う", "てつだう", "돕다"),
            ("好き", "すき", "좋아함"), ("思い出", "おもいで", "추억"),
            ("嬉しい", "うれしい", "기쁨"), ("効果", "こうか", "효과"),
            ("温泉", "おんせん", "온천"), ("懐かしい", "なつかしい", "그립다"),
        ]
        for word in samples:
            for template_index in range(2):
                _setup, reveal, _bridge = ds._vocab_situation_lines(word, template_index)
                self.assertNotIn("라는 말이", reveal, f"{word!r} reveal에 참조형이 되돌아옴: {reveal!r}")
                self.assertNotIn("라는 말을", reveal, f"{word!r} reveal에 참조형이 되돌아옴: {reveal!r}")

    def test_each_category_has_more_than_one_template_for_real_rotation(self):
        """★ 2026-09-18(10차) 실제 버그: "매일 반복되는 패턴은 너무
        이상하잖아" 신고 — template_index로 회전하는 구조는 이미
        있었지만 카테고리마다 템플릿이 1개뿐이라 `% 1`이 항상 0이 되어
        실제로는 절대 회전하지 않았다. 모든 카테고리가 최소 2개 이상의
        서로 다른 템플릿을 갖고 있는지 확인한다."""
        for category, templates in ds.VOCAB_SITUATION_TEMPLATES.items():
            self.assertGreaterEqual(
                len(templates), 2,
                f"{category} 카테고리 템플릿이 {len(templates)}개뿐이라 회전이 안 됨",
            )
            self.assertEqual(len(set(templates)), len(templates), f"{category} 카테고리에 중복 템플릿이 있음")


if __name__ == "__main__":
    unittest.main()
