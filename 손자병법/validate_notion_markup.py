#!/usr/bin/env python3
"""손자병법 Notion enhanced Markdown 구조 검증기."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


STRUCTURAL_TAGS = ("table", "tr", "td", "details", "summary")
TAG_RE = re.compile(r"<(/?)(table|tr|td|details|summary)\b[^>]*>")
ESCAPED_TAG_RE = re.compile(
    r"\\</?(?:table|tr|td|details|summary)\b|"
    r"\\<(?:table|tr|td|details|summary)\b|"
    r"</?(?:table|tr|td|details|summary)\\>"
)


def validate(text: str, require_five_sections: bool = False) -> list[str]:
    errors: list[str] = []

    for match in ESCAPED_TAG_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        errors.append(f"{line}행: 구조 태그에 역슬래시가 있습니다: {match.group(0)!r}")

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

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", help="검증할 파일. 생략하면 표준입력 사용")
    parser.add_argument("--require-five-sections", action="store_true")
    args = parser.parse_args()

    if args.path:
        text = Path(args.path).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    errors = validate(text, require_five_sections=args.require_five_sections)
    if errors:
        print("NOTION_MARKUP_INVALID")
        for error in errors:
            print(f"- {error}")
        return 1

    print("NOTION_MARKUP_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
