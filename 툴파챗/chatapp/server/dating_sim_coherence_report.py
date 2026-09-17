"""미연시 콘텐츠 개연성 점검 파이프라인.

★ 2026-09-17: "개연성이 말이안되 개연성 완성도를 훨씬높이도록 파이프라인구성해"
요청 — 스크린샷 두 건(① EPUB 표현 줄이 선택지가 답할 마지막 대사 뒤에 붙어
선택지가 엉뚱한 말에 답하는 것처럼 보임, ② 2일차만 장소 라벨이 "문자 답장"
투로 돼 있는데 실제로는 물리적 장소 장면으로 이어짐)를 계기로, 이런 유형의
불일치를 사람이 스크린샷을 볼 때까지 기다리지 않고 자동으로 잡아내는
점검 도구를 만들었다.

★ 2026-09-17 확장: "이런식으로 억지대화가 나지않게 파이프라인구성하고
갑자기대화가 끝나는식으로 되지않게 파이프라인구성해서 시나리오개연성
완성도 점수까지 평가하도록하자" 요청 — 2일차 라벨·EPUB 표현 줄 버그를
잡은 1차 파이프라인에 이어, "장래 고민인데 왜 무관한 단어 얘기를 하냐"와
"장면이 갑자기 끝난다"(고민 내용 없이 바로 질문으로 넘어가는 구조)를 잡는
규칙, 그리고 0~100 완성도 점수를 매기는 3단계를 추가했다.

★ 2026-09-17 재확장: "건너뛰고 그러는것보다 그표현에맞는 적절한상황을 더
만들어서 대응... 7일이라는 제한도 풀고 하루에 나누는 대화제한도 풀어버려"
요청 — 감정적으로 무거운 요일에 표현 줄을 건너뛰던 방식(DAYS_WITHOUT_
VOCAB_ASIDE)을 버리고 단어 뜻을 카테고리로 분류해 어울리는 상황 문장을
만드는 방식(VOCAB_SITUATION_TEMPLATES)으로 바꿨다. DAY_BEATS의 대사 줄
수를 2개 고정에서 몇 개든 되도록 일반화하고, 7일 → 14일로 확장했다.

★ 2026-09-17 재수정: "왜 갑자기 세탁에대해 이야기한다니 너무 뜬금없잖아
이런식으로 작품에서 표현하나가져온다음 그거에대해서 물어본다던지 하는
컨셉 버려 너무이상해 다른 여주와의 시나리오도 전부 수정해" 요청 — 카테고리
분류로도 여전히 뜬금없었다(분류 실패 단어가 general로 떨어지면 예전과
똑같이 어색함). "오늘의 표현" 기능 자체를 완전히 제거했다 — 관련 규칙
(check_vocab_situation_fits_its_category)도 함께 삭제했다.

구조 (3단계):
  1. 결정론적 규칙 검사(이 파일의 check_*() 함수들, LLM 없이 코드로 판정) —
     "마지막 줄은 항상 선택지가 답하는 문장이어야 한다", "장소 라벨은 전부
     물리적 행동 표현이어야 한다(따옴표+답한다 금지)", "요일별 데이터가
     전부 1~TOTAL_DAYS를 빠짐없이 갖춰야 한다" 같은, 과거 실제로 터진
     버그에서 뽑아낸 불변식을 코드로 고정한다. test_dating_sim_coherence.py가
     이 함수들을 그대로 호출해 전체 테스트 스위트에 편입시켰으므로, 앞으로
     DAY_BEATS·LOCATION_LINES 등을 고칠 때마다 자동으로 재검증된다.
  2. 완성도 점수(score_narrative_completeness) — 1단계 규칙 위반 개수 +
     요일별 대화 깊이(문장 쌍 수로 근사)를 합쳐 0~100 점수를 낸다. ⚠️ 이건
     "적어도 구조적으로 얕지 않다"는 하한선을 보장하는 대리 지표이지 진짜
     의미 판정이 아니다.
  3. 사람(또는 콘텐츠 검토 에이전트)이 읽는 전체 대본 출력(render_full_script) —
     1·2단계로도 못 잡는 "말투가 갑자기 바뀐다"류의 미묘한 어색함은 하루·
     장소·변형별로 실제 플레이 순서 그대로 조립한 전체 대사를 사람이 직접
     읽고 판단해야 한다.

실행: server/.venv/bin/python3 dating_sim_coherence_report.py
"""
import sys
from pathlib import Path

# server/ 패키지의 부모(chatapp/)를 sys.path에 넣어야 `from server import ...`가
# 풀린다 — 이 스크립트를 `python3 dating_sim_coherence_report.py`로 단독
# 실행할 때(테스트 디스커버리를 거치지 않을 때)를 위한 안전장치다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import dating_sim_story as ds


def variant_scenes(location_lines):
    """LOCATION_LINES 또는 VARIANT_2_LOCATION_LINES를 DAY_BEATS와 합쳐
    실제 엔진(_seven_day_scenes)과 똑같은 조립 결과를 돌려준다 — 점검
    로직이 실제 게임 로직과 따로 놀지 않도록 이 함수 자체를 재사용한다."""
    return ds._seven_day_scenes(location_lines)


