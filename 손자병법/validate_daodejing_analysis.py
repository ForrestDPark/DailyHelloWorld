#!/usr/bin/env python3
"""도덕경 원고의 공통 1번 독해층과 1~5번 구조를 검증한다."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from validate_notion_markup import validate as validate_markup


def validate(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors = validate_markup(text)
    if "<!-- classical-work: daodejing -->" not in text:
        errors.append("도덕경 고전 표식이 없습니다")

    expected = (1, 2, 3, 5) if "sunzi-analysis-mode: light" in text else (1, 2, 3, 4, 5)
    for number in expected:
        count = len(re.findall(rf"^##\s+{number}\.\s+", text, re.MULTILINE))
        if count != 1:
            errors.append(f"{number}번 섹션 헤더가 {count}개입니다(정상: 1개)")

    section1_end = text.find("## 2.")
    section1 = text[text.find("## 1."):section1_end]
    required = (
        "<details",
        "<summary>",
        "**직역**",
        "**아주 쉽게 먼저 말하면**",
        "#### 낱글자부터 뜻을 풀기",
        "#### 먼저 문장이 어떻게 움직이는지",
        "이제 이 전체 흐름을 만든 핵심 글자",
        "#### 글자들이 완성하는 한 장면",
    )
    positions = []
    for token in required:
        position = section1.find(token)
        positions.append(position)
        if position < 0:
            errors.append(f"도덕경 1번 필수 요소 누락: {token}")
    if all(position >= 0 for position in positions) and positions != sorted(positions):
        errors.append("도덕경 1번 섹션의 첫 이해층 순서가 올바르지 않습니다")

    beginner_start = section1.find("#### 낱글자부터 뜻을 풀기")
    beginner_end = section1.find("#### 먼저 문장이 어떻게 움직이는지")
    beginner = section1[beginner_start:beginner_end] if beginner_start >= 0 and beginner_end > beginner_start else ""
    beginner_tokens = (
        "`非(비)`", "`常(상)`", "비상사태", "`常道(상도)`",
        "`無名(무명)`", "`有名(유명)`", "유명인",
        "`無欲(무욕)`", "`有欲(유욕)`", "`妙(묘)`", "`徼(요)`",
        "`此(차)`", "`兩(량)`", "`者(자)`", "`此兩者(차량자)`",
    )
    for token in beginner_tokens:
        if token not in beginner:
            errors.append(f"도덕경 초보자 낱글자 풀이 누락: {token}")
    anchor_counts = {
        "**원문 구절**": 8,
        "**독음**": 8,
        "**한 문장 뜻**": 8,
        "**앞 문장과의 연결**": 8,
    }
    for token, minimum in anchor_counts.items():
        count = beginner.count(token)
        if count < minimum:
            errors.append(f"도덕경 초보자 문맥 발판 부족: {token} {count}개(최소 {minimum}개)")
    source_clauses = (
        "`道可道，非常道。`",
        "`名可名，非常名。`",
        "`無名天地之始；有名萬物之母。`",
        "`故常無欲以觀其妙；常有欲以觀其徼。`",
        "`此兩者同出而異名，同謂之玄。`",
        "`玄之又玄，衆妙之門。`",
    )
    for token in source_clauses:
        if token not in beginner:
            errors.append(f"도덕경 초보자 풀이의 원문 구절 누락: {token}")
    if len(beginner) < 1800:
        errors.append("도덕경 초보자 낱글자 풀이가 지나치게 짧습니다")

    flow_start = section1.find("#### 먼저 문장이 어떻게 움직이는지")
    flow_end = section1.find("이제 이 전체 흐름을 만든 핵심 글자")
    flow = section1[flow_start:flow_end] if flow_start >= 0 and flow_end > flow_start else ""
    for token in ("道可道", "名", "無名", "有名", "無欲", "有欲", "同出而異名", "玄之又玄"):
        if token not in flow:
            errors.append(f"도덕경 문장 흐름 풀이의 핵심 전환 누락: {token}")
    if len(flow) < 700:
        errors.append("도덕경 문장 흐름 풀이가 지나치게 짧습니다")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    errors = validate(args.path)
    if errors:
        print("DAODEJING_ANALYSIS_INVALID")
        for error in errors:
            print(f"- {error}")
        return 1
    print("DAODEJING_ANALYSIS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
