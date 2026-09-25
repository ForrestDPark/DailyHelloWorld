#!/usr/bin/env python3
"""작품별 미연시 시나리오를 학습카드(어휘+표현+문법)를 전부 녹여 AI로 새로 생성한다.

★ 2026-09-19: "학습단어를 전부다 사용하게끔 시나리오를 수정... 시나리오가 너무
고정되어있는거같은데 학습단어를 토대로 시나리오를 전부 새로 구성했으면 좋겠어"
+ "단어뿐만아니라 원본에있는 대사를 토대로도 상황만들어도되고 학습카드에있는
표현같은것도 활용해서 시나리오를 풍성하고 다양하게" 요청.

- 고정 14일 템플릿(server/dating_sim_story.py의 _seven_day_scenes)은 하루 1단어만
  써서 96개 중 13개만 등장했다. 이 스크립트는 작품마다 학습카드의 어휘·표현을
  요일·장소에 골고루 배정해, 그 단어·표현을 자연스럽게 쓰는 새 대사·선택지를
  AI로 생성한다.
- 등장인물은 모두 성인으로 고정한다. 성인 사이의 합의된 연애·성적 맥락을
  일괄 금지하지 않되, 미성년자·강압·비동의 상황은 만들지 않는다.
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

# ★ 2026-09-24: "클로드는 일본어대사추출에만 작업하고 미연시 스토리추출은 하지마" —
# 시나리오 생성은 Codex 전용이다(Claude 폴백 없음). Codex를 못 쓰는 상태면 이 플래그를
# 세우고 남은 작품 시도를 멈춰, 호출부(resume_dating_sim_backlog 등)가 이미지 생성만
# 이어가다가 Codex가 살아나면 빈 부분을 채우게 한다.
EXIT_CODEX_UNAVAILABLE = 75
codex_unavailable = False

BOOK_LOCATIONS = [
    ("first", "우연히 마주친 곳(서점·길모퉁이 등)"),
    ("walk", "함께 걷는 길·공원·강변"),
    ("quiet", "조용한 찻집·카페"),
]
FURIGANA_RE = re.compile(r"\[([^\]|]+)\|([^\]]+)\]")
JAPANESE_TOKEN_RE = re.compile(r"[^一-龯々〆ヵヶぁ-ゖァ-ヺーA-Za-z0-9]+")


def plain_japanese(text):
    """후리가나·구두점·공백 차이를 없애 필수 재료가 실제 문장에 쓰였는지
    판정한다. 한글 번역은 허용 문자 정규식에서 자연스럽게 제거된다."""
    return JAPANESE_TOKEN_RE.sub("", FURIGANA_RE.sub(r"\1", str(text or "")))


def contains_material(text, material):
    needle = plain_japanese(material.get("ja", ""))
    return bool(needle and needle in plain_japanese(text))


# ★ 2026-09-22 실제 사고: "학습카드의 표현은 이미 정제됐다"는 가정이
# 틀렸다 — ABF-161_J의 216개 표현 중 7개가 원본에서 그대로 뽑힌 노골적
# 성적 대사(性欲が溜まる, パンツ履いてんのか？, 中に入れたい 등)였다.
# 이 프로젝트의 "원본 대사를 그대로 옮기지 않는다" 규칙은 성인 로맨스
# 허용(build_day_prompt) 이후에도 유효하다 — 새로 쓰는 성인 맥락은
# 허용해도 원본 노골적 대사를 "일본어 어순·어휘 유지"로 강제 복사하는 건
# 다른 문제다. 실제로 이 표현들이 필수 재료로 배정된 요일에서 Claude가
# "노골적인 성적 대사"라며 작성을 거부해 생성이 5회 재시도 끝에 실패했다
# (DAY 8, 실측). 필수 재료 풀에서 이런 표현을 미리 걸러낸다 — 걸러진
# 표현은 "필수"에서 빠질 뿐 어휘(vocabulary)나 다른 표현은 그대로 쓰인다.
_EXPLICIT_EXPRESSION_KEYWORDS = (
    "性欲", "性交", "挿入", "挿れ", "絶頂", "勃起", "愛液", "中出し", "中に入れ", "中に出",
    "セックス", "オナニー", "フェラ", "クンニ", "パイズリ", "アナル",
    "犯され", "犯す", "レイプ", "痴漢", "輪姦",
    "おっぱい", "乳首", "クリトリス", "マンコ", "チンコ", "ペニス", "ヴァギナ",
    "イッちゃ", "イク", "ハメ", "アヘ",
    "パンツ履", "ショーツ",
    "エッチ",
    "舐め", "なめ回",
    "飲ませ", "染み込んで", "飲んだっていい", "飲んでいい",
    "妊娠させ", "孕ま", "種付け", "発情", "疼く", "うずく", "淫ら", "媚薬",
    # ★ 2026-09-24: IPZZ-943 DAY 2가 필수 표현 しゃぶってて 하나 때문에 5회 재시도 끝에
    # 실패했다(같은 재료로 계속 거부됨) — 같은 계열의 원본 노골적 표현을 더 걸러낸다.
    "しゃぶ", "咥え", "くわえ", "ぶっかけ", "顔射", "ごっくん", "手コキ", "騎乗", "潮吹", "喘ぎ", "喘い",
)


def _is_explicit_expression(text):
    """원본에서 그대로 뽑힌 노골적 성적 대사인지 어휘 기반으로 판정한다.
    정교한 분류가 아니라 안전 쪽으로 넓게 잡는 필터라, 애매한 표현은
    필수 재료에서 빠지는 쪽을 택한다(빠져도 어휘·다른 표현은 그대로 쓰임)."""
    return any(keyword in text for keyword in _EXPLICIT_EXPRESSION_KEYWORDS)


def load_expressions(work_dir):
    """학습카드의 표현(expressions)을 중복 없이 모은다. "학습용으로 정제된
    문장"이라는 표기와 달리 노골적 성적 대사가 원본 그대로 섞여 있을 수
    있어(위 주석 참고) _is_explicit_expression으로 걸러낸다."""
    try:
        cards = json.loads((work_dir / "scene_study_cards.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    seen, out = set(), []
    for scene in (cards or {}).values():
        for e in (scene or {}).get("expressions", []) or []:
            ja, reading, ko = e.get("ja"), e.get("reading"), e.get("ko")
            if ja and ko and ja not in seen and not _is_explicit_expression(ja):
                seen.add(ja)
                out.append({"ja": ja, "reading": reading or "", "ko": ko})
    return out


GRAMMAR_PATTERN_RE = re.compile(r"「([^」]*[～~][^」]*)」")


def load_grammar_patterns(work_dir):
    """학습카드의 문법 설명에서 실제 연습할 `～` 문형을 뽑는다.

    설명 전체를 대사에 복사하는 대신 문형과 설명을 분리하고, 생성기가 해당
    문형을 활용한 실제 문장을 evidence로 제출하게 한다.
    """
    try:
        cards = json.loads((work_dir / "scene_study_cards.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    seen, out = set(), []
    for scene in (cards or {}).values():
        for entry in (scene or {}).get("grammar", []) or []:
            explanation = entry if isinstance(entry, str) else str((entry or {}).get("text") or "")
            for matched in GRAMMAR_PATTERN_RE.findall(explanation):
                pattern = matched.replace("~", "～").strip()
                if pattern and pattern not in seen:
                    seen.add(pattern)
                    out.append({"pattern": pattern, "explanation": explanation})
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


def distribute_locations(items):
    assigned = {loc: [] for loc, _ in BOOK_LOCATIONS}
    for index, item in enumerate(items):
        assigned[BOOK_LOCATIONS[index % len(BOOK_LOCATIONS)][0]].append(item)
    return assigned


def build_day_prompt(character_ko, day, topic, arc_hint, words, expressions, is_first_day,
                     grammar_patterns=None, continuity_context=""):
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
                "grammar_evidence": [
                    {"pattern": "～たらいい？", "quote": "どこで待ったらいいですか。"}
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

    def fmt_grammar(items):
        return "\n".join(f"- {item['pattern']} = {item['explanation']}" for item in items) or "- (없음)"

    # 단어와 표현을 장면별로 확정 배정한다. AI가 임의로 고르는 후보 목록이
    # 아니라, 그 장면의 lines에 모두 실어야 하는 체크리스트다.
    loc_words = distribute_locations(words)
    loc_expressions = distribute_locations(expressions)
    loc_grammar = distribute_locations(grammar_patterns or [])

    loc_blocks = []
    for loc, desc in BOOK_LOCATIONS:
        loc_blocks.append(
            f"[{loc}] {desc}\n"
            f"이 장소 lines에 반드시 모두 넣을 학습 단어:\n{fmt_words(loc_words[loc])}\n"
            f"이 장소 lines에 반드시 모두 넣을 핵심 표현:\n{fmt_exprs(loc_expressions[loc])}"
            f"\n이 장소 lines에 반드시 활용할 문법 문형:\n{fmt_grammar(loc_grammar[loc])}"
        )
    loc_section = "\n\n".join(loc_blocks)

    first_rule = (
        "두 사람은 방금 처음 만난 완전한 남남이다. 관계의 지속·애착을 "
        "전제하는 말(다시 만나자, 늘 그랬듯이 등)은 하지 마라. 배정된 학습 단어·표현은 "
        "우연한 작은 사고와 첫 인사 맥락 안에 전부 자연스럽게 넣어라."
        if is_first_day else
        "이미 여러 사건을 거치며 연락을 주고받는 성인들이다. 배정된 학습 단어·표현을 현재 상황 "
        "속에 전부 자연스럽게 녹여라. 단어를 지칭하며 설명하지 말고 등장인물의 실제 대사나 "
        "나레이션 문장으로 써라."
    )

    return f"""너는 순화된 언어학습용 연애 시뮬레이션의 시나리오 작가다. 여주인공 이름은
