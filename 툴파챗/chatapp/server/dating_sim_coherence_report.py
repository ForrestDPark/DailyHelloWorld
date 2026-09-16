"""미연시 콘텐츠 개연성 점검 파이프라인.

★ 2026-09-17: "개연성이 말이안되 개연성 완성도를 훨씬높이도록 파이프라인구성해"
요청 — 스크린샷 두 건(① EPUB 표현 줄이 선택지가 답할 마지막 대사 뒤에 붙어
선택지가 엉뚱한 말에 답하는 것처럼 보임, ② 2일차만 장소 라벨이 "문자 답장"
투로 돼 있는데 실제로는 물리적 장소 장면으로 이어짐)를 계기로, 이런 유형의
불일치를 사람이 스크린샷을 볼 때까지 기다리지 않고 자동으로 잡아내는
점검 도구를 만들었다.

구조 (2단계):
  1. 결정론적 규칙 검사(이 파일의 check_*() 함수들, LLM 없이 코드로 판정) —
     "마지막 줄은 항상 선택지가 답하는 문장이어야 한다", "장소 라벨은 전부
     물리적 행동 표현이어야 한다(따옴표+답한다 금지)", "요일별 데이터가
     전부 1~TOTAL_DAYS를 빠짐없이 갖춰야 한다" 같은, 과거 실제로 터진
     버그에서 뽑아낸 불변식을 코드로 고정한다. test_dating_sim_coherence.py가
     이 함수들을 그대로 호출해 전체 테스트 스위트에 편입시켰으므로, 앞으로
     DAY_BEATS·LOCATION_LINES 등을 고칠 때마다 자동으로 재검증된다.
  2. 사람(또는 콘텐츠 검토 에이전트)이 읽는 전체 대본 출력(render_full_script) —
     결정론적 규칙만으로는 "말투가 갑자기 바뀐다"류의 미묘한 어색함까지는
     못 잡으므로, 하루·장소·변형별로 실제 플레이 순서 그대로 조립한 전체
     대사를 사람이 읽고 검토할 수 있게 텍스트로 뽑아준다.

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
    표현 줄을 맨 끝에 붙였던 버그(2026-09-17)가 이 불변식을 깼었다."""
    issues = []
    for variant_name, scenes in scenes_by_variant.items():
        for day, locations in scenes.items():
            expected_outro = ds.DAY_BEATS[day][0][1]
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
            expected_outro = ds.DAY_BEATS[day][0][1]
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
    issues = run_all_checks()
    print(render_full_script())
    print("===== 규칙 검사 결과 =====")
    if issues:
        for issue in issues:
            print(f"⚠️ {issue}")
        sys.exit(1)
    print("이상 없음.")
