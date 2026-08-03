#!/usr/bin/env python3
"""Apple Books용 고정 레이아웃 Read Aloud EPUB 3를 만든다.

일본어 문장과 Edge TTS 음성을 EPUB Media Overlays(SMIL)로 연결한다. Apple Books에서
오디오 버튼을 누르면 현재 일본어 문장이 강조되고 페이지가 자동으로 넘어간다.
"""

import argparse
import asyncio
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from xml.etree import ElementTree

import edge_tts

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
from build_audiobook import load_lines, resolve_books
from book_title import display_title, filename_title


VOICE = "ja-JP-NanamiNeural"
RATE = "-10%"
LINES_PER_PAGE = 4
VIEWPORT_WIDTH = 960
VIEWPORT_HEIGHT = 1440
STUDY_DWELL_SECONDS = 12.0


def clock(seconds):
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def audio_duration(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


async def synthesize_page(text, mp3_path, timing_path):
    """오디오와 Edge TTS WordBoundary 타이밍을 한 번의 요청으로 함께 저장한다."""
    temp_mp3 = mp3_path + ".partial"
    last_error = None
    for attempt in range(3):
        boundaries = []
        try:
            with open(temp_mp3, "wb") as audio_file:
                communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_file.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        boundaries.append({
                            "offset": chunk["offset"] / 10_000_000,
                            "duration": chunk["duration"] / 10_000_000,
                            "text": chunk["text"],
                        })
            if not os.path.isfile(temp_mp3) or os.path.getsize(temp_mp3) == 0:
                raise RuntimeError("TTS가 빈 오디오를 반환했습니다.")
            os.replace(temp_mp3, mp3_path)
            with open(timing_path, "w", encoding="utf-8") as file:
                json.dump(boundaries, file, ensure_ascii=False, indent=2)
            return
        except Exception as exc:
            last_error = exc
            if os.path.exists(temp_mp3):
                os.unlink(temp_mp3)
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"TTS 3회 재시도 실패: {last_error}")


def boundary_positions(full_text, boundaries):
    positions = []
    cursor = 0
    for boundary in boundaries:
        token = boundary.get("text", "")
        position = full_text.find(token, cursor)
        if position < 0:
            position = cursor
        positions.append((position, float(boundary["offset"])))
        cursor = position + len(token)
    return positions


def sentence_timings(lines, full_text, boundaries, duration):
    starts = []
    cursor = 0
    for line in lines:
        position = full_text.find(line, cursor)
        starts.append(max(cursor, position))
        cursor = starts[-1] + len(line) + 1

    positioned = boundary_positions(full_text, boundaries)
    timings = []
    for index, start_char in enumerate(starts):
        end_char = starts[index + 1] if index + 1 < len(starts) else len(full_text) + 1
        candidates = [time for pos, time in positioned if start_char <= pos < end_char]
        if candidates:
            start_time = candidates[0]
        else:
            start_time = duration * start_char / max(1, len(full_text))
        if index + 1 < len(starts):
            next_candidates = [time for pos, time in positioned if pos >= end_char]
            end_time = next_candidates[0] if next_candidates else (
                duration * end_char / max(1, len(full_text))
            )
        else:
            end_time = duration
        end_time = max(start_time + 0.05, min(duration, end_time))
        timings.append((start_time, end_time))
    return timings


