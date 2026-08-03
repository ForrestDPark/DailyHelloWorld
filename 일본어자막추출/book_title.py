#!/usr/bin/env python3
"""일본어 학습책의 원본명·내용 기반 부제목을 일관되게 조합한다."""

import os
import re


SUBTITLE_FILENAME = "BOOK_SUBTITLE.txt"


def clean_subtitle(value):
    value = re.sub(r"\s+", " ", (value or "").strip())
    value = value.strip('"“”\'‘’—–-:：').strip()
    if not 4 <= len(value) <= 40:
        return ""
    return value


def load_book_subtitle(book_dir):
    path = os.path.join(book_dir, SUBTITLE_FILENAME)
    if not os.path.isfile(path):
        return ""
    try:
        return clean_subtitle(open(path, encoding="utf-8").read())
    except OSError:
        return ""


def display_title(book_dir, base_name=None):
    base_name = base_name or os.path.basename(os.path.abspath(book_dir))
    subtitle = load_book_subtitle(book_dir)
    return f"{base_name} — {subtitle}" if subtitle else base_name


def filename_title(book_dir, base_name=None):
    """표시 제목을 macOS 파일명에 안전한 형태로 돌려준다."""
    title = display_title(book_dir, base_name)
    title = re.sub(r'[/:\\\x00-\x1f]', '-', title)
    return re.sub(r"\s+", " ", title).strip(" .")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("book_dir")
    parser.add_argument("--base-name")
    parser.add_argument("--filename", action="store_true")
    args = parser.parse_args()
    function = filename_title if args.filename else display_title
    print(function(os.path.abspath(args.book_dir), args.base_name))
