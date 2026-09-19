#!/usr/bin/env python3
"""작품별 미연시 시나리오를 학습카드(어휘+표현)를 최대한 녹여 AI로 새로 생성한다.

★ 2026-09-19: "학습단어를 전부다 사용하게끔 시나리오를 수정... 시나리오가 너무
고정되어있는거같은데 학습단어를 토대로 시나리오를 전부 새로 구성했으면 좋겠어"
+ "단어뿐만아니라 원본에있는 대사를 토대로도 상황만들어도되고 학습카드에있는
표현같은것도 활용해서 시나리오를 풍성하고 다양하게" 요청.

- 고정 14일 템플릿(server/dating_sim_story.py의 _seven_day_scenes)은 하루 1단어만
  써서 96개 중 13개만 등장했다. 이 스크립트는 작품마다 학습카드의 어휘·표현을
  요일·장소에 골고루 배정해, 그 단어·표현을 자연스럽게 쓰는 새 대사·선택지를
  AI로 생성한다.
- ★ 안전: 이 미연시는 순화된 언어학습용이다. 원작은 성인물이라 원본 대사를
  그대로 옮기지 않는다. 재료는 이미 학습용으로 추출·정제된 어휘(vocabulary)와
  표현(expressions)만 쓰고, 노골적/성적 내용은 만들지 않는다. 원작 줄거리
  요약(성인 내용)도 프롬프트에 넣지 않는다.
- 생성 결과는 library/<작품>/dating_sim_scenario.json에 캐싱되고, 챗앱 런타임
  (story_for)이 있으면 그걸 쓰고 없으면 고정 템플릿으로 폴백한다.

실행: python3 generate_dating_sim_scenario.py "library/<작품 폴더>"
      python3 generate_dating_sim_scenario.py --all   # 학습카드 있는 전 작품
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LIBRARY_DIR = SCRIPT_DIR / "library"
# 챗앱의 dating_sim_story를 재사용해 스키마·검증·상수를 한 곳에서 관리한다
# (dating_sim_story는 FastAPI 등에 의존하지 않아 단독 import 가능).
CHATAPP_SERVER = SCRIPT_DIR.parent / "툴파챗" / "chatapp" / "server"
sys.path.insert(0, str(CHATAPP_SERVER))
import dating_sim_story as ds  # noqa: E402

sys.path.insert(0, str(SCRIPT_DIR))
from ai_exec import run_ai_exec  # noqa: E402

BOOK_LOCATIONS = [
    ("first", "우연히 마주친 곳(서점·길모퉁이 등)"),
    ("walk", "함께 걷는 길·공원·강변"),
    ("quiet", "조용한 찻집·카페"),
]
FURIGANA_RE = re.compile(r"\[([^\]|]+)\|([^\]]+)\]")


def load_expressions(work_dir):
    """학습카드의 표현(expressions)을 중복 없이 모은다 — 이미 학습용으로 정제된
    문장이라 재료로 안전하게 쓴다."""
    try:
        cards = json.loads((work_dir / "scene_study_cards.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    seen, out = set(), []
    for scene in (cards or {}).values():
        for e in (scene or {}).get("expressions", []) or []:
            ja, reading, ko = e.get("ja"), e.get("reading"), e.get("ko")
            if ja and ko and ja not in seen:
                seen.add(ja)
                out.append({"ja": ja, "reading": reading or "", "ko": ko})
    return out


def assign_round_robin(items, day_count, per_day):
    """items를 요일별로 per_day개씩 순서대로 배정(순환)한다. 남으면 다음
    요일로 계속 돌려 최대한 많이 배정한다."""
    assignments = {day: [] for day in range(2, day_count + 1)}
    if not items:
        return assignments
    idx = 0
    # 전체를 다 소진할 때까지 요일을 순환하며 per_day씩 채운다.
    day_cycle = list(range(2, day_count + 1))
    slot = 0
    while idx < len(items):
        day = day_cycle[slot % len(day_cycle)]
        if len(assignments[day]) < per_day * ((slot // len(day_cycle)) + 1):
            assignments[day].append(items[idx])
            idx += 1
        slot += 1
        if slot > len(day_cycle) * (len(items) + per_day):
            break
    return assignments


def build_day_prompt(character_ko, day, topic, arc_hint, words, expressions, is_first_day):
    schema_example = json.dumps({
        "narration": "[今日|きょう]は[雨|あめ]が[降|ふ]っていた。\n오늘은 비가 내리고 있었다.",
        "scenes": {
            "first": {
                "lines": [
                    "[久|ひさ]しぶりですね。\n오랜만이에요.",
                    "…선택지가 답이 되는 마지막 질문/화제 줄",
                ],
                "choices": [
                    {"text": "[僕|ぼく]も[会|あ]いたかったです。\n저도 보고 싶었어요.", "tone": "positive"},
                    {"text": "그냥 지나가던 길이었어요.", "tone": "negative"},
                ],
            },
            "walk": {"lines": ["..."], "choices": [{"text": "...", "tone": "positive"}, {"text": "...", "tone": "negative"}]},
            "quiet": {"lines": ["..."], "choices": [{"text": "...", "tone": "positive"}, {"text": "...", "tone": "negative"}]},
        },
    }, ensure_ascii=False, indent=1)

    def fmt_words(ws):
        return "\n".join(f"- {w['ja']}({w['reading']}) = {w['ko']}" for w in ws) or "- (이 장소엔 지정 단어 없음, 자연스러우면 생략 가능)"

    def fmt_exprs(es):
        return "\n".join(f"- {e['ja']} = {e['ko']}" for e in es) or "- (없음)"

    # 장소별로 단어를 다시 3등분해 배정한다(각 장소가 다른 단어를 쓰게).
    loc_words = {loc: [] for loc, _ in BOOK_LOCATIONS}
    for i, w in enumerate(words):
        loc_words[BOOK_LOCATIONS[i % 3][0]].append(w)

    loc_blocks = []
    for loc, desc in BOOK_LOCATIONS:
        loc_blocks.append(
            f"[{loc}] {desc}\n"
            f"이 장소 장면에서 자연스럽게 녹일 학습 단어:\n{fmt_words(loc_words[loc])}"
        )
    loc_section = "\n\n".join(loc_blocks)

    first_rule = (
        "오늘은 1일차 — 두 사람은 방금 처음 만난 완전한 남남이다. 관계의 지속·애착을 "
        "전제하는 말(다시 만나자, 늘 그랬듯이 등)이나 학습 단어 삽입은 하지 마라. "
        "우연한 작은 사고로 인사만 나누는 풋풋한 첫 만남이어야 한다."
        if is_first_day else
        "이미 며칠째 만나 연락을 주고받는 사이다. 위 학습 단어·표현을 그날 상황 속에 "
        "자연스럽게 녹여라 — 단어를 지칭하며 설명하지 말고, 등장인물이 실제로 그 단어를 "
        "쓰는 대사가 되게 하라. 억지로 다 넣지 말고 자연스러운 것만."
    )

    return f"""너는 순화된 언어학습용 연애 시뮬레이션의 시나리오 작가다. 여주인공 이름은