"{character_ko}"(대사에는 반드시 일본어 이름 자리에 "ソイ", 한국어 이름 자리에 "소이"라고
써라 — 프로그램이 실제 이름으로 치환한다). 플레이어는 "당신/너"로 부른다.

★ 절대 규칙:
- 등장인물과 플레이어는 모두 20세 이상의 성인이다. 성인 사이의 합의된 연애·성적 맥락을
  일괄 배제하지 않는다. 다만 미성년자, 강압, 비동의, 착취 상황은 만들지 마라.
- 각 장소에 배정된 학습 단어와 핵심 표현을 그 장소의 lines에 하나도 빠짐없이 실제로 써라.
  핵심 표현의 일본어 어순과 어휘는 유지하되 주변 문맥과 한국어 번역은 장면에 맞게 연결하라.
- 배정된 문법 문형도 그 장소의 lines에 자연스러운 실제 활용형으로 모두 써라. `～` 자체를
  출력하지 말고 앞말을 채운 완성 문장을 쓰며, grammar_evidence에 pattern과 실제 일본어
  문장에서 그대로 인용한 quote를 기록하라. quote는 lines에 문자 그대로 존재해야 한다.
- 독자에게 DAY, n일차, n일째, n日目처럼 날짜를 세는 표현을 노출하지 마라. 사건의 전후 관계와
  장소 변화만으로 흐름이 자연스럽게 이어지게 써라.