def fixed_layout_css():
    return """\
@namespace epub "http://www.idpf.org/2007/ops";
:root { color-scheme: light dark; }
html, body {
    width: 960px; height: 1440px; margin: 0; padding: 0; overflow: hidden;
}
body {
    box-sizing: border-box; padding: 54px 62px;
    background: #ffffff; color: #1a1a1a;
    font-family: "Hiragino Kaku Gothic Pro", "Yu Gothic", sans-serif;
}
h1 { margin: 0 0 18px; color: #9a6a00; font-size: 34px; }
.read-control {
    display: block; width: 52%; margin: 0 auto 22px; padding: 13px 18px;
    border: 2px solid #9a6a00; border-radius: 20px;
    color: #9a6a00; font-size: 24px; font-weight: bold; text-align: center;
    -webkit-user-select: none; user-select: none; touch-action: manipulation;
}
.scene-thumb {
    display: block; width: 78%; max-height: 320px; margin: 4px auto 24px;
    object-fit: cover; border-radius: 12px; opacity: .94;
}
.dialogues { margin-top: 12px; }
.pair { margin: 0 0 20px; padding: 0 0 12px; border-bottom: 1px solid #dddddd; }
.ja {
    margin: 0 0 7px; color: #000000; font-size: 44px; line-height: 1.28;
    font-weight: bold;
}
.ko {
    margin: 0; padding-left: 12px; border-left: 3px solid #cccccc;
    color: #777777; font-size: 27px; line-height: 1.3;
}
.intro-page h1 { text-align: center; font-size: 40px; margin-bottom: 28px; }
.book-cover {
    display: block; width: 78%; height: 1120px; object-fit: contain;
    margin: 0 auto; border-radius: 14px;
}
.overview-text { font-size: 31px; line-height: 1.6; margin: 30px 20px; }
.scene-toc { margin: 0; padding-left: 44px; font-size: 27px; line-height: 1.45; }
.scene-toc li { margin-bottom: 14px; }
.scene-toc a { color: #765300; text-decoration: none; }
.study-card { margin: 6px 0 10px; padding: 14px 18px; border: 2px solid #d8b84b; border-radius: 12px; background: #fff9df; }
.study-card h2 { margin: 0 0 12px; font-size: 38px; color: #765300; }
.study-card h3 { margin: 10px 0 7px; font-size: 34px; color: #765300; }
.study-card p, .study-card li, .study-card .vocab-line { margin: 7px 0; font-size: 32px; line-height: 1.38; }
.study-card ul, .study-card ol { margin: 3px 0 7px; padding-left: 30px; }
.study-card .expressions { columns: 1; }
.study-card .expressions li { margin-bottom: 9px; }
.study-card ruby rt { font-size: 18px; color: #765300; }
.study-card .card-ja { font-weight: bold; }
.study-card .card-ko {
    display: block; margin: 5px 0 12px 14px; padding-left: 12px;
    border-left: 3px solid #d8b84b; color: #666666; font-weight: normal;
}
.study-page h1 { margin-bottom: 22px; text-align: center; }
.study-page .study-card { margin-top: 18px; padding: 24px 28px; }
.-epub-media-overlay-active {
    color: #d43b00 !important;
    background-color: #ffe36e !important;
    border-radius: 5px;
    box-shadow: 0 0 0 5px #ffe36e;
}
@media (prefers-color-scheme: dark) {
    body { background: #111111; color: #dddddd; }
    h1 { color: #f5c842; }
    .read-control { color: #f5c842; border-color: #f5c842; }
    .pair { border-bottom-color: #333333; }
    .ja { color: #f5c842; }
    .ko { color: #888888; border-left-color: #444444; }
    .scene-toc a { color: #f5c842; }
    .study-card { background: #211e12; border-color: #f5c842; }
    .study-card h2, .study-card h3 { color: #f5c842; }
    .-epub-media-overlay-active {
        color: #111111 !important; background-color: #ffe36e !important;
        box-shadow: 0 0 0 5px #ffe36e;
    }
}
"""


KANJI_RUN_RE = re.compile(r"[一-鿿々〆ヵヶ]+")


def inline_furigana_html(text):
    """`朝(あさ)`, `食べ(たべ)`를 한자 부분만 ruby인 XHTML로 바꾼다."""
    output, cursor = [], 0
    pattern = re.compile(
        r"([一-鿿々〆ヵヶ]+[ぁ-ゖァ-ヺー]*)\(([ぁ-ゖァ-ヺー]+)\)"
    )
    for match in pattern.finditer(text or ""):
        output.append(html.escape(text[cursor:match.start()]))
        output.append(kanji_only_ruby(match.group(1), match.group(2)))
        cursor = match.end()
    output.append(html.escape((text or "")[cursor:]))
    return "".join(output)


def kanji_only_ruby(ja, reading):
    """전체 읽기를 비한자 조사·어미를 기준으로 나눠 한자 덩어리에만 붙인다."""
    ja, reading = str(ja or ""), str(reading or "")
    if not reading or not KANJI_RUN_RE.search(ja):
        return html.escape(ja)
    matches = list(KANJI_RUN_RE.finditer(ja))
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
            output.append(
                f'<ruby>{html.escape(match.group(0))}<rt>{html.escape(ruby_reading)}</rt></ruby>'
            )
            reading_cursor += len(ruby_reading)
        else:
            output.append(html.escape(match.group(0)))
        ja_cursor = match.end()
    output.append(html.escape(ja[ja_cursor:]))
    return "".join(output)