"{character_ko}"(대사에는 반드시 일본어 이름 자리에 "ソイ", 한국어 이름 자리에 "소이"라고
써라 — 프로그램이 실제 이름으로 치환한다). 플레이어는 "당신/너"로 부른다.

★ 절대 규칙:
- 전연령가 풋풋한 연애물이다. 노골적/성적/폭력적 내용은 절대 만들지 마라.
- 아래 학습 단어와 표현(이미 학습용으로 정제된 것)만 재료로 쓴다. 원작의 성인 내용은
  참고하지 않는다.
- 모든 대사·나레이션·선택지는 "일본어\\n한국어" 두 줄로 쓴다(한 문자열 안에 \\n 하나).
- 한자에는 반드시 [한자|요미가나] 형식으로 후리가나를 단다(한자 덩어리에만, 예:
  [久|ひさ]しぶり, [約束|やくそく]). 히라가나·가타카나·조사에는 달지 않는다. 한국어 줄에는
  후리가나를 넣지 않는다.
- 각 장면(scene)의 lines는 4~7줄. 마지막 줄은 반드시 두 선택지가 자연스럽게 답이 되는
  질문이나 화제여야 한다.
- 선택지는 정확히 2개: 하나는 호감이 오르는 다정/진솔한 답(tone:positive), 하나는
  거리를 두는 무뚝뚝/회피 답(tone:negative).