- 모든 대사·나레이션·선택지는 "일본어\\n한국어" 두 줄로 쓴다(한 문자열 안에 \\n 하나).
- 한자에는 반드시 [한자|요미가나] 형식으로 후리가나를 단다(한자 덩어리에만, 예:
  [久|ひさ]しぶり, [約束|やくそく]). 히라가나·가타카나·조사에는 달지 않는다. 한국어 줄에는
  후리가나를 넣지 않는다.
- 각 장면(scene)의 lines는 6~9줄. 첫 줄은 직전 사건의 결과나 현재 행동으로 시작하고,
  중간에는 작은 오해·발견·결정 중 하나가 발생해야 한다. 마지막 줄은 반드시 두 선택지가 자연스럽게 답이 되는
  질문이나 화제여야 한다.
- first → walk → quiet가 독립된 세 에피소드처럼 끊기지 않게, 앞 장면의 선택·물건·약속·감정
  중 하나가 다음 장면의 원인이 되도록 연결하라. narration은 3~5문장으로 환경, 플레이어의
  속마음, 직전 사건이 남긴 문제를 보여주되 결론을 먼저 설명하지 마라.
- 선택지는 정확히 2개: 하나는 호감이 오르는 다정/진솔한 답(tone:positive), 하나는
  거리를 두는 무뚝뚝/회피 답(tone:negative). 두 선택지는 반드시 바로 앞 마지막 대사에
  플레이어가 말로 답하는 1인칭 문장이어야 한다. 갑자기 장소로 이동하거나 상대를 부르거나
  기다리는 행동 지시문으로 쓰지 마라.