def render_study_card(study_card, heading="장면 학습 카드"):
    def ruby_text(item):
        return kanji_only_ruby(item.get("ja", ""), item.get("reading", ""))

    sections = []
    vocabulary_items = []
    for item in study_card.get("vocabulary", []):
        hanja = ""
        if item.get("hanja_sound") or item.get("hanja_hun"):
            hanja = (
                f' / 한자음: {html.escape(item.get("hanja_sound", ""))}'
                f' / 훈: {html.escape(item.get("hanja_hun", ""))}'
            )
        vocabulary_items.append(
            f'<div class="vocab-line"><span class="card-ja">{ruby_text(item)}</span>'
            f' — {html.escape(item.get("ko", ""))}{hanja}</div>'
        )
    if vocabulary_items:
        sections.append('<div class="card-section"><h3>주요 단어와 뜻</h3>' + "".join(vocabulary_items) + '</div>')
    expressions = "".join(
        f'<li><span class="card-ja">{ruby_text(item)}</span>'
        f'<span class="card-ko">{html.escape(item.get("ko", ""))}</span></li>'
        for item in study_card.get("expressions", [])
    )
    if expressions:
        sections.append(f'<div class="card-section"><h3>핵심 일본어 표현</h3><ol class="expressions">{expressions}</ol></div>')
    grammar = " / ".join(html.escape(str(item)) for item in study_card.get("grammar", []))
    if grammar:
        sections.append(f'<div class="card-section"><h3>문법·어미·뉘앙스</h3><p>{grammar}</p></div>')
    shadow = study_card.get("shadowing", {})
    if shadow:
        sections.append(
            f'<div class="card-section"><h3>쉐도잉 추천 문장</h3><p><span class="card-ja">'
            f'{ruby_text(shadow)}</span><span class="card-ko">'
            f'{html.escape(shadow.get("ko", ""))}</span></p></div>'
        )
    return f'<aside class="study-card"><h2>{html.escape(heading)}</h2>{"".join(sections)}</aside>'


def split_study_card(card, budget=6):
    """긴 카드를 고정 레이아웃 높이에 맞춰 내용 단위로 나눈다."""
    atoms = []
    atoms.extend(("vocabulary", item, 1) for item in card.get("vocabulary", []))
    atoms.extend(("expressions", item, 1) for item in card.get("expressions", []))
    atoms.extend(("grammar", item, 1) for item in card.get("grammar", []))
    if card.get("shadowing"):
        atoms.append(("shadowing", card["shadowing"], 2))
    chunks, current, used = [], {}, 0
    for section, item, weight in atoms:
        if current and used + weight > budget:
            chunks.append(current)
            current, used = {}, 0
        if section == "shadowing":
            current[section] = item
        else:
            current.setdefault(section, []).append(item)
        used += weight
    if current:
        chunks.append(current)
    return chunks or [card]


