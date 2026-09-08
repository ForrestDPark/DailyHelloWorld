#!/usr/bin/env python3
"""4번 역사 사례만 생략하는 손자병법 라이트 분석 검증기."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from validate_notion_markup import validate as validate_markup
COMMENTATORS = (
    "조조(曹操)", "이전(李筌)", "두목(杜牧)", "매요신(梅堯臣)",
    "장예(張預)", "왕석(王晳)", "가림(賈林)", "두우(杜佑)", "진호(陳皞)",
)
FORBIDDEN_COMMENTARY_PHRASES = (
    "라고 풀이한다", "라고 본다", "라고 설명한다", "라고 강조한다",
    "로 풀이한다", "로 읽는다", "을 강조한다", "을 설명한다",
)


def validate(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors = validate_markup(text)
    if text.count("<!-- sunzi-analysis-mode: light -->") != 1:
        errors.append("라이트 모드 표식이 정확히 1개가 아닙니다")
    expected = (1, 2, 3, 5)
    for number in expected:
        count = len(re.findall(rf"^##\s+{number}\.\s+", text, re.MULTILINE))
        if count != 1:
            errors.append(f"{number}번 섹션 헤더가 {count}개입니다(정상: 1개)")
    if re.search(r"^##\s+4\.\s+", text, re.MULTILINE):
        errors.append("라이트 모드에는 4번 역사적 실증 사례가 없어야 합니다")
    if re.search(r"!\[[^]]*\]\(", text):
        errors.append("라이트 모드에는 전투 도판을 넣지 않습니다")
    if "<table_of_contents" in text:
        errors.append("자동 목차가 남아 있습니다")
    section1 = text[text.find("## 1."):text.find("## 2.")]
    for token in ("<details", "<summary>", "<br>", "**직역**", "#### 글자들이 완성하는 한 장면"):
        if token not in section1:
            errors.append(f"1번 필수 요소 누락: {token}")
    if '<span color="red">' not in section1:
        errors.append("1번 원문의 핵심 한자 붉은색 강조가 없습니다")
    section2 = text[text.find("## 2."):text.find("## 3.")]
    for commentator in COMMENTATORS:
        if f"**{commentator}**" not in section2:
            errors.append(f"전통 주석가 누락: {commentator}")
    for phrase in FORBIDDEN_COMMENTARY_PHRASES:
        if phrase in section2:
            errors.append(f"전통 주석의 보고서체 표현이 남아 있습니다: {phrase}")
    section3 = text[text.find("## 3."):text.find("## 5.")]
    for axis in ("손자병법 내 교차", "클라우제비츠", "오륜서", "오자병법", "현대 심리학·군사학"):
        if axis not in section3:
            errors.append(f"3번 교차 설명 축 누락: {axis}")
    section5 = text[text.find("## 5."):]
    for token in ("핵심 통찰", "실생활 적용", "생활루틴"):
        if token not in section5:
            errors.append(f"5번 필수 요소 누락: {token}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    errors = validate(args.path)
    if errors:
        print("LIGHT_ANALYSIS_INVALID")
        for error in errors:
            print(f"- {error}")
        return 1
    print("LIGHT_ANALYSIS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