- JSON 객체 하나만 출력하라(코드펜스·설명 금지).

오늘(DAY {day}) 이야기 주제: {topic}
전개 톤 가이드(참고용, 그대로 베끼지 말 것): {arc_hint}
{first_rule}

장소별 지정 재료:
{loc_section}

이 회차에서 함께 쓰면 좋은 표현(자연스러운 것만 골라 대사에 녹여라, 전부 안 써도 됨):
{fmt_exprs(expressions)}

출력 JSON 스키마(정확히 이 구조, 장소는 first/walk/quiet 3개 모두):
{schema_example}"""


def validate_day(day_obj):
    if not isinstance(day_obj, dict):
        return False
    scenes = day_obj.get("scenes")
    if not isinstance(scenes, dict):
        return False
    for loc, _ in BOOK_LOCATIONS:
        sc = scenes.get(loc)
        if not isinstance(sc, dict):
            return False
        lines = sc.get("lines")
        choices = sc.get("choices")
        if not isinstance(lines, list) or len(lines) < 2 or not all(isinstance(x, str) and x.strip() for x in lines):
            return False
        if not isinstance(choices, list) or len(choices) != 2:
            return False
        tones = {c.get("tone") for c in choices if isinstance(c, dict) and c.get("text", "").strip()}
        if tones != {"positive", "negative"}:
            return False
    return True


def finalize_day(day, day_obj, word_tags):
    """AI 출력(tone 기반 선택지)을 엔진 스키마(affection 점수)로 변환하고,
    실제로 대사에 등장한 학습 단어를 스캔해 vocab_used로 기록한다."""
    out = {"scenes": {}}
    narration = day_obj.get("narration")
    if isinstance(narration, str) and narration.strip():
        out["narration"] = narration.strip()
    for loc, _ in BOOK_LOCATIONS:
        sc = day_obj["scenes"][loc]
        pos, neg = ds.choice_scores(day, loc, 1)
        choices = []
        for c in sc["choices"]:
            score = pos if c.get("tone") == "positive" else neg
            choices.append({"text": c["text"].strip(), "affection": int(score)})
        # positive가 먼저 오게 정렬(엔진은 순서 무관하지만 캐시 일관성 위해)
        choices.sort(key=lambda c: c["affection"], reverse=True)
        lines = [x.strip() for x in sc["lines"]]
        joined = "\n".join(lines)
        vocab_used = [meta for tag, meta in word_tags if tag in joined]
        scene = {"lines": lines, "choices": choices}
        if vocab_used:
            scene["vocab_used"] = vocab_used
        out["scenes"][loc] = scene
    return out


def generate_for_work(work_dir, log=print):
    title = work_dir.name
    vocab_pool = [{"ja": ja, "reading": reading, "ko": ko}
                  for ja, reading, ko in ds._load_work_vocabulary(title)]
    if not vocab_pool:
        log(f"❌ {title}: 학습 단어가 없어 생성 불가(학습카드 먼저 생성 필요)")
        return False
    expressions = load_expressions(work_dir)
    word_tags = [(f"[{w['ja']}|{w['reading']}]", w) for w in vocab_pool]

    total_days = ds.TOTAL_DAYS
    # 96단어를 2~14일차(13일)에 골고루 → 하루 약 8개, 장소당 2~3개.
    per_day = max(3, -(-len(vocab_pool) // (total_days - 1)))
    word_by_day = assign_round_robin(vocab_pool, total_days, per_day)
    expr_by_day = assign_round_robin(expressions, total_days, max(2, -(-len(expressions) // (total_days - 1))))

    partial_path = work_dir / "dating_sim_scenario.partial.json"
    days = {}
    if partial_path.is_file():
        try:
            days = json.loads(partial_path.read_text(encoding="utf-8")).get("days", {})
        except (OSError, ValueError):
            days = {}

    for day in range(1, total_days + 1):
        if str(day) in days:
            log(f"   ↪️ DAY {day} 중간 저장본 재사용")
            continue
        is_first = day == 1
        words = [] if is_first else word_by_day.get(day, [])
        exprs = [] if is_first else expr_by_day.get(day, [])
        topic = ds.DAY_TOPICS.get(day, "")
        arc_hint = ds.DAY_NARRATION.get(day, "").split("\n")[-1]
        prompt = build_day_prompt(title.split("_")[0], day, topic, arc_hint, words, exprs, is_first)
        day_obj = None
        for attempt in range(3):
            try:
                stdout, engine = run_ai_exec(prompt, str(work_dir), timeout=600)
            except RuntimeError as exc:
                log(f"   ⚠️ DAY {day} AI 호출 실패({exc})")
                break
            match = re.search(r"\{.*\}", stdout, re.S)
            try:
                candidate = json.loads(match.group(0)) if match else None
            except json.JSONDecodeError:
                candidate = None
            if candidate and validate_day(candidate):
                day_obj = candidate
                break
            prompt += ("\n\n★ 이전 출력이 형식 검사를 통과하지 못했다. 장소 3개(first/walk/quiet) "
                       "모두, 각 lines 4~7줄에 마지막이 질문, 선택지 정확히 2개(positive/negative), "
                       "모든 문자열 '일본어\\n한국어' 형식으로 JSON만 다시 출력하라.")
            log(f"   ↻ DAY {day} 재시도 {attempt + 2}/3")
        if not day_obj:
            log(f"❌ {title}: DAY {day} 생성 실패 — 중간 저장본은 남김, 재실행 시 이어감")
            return False
        days[str(day)] = finalize_day(day, day_obj, word_tags)
        partial_path.write_text(json.dumps({"days": days}, ensure_ascii=False, indent=1), encoding="utf-8")
        used = sum(len(days[str(day)]["scenes"][loc].get("vocab_used", [])) for loc, _ in BOOK_LOCATIONS)
        log(f"   ✅ DAY {day} 생성 완료 (단어 {used}개 삽입)")

    scenario = {"content_version": ds.GENERATED_SCENARIO_VERSION, "days": days}
    if not ds._validate_generated_scenario(scenario, [loc for loc, _ in BOOK_LOCATIONS]):
        log(f"❌ {title}: 최종 검증 실패 — 캐시를 쓰지 않음")
        return False
    (work_dir / "dating_sim_scenario.json").write_text(
        json.dumps(scenario, ensure_ascii=False, indent=1), encoding="utf-8")
    partial_path.unlink(missing_ok=True)
    # 실제 사용된 단어 수 집계
    used_ja = set()
    for day_obj in days.values():
        for loc, _ in BOOK_LOCATIONS:
            for w in day_obj["scenes"][loc].get("vocab_used", []):
                used_ja.add(w["ja"])
    log(f"🎉 {title}: 시나리오 생성 완료 — 학습 단어 {len(used_ja)}/{len(vocab_pool)}개 활용")
    return True


def works_with_cards():
    if not LIBRARY_DIR.is_dir():
        return []
    out = []
    for folder in sorted(LIBRARY_DIR.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        cards = folder / "scene_study_cards.json"
        if cards.is_file() and cards.stat().st_size > 0:
            out.append(folder)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("work_dir", nargs="?", help="library/<작품 폴더>")
    parser.add_argument("--all", action="store_true", help="학습카드 있는 전 작품 생성")
    parser.add_argument("--force", action="store_true", help="이미 생성된 작품도 다시 생성")
    args = parser.parse_args()

    if args.all:
        targets = works_with_cards()
    elif args.work_dir:
        targets = [Path(args.work_dir).resolve()]
    else:
        parser.error("work_dir 또는 --all 중 하나가 필요합니다")

    ok, fail = 0, 0
    for work_dir in targets:
        if not args.force and (work_dir / "dating_sim_scenario.json").is_file():
            print(f"⏭️  {work_dir.name}: 이미 생성됨(--force로 재생성)")
            continue
        print(f"\n===== {work_dir.name} =====")
        try:
            if generate_for_work(work_dir):
                ok += 1
            else:
                fail += 1
        except Exception as exc:  # noqa: BLE001
            print(f"❌ {work_dir.name}: 예외 {exc}")
            fail += 1
    print(f"\n완료 — 성공 {ok}개, 실패 {fail}개")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