def check_last_line_matches_outro(scenes_by_variant):
    """선택지는 항상 그 장면의 마지막 줄(beat_outro)에 답해야 한다. EPUB
    표현 줄을 맨 끝에 붙였던 버그(2026-09-17)가 이 불변식을 깼었다.
    DAY_BEATS[day][0]는 몇 줄이든 될 수 있으므로(★ 2026-09-17, "하루에
    나누는 대화제한도 풀어버려" 요청) beat_outro는 항상 마지막 원소[-1]다."""
    issues = []
    for variant_name, scenes in scenes_by_variant.items():
        for day, locations in scenes.items():
            expected_outro = ds.DAY_BEATS[day][0][-1]
            for location, scene in locations.items():
                if scene["lines"][-1] != expected_outro:
                    issues.append(
                        f"[{variant_name}] day={day} location={location}: "
                        f"마지막 줄이 beat_outro가 아님 — {scene['lines'][-1]!r}"
                    )
    return issues


def check_location_labels_are_physical(day_location_actions):
    """장소 선택 라벨은 "어디로 가서 뭘 하는지"를 나타내는 물리적 행동
    표현이어야 한다. 따옴표로 감싼 대사 + "답한다"류 표현은 마치 문자
    답장을 고르는 화면처럼 보이는데, 실제로는 그 장소의 물리적 장면으로
    바로 이어져 어색하다(2일차에서 실제로 발생했던 버그, 2026-09-17)."""
    issues = []
    reply_markers = ("“", "‘", "\"", "'", "「")
    for day, actions in day_location_actions.items():
        for location, label in actions.items():
            if label.startswith(reply_markers) or label.rstrip("다").endswith("답한"):
                issues.append(
                    f"day={day} location={location}: 라벨이 문자 답장투 — {label!r}"
                )
    return issues


def check_day_range_completeness(total_days=ds.TOTAL_DAYS):
    """DAY_BEATS·DAY_NARRATION·DAY_OPENINGS·LOCATION_LINES·
    VARIANT_2_LOCATION_LINES·DAY_LOCATION_ACTIONS가 전부 1~TOTAL_DAYS를
    빠짐없이 갖췄는지 확인한다. 하루라도 빠지면 그 요일에 도달했을 때
    KeyError로 게임이 죽는다 — 개연성 이전에 아예 진행이 끊기는 사고를
    사전에 잡는다."""
    expected_days = set(range(1, total_days + 1))
    issues = []
    named_day_maps = {
        "DAY_BEATS": ds.DAY_BEATS, "DAY_NARRATION": ds.DAY_NARRATION,
        "DAY_OPENINGS": ds.DAY_OPENINGS, "DAY_LOCATION_ACTIONS": ds.DAY_LOCATION_ACTIONS,
    }
    for name, mapping in named_day_maps.items():
        missing = expected_days - set(mapping.keys())
        if missing:
            issues.append(f"{name}에 {sorted(missing)}일차가 없음")
    for name, location_lines in {
        "LOCATION_LINES": ds.LOCATION_LINES, "VARIANT_2_LOCATION_LINES": ds.VARIANT_2_LOCATION_LINES,
    }.items():
        for location, day_map in location_lines.items():
            missing = expected_days - set(day_map.keys())
            if missing:
                issues.append(f"{name}[{location}]에 {sorted(missing)}일차가 없음")
        missing_locations = set(ds.LOCATIONS.keys()) - set(location_lines.keys())
        if missing_locations:
            issues.append(f"{name}에 장소 {sorted(missing_locations)}이(가) 없음")
    return issues


def check_hidden_events_preserve_outro(conn_factory):
    """5·7일차 히든 이벤트(가중치 1)도 활동 대사만 바뀔 뿐, 마지막 줄은
    여전히 beat_outro여야 한다. DB 시드 경로(seed_dating_sim_content)는
    _seven_day_scenes를 안 쓰므로 별도로 확인한다."""
    conn = conn_factory()
    try:
        ds.seed_dating_sim_content(conn)
        issues = []
        for day in sorted(ds.HIDDEN_EVENTS):
            expected_outro = ds.DAY_BEATS[day][0][-1]
            for location in ds.LOCATIONS:
                row = conn.execute(
                    "SELECT outro_line FROM dating_sim_scenarios "
                    "WHERE character_id=? AND day=? AND location_id=? AND variant=3",
                    (ds.CHARACTER_ID, day, location),
                ).fetchone()
                if row is None:
                    issues.append(f"히든 이벤트 day={day} location={location} 행이 없음")
                elif row["outro_line"] != expected_outro:
                    issues.append(f"히든 이벤트 day={day} location={location}: outro_line 불일치")
        return issues
    finally:
        conn.close()