def make_page_xhtml(title, page_number, records, image_href=None):
    pairs = []
    for index, record in enumerate(records, 1):
        line_id = f"line-{page_number:04d}-{index:02d}"
        pairs.append(
            '<div class="pair">'
            f'<p id="{line_id}" class="ja ibooks-dark-theme-use-custom-text-color">'
            f'{inline_furigana_html(record.get("furigana") or record["ja"])}</p>'
            f'<p class="ko ibooks-dark-theme-use-custom-text-color">'
            f'{html.escape(record["ko"])}</p></div>'
        )
    image = (
        f'<img class="scene-thumb" src="{html.escape(image_href)}" alt="장면 대표 이미지"/>'
        if image_href else ""
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"
      xmlns:ibooks="http://apple.com/ibooks/html-extensions"
      epub:prefix="ibooks: http://vocabulary.itunes.apple.com/rdf/ibooks/vocabulary-extensions-1.0"
      xml:lang="ja">
<head>
  <title>{html.escape(title)}</title>
  <meta name="viewport" content="width={VIEWPORT_WIDTH}, height={VIEWPORT_HEIGHT}"/>
  <link rel="stylesheet" type="text/css" href="../styles/readaloud.css"/>
</head>
<body>
  <section epub:type="bodymatter">
    <h1 class="ibooks-dark-theme-use-custom-text-color">{html.escape(title)}</h1>
    <p class="read-control ibooks-dark-theme-use-custom-text-color"
       ibooks:readaloud="startstop"
       ibooks:readaloud-turn-style="automatic">▶ 자동 읽기</p>
    {image}
    <div class="dialogues">{''.join(pairs)}</div>
  </section>
</body>
</html>
"""


def make_study_xhtml(title, card, heading):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ko">
<head><title>{html.escape(heading)}</title>
<meta name="viewport" content="width={VIEWPORT_WIDTH}, height={VIEWPORT_HEIGHT}"/>
<link rel="stylesheet" type="text/css" href="../styles/readaloud.css"/></head>
<body><section id="study-content" class="study-page" epub:type="bodymatter">
<h1 class="ibooks-dark-theme-use-custom-text-color">{html.escape(title)}</h1>
{render_study_card(card, heading)}
</section></body></html>"""


def make_study_smil(study_id, duration=STUDY_DWELL_SECONDS):
    """Apple Books가 학습카드를 즉시 건너뛰지 않도록 무음 체류 구간을 붙인다."""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<smil xmlns="http://www.w3.org/ns/SMIL" version="3.0">
  <body>
    <seq id="seq-{study_id}" textref="../study/{study_id}.xhtml">
      <par id="par-{study_id}">
        <text src="../study/{study_id}.xhtml#study-content"/>
        <audio src="../audio/study-silence.m4a" clipBegin="00:00:00.000" clipEnd="{clock(duration)}"/>
      </par>
    </seq>
  </body>
</smil>
"""


def create_study_silence(path, duration=STUDY_DWELL_SECONDS):
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", str(duration), "-c:a", "aac", "-b:a", "32k", path,
            "-loglevel", "error",
        ],
        check=True,
    )


def make_smil(page_number, count, timings, duration):
    pars = []
    for index in range(count):
        line_id = f"line-{page_number:04d}-{index + 1:02d}"
        start, end = timings[index]
        pars.append(
            f'<par id="par-{page_number:04d}-{index + 1:02d}">'
            f'<text src="../pages/page{page_number:04d}.xhtml#{line_id}"/>'
            f'<audio src="../audio/page{page_number:04d}.m4a" '
            f'clipBegin="{clock(start)}" clipEnd="{clock(end)}"/>'
            "</par>"
        )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<smil xmlns="http://www.w3.org/ns/SMIL"
      xmlns:epub="http://www.idpf.org/2007/ops" version="3.0">
  <body>
    <seq id="seq-{page_number:04d}" epub:textref="../pages/page{page_number:04d}.xhtml">
      {''.join(pars)}
    </seq>
  </body>
</smil>
""", duration


def make_intro_xhtml(title, heading, body, cover=False):
    cover_html = (
        '<img class="book-cover" src="../images/cover.jpg" alt="책 표지"/>'
        if cover else ""
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ko">
<head><title>{html.escape(heading)}</title>
<meta name="viewport" content="width={VIEWPORT_WIDTH}, height={VIEWPORT_HEIGHT}"/>
<link rel="stylesheet" type="text/css" href="../styles/readaloud.css"/></head>
<body><section class="intro-page" epub:type="frontmatter">
<h1>{html.escape(heading)}</h1>{cover_html}{body}
</section></body></html>"""


def load_overview(book_dir):
    path = os.path.join(book_dir, "SUMMARY.md")
    if not os.path.isfile(path):
        return "요약이 준비되지 않았습니다."
    text = open(path, encoding="utf-8").read()
    match = re.search(r"## 전체 줄거리\s*\n(.*?)(?=\n##|\Z)", text, re.S)
    return (match.group(1) if match else text).strip()


def load_scene_descriptions(book_dir):
    path = os.path.join(book_dir, "scene_descriptions.json")
    if not os.path.isfile(path):
        return {}
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_study_cards(book_dir):
    path = os.path.join(book_dir, "scene_study_cards.json")
    if not os.path.isfile(path):
        return {}
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def paginate_scene(records):
    """학습 카드는 별도 쪽이므로 모든 대사 쪽을 동일한 4문장으로 묶는다."""
    return [records[index:index + LINES_PER_PAGE] for index in range(0, len(records), LINES_PER_PAGE)]


def make_nav(title, pages, intro_pages):
    intro_entries = "".join(
        f'<li><a href="{item["href"]}">{html.escape(item["title"])}</a></li>'
        for item in intro_pages
    )
    entries = "".join(
        f'<li><a href="pages/page{page["number"]:04d}.xhtml">'
        f'{html.escape(page["title"])}</a></li>'
        for page in pages
    )
    first_href = intro_pages[0]["href"] if intro_pages else f'pages/page{pages[0]["number"]:04d}.xhtml'
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ko">
<head><title>{html.escape(title)} 목차</title></head>
<body>
<nav epub:type="toc" id="toc"><h1>목차</h1><ol>{intro_entries}{entries}</ol></nav>
<nav epub:type="landmarks" hidden="hidden">
  <ol><li><a epub:type="bodymatter" href="{first_href}">본문 시작</a></li></ol>
</nav>
</body></html>
"""


def make_opf(title, pages, image_names, has_cover, identifier, intro_pages, study_pages):
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total_duration = (
        sum(page["duration"] for page in pages)
        + len(study_pages) * STUDY_DWELL_SECONDS
    )
    page_items = []
    smil_items = []
    audio_items = []
    duration_meta = []
    spine = []
    study_before = {}
    for item in study_pages:
        study_before.setdefault(item["before_page"], []).append(item)
    for page in pages:
        number = page["number"]
        page_items.append(
            f'<item id="page{number:04d}" href="pages/page{number:04d}.xhtml" '
            f'media-type="application/xhtml+xml" media-overlay="smil{number:04d}"/>'
        )
        smil_items.append(
            f'<item id="smil{number:04d}" href="overlays/page{number:04d}.smil" '
            'media-type="application/smil+xml"/>'
        )
        audio_items.append(
            f'<item id="audio{number:04d}" href="audio/page{number:04d}.m4a" '
            'media-type="audio/m4a"/>'
        )
        duration_meta.append(
            f'<meta property="media:duration" refines="#smil{number:04d}">'
            f'{clock(page["duration"])}</meta>'
        )
        spine.extend(f'<itemref idref="{item["id"]}"/>' for item in study_before.get(number, []))
        spine.append(f'<itemref idref="page{number:04d}"/>')
    images = []
    for index, name in enumerate(image_names, 1):
        media_type = "image/png" if name.lower().endswith(".png") else "image/jpeg"
        images.append(
            f'<item id="image{index:04d}" href="images/{html.escape(name)}" '
            f'media-type="{media_type}"/>'
        )
    cover_item = (
        '<item id="cover-image" href="images/cover.jpg" media-type="image/jpeg" '
        'properties="cover-image"/>' if has_cover else ""
    )
    intro_items = "".join(
        f'<item id="{item["id"]}" href="{item["href"]}" media-type="application/xhtml+xml"/>'
        for item in intro_pages
    )
    intro_spine = "".join(f'<itemref idref="{item["id"]}"/>' for item in intro_pages)
    study_items = "".join(
        f'<item id="{item["id"]}" href="{item["href"]}" media-type="application/xhtml+xml" '
        f'media-overlay="{item["smil_id"]}"/>'
        for item in study_pages
    )
    study_smil_items = "".join(
        f'<item id="{item["smil_id"]}" href="{item["smil_href"]}" '
        f'media-type="application/smil+xml"/>'
        for item in study_pages
    )
    study_duration_meta = "".join(
        f'<meta property="media:duration" refines="#{item["smil_id"]}">'
        f'{clock(STUDY_DWELL_SECONDS)}</meta>'
        for item in study_pages
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0"
         unique-identifier="bookid" prefix="media: http://www.idpf.org/epub/vocab/overlays/#">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:identifier id="bookid">{identifier}</dc:identifier>
  <dc:title>{html.escape(title)}</dc:title>
  <dc:language>ja</dc:language>
  <dc:creator>LanguageStudy</dc:creator>
  <meta property="dcterms:modified">{modified}</meta>
  <meta property="rendition:layout">pre-paginated</meta>
  <meta property="rendition:spread">auto</meta>
  <meta property="media:active-class">-epub-media-overlay-active</meta>
  <meta property="media:duration">{clock(total_duration)}</meta>
  {''.join(duration_meta)}
  {study_duration_meta}
</metadata>
<manifest>
  <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
  <item id="style" href="styles/readaloud.css" media-type="text/css"/>
  {cover_item}
  {intro_items}
  {study_items}
  {study_smil_items}
  {'<item id="study-silence" href="audio/study-silence.m4a" media-type="audio/m4a"/>' if study_pages else ''}
  {''.join(page_items)}
  {''.join(smil_items)}
  {''.join(audio_items)}
  {''.join(images)}
</manifest>
<spine page-progression-direction="ltr">{intro_spine}{''.join(spine)}</spine>
</package>
"""


def validate_readaloud_epub(path):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip():
            raise RuntimeError("EPUB ZIP 무결성 검사 실패")
        if archive.namelist()[0] != "mimetype":
            raise RuntimeError("mimetype가 EPUB 첫 항목이 아닙니다.")
        if archive.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
            raise RuntimeError("mimetype가 무압축 저장되지 않았습니다.")
        opf = archive.read("OEBPS/content.opf").decode("utf-8")
        if "pre-paginated" not in opf or "media-overlay=" not in opf:
            raise RuntimeError("고정 레이아웃 또는 Media Overlay 메타데이터 누락")
        if "media:duration" not in opf or "media:active-class" not in opf:
            raise RuntimeError("Read Aloud 필수 메타데이터 누락")
        for required_intro in ("OEBPS/intro/cover.xhtml", "OEBPS/intro/summary.xhtml"):
            if required_intro not in archive.namelist():
                raise RuntimeError(f"앞부분 페이지 누락: {required_intro}")
        if '<itemref idref="intro-cover"/>' not in opf:
            raise RuntimeError("표지가 첫 읽기 페이지에 포함되지 않았습니다")
        if "<meta property=\"rendition:spread\">auto</meta>" not in opf:
            raise RuntimeError("두 페이지 펼침(auto) 메타데이터 누락")
        pages = "\n".join(
            archive.read(name).decode("utf-8", errors="replace")
            for name in archive.namelist() if name.endswith(".xhtml")
        )
        if 'ibooks:readaloud-turn-style="automatic"' not in pages:
            raise RuntimeError("Apple Books 자동 페이지 넘김 제어 누락")
        for name in archive.namelist():
            if name.endswith((".opf", ".xhtml", ".smil", ".xml")):
                try:
                    ElementTree.fromstring(archive.read(name))
                except ElementTree.ParseError as exc:
                    raise RuntimeError(f"XML 구조 오류: {name}: {exc}") from exc
        for match in re.finditer(r'href="([^"]+)"', opf):
            href = match.group(1).split("#", 1)[0]
            if href and f"OEBPS/{href}" not in archive.namelist():
                raise RuntimeError(f"OPF manifest 파일 누락: {href}")


def build_book(book_dir, output):
    base_name = os.path.basename(book_dir)
    book_title = display_title(book_dir, base_name)
    records = load_lines(book_dir)
    if not records:
        raise RuntimeError(f"대사 원본이 없습니다: {book_dir}")
    records.sort(key=lambda item: (
        int(item["part"]), int(item["scene"]), float(item.get("start", 0))
    ))
    # 페이지 경계에서 다음 장면이 섞이지 않게 장면별로 먼저 묶는다. 그래야
    # 장면 후반 페이지에 보조 이미지를 전환하는 기준도 정확해진다.
    pages_records = []
    current_scene_key = None
    current_scene_records = []
    for record in records:
        scene_key = (int(record["part"]), int(record["scene"]))
        if current_scene_key is not None and scene_key != current_scene_key:
            pages_records.extend(paginate_scene(current_scene_records))
            current_scene_records = []
        current_scene_key = scene_key
        current_scene_records.append(record)
    if current_scene_records:
        pages_records.extend(paginate_scene(current_scene_records))
    scene_page_totals = {}
    for page_records in pages_records:
        key = (int(page_records[0]["part"]), int(page_records[0]["scene"]))
        scene_page_totals[key] = scene_page_totals.get(key, 0) + 1
    scene_page_seen = {}
    study_cards = load_study_cards(book_dir)
    cache_dir = os.path.join(book_dir, ".readaloud_cache")
    os.makedirs(cache_dir, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="readaloud_build_") as temp_root:
        oebps = os.path.join(temp_root, "OEBPS")
        for subdir in ("pages", "overlays", "audio", "styles", "images", "intro", "study"):
            os.makedirs(os.path.join(oebps, subdir), exist_ok=True)

        pages = []
        copied_images = set()
        for page_index, page_records in enumerate(pages_records, 1):
            part = int(page_records[0]["part"])
            scene = int(page_records[0]["scene"])
            scene_key = (part, scene)
            scene_page_seen[scene_key] = scene_page_seen.get(scene_key, 0) + 1
            title = f"{part}편 장면 {scene} · {page_index}쪽"
            japanese_lines = [record["ja"] for record in page_records]
            speech_text = "\n".join(japanese_lines)
            cache_key = hashlib.sha256(
                f"{VOICE}\0{RATE}\0{speech_text}".encode("utf-8")
            ).hexdigest()
            cached_mp3 = os.path.join(cache_dir, cache_key + ".mp3")
            cached_timing = os.path.join(cache_dir, cache_key + ".json")
            if not os.path.isfile(cached_mp3) or not os.path.isfile(cached_timing):
                print(
                    f"🎙️  {base_name} 낭독판 음성 생성 "
                    f"({page_index}/{len(pages_records)})"
                )
                asyncio.run(synthesize_page(speech_text, cached_mp3, cached_timing))
            else:
                print(
                    f"♻️  {base_name} 낭독판 캐시 재사용 "
                    f"({page_index}/{len(pages_records)})"
                )

            m4a_path = os.path.join(oebps, "audio", f"page{page_index:04d}.m4a")
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", cached_mp3,
                    "-c:a", "aac", "-b:a", "96k", m4a_path, "-loglevel", "error",
                ],
                check=True,
            )
            duration = audio_duration(m4a_path)
            boundaries = json.load(open(cached_timing, encoding="utf-8"))
            timings = sentence_timings(
                japanese_lines, speech_text, boundaries, duration
            )

            page_image_name = (
                f"part{part}_scene{scene:03d}_page"
                f"{scene_page_seen[scene_key]:02d}.jpg"
            )
            primary_name = f"part{part}_scene{scene:03d}.jpg"
            secondary_name = f"part{part}_scene{scene:03d}_alt.jpg"
            use_secondary = (
                scene_page_seen[scene_key] > scene_page_totals[scene_key] / 2
                and os.path.isfile(os.path.join(book_dir, "images", secondary_name))
            )
            if os.path.isfile(os.path.join(book_dir, "images", page_image_name)):
                image_name = page_image_name
            else:
                image_name = secondary_name if use_secondary else primary_name
            source_image = os.path.join(book_dir, "images", image_name)
            image_href = None
            if os.path.isfile(source_image):
                if image_name not in copied_images:
                    shutil.copy2(source_image, os.path.join(oebps, "images", image_name))
                    copied_images.add(image_name)
                image_href = f"../images/{image_name}"

            with open(
                os.path.join(oebps, "pages", f"page{page_index:04d}.xhtml"),
                "w", encoding="utf-8",
            ) as file:
                file.write(make_page_xhtml(title, page_index, page_records, image_href))
            smil, _ = make_smil(
                page_index, len(page_records), timings, duration
            )
            with open(
                os.path.join(oebps, "overlays", f"page{page_index:04d}.smil"),
                "w", encoding="utf-8",
            ) as file:
                file.write(smil)
            pages.append({
                "number": page_index, "title": title, "duration": duration
            })

        # 학습카드는 대사와 같은 고정 페이지에 넣지 않는다. 내용량을 기준으로
        # 여러 페이지로 나눠 각 장면의 첫 대사 페이지 바로 앞에 삽입한다.
        scene_first_pages = {}
        for page in pages:
            match = re.match(r"(\d+)편 장면 (\d+)", page["title"])
            if match:
                scene_first_pages.setdefault((int(match.group(1)), int(match.group(2))), page)
        study_pages = []
        study_index = 0
        for (part, scene), first_page in sorted(scene_first_pages.items()):
            card = study_cards.get(f"{part}-{scene}")
            if not card:
                continue
            chunks = split_study_card(card)
            for chunk_number, chunk in enumerate(chunks, 1):
                study_index += 1
                heading = f"장면 학습 카드 {chunk_number}/{len(chunks)}"
                study_id = f"study{study_index:04d}"
                study_href = f"study/{study_id}.xhtml"
                study_smil_id = f"{study_id}-smil"
                study_smil_href = f"overlays/{study_id}.smil"
                with open(os.path.join(oebps, study_href), "w", encoding="utf-8") as file:
                    file.write(make_study_xhtml(
                        f"{part}편 장면 {scene}", chunk, heading
                    ))
                with open(os.path.join(oebps, study_smil_href), "w", encoding="utf-8") as file:
                    file.write(make_study_smil(study_id))
                study_pages.append({
                    "id": study_id, "href": study_href,
                    "smil_id": study_smil_id, "smil_href": study_smil_href,
                    "before_page": first_page["number"],
                })

        if study_pages:
            create_study_silence(os.path.join(oebps, "audio", "study-silence.m4a"))

        cover_source = os.path.join(book_dir, "cover.jpg")
        has_cover = os.path.isfile(cover_source)
        if has_cover:
            shutil.copy2(cover_source, os.path.join(oebps, "images", "cover.jpg"))
        intro_pages = []
        cover_body = f'<p class="overview-text">{html.escape(book_title)}</p>' if not has_cover else ""
        cover_href = "intro/cover.xhtml"
        with open(os.path.join(oebps, cover_href), "w", encoding="utf-8") as file:
            file.write(make_intro_xhtml(book_title, book_title, cover_body, cover=has_cover))
        intro_pages.append({"id": "intro-cover", "href": cover_href, "title": "표지"})

        overview = load_overview(book_dir)
        overview_html = "".join(
            f'<p class="overview-text">{html.escape(paragraph.strip())}</p>'
            for paragraph in re.split(r"\n\s*\n", overview) if paragraph.strip()
        )
        summary_href = "intro/summary.xhtml"
        with open(os.path.join(oebps, summary_href), "w", encoding="utf-8") as file:
            file.write(make_intro_xhtml(book_title, "내용 요약", overview_html))
        intro_pages.append({"id": "intro-summary", "href": summary_href, "title": "내용 요약"})

        descriptions = load_scene_descriptions(book_dir)
        toc_rows = []
        for (part, scene), page in sorted(scene_first_pages.items()):
            description = descriptions.get(f"{part}-{scene}", "")
            label = f"{part}편 장면 {scene}" + (f" — {description}" if description else "")
            toc_rows.append((page["number"], label))
        for chunk_index in range(0, len(toc_rows), 10):
            chunk = toc_rows[chunk_index:chunk_index + 10]
            toc_html = '<ol class="scene-toc">' + "".join(
                f'<li><a href="../pages/page{number:04d}.xhtml">{html.escape(label)}</a></li>'
                for number, label in chunk
            ) + "</ol>"
            toc_number = chunk_index // 10 + 1
            toc_href = f"intro/toc{toc_number:02d}.xhtml"
            heading = "장면 목차" if len(toc_rows) <= 10 else f"장면 목차 {toc_number}"
            with open(os.path.join(oebps, toc_href), "w", encoding="utf-8") as file:
                file.write(make_intro_xhtml(book_title, heading, toc_html))
            intro_pages.append({
                "id": f"intro-toc{toc_number:02d}", "href": toc_href, "title": heading
            })
        with open(os.path.join(oebps, "styles", "readaloud.css"), "w", encoding="utf-8") as file:
            file.write(fixed_layout_css())
        with open(os.path.join(oebps, "nav.xhtml"), "w", encoding="utf-8") as file:
            file.write(make_nav(f"{book_title} 낭독판", pages, intro_pages))
        with open(os.path.join(oebps, "content.opf"), "w", encoding="utf-8") as file:
            file.write(make_opf(
                f"{book_title} 낭독판", pages, sorted(copied_images),
                has_cover, f"urn:uuid:{uuid.uuid4()}", intro_pages, study_pages,
            ))
        meta_inf = os.path.join(temp_root, "META-INF")
        os.makedirs(meta_inf)
        with open(os.path.join(meta_inf, "container.xml"), "w", encoding="utf-8") as file:
            file.write("""<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""")

        output = os.path.abspath(output)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        temp_output = output + ".partial"
        try:
            with zipfile.ZipFile(temp_output, "w") as archive:
                archive.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
                for root, _, files in os.walk(temp_root):
                    for name in sorted(files):
                        full_path = os.path.join(root, name)
                        relative = os.path.relpath(full_path, temp_root)
                        archive.write(full_path, relative, zipfile.ZIP_DEFLATED)
            validate_readaloud_epub(temp_output)
            os.replace(temp_output, output)
        finally:
            if os.path.exists(temp_output):
                os.unlink(temp_output)
        print(f"✅ Apple Books 낭독판 EPUB 생성 완료: {output}")
        return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "source",
        help="완성 EPUB이 들어 있는 폴더 또는 내부 작품 원본 폴더",
    )
    parser.add_argument("--output", help="단일 작품 출력 EPUB 경로")
    parser.add_argument("--output-dir", help="낭독판 EPUB을 저장할 폴더")
    args = parser.parse_args()

    source = os.path.abspath(args.source)
    jobs = resolve_books(source)
    if args.output and len(jobs) != 1:
        sys.exit("❌ --output은 단일 작품에서만 사용할 수 있습니다.")
    output_dir = (
        os.path.abspath(args.output_dir) if args.output_dir
        else source if os.path.isdir(source) and any(
            name.lower().endswith(".epub") for name in os.listdir(source)
        )
        else jobs[0][0]
    )

    failures = []
    for index, (book_dir, output_name) in enumerate(jobs, 1):
        output_file_title = filename_title(book_dir, output_name)
        output = (
            os.path.abspath(args.output) if args.output
            else os.path.join(output_dir, f"{output_file_title}_낭독판.epub")
        )
        print(f"\n📖 [{index}/{len(jobs)}] {output_name} 낭독판 EPUB 생성 시작")
        try:
            build_book(book_dir, output)
        except Exception as exc:
            failures.append((output_name, str(exc)))
            print(f"❌ {output_name} 실패: {exc}")
    if failures:
        print("\n⚠️ 실패 목록:")
        for name, reason in failures:
            print(f"  - {name}: {reason}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
