#!/usr/bin/env python3
"""이미 만들어진 transcript_part*.md의 <p class="ja">에 남아있는 "漢字(かんじ)"
괄호 표기를 실제 <ruby> 태그로 바꾼다.

★ 2026-09-06: "SONE-670... 후리가나 표현이 안되고 가로에 후리가나가있지?
읽기할때 이상하게 읽는거같아" 실측 피드백으로 발견한 subtitle_pipeline_body.sh의
버그(transcript_part*.md 생성 시 <ruby> 변환 없이 괄호 표기를 그대로 씀)를
고쳤지만, 그 고침은 앞으로 새로 만들어지는 회차에만 적용된다. 이미 디스크에
있는 .md 파일은 그대로 남아있어서, 이 스크립트로 기존 파일을 직접 고치고
finalize_japanese_book.py로 "일반 EPUB"을 다시 빌드한다(AI 호출 없음 — 순수
텍스트 치환 + pandoc 재빌드).
"""

import argparse
import glob
import html
import os
import re
import subprocess
import sys

_KANJI_RUN_RE = re.compile(r"[一-鿿々〆ヵヶ]+")
_JA_PARAGRAPH_RE = re.compile(
    r'(<p class="ja ibooks-dark-theme-use-custom-text-color">)(.*?)(</p>)'
)


def _kanji_only_ruby(ja, reading):
    ja, reading = str(ja or ""), str(reading or "")
    if not reading or not _KANJI_RUN_RE.search(ja):
        return html.escape(ja)
    matches = list(_KANJI_RUN_RE.finditer(ja))
    output, ja_cursor, reading_cursor = [], 0, 0
    for index, match in enumerate(matches):
        plain = ja[ja_cursor:match.start()]
        output.append(html.escape(plain))
        kana = "".join(re.findall(r"[ぁ-ゖァ-ヺー]+", plain))
        if kana:
            found = reading.find(kana, reading_cursor)
            if found >= 0:
                reading_cursor = found + len(kana)
        following_start = match.end()
        following_end = matches[index + 1].start() if index + 1 < len(matches) else len(ja)
        following = ja[following_start:following_end]
        anchor_match = re.search(r"[ぁ-ゖァ-ヺー]+", following)
        anchor = anchor_match.group(0) if anchor_match else ""
        anchor_at = reading.find(anchor, reading_cursor) if anchor else -1
        ruby_reading = reading[reading_cursor:anchor_at] if anchor_at >= 0 else reading[reading_cursor:]
        if ruby_reading:
            output.append(f'<ruby>{html.escape(match.group(0))}<rt>{html.escape(ruby_reading)}</rt></ruby>')
            reading_cursor = anchor_at if anchor_at >= 0 else len(reading)
        else:
            output.append(html.escape(match.group(0)))
        ja_cursor = following_start
    output.append(html.escape(ja[ja_cursor:]))
    return "".join(output)


def furigana_paren_to_ruby_html(text):
    if "<ruby>" in text:
        return text  # 이미 변환됨 — 재실행해도 안전(idempotent)
    output, cursor = [], 0
    pattern = re.compile(r"([一-鿿々〆ヵヶ]+[ぁ-ゖァ-ヺー]*)\(([ぁ-ゖァ-ヺー]+)\)")
    for match in pattern.finditer(text or ""):
        output.append(text[cursor:match.start()])
        output.append(_kanji_only_ruby(match.group(1), match.group(2)))
        cursor = match.end()
    output.append(text[cursor:])
    return "".join(output)


def fix_md_file(path):
    with open(path, encoding="utf-8") as f:
        content = f.read()

    def _replace(m):
        return m.group(1) + furigana_paren_to_ruby_html(m.group(2)) + m.group(3)

    new_content, count = _JA_PARAGRAPH_RE.subn(_replace, content)
    if new_content != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_dir")
    parser.add_argument("--rebuild", action="store_true", help="수정 후 finalize_japanese_book.py로 일반 EPUB 재빌드")
    args = parser.parse_args()

    md_files = sorted(glob.glob(os.path.join(args.book_dir, "transcript_part*.md")))
    if not md_files:
        sys.exit(f"❌ transcript_part*.md가 없습니다: {args.book_dir}")

    total = 0
    for path in md_files:
        n = fix_md_file(path)
        print(f"  {os.path.basename(path)}: {n}줄 수정")
        total += n
    print(f"✅ 총 {total}줄의 후리가나를 <ruby> 태그로 변환")

    if args.rebuild:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        result = subprocess.run(
            [sys.executable, os.path.join(script_dir, "finalize_japanese_book.py"), args.book_dir]
        )
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
