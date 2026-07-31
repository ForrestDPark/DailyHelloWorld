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
    # ★ 2026-07-31: subtitle_pipeline_body.sh가 만드는 "빠른" EPUB에는 표지가
    # 있었는데, 이 스크립트가 그걸 덮어쓰면서 표지 관련 옵션이 아예 없어서
    # 최종 EPUB에서 표지가 사라지는 버그가 있었다(사용자 리포트로 발견) —
    # subtitle_pipeline_body.sh가 book_dir에 복사해두는 cover.jpg를 그대로 쓴다.
    cover = os.path.join(book_dir, "cover.jpg")

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
    if os.path.isfile(cover):
        command.append(f"--epub-cover-image={cover}")
    subprocess.run(command, check=True, cwd=book_dir)
    print(output)


if __name__ == "__main__":
    main()
