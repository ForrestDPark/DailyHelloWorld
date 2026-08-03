#!/usr/bin/env python3
"""로컬 독서 세션과 Notion 캐시를 책별 학습판 EPUB으로 묶는다."""

import argparse
import collections
import html
import json
import os
import re
import uuid

from ebooklib import epub


SESSION_DIR = os.path.expanduser("~/.ebook_reader/sessions")
NOTION_CACHE_DIR = os.path.expanduser("~/.ebook_reader/notion_cache")
STOPWORDS = {
    "about", "after", "again", "also", "and", "are", "because", "been", "before",
    "but", "can", "could", "did", "does", "for", "from", "had", "has", "have",
    "her", "him", "his", "how", "into", "its", "more", "not", "now", "one",
    "only", "our", "out", "said", "she", "some", "than", "that", "the", "their",
    "them", "then", "there", "these", "they", "this", "those", "through", "too",
    "was", "were", "what", "when", "where", "which", "who", "will", "with", "would",
    "you", "your",
}


def load_json(path):
    try:
        with open(path, encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return None


def normalized_stem(path_or_name):
    return os.path.splitext(os.path.basename(path_or_name))[0].casefold()


def load_sessions(book_path):
    target_path = os.path.abspath(book_path)
    target_stem = normalized_stem(book_path)
    sessions = []
    if not os.path.isdir(SESSION_DIR):
        return sessions
    for name in sorted(os.listdir(SESSION_DIR)):
        if not name.endswith(".json"):
            continue
        record = load_json(os.path.join(SESSION_DIR, name))
        if not record:
            continue
        same_path = os.path.abspath(record.get("book_file", "")) == target_path
        same_name = normalized_stem(record.get("book_name", "")) == target_stem
        if same_path or same_name:
            sessions.append(record)
    return sessions


def block_plain_text(block):
    block_type = block.get("type", "")
    value = block.get(block_type, {}) if block_type else {}
    text = "".join(item.get("plain_text", "") for item in value.get("rich_text", []))
    child_text = "\n".join(block_plain_text(child) for child in block.get("children", []))
    return "\n".join(part for part in (text, child_text) if part)


def load_notion_history(book_path):
    index = load_json(os.path.join(NOTION_CACHE_DIR, "index.json")) or {}
    target = normalized_stem(book_path)
    results = []
    for item in index.get("pages", []):
        if target not in normalized_stem(item.get("title", "")):
            continue
        record = load_json(os.path.join(NOTION_CACHE_DIR, item["file"])) or {}
        text = "\n\n".join(block_plain_text(block) for block in record.get("blocks", []))
        if text.strip():
            results.append({"title": item.get("title", "Notion 기록"), "text": text.strip()})
    return results


def sentences(text):
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def key_words(text, count=15):
    words = re.findall(r"[A-Za-z][A-Za-z'-]{3,}", text.casefold())
    frequencies = collections.Counter(word for word in words if word not in STOPWORDS)
    return frequencies.most_common(count)


def shadowing_sentences(text, count=5):
    candidates = [sentence for sentence in sentences(text) if 45 <= len(sentence) <= 180]
    candidates.sort(key=lambda value: (abs(len(value) - 95), value))
    return candidates[:count]


def xhtml_page(title, body):
    return f'''<html xmlns="http://www.w3.org/1999/xhtml"><head><title>{html.escape(title)}</title></head>
<body><h1>{html.escape(title)}</h1>{body}</body></html>'''


def paragraphs(text, class_name=""):
    class_attr = f' class="{class_name}"' if class_name else ""
    return "".join(f"<p{class_attr}>{html.escape(part)}</p>" for part in text.split("\n\n") if part.strip())


def build(book_path, output_path=None):
    sessions = load_sessions(book_path)
    notion_history = load_notion_history(book_path)
    if not sessions and not notion_history:
        raise RuntimeError("이 책의 로컬 세션이나 동기화된 Notion 기록이 없습니다.")

    title = os.path.splitext(os.path.basename(book_path))[0]
    output_path = output_path or os.path.join(os.path.dirname(book_path), f"{title}_학습판.epub")
    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(f"{title} — 아침 독서 학습판")
    book.set_language("ko")
    book.add_author("Morning Ebook Study")
    style = epub.EpubItem(
        uid="study_style", file_name="style/study.css", media_type="text/css",
        content=b"body{font-size:1.15em;line-height:1.75;margin:6%;}h1{font-size:1.7em;}h2{margin-top:1.6em;}p.original{font-family:serif;}p.translation{background:#eef5ff;padding:.8em;border-radius:.4em;}li{margin:.5em 0;}"
    )
    book.add_item(style)
    chapters = []

    intro = epub.EpubHtml(title="학습 안내", file_name="intro.xhtml", lang="ko")
    intro.content = xhtml_page("아침 독서 학습판", f"<p><strong>{html.escape(title)}</strong></p><p>독서 세션 {len(sessions)}개 · Notion 기록 {len(notion_history)}개를 모았습니다.</p>")
    intro.add_item(style)
    book.add_item(intro)
    chapters.append(intro)

    for index, session in enumerate(sessions, 1):
        original = session.get("original", "")
        translation = session.get("translation_ko", "")
        words = key_words(original)
        shadowing = shadowing_sentences(original)
        page_range = f"P.{session.get('start_page', '?')}~P.{session.get('end_page', '?')}"
        body = f"<p>{html.escape(session.get('created_at', ''))} · {html.escape(page_range)}</p>"
        if words:
            body += "<h2>핵심 반복 단어</h2><ol>" + "".join(
                f"<li><strong>{html.escape(word)}</strong> — {frequency}회</li>" for word, frequency in words
            ) + "</ol>"
        if shadowing:
            body += "<h2>쉐도잉 추천 문장</h2><ol>" + "".join(
                f"<li>{html.escape(sentence)}</li>" for sentence in shadowing
            ) + "</ol>"
        body += "<h2>원문</h2>" + paragraphs(original, "original")
        if translation:
            body += "<h2>한국어 번역</h2>" + paragraphs(translation, "translation")
        chapter = epub.EpubHtml(title=f"독서 세션 {index}", file_name=f"session_{index:03d}.xhtml", lang="ko")
        chapter.content = xhtml_page(f"독서 세션 {index}", body)
        chapter.add_item(style)
        book.add_item(chapter)
        chapters.append(chapter)

    for index, record in enumerate(notion_history, 1):
        chapter = epub.EpubHtml(title=f"과거 Notion 기록 {index}", file_name=f"notion_{index:03d}.xhtml", lang="ko")
        chapter.content = xhtml_page(record["title"], paragraphs(record["text"]))
        chapter.add_item(style)
        book.add_item(chapter)
        chapters.append(chapter)

    book.toc = tuple(chapters)
    book.spine = ["nav", *chapters]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(output_path, book)
    return output_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book", help="원본 PDF 또는 EPUB 경로")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        output = build(os.path.abspath(args.book), args.output)
    except Exception as error:
        print(f"❌ 학습판 EPUB 생성 실패: {error}")
        return 1
    print(f"✅ 학습판 EPUB 생성 완료: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
