#!/usr/bin/env python3
"""Codex 요약이 끝난 일본어 책 자료를 최종 EPUB으로 빌드한다."""

import argparse
import glob
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book_dir", help="일본어자막추출/library/<작품명> 폴더")
    parser.add_argument("--output", help="출력 EPUB 경로")
    args = parser.parse_args()

    book_dir = os.path.abspath(args.book_dir)
    summary = os.path.join(book_dir, "SUMMARY.md")
    transcripts = sorted(glob.glob(os.path.join(book_dir, "transcript_part*.md")))
    css = os.path.join(book_dir, "epub_style.css")

    if not os.path.isfile(summary):
        sys.exit(f"SUMMARY.md가 없습니다: {summary}")
    summary_text = open(summary, encoding="utf-8").read()
    if "요약 대기 중" in summary_text:
        sys.exit("SUMMARY.md가 아직 Codex 요약 대기 상태입니다.")
    if not transcripts:
        sys.exit("transcript_part*.md가 없습니다.")
    if not os.path.isfile(css):
        sys.exit("epub_style.css가 없습니다.")

    output = args.output or os.path.join(
        book_dir, os.path.basename(book_dir) + ".epub"
    )
    command = [
        "pandoc",
        summary,
        *transcripts,
        "--resource-path", book_dir,
        "--css", css,
        "--toc",
        "--toc-depth=2",
        "--metadata", f"title={os.path.basename(book_dir)}",
        "-o", output,
    ]
    subprocess.run(command, check=True, cwd=book_dir)
    print(output)


if __name__ == "__main__":
    main()
