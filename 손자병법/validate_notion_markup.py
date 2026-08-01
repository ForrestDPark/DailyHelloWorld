#!/usr/bin/env python3
"""손자병법 Notion enhanced Markdown 구조 검증기."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


STRUCTURAL_TAGS = ("table", "tr", "td", "details", "summary", "span")
TAG_RE = re.compile(r"<(/?)(table|tr|td|details|summary|span)\b[^>]*>")
ESCAPED_TAG_RE = re.compile(
    r"\\</?(?:table|tr|td|details|summary|span)\b|"
    r"\\<(?:table|tr|td|details|summary|span)\b|"
    r"</?(?:table|tr|td|details|summary|span)\\>|"
    r"&lt;/?(?:table|tr|td|details|summary|span)\b"
)

LATEST_FIVE_ROWS = (
    '<td color="orange_bg">🤝 **道**</td>',
    '<td color="blue_bg">🌤️ **天**</td>',
    '<td color="green_bg">🧭 **地**</td>',
    '<td color="purple_bg">🎖️ **將**</td>',
    '<td color="yellow_bg">⚙️ **法**</td>',
)


def validate(
    text: str,
    require_five_sections: bool = False,
    require_latest_five_tables: bool = False,
) -> list[str]:
    errors: list[str] = []

    for match in ESCAPED_TAG_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        errors.append(f"{line}행: 구조 태그에 역슬래시가 있습니다: {match.group(0)!r}")

    inline_token_re = re.compile(r"\*\*|</?span\b[^>]*>")
    for line_number, line_text in enumerate(text.splitlines(), 1):
        bold_open = False
        for token in inline_token_re.finditer(line_text):
            if token.group(0) == "**":
                bold_open = not bold_open
            elif bold_open:
                errors.append(
                    f"{line_number}행: 굵은 글씨가 <span> 경계를 가로지릅니다"
                )
                break

    stack: list[tuple[str, int]] = []
    for match in TAG_RE.finditer(text):
        closing, tag = match.group(1), match.group(2)
        line = text.count("\n", 0, match.start()) + 1
        if not closing:
            stack.append((tag, line))
            continue
        if not stack:
            errors.append(f"{line}행: 짝이 없는 닫는 태그 </{tag}>")
            continue
        open_tag, open_line = stack[-1]
        if open_tag != tag:
            errors.append(
                f"{line}행: </{tag}> 앞에 닫히지 않은 <{open_tag}>가 있습니다"
                f"({open_line}행)"
            )
            continue
        stack.pop()

    for tag, line in reversed(stack):
        errors.append(f"{line}행: 닫히지 않은 <{tag}> 태그")

    for match in re.finditer(r"</table>\s*</table>", text):
        line = text.count("\n", 0, match.start()) + 1
        errors.append(f"{line}행: </table>이 연속으로 중복됐습니다")

    for match in re.finditer(r"<table\b[^>]*>.*?</table>", text, re.DOTALL):
        table = match.group(0)
        line = text.count("\n", 0, match.start()) + 1
        if "\n" not in table:
            errors.append(f"{line}행: 표 전체가 한 줄입니다. 행·셀을 줄 단위로 분리하십시오")
        rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", table, re.DOTALL)
        if not rows:
            errors.append(f"{line}행: <tr>이 없는 빈 표입니다")
            continue
        widths = [len(re.findall(r"<td\b[^>]*>.*?</td>", row, re.DOTALL)) for row in rows]
        if any(width == 0 for width in widths):
            errors.append(f"{line}행: <td>가 없는 행이 있습니다")
        if len(set(widths)) > 1:
            errors.append(f"{line}행: 표의 행별 셀 개수가 다릅니다: {widths}")

    if require_five_sections:
        for number in range(1, 6):
            count = len(
                re.findall(
                    rf"(?:<summary>{number}\.|^##\s+{number}\.)",
                    text,
                    re.MULTILINE,
                )
            )
            if count != 1:
                errors.append(f"{number}번 섹션 헤더 개수가 {count}개입니다(정상: 1개)")

        for match in re.finditer(r"^##\s+[1-5]\.\s+.*?(?:\{[^}]+\})?$", text, re.MULTILINE):
            heading = match.group(0)
            if 'toggle="true"' in heading or re.search(r'color="(?:blue|green|purple|orange|yellow|red)(?:_bg)?"', heading):
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"{line}행: 1~5번 섹션 제목은 일반 제목·기본 검은색이어야 합니다")

        for match in re.finditer(r"<details\b[^>]*>(.*?)</details>", text, re.DOTALL):
            if re.search(r"^##\s+[1-5]\.\s+", match.group(1), re.MULTILINE):
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"{line}행: 1~5번 섹션 전체를 감싼 토글이 남아 있습니다")

        section_two_start = text.find("## 2.")
        section_three_start = text.find("## 3.", section_two_start + 1)
        section_four_start = text.find("## 4.", section_three_start + 1)
        section_two = text[section_two_start:section_three_start]
        section_three = text[section_three_start:section_four_start]
        for number, section in ((2, section_two), (3, section_three)):
            color_match = re.search(r'<span\s+color="[^"]+">|\{[^}]*color="[^"]+"[^}]*\}', section)
            if color_match:
                line = text.count("\n", 0, (section_two_start if number == 2 else section_three_start) + color_match.start()) + 1
                errors.append(f"{line}행: {number}번 섹션에 불필요한 색상 강조가 남아 있습니다")

    if require_latest_five_tables:
        five_tables: list[tuple[int, str]] = []
        for match in re.finditer(r"<table\b[^>]*>.*?</table>", text, re.DOTALL):
            table = match.group(0)
            if any(f"**{axis}**" in table for axis in "道天地將法"):
                line = text.count("\n", 0, match.start()) + 1
                five_tables.append((line, table))

        if len(five_tables) != 4:
            errors.append(
                f"최신 五事 표가 {len(five_tables)}개입니다"
                "(정상: 서양 패·승 + 동양 패·승 = 4개)"
            )

        for line, table in five_tables:
            if "<td>요소</td>" not in table or "<td>판단</td>" not in table:
                errors.append(f"{line}행 五事 표: 헤더가 '요소 | 판단'이 아닙니다")
            positions = [table.find(row) for row in LATEST_FIVE_ROWS]
            for row, position in zip(LATEST_FIVE_ROWS, positions):
                if position < 0:
                    errors.append(f"{line}행 五事 표: 최신 행 서식 누락: {row}")
            if all(position >= 0 for position in positions) and positions != sorted(positions):
                errors.append(f"{line}행 五事 표: 道→天→地→將→法 순서가 아닙니다")
            if len(re.findall(r"<tr\b", table)) != 6:
                errors.append(f"{line}행 五事 표: 헤더 포함 정확히 6행이어야 합니다")

        legacy_patterns = (
            r"<td>五事</td>",
            r"<td>분석</td>",
            r"<td>道\(",
            r"<td>天\(",
            r"<td>地\(",
            r"<td>將\(",
            r"<td>法\(",
        )
        for pattern in legacy_patterns:
            match = re.search(pattern, text)
            if match:
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"{line}행: 폐기된 구형 五事 표 서식이 남아 있습니다")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", help="검증할 파일. 생략하면 표준입력 사용")
    parser.add_argument("--require-five-sections", action="store_true")
    parser.add_argument("--require-latest-five-tables", action="store_true")
    args = parser.parse_args()

    if args.path:
        text = Path(args.path).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    errors = validate(
        text,
        require_five_sections=args.require_five_sections,
        require_latest_five_tables=args.require_latest_five_tables,
    )
    if errors:
        print("NOTION_MARKUP_INVALID")
        for error in errors:
            print(f"- {error}")
        return 1

    print("NOTION_MARKUP_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
