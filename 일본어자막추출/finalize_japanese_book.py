#!/usr/bin/env python3
"""Codex 요약이 끝난 일본어 책 자료를 최종 EPUB으로 빌드한다."""

import argparse
import glob
import os
import subprocess
import sys
import tempfile
import zipfile

from book_title import display_title


def validate_epub(path):
    """README의 Apple Books 색상 규칙과 기본 EPUB 무결성을 확인한다."""
    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise RuntimeError(f"EPUB ZIP 손상: {bad_member}")
        xhtml = "\n".join(
            archive.read(name).decode("utf-8", errors="replace")
            for name in archive.namelist()
            if name.endswith((".xhtml", ".html"))
        )
        css = "\n".join(
            archive.read(name).decode("utf-8", errors="replace")
            for name in archive.namelist()
            if name.endswith(".css")
        )
    required = [
        ('class="ja ibooks-dark-theme-use-custom-text-color"', xhtml),
        ('class="ko ibooks-dark-theme-use-custom-text-color"', xhtml),
        ("color-scheme: light dark", css),
        ("@media (prefers-color-scheme: dark)", css),
        ("p.ja", css),
        ("p.ko", css),
    ]
    missing = [needle for needle, haystack in required if needle not in haystack]
    if missing:
        raise RuntimeError("EPUB 필수 스타일 누락: " + ", ".join(missing))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book_dir", help="일본어자막추출/library/<작품명> 폴더")
    parser.add_argument("--output", help="출력 EPUB 경로")
    args = parser.parse_args()

    book_dir = os.path.abspath(args.book_dir)
    book_title = display_title(book_dir)
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

    output = os.path.abspath(args.output) if args.output else os.path.join(
        book_dir, os.path.basename(book_dir) + ".epub"
    )
    os.makedirs(os.path.dirname(output), exist_ok=True)
    temp_output = tempfile.NamedTemporaryFile(
        prefix=".epub_build_", suffix=".epub",
        dir=os.path.dirname(output), delete=False,
    ).name
    command = [
        "pandoc",
        summary,
        *transcripts,
        "--resource-path", book_dir,
        "--css", css,
        "--toc",
        "--toc-depth=2",
        "--metadata", f"title={book_title}",
        "-o", temp_output,
    ]
    if os.path.isfile(cover):
        command.append(f"--epub-cover-image={cover}")
    try:
        subprocess.run(command, check=True, cwd=book_dir)
        validate_epub(temp_output)
        os.replace(temp_output, output)
    finally:
        if os.path.exists(temp_output):
            os.unlink(temp_output)
    print(output)


if __name__ == "__main__":
    main()
