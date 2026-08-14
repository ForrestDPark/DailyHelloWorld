#!/usr/bin/env python3
"""구지편 전체 페이지가 현재 최신화 기준을 충족하는지 검사한다."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from validate_notion_markup import validate as validate_markup


LAW_TITLE_TEXT = "法을 압축하지 않고 보기 — 곡제·관도·주용"
LAW_SECTIONS = (
    ("곡제", "부대를 어떻게 나누고 결합했는가"),
    ("관도", "누가 명령하고 어떻게 전달했는가"),
    ("주용", "군량·장비·전투 지속 능력을 어떻게 썼는가"),
)
COMMENTATORS = (
    "조조(曹操)", "이전(李筌)", "두목(杜牧)", "매요신(梅堯臣)",
    "장예(張預)", "왕석(王晳)", "가림(賈林)", "두우(杜佑)", "진호(陳皞)",
)
FORBIDDEN_COMMENTARY_PHRASES = (
    "라고 풀이한다", "라고 본다", "라고 설명한다", "라고 강조한다",
    "로 풀이한다", "로 읽는다", "을 강조한다", "을 설명한다",
)
PERSON_COLOR_MANIFESTS = {
    "jiudi8_full_page.md": {
        "red": (
            "삼소노프", "렌넨캄프", "질린스키", "클리우예프",
            "아르타모노프", "블라고베셴스키", "방연", "태자 신",
            "위 혜왕",
        ),
        "blue": (
            "힌덴부르크", "루덴도르프", "호프만", "프랑수아", "숄츠",
            "마켄젠", "벨로", "몰트케", "손빈", "전기", "제 위왕",
        ),
    },
    "jiudi9_full_page.md": {
        "red": (
            "펨버턴", "존스턴", "데이비스", "원소", "안량", "문추",
            "유비", "전풍", "저수", "곽도", "심배", "순우경",
        ),
        "blue": (
            "그랜트", "포터", "조조", "관우", "순유", "순욱", "허유",
        ),
    },
}
CITY_HIGHLIGHT_MANIFESTS = {
    "jiudi8_full_page.md": (
        "알렌슈타인", "호엔슈타인", "나이덴부르크", "빌렌베르크", "대량",
    ),
    "jiudi9_full_page.md": (
        "빅스버그", "브루인즈버그", "잭슨", "포트 허드슨",
        "허(許)", "백마", "연진", "오소",
    ),
}
CITY_CAMP_MANIFESTS = {
    "jiudi9_full_page.md": {
        "blue": ("브루인즈버그", "허(許)", "백마", "연진", "관도"),
        "red": ("빅스버그", "잭슨", "포트 허드슨", "오소"),
    },
}
DECEPTION_QUESTIONS = (
    "누가 누구를 속였는가?",
    "어떤 사실이 거짓이었는가?",
    "어떤 사실은 진실이지만 오해를 유도했는가?",
    "상대는 왜 그것을 믿고 싶어 했는가?",
    "속임수가 없었어도 같은 오판이 발생했을까?",
    "속은 사람은 어떤 독립 확인을 생략했는가?",
    "신뢰·동의·안전을 해치지 않으면서 같은 원리를 어디서 연습할 수 있는가?",
)
DECEPTION_NARRATIVE_BEATS = (
    "주체와 의도", "보인 신호와 믿은 이유", "유발된 행동과 결과", "사료의 경계",
)
DECEPTION_TWELVE = (
    "能而示之不能", "用而示之不用", "近而示之遠", "遠而示之近",
    "利而誘之", "亂而取之", "實而備之", "強而避之",
    "怒而撓之", "卑而驕之", "佚而勞之", "親而離之",
)
COUNTRY_EMOJI_MANIFESTS = {
    "jiudi15_full_page.md": (
        "🇲🇹 몰타", "🏛️ 오스만 제국", "🏛️ 시칠리아 왕국", "🏛️ 신(新) 왕조",
    ),
}


def tables(text: str) -> list[str]:
    return re.findall(r"<table\b[^>]*>.*?</table>", text, re.DOTALL)


def validate_law_comparisons(text: str) -> list[str]:
    errors: list[str] = []
    title_positions = [
        m.start()
        for m in re.finditer(
            rf"^\s*#{{4,5}}\s+{re.escape(LAW_TITLE_TEXT)}\s*$",
            text,
            re.MULTILINE,
        )
    ]
    if len(title_positions) != 2:
        errors.append(
            f"法 상세 비교 묶음이 {len(title_positions)}개입니다"
            "(정상: 서양 1개 + 동양 1개)"
        )

    for index, start in enumerate(title_positions):
        end = title_positions[index + 1] if index + 1 < len(title_positions) else len(text)
        block = text[start:end]
        headings = [
            m.start()
            for name, question in LAW_SECTIONS
            for m in [re.search(rf"\*\*{name} [^*]+\({name}\): {re.escape(question)}\*\*", block)]
            if m
        ]
        if len(headings) != 3:
            errors.append(
                f"{index + 1}번째 法 상세 비교: 곡제·관도·주용 표준 제목이 모두 있지 않습니다"
            )
            continue
        if headings != sorted(headings):
            errors.append(f"{index + 1}번째 法 상세 비교: 곡제→관도→주용 순서가 아닙니다")

        block_tables = tables(block)
        if len(block_tables) < 3:
            errors.append(
                f"{index + 1}번째 法 상세 비교: 비교표가 {len(block_tables)}개입니다(정상: 3개)"
            )
            continue
        for table_index, table in enumerate(block_tables[:3], start=1):
            rows = re.findall(r"<tr\b[^>]*>.*?</tr>", table, re.DOTALL)
            if len(rows) != 3:
                errors.append(
                    f"{index + 1}번째 法 상세 비교 {table_index}번 표: "
                    f"헤더+양군 정확히 3행이어야 합니다(현재 {len(rows)}행)"
                )
            if 'color="blue"' not in table or 'color="red"' not in table:
                errors.append(
                    f"{index + 1}번째 法 상세 비교 {table_index}번 표: "
                    "승군 파란색·패군 붉은색 진영 행이 모두 필요합니다"
                )

    return errors


def validate_page(path: Path) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    errors = validate_markup(
        text,
        require_five_sections=True,
        require_latest_five_tables=True,
    )
    warnings: list[str] = []
    errors.extend(validate_law_comparisons(text))

    for label in COUNTRY_EMOJI_MANIFESTS.get(path.name, ()):
        if label not in text:
            errors.append(f"국가·역사 세력 식별 이모지 표기 누락: {label}")

    if "<table_of_contents" not in text:
        errors.append("페이지 맨 위 자동 목차가 없습니다")
    subtitle = next((line for line in text.splitlines() if line.startswith("> ")), "")
    if not re.search(r"[一-龥]+\([가-힣]+\)\s*—\s*\S", subtitle):
        errors.append("맨 위 부제가 '핵심 한자(독음) — 간단 요약' 구조가 아닙니다")
    if "prod-files-secure" in text or "X-Amz-Expires" in text:
        errors.append("만료되는 임시 이미지 URL이 남아 있습니다")

    permanent_images = re.findall(
        r"!\[[^\]]*\]\(https://raw\.githubusercontent\.com/"
        r"ForrestDPark/DailyHelloWorld/main/[^)]+\)",
        text,
    )
    generated_images = [
        image for image in permanent_images
        if "/generated/jiudi" in image
    ]
    if not 10 <= len(generated_images) <= 12:
        errors.append(
            f"신규 핵심 이미지가 {len(generated_images)}개입니다"
            "(정상: 전투별 핵심 5종 × 2 = 10개; "
            "선택 병사 안내판 포함 시 최대 12개)"
        )

    for section_number in range(2, 6):
        heading = re.search(rf"^## {section_number}\..*$", text, re.MULTILINE)
        if not heading or 'toggle="true"' not in heading.group(0):
            errors.append(f"{section_number}번 섹션 제목에 기준본 대형 토글이 없습니다")

    if text.count("🏳️ <span color=\"red\">**패군 측 결과**</span>") != 2:
        errors.append("패군 측 결과 라벨이 정확히 2개가 아닙니다")
    if text.count("🏆 <span color=\"blue\">**승군 측 결과**</span>") != 2:
        errors.append("승군 측 결과 라벨이 정확히 2개가 아닙니다")

    section_one_start = text.find("## 1.")
    section_two_start = text.find("## 2.", section_one_start + 1)
    section_one = (
        text[section_one_start:section_two_start]
        if section_one_start >= 0 and section_two_start > section_one_start
        else ""
    )
    details_match = re.search(r"<details(?P<attrs>[^>]*)>", section_one)
    if not details_match:
        errors.append("1번 섹션에 원문·독음 토글이 없습니다")
    elif re.search(r"\bcolor\s*=", details_match.group("attrs")):
        errors.append("1번 섹션 원문·독음 토글에 금지된 색상 속성이 있습니다")
    summary_match = re.search(
        r"<summary>(.*?)<br>(.*?)</summary>",
        section_one,
        re.DOTALL,
    )
    if not summary_match:
        errors.append("1번 섹션 토글 제목에 원문과 독음이 <br>로 결합돼 있지 않습니다")
    elif '<span color="red">' not in summary_match.group(1):
        errors.append("1번 섹션 원문의 핵심 한자가 붉은색으로 표시돼 있지 않습니다")
    if "**직역**" not in section_one:
        errors.append("1번 섹션에 직역이 없습니다")
    if "#### 글자들이 완성하는 한 장면" not in section_one:
        errors.append("1번 섹션 끝에 '글자들이 완성하는 한 장면'이 없습니다")
    key_headings = re.findall(
        r"^\s*#### (?!글자들이 완성하는 한 장면)(.+)$",
        section_one,
        re.MULTILINE,
    )
    if len(key_headings) < 3:
        errors.append(
            f"1번 섹션의 핵심 한자 서사 풀이가 {len(key_headings)}개입니다(최소 3개)"
        )

    section_three_start = text.find("## 3.", section_two_start + 1)
    section_two = (
        text[section_two_start:section_three_start]
        if section_two_start >= 0 and section_three_start > section_two_start
        else ""
    )
    for commentator in COMMENTATORS:
        if f"**{commentator}**" not in section_two:
            errors.append(f"2번 전통 주석에 {commentator}가 없습니다")
    commentary_rows = re.findall(
        r'^\s*-\s+\*\*[^*]+\*\*\s+—\s+"[^"]+"',
        section_two,
        re.MULTILINE,
    )
    if len(commentary_rows) != len(COMMENTATORS):
        errors.append(
            f"직접화법 큰따옴표 전통 주석이 {len(commentary_rows)}개입니다"
            f"(정상: {len(COMMENTATORS)}개)"
        )
    emphasized_commentary_rows = [
        row for row in commentary_rows
        if re.search(r'—\s+"[^"\n]*\*\*[^*\n]+\*\*[^"\n]*"', row)
    ]
    if len(emphasized_commentary_rows) != len(COMMENTATORS):
        errors.append(
            f"핵심 구절이 굵게 강조된 전통 주석이 "
            f"{len(emphasized_commentary_rows)}개입니다"
            f"(정상: {len(COMMENTATORS)}개)"
        )
    if '<span color="blue">' in section_two:
        errors.append("2번 전통 주석에 폐기된 파란색 글자 강조가 남아 있습니다")
    for phrase in FORBIDDEN_COMMENTARY_PHRASES:
        if phrase in section_two:
            errors.append(f"2번 전통 주석에 금지된 3인칭 간접화법이 있습니다: {phrase}")

    section_four_for_cross = text.find("## 4.", section_three_start + 1)
    section_three = (
        text[section_three_start:section_four_for_cross]
        if section_three_start >= 0 and section_four_for_cross > section_three_start
        else ""
    )
    cross_axes = (
        "① 손자병법", "② 클라우제비츠", "③ 미야모토 무사시",
        "④ 오자병법", "⑤ 현대",
    )
    axis_positions: list[int] = []
    for axis in cross_axes:
        position = section_three.find(axis)
        axis_positions.append(position)
        if position < 0:
            errors.append(f"3번 교차 설명에 {axis} 축이 없습니다")
    if all(position >= 0 for position in axis_positions):
        for index, start in enumerate(axis_positions):
            end = axis_positions[index + 1] if index + 1 < len(axis_positions) else len(section_three)
            axis_block = section_three[start:end]
            # Notion은 저장 과정에서 빈 줄을 제거하지만 서로 다른 문단은
            # 별도 블록/줄로 유지한다. 로컬 초안의 빈 줄과 저장 후 본문을
            # 같은 기준으로 검사하기 위해 비어 있지 않은 본문 줄을 센다.
            paragraphs = [
                line.strip()
                for line in axis_block.splitlines()[1:]
                if line.strip()
                and not re.match(r"^\s*(?:#{1,4}\s+|-\s+\*\*)", line)
            ]
            if len(paragraphs) < 2:
                errors.append(
                    f"3번 교차 설명 {cross_axes[index]} 축이 {len(paragraphs)}문단입니다"
                    "(최소 2문단)"
                )

    section_four_start = text.find("## 4.")
    section_five_start = text.find("## 5.", section_four_start + 1)
    section_four = (
        text[section_four_start:section_five_start]
        if section_four_start >= 0 and section_five_start > section_four_start
        else ""
    )
    audit_section = re.sub(r"^!\[[^\]]*\]\([^\n]+\)$", "", section_four, flags=re.MULTILINE)
    person_manifest = PERSON_COLOR_MANIFESTS.get(path.name)
    if person_manifest:
        for color, names in person_manifest.items():
            for name in names:
                correctly_colored = re.compile(
                    rf'<span color="{color}">\*\*[^*\n]*{re.escape(name)}[^*\n]*\*\*</span>'
                )
                without_correct = correctly_colored.sub("", audit_section)
                if re.search(re.escape(name), without_correct):
                    errors.append(f"장수 이름의 {color} 진영색 누락 또는 오색: {name}")

    if "🏙️" in text:
        errors.append("폐지된 도시 이모지 🏙️가 남아 있습니다")

    city_manifest = CITY_HIGHLIGHT_MANIFESTS.get(path.name)
    if city_manifest:
        city_audit = audit_section
        for city in city_manifest:
            correctly_marked = re.compile(
                rf'<span color="yellow_bg">\*\*[^*\n]*{re.escape(city)}[^*\n]*\*\*</span>'
            )
            city_audit = correctly_marked.sub("", city_audit)
        for city in city_manifest:
            if re.search(re.escape(city), city_audit):
                errors.append(f"도시·마을 이름의 노란 배경 굵은 표기 누락: {city}")

    city_camp_manifest = CITY_CAMP_MANIFESTS.get(path.name)
    if city_camp_manifest:
        for color, cities in city_camp_manifest.items():
            for city in cities:
                city_spans = list(re.finditer(
                    rf'<span color="yellow_bg">\*\*[^*\n]*{re.escape(city)}[^*\n]*\*\*</span>',
                    audit_section,
                ))
                required_prefix = f'<span color="{color}">**▰**</span> '
                if any(
                    not audit_section[:match.start()].endswith(required_prefix)
                    for match in city_spans
                ):
                    errors.append(f"도시·마을의 {color} 진영색 ▰ 누락 또는 오색: {city}")

    case_starts = [m.start() for m in re.finditer(r"^\s*### (?:서양|동양) — ", section_four, re.MULTILINE)]
    if len(case_starts) != 2:
        errors.append(f"서양·동양 역사 사례가 {len(case_starts)}개입니다(정상: 2개)")
    for index, start in enumerate(case_starts):
        end = case_starts[index + 1] if index + 1 < len(case_starts) else len(section_four)
        case = section_four[start:end]
        case_title = case.splitlines()[0].strip()
        if " vs " not in case_title or " │ " not in case_title:
            errors.append(
                f"{index + 1}번째 역사 사례 제목에 'A 진영 vs B 진영 │ 전투명' 구조가 없습니다"
            )
        else:
            matchup = case_title.split("—", 1)[-1].split("│", 1)[0]
            sides = [side.strip() for side in matchup.split(" vs ")]
            if len(sides) != 2 or any(len(side) < 2 for side in sides):
                errors.append(f"{index + 1}번째 역사 사례 제목의 양측 집단명이 불완전합니다")
        deception_headings = list(re.finditer(
            r"^\s*#### 전투에서 사용된 속임수 — \S.+$", case, re.MULTILINE
        ))
        structure_headings = list(re.finditer(
            r"^\s*#### 속임수 작동 구조\s*$", case, re.MULTILINE
        ))
        questions_headings = list(re.finditer(
            r"^\s*#### 속임수 일곱 질문\s*$", case, re.MULTILINE
        ))
        selected_deception_headings = list(re.finditer(
            r"^\s*#### 시계편 兵者詭道也 — 이 전장에 해당하는 속이는 길\s*$",
            case,
            re.MULTILINE,
        ))
        law_heading = re.search(
            r"^\s*#### 法 한눈 비교 — 곡제·관도·주용\s*$", case, re.MULTILINE
        )
        has_deception_bundle = bool(
            deception_headings or structure_headings or questions_headings
            or selected_deception_headings
        )
        if has_deception_bundle and len(deception_headings) < 1:
            errors.append(f"{index + 1}번째 역사 사례의 선택 속임수 묶음에 전투서사가 없습니다")
        if has_deception_bundle and len(structure_headings) != 1:
            errors.append(
                f"{index + 1}번째 역사 사례의 속임수 작동 구조 제목이 "
                f"{len(structure_headings)}개입니다(정상: 1개)"
            )
        if has_deception_bundle and len(questions_headings) > 1:
            errors.append(
                f"{index + 1}번째 역사 사례의 속임수 일곱 질문 제목이 "
                f"{len(questions_headings)}개입니다(정상: 0~1개)"
            )
        if has_deception_bundle and len(selected_deception_headings) != 1:
            errors.append(
                f"{index + 1}번째 역사 사례의 시계편 해당 길 선별 제목이 "
                f"{len(selected_deception_headings)}개입니다(정상: 1개)"
            )
        if deception_headings and structure_headings and questions_headings and selected_deception_headings and law_heading:
            if not (
                deception_headings[-1].start()
                < structure_headings[0].start()
                < questions_headings[0].start()
                < selected_deception_headings[0].start()
                < law_heading.start()
            ):
                errors.append(
                    f"{index + 1}번째 역사 사례의 순서가 "
                    "속임수 서사→작동 구조→일곱 질문→시계편 해당 길 선별→法 비교가 아닙니다"
                )
            structure_block = case[
                structure_headings[0].end():questions_headings[0].start()
            ]
            structure_tables = tables(structure_block)
            if structure_tables:
                errors.append(
                    f"{index + 1}번째 역사 사례의 속임수 작동 구조에 "
                    f"폐기된 표가 {len(structure_tables)}개 남아 있습니다"
                )
            for beat in DECEPTION_NARRATIVE_BEATS:
                if structure_block.count(f"**{beat}.**") != 1:
                    errors.append(
                        f"{index + 1}번째 속임수 작동 구조 서사의 필수 문단 누락: {beat}"
                    )
        if questions_headings:
            for question in DECEPTION_QUESTIONS:
                if case.count(f"**{question}**") != 1:
                    errors.append(
                        f"{index + 1}번째 역사 사례의 선택 일곱 질문 누락·중복: {question}"
                    )
        if selected_deception_headings and law_heading:
            selected_block = case[selected_deception_headings[0].end():law_heading.start()]
            selected_tables = tables(selected_block)
            if len(selected_tables) != 1:
                errors.append(
                    f"{index + 1}번째 역사 사례의 시계편 해당 길 표가 "
                    f"{len(selected_tables)}개입니다(정상: 1개)"
                )
            else:
                selected_maxims = [m for m in DECEPTION_TWELVE if m in selected_tables[0]]
                if not selected_maxims:
                    errors.append(f"{index + 1}번째 시계편 표에 실제 적용 항목이 없습니다")
                if len(selected_maxims) >= len(DECEPTION_TWELVE):
                    errors.append(f"{index + 1}번째 시계편 표가 열두 길을 전부 나열했습니다")
                if len(selected_maxims) != len(set(selected_maxims)):
                    errors.append(f"{index + 1}번째 시계편 표에 중복 항목이 있습니다")
                if "확인되지 않음" in selected_tables[0] or "방어 원칙" in selected_tables[0]:
                    errors.append(f"{index + 1}번째 시계편 표에 미사용·일반 원칙이 포함됐습니다")
                selected_rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", selected_tables[0], re.DOTALL)
                for row_number, row in enumerate(selected_rows, start=1):
                    cell_count = len(re.findall(r"<td\b[^>]*>", row))
                    if cell_count != 2:
                        errors.append(
                            f"{index + 1}번째 시계편 표 {row_number}행이 {cell_count}열입니다(정상: 2열)"
                        )
                    if row_number > 1:
                        first_cell = re.search(r"<td\b[^>]*>(.*?)</td>", row, re.DOTALL)
                        if not first_cell or "<br>" not in first_cell.group(1):
                            errors.append(
                                f"{index + 1}번째 시계편 표 {row_number}행 첫 칸에 한문과 독음·뜻을 잇는 <br>가 없습니다"
                            )
        terrain_marker = "**뒤에서 반복될 지형을 먼저 잡아두기**"
        marker_count = case.count(terrain_marker)
        if marker_count != 1:
            errors.append(
                f"{index + 1}번째 역사 사례의 지형 예고 제목이 "
                f"{marker_count}개입니다(정상: 1개)"
            )
        else:
            terrain_start = case.find(terrain_marker) + len(terrain_marker)
            terrain_tail = case[terrain_start:]
            next_heading = re.search(r"^\s*#{3,4}\s+", terrain_tail, re.MULTILINE)
            terrain_block = terrain_tail[:next_heading.start()] if next_heading else terrain_tail
            terrain_items = re.findall(r"^\s*-\s+\S.+$", terrain_block, re.MULTILINE)
            if len(terrain_items) < 3:
                errors.append(
                    f"{index + 1}번째 역사 사례의 지형 예고 목록이 "
                    f"{len(terrain_items)}개입니다(최소 3개)"
                )
        scene_headings = re.findall(r"^\s*#### (.+)$", case, re.MULTILINE)
        narrative_headings = [
            heading for heading in scene_headings
            if not heading.startswith(("法 한눈 비교", "참고자료"))
        ]
        if len(narrative_headings) < 3:
            errors.append(
                f"{index + 1}번째 역사 사례의 구체적 장면 소제목이 "
                f"{len(narrative_headings)}개입니다(최소 3개)"
            )
        for heading in narrative_headings:
            if heading.strip() in {
                "전투의 흐름", "상세 전역 서사", "승리의 비결",
                "하나의 장면", "전역의 뼈대",
            }:
                errors.append(
                    f"전투 서사 제목이 구체적 분기점을 드러내지 않습니다: {heading}"
                )

    if text.count("#### 法 한눈 비교 — 곡제·관도·주용") != 2:
        errors.append("전투별 法 한눈 비교표 제목이 정확히 2개가 아닙니다")

    # 이름과 지명은 고유명사 사전 없이는 완전 자동 판별할 수 없어 사람의 전수 확인을 남긴다.
    if not person_manifest:
        warnings.append("장수 이름 전수 진영색 검사는 인물 별칭 목록과 사람이 함께 확인해야 합니다")
    warnings.append("자연지형 전수 이모지·배경색 검사는 지명 목록과 사람이 함께 확인해야 합니다")
    warnings.append(
        "이미지의 내용·배치·가독성과 카우펜스·채주 기준본 대비 품질은 "
        "실제 이미지를 나란히 열어 확인해야 합니다"
    )
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument(
        "--all",
        action="store_true",
        help="손자병법/jiudi*_full_page.md를 모두 검사",
    )
    args = parser.parse_args()

    paths = list(args.paths)
    if args.all:
        base = Path(__file__).resolve().parent
        paths.extend(sorted(base.glob("jiudi*_full_page.md")))
    paths = list(dict.fromkeys(path.resolve() for path in paths))
    if not paths:
        parser.error("검사할 파일을 지정하거나 --all을 사용하십시오")

    failed = False
    for path in paths:
        errors, warnings = validate_page(path)
        status = "PASS" if not errors else "FAIL"
        failed |= bool(errors)
        print(f"[{status}] {path}")
        for error in errors:
            print(f"  ERROR: {error}")
        for warning in warnings:
            print(f"  MANUAL: {warning}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