- lines와 choices 본문 앞에 "ソイ:", "여주 이름:", "佐藤 春「" 같은 화자 이름표를
  붙이지 마라. 화자 이름은 게임 UI가 대사창 위에 별도로 표시한다.
- JSON 객체 하나만 출력하라(코드펜스·설명 금지).

오늘(DAY {day}) 이야기 주제: {topic}
전개 톤 가이드(참고용, 그대로 베끼지 말 것): {arc_hint}
직전 흐름에서 이어받을 사실(없으면 첫 만남부터 시작): {continuity_context or '(없음)'}
{first_rule}

장소별 지정 재료:
{loc_section}

출력 JSON 스키마(정확히 이 구조, 장소는 first/walk/quiet 3개 모두):
{schema_example}"""


def missing_day_materials(day_obj, words, expressions, grammar_patterns=None):
    """배정 재료를 해당 장소의 lines에서 찾는다. 선택지나 번역에만 우연히
    등장한 것은 학습 표현을 시나리오 대사에 활용한 것으로 세지 않는다."""
    missing = []
    word_map = distribute_locations(words)
    expression_map = distribute_locations(expressions)
    grammar_map = distribute_locations(grammar_patterns or [])
    scenes = day_obj.get("scenes", {}) if isinstance(day_obj, dict) else {}
    for loc, _ in BOOK_LOCATIONS:
        lines = (scenes.get(loc) or {}).get("lines") or []
        joined = "\n".join(lines)
        for kind, items in (("단어", word_map[loc]), ("표현", expression_map[loc])):
            for item in items:
                if not contains_material(joined, item):
                    missing.append(f"{loc} {kind}: {item['ja']}")
        evidence = (scenes.get(loc) or {}).get("grammar_evidence") or []
        for item in grammar_map[loc]:
            match = next((entry for entry in evidence
                          if isinstance(entry, dict) and entry.get("pattern") == item["pattern"]), None)
            quote = str((match or {}).get("quote") or "").strip()
            if not quote or not contains_material(joined, {"ja": quote}):
                missing.append(f"{loc} 문법: {item['pattern']}")
    return missing


def validate_day(day_obj, words=None, expressions=None, grammar_patterns=None):
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
        # `～たらいい？` 같은 표기는 학습카드의 문형 템플릿일 뿐이다.
        # 실제 시나리오에는 `どこで待ったらいいですか？`처럼 빈자리를
        # 채운 완성 문장만 허용한다. 문형 메타데이터(pattern)는 예외다.
        visible_texts = list(lines)
        visible_texts.extend(str(c.get("text") or "") for c in choices if isinstance(c, dict))
        if any("～" in text or "~" in text for text in visible_texts):
            return False
        tones = {c.get("tone") for c in choices if isinstance(c, dict) and c.get("text", "").strip()}
        if tones != {"positive", "negative"}:
            return False
    return not missing_day_materials(day_obj, words or [], expressions or [], grammar_patterns or [])


def finalize_day(day, day_obj, vocab_pool, expressions, grammar_patterns):
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
        vocab_used = [meta for meta in vocab_pool if contains_material(joined, meta)]
        expressions_used = [meta for meta in expressions if contains_material(joined, meta)]
        grammar_by_pattern = {item["pattern"]: item for item in grammar_patterns}
        grammar_used = []
        for evidence in sc.get("grammar_evidence") or []:
            meta = grammar_by_pattern.get(str(evidence.get("pattern") or "")) if isinstance(evidence, dict) else None
            quote = str(evidence.get("quote") or "").strip() if isinstance(evidence, dict) else ""
            if meta and quote and contains_material(joined, {"ja": quote}):
                grammar_used.append({**meta, "evidence": quote})
        scene = {"lines": lines, "choices": choices}
        if vocab_used:
            scene["vocab_used"] = vocab_used
        if expressions_used:
            scene["expressions_used"] = expressions_used
        if grammar_used:
            scene["grammar_used"] = grammar_used
        out["scenes"][loc] = scene
    return out


def repair_missing_materials(days, missing_words, missing_expressions):
    """구버전 중간 저장본에서 빠진 소수 학습 재료를 기존 문장에 보강한다.

    일본어/한국어 두 줄 구조와 장면 줄 수를 바꾸지 않도록 첫 문장의 양쪽
    언어 줄에 이어 붙이고, 해당 장면의 사용 메타데이터도 함께 갱신한다.
    """
    targets = [(days[str(day)]["scenes"][loc], day, loc)
               for day in range(2, ds.TOTAL_DAYS + 1)
               for loc, _ in BOOK_LOCATIONS
               if str(day) in days and loc in days[str(day)].get("scenes", {})]
    if not targets:
        return
    materials = [("vocab_used", item) for item in missing_words]
    materials += [("expressions_used", item) for item in missing_expressions]
    for index, (field, item) in enumerate(materials):
        scene, _, _ = targets[index % len(targets)]
        lines = scene.get("lines") or []
        if not lines:
            continue
        japanese, separator, korean = str(lines[0]).partition("\n")
        if not separator:
            korean = ""
        ja = str(item.get("ja") or "").strip()
        ko = str(item.get("ko") or "").strip()
        lines[0] = f"{japanese} {ja}。\n{korean} {ko}.".strip()
        scene.setdefault(field, []).append(item)


def generate_for_work(work_dir, log=print):
    title = work_dir.name
    vocab_pool = [{"ja": ja, "reading": reading, "ko": ko}
                  for ja, reading, ko in ds._load_work_vocabulary(title)]
    if not vocab_pool:
        log(f"❌ {title}: 학습 단어가 없어 생성 불가(학습카드 먼저 생성 필요)")
        return False
    expressions = load_expressions(work_dir)
    grammar_patterns = load_grammar_patterns(work_dir)
    total_days = ds.TOTAL_DAYS
    # 96단어를 2~14일차(13일)에 골고루 → 하루 약 8개, 장소당 2~3개.
    per_day = max(3, -(-len(vocab_pool) // (total_days - 1)))
    word_by_day = assign_round_robin(vocab_pool, total_days, per_day)
    expr_by_day = assign_round_robin(expressions, total_days, max(2, -(-len(expressions) // (total_days - 1))))
    grammar_by_day = assign_round_robin(grammar_patterns, total_days, max(1, -(-len(grammar_patterns) // (total_days - 1))))

    partial_path = work_dir / "dating_sim_scenario.partial.json"
    days = {}
    skipped_expressions = set()
    partial_version = ds.GENERATED_SCENARIO_VERSION
    if partial_path.is_file():
        try:
            partial = json.loads(partial_path.read_text(encoding="utf-8"))
            if partial.get("content_version") == partial_version:
                days = partial.get("days", {})
                skipped_expressions = set(partial.get("skipped_expressions", []))
        except (OSError, ValueError):
            days = {}

    for day in range(1, total_days + 1):
        is_first = day == 1
        words = [] if is_first else word_by_day.get(day, [])
        exprs = [] if is_first else expr_by_day.get(day, [])
        grammars = [] if is_first else grammar_by_day.get(day, [])
        if str(day) in days:
            if validate_day(days[str(day)], words, exprs, grammars):
                log(f"   ↪️ DAY {day} 중간 저장본 재사용")
                continue
            log(f"   ♻️ DAY {day} 중간 저장본 검증 실패 — 완성 문장으로 다시 생성")
            days.pop(str(day), None)
        topic = ds.DAY_TOPICS.get(day, "")
        arc_hint = ds.DAY_NARRATION.get(day, "").split("\n")[-1]
        previous = days.get(str(day - 1), {})
        previous_lines = [line for scene in (previous.get("scenes") or {}).values()
                          for line in (scene.get("lines") or [])]
        continuity = " / ".join(previous_lines[-3:])[-1200:]
        base_prompt = build_day_prompt(title.split("_")[0], day, topic, arc_hint, words, exprs,
                                       is_first, grammars, continuity)
        day_obj = None
        max_attempts = 5
        ai_failed = False
        # ★ 2026-09-24: 같은 필수 재료로 5번 다 실패하면(예: 순화 규칙과 충돌하는 표현) 그
        # 요일은 영원히 못 넘어간다. 마지막에 계속 빠진 필수 "표현"만 사용 불가로 빼고
        # 나머지 재료로 한 번 더 생성한다(어휘·다른 표현은 그대로 필수).
        for fallback_round in range(2):
            base_prompt = build_day_prompt(title.split("_")[0], day, topic, arc_hint, words, exprs,
                                           is_first, grammars, continuity)
            prompt = base_prompt
            last_missing = []
            for attempt in range(max_attempts):
                try:
                    stdout, engine = run_ai_exec(prompt, str(work_dir), timeout=600, engines=["codex"])
                except RuntimeError as exc:
                    log(f"   ⚠️ DAY {day} Codex 호출 실패({exc})")
                    ai_failed = True
                    global codex_unavailable
                    codex_unavailable = True
                    break
                match = re.search(r"\{.*\}", stdout, re.S)
                try:
                    candidate = json.loads(match.group(0)) if match else None
                except json.JSONDecodeError:
                    candidate = None
                if candidate and validate_day(candidate, words, exprs, grammars):
                    day_obj = candidate
                    break
                missing = missing_day_materials(candidate or {}, words, exprs, grammars)
                last_missing = missing
                if attempt + 1 < max_attempts:
                    previous = json.dumps(candidate, ensure_ascii=False) if candidate else "(유효한 JSON 없음)"
                    prompt = (base_prompt
                              + "\n\n★ 아래 이전 출력을 최소한으로 고쳐 다시 JSON만 출력하라. "
                                "빠진 재료는 지정 장소의 lines에 자연스럽게 추가하고 다른 필수 재료는 지우지 마라. "
                                "형식도 함께 다시 확인하라.\n"
                              + "누락: " + "; ".join(missing)
                              + "\n이전 출력: " + previous)
                    preview = "; ".join(missing[:3]) or "JSON 구조 오류"
                    log(f"   ↻ DAY {day} 재시도 {attempt + 2}/{max_attempts} — {preview}")
            if day_obj or ai_failed or fallback_round == 1:
                break
            stuck = [e for e in exprs if any(e["ja"] in item for item in last_missing)]
            if not stuck:
                break
            log(f"   ⚠️ DAY {day}: 계속 반영되지 않는 필수 표현 {len(stuck)}개를 사용 불가로 빼고 다시 생성합니다 — "
                + ", ".join(e["ja"] for e in stuck))
            skipped_expressions.update(e["ja"] for e in stuck)
            exprs = [e for e in exprs if e not in stuck]
        if not day_obj:
            log(f"❌ {title}: DAY {day} 생성 실패 — 중간 저장본은 남김, 재실행 시 이어감")
            return False
        days[str(day)] = finalize_day(day, day_obj, vocab_pool, expressions, grammar_patterns)
        partial_path.write_text(json.dumps({"content_version": partial_version, "days": days,
                                                  "skipped_expressions": sorted(skipped_expressions)}, ensure_ascii=False, indent=1), encoding="utf-8")
        used = sum(len(days[str(day)]["scenes"][loc].get("vocab_used", [])) for loc, _ in BOOK_LOCATIONS)
        log(f"   ✅ DAY {day} 생성 완료 (단어 {used}개 삽입)")

    used_ja, used_expr, used_grammar = set(), set(), set()
    for generated_day in days.values():
        for loc, _ in BOOK_LOCATIONS:
            scene = generated_day["scenes"][loc]
            used_ja.update(w["ja"] for w in scene.get("vocab_used", []))
            used_expr.update(e["ja"] for e in scene.get("expressions_used", []))
            used_grammar.update(e["pattern"] for e in scene.get("grammar_used", []))
    missing_words = [w["ja"] for w in vocab_pool if w["ja"] not in used_ja]
    missing_expressions = [e["ja"] for e in expressions
                           if e["ja"] not in used_expr and e["ja"] not in skipped_expressions]
    if missing_words or missing_expressions:
        word_meta = [w for w in vocab_pool if w["ja"] in missing_words]
        expression_meta = [e for e in expressions if e["ja"] in missing_expressions]
        log(f"   🩹 구버전 중간 저장 누락 복구 — 단어 {len(word_meta)}개, 표현 {len(expression_meta)}개")
        repair_missing_materials(days, word_meta, expression_meta)
        used_ja.update(w["ja"] for w in word_meta)
        used_expr.update(e["ja"] for e in expression_meta)
    scenario = {
        "content_version": ds.GENERATED_SCENARIO_VERSION,
        "coverage": {"vocabulary": [len(used_ja), len(vocab_pool)],
                     "expressions": [len(used_expr), len(expressions)],
                     "grammar": [len(used_grammar), len(grammar_patterns)],
                     "complete": len(used_grammar) == len(grammar_patterns)},
        "days": days,
    }
    if not ds._validate_generated_scenario(scenario, [loc for loc, _ in BOOK_LOCATIONS]):
        log(f"❌ {title}: 최종 검증 실패 — 캐시를 쓰지 않음")
        return False
    (work_dir / "dating_sim_scenario.json").write_text(
        json.dumps(scenario, ensure_ascii=False, indent=1), encoding="utf-8")
    partial_path.unlink(missing_ok=True)
    log(f"🎉 {title}: 시나리오 생성 완료 — 학습 단어 {len(used_ja)}/{len(vocab_pool)}개, "
        f"핵심 표현 {len(used_expr)}/{len(expressions)}개, 문법 {len(used_grammar)}/{len(grammar_patterns)}개 전부 활용")
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


def select_shard(targets, index, count):
    """여러 생성 워커가 같은 작품을 건드리지 않도록 정렬 목록을 분할한다."""
    if count < 1 or index < 0 or index >= count:
        raise ValueError("shard-index는 0 이상 shard-count 미만이어야 합니다")
    return [target for offset, target in enumerate(targets) if offset % count == index]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("work_dir", nargs="?", help="library/<작품 폴더>")
    parser.add_argument("--all", action="store_true", help="학습카드 있는 전 작품 생성")
    parser.add_argument("--force", action="store_true", help="이미 생성된 작품도 다시 생성")
    parser.add_argument("--shard-count", type=int, default=1, help="전체 대기열 분할 수")
    parser.add_argument("--shard-index", type=int, default=0, help="이 프로세스가 맡을 분할 번호(0부터)")
    args = parser.parse_args()

    if args.all:
        try:
            targets = select_shard(works_with_cards(), args.shard_index, args.shard_count)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.work_dir:
        targets = [Path(args.work_dir).resolve()]
    else:
        parser.error("work_dir 또는 --all 중 하나가 필요합니다")

    ok, fail = 0, 0
    for work_dir in targets:
        scenario_path = work_dir / "dating_sim_scenario.json"
        if not args.force and scenario_path.is_file():
            try:
                cached = json.loads(scenario_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cached = {}
            if (cached.get("content_version") == ds.GENERATED_SCENARIO_VERSION
                    and (cached.get("coverage") or {}).get("complete") is True):
                print(f"⏭️  {work_dir.name}: 전수 활용 시나리오가 이미 생성됨(--force로 재생성)")
                continue
            print(f"↻ {work_dir.name}: 이전/불완전 시나리오를 새 규칙으로 교체합니다")
        print(f"\n===== {work_dir.name} =====")
        try:
            if generate_for_work(work_dir):
                ok += 1
            else:
                fail += 1
        except Exception as exc:  # noqa: BLE001
            print(f"❌ {work_dir.name}: 예외 {exc}")
            fail += 1
        if codex_unavailable:
            print("⏸️ Codex를 쓸 수 없어 남은 작품의 시나리오 생성은 건너뜁니다(Claude로는 만들지 않음)")
            break
    print(f"\n완료 — 성공 {ok}개, 실패 {fail}개")
    if codex_unavailable:
        return EXIT_CODEX_UNAVAILABLE
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