def run_all_checks(conn_factory=None):
    """모든 결정론적 규칙을 돌려 이슈 목록을 합쳐 돌려준다. 빈 리스트면 통과."""
    issues = []
    scenes_by_variant = {
        "variant1": variant_scenes(ds.LOCATION_LINES),
        "variant2": variant_scenes(ds.VARIANT_2_LOCATION_LINES),
    }
    issues += check_last_line_matches_outro(scenes_by_variant)
    issues += check_location_labels_are_physical(ds.DAY_LOCATION_ACTIONS)
    issues += check_day_range_completeness()
    if conn_factory is not None:
        issues += check_hidden_events_preserve_outro(conn_factory)
    return issues


# ── 완성도 점수 (heuristic — 진짜 의미 판정은 render_full_script()를 사람이나
# 콘텐츠 검토 에이전트가 읽는 3단계가 맡는다. 여기서는 "장면당 문장 쌍이
# 몇 개인지"라는 구조적 대리 지표로만 얕은 대화를 근사 탐지한다.) ─────────

def _sentence_pair_count(text):
    """JP/KO 두 줄이 한 쌍이므로 빈 줄을 뺀 줄 수를 2로 나눈다."""
    non_empty = [line for line in text.split("\n") if line.strip()]
    return max(1, len(non_empty) // 2)


def score_day_depth(day):
    """그 날의 대사(DAY_BEATS[day]의 모든 대화 턴)에 담긴 문장 쌍 수로 대화
    깊이를 근사 채점한다. "장래에 대한 고민인데... 고민 내용에 대해서 더
    대화를 해야지" 신고처럼, 원인은 문장 쌍이 2개(도입 1 + 질문 1)뿐이라
    고민의 실체 없이 바로 질문으로 넘어가는 구조였다. 3쌍 이상이면 도입만이
    아니라 구체적인 내용이 최소 한 번은 더 들어간 것으로 본다."""
    beat_lines = ds.DAY_BEATS[day][0]
    total_pairs = sum(_sentence_pair_count(line) for line in beat_lines)
    if total_pairs >= 3:
        return 100
    if total_pairs == 2:
        return 70
    return 40


def score_narrative_completeness(conn_factory=None):
    """결정론적 규칙 위반 개수 + 요일별 대화 깊이를 합쳐 0~100 종합 점수를
    낸다. ⚠️ 이건 구조적 대리 지표일 뿐 진짜 의미 판정이 아니다 — "말투가
    갑자기 바뀐다"류는 여전히 render_full_script() 출력을 사람이 읽어야
    잡힌다. 이 점수는 "적어도 구조적으로는 얕지 않다"는 하한선만 보장한다."""
    issues = run_all_checks(conn_factory=conn_factory)
    invariant_score = max(0, 100 - 20 * len(issues))
    depth_by_day = {day: score_day_depth(day) for day in ds.DAY_BEATS}
    avg_depth = sum(depth_by_day.values()) / len(depth_by_day)
    overall = round((invariant_score + avg_depth) / 2)
    return {
        "overall": overall, "invariant_score": invariant_score,
        "avg_depth_score": round(avg_depth, 1), "depth_by_day": depth_by_day,
        "issues": issues,
    }


def render_full_script():
    """하루·장소·변형별로 실제 플레이 순서 그대로 조립한 전체 대사를 사람이
    읽을 수 있는 텍스트로 뽑는다 — 규칙으로 못 잡는 미묘한 어색함은 이
    출력을 사람(또는 콘텐츠 검토 에이전트)이 직접 읽고 판단한다."""
    lines = []
    for day in sorted(ds.DAY_OPENINGS):
        lines.append(f"===== DAY {day} =====")
        lines.append("[내레이션] " + ds.DAY_NARRATION[day].split("\n")[-1])
        for i, opening in enumerate(ds.DAY_OPENINGS[day], start=1):
            lines.append(f"[도입부 후보 {i}] " + opening.split("\n")[-1])
        for variant_name, location_lines in (("변형1", ds.LOCATION_LINES), ("변형2", ds.VARIANT_2_LOCATION_LINES)):
            scenes = variant_scenes(location_lines)[day]
            for location, scene in scenes.items():
                label = ds.DAY_LOCATION_ACTIONS[day][location]
                lines.append(f"  -- {variant_name} / {location} (라벨: {label}) --")
                for line in scene["lines"]:
                    lines.append("     " + line.split("\n")[-1])
                for choice in scene["choices"]:
                    lines.append(f"     선택지({choice['affection']:+d}): " + choice["text"].split("\n")[-1])
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_full_script())
    score = score_narrative_completeness()
    print("===== 규칙 검사 결과 =====")
    if score["issues"]:
        for issue in score["issues"]:
            print(f"⚠️ {issue}")
    else:
        print("이상 없음.")
    print("===== 완성도 점수 (구조적 대리 지표 — 참고용) =====")
    print(f"종합: {score['overall']}/100 (규칙 {score['invariant_score']}/100, "
          f"평균 대화 깊이 {score['avg_depth_score']}/100)")
    for day, depth in sorted(score["depth_by_day"].items()):
        flag = "" if depth >= 100 else " ⚠️ 얕음 — 대화 내용을 한 줄 더 늘리는 걸 고려"
        print(f"  DAY {day}: 깊이 점수 {depth}/100{flag}")
    if score["issues"]:
        sys.exit(1)
