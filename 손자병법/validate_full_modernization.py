#!/usr/bin/env python3
"""구지편 전체 페이지가 현재 최신화 기준을 충족하는지 검사한다."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from validate_notion_markup import validate as validate_markup


LAW_TITLE = "##### 法을 압축하지 않고 보기 — 곡제·관도·주용"
LAW_SECTIONS = (
    ("곡제", "부대를 어떻게 나누고 결합했는가"),
    ("관도", "누가 명령하고 어떻게 전달했는가"),
    ("주용", "군량·장비·전투 지속 능력을 어떻게 썼는가"),
)


def tables(text: str) -> list[str]:
    return re.findall(r"<table\b[^>]*>.*?</table>", text, re.DOTALL)


def validate_law_comparisons(text: str) -> list[str]:
    errors: list[str] = []
    title_positions = [m.start() for m in re.finditer(re.escape(LAW_TITLE), text)]
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

    if "<table_of_contents" not in text:
        errors.append("페이지 맨 위 자동 목차가 없습니다")
    if "prod-files-secure" in text or "X-Amz-Expires" in text:
        errors.append("만료되는 임시 이미지 URL이 남아 있습니다")

    permanent_images = re.findall(
        r"!\[[^\]]*\]\(https://raw\.githubusercontent\.com/"
        r"ForrestDPark/DailyHelloWorld/main/[^)]+\)",
        text,
    )
    if len(permanent_images) != 10:
        errors.append(
            f"GitHub 영구 URL 이미지가 {len(permanent_images)}개입니다"
            "(정상: 전투별 5종 × 2 = 10개)"
        )

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
    if '<details color="orange_bg">' not in section_one:
        errors.append("1번 섹션 원문·독음 토글의 주황 배경이 없습니다")
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

    section_four_start = text.find("## 4.")
    section_five_start = text.find("## 5.", section_four_start + 1)
    section_four = (
        text[section_four_start:section_five_start]
        if section_four_start >= 0 and section_five_start > section_four_start
        else ""
    )
    case_starts = [m.start() for m in re.finditer(r"^\s*### (?:서양|동양) — ", section_four, re.MULTILINE)]
    if len(case_starts) != 2:
        errors.append(f"서양·동양 역사 사례가 {len(case_starts)}개입니다(정상: 2개)")
    for index, start in enumerate(case_starts):
        end = case_starts[index + 1] if index + 1 < len(case_starts) else len(section_four)
        case = section_four[start:end]
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
    warnings.append("장수 이름 전수 진영색 검사는 인물 별칭 목록과 사람이 함께 확인해야 합니다")
    warnings.append("자연지형 전수 이모지·배경색 검사는 지명 목록과 사람이 함께 확인해야 합니다")
    warnings.append(
        "이미지의 내용·배치·가독성과 셔먼·손책 기준본 대비 품질은 "
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
