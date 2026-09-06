#!/usr/bin/env python3
"""av완성작의 완성된 낭독판(_낭독판.epub)에서 대사(ja/ko/후리가나)와 장면 이미지를
그대로 뽑아 library/<작품명>/ 폴더를 새로 만든다.

★ 2026-09-05: "라이브러리가 없으면 여기서(av완성작) 보충해" 요청 — 예전엔 학습카드가
성공적으로 만들어진 회차도 "성공 후 원본만 남기고 중간 작업물 영구 삭제" 규칙에 따라
library/<작품명>/이 통째로 지워졌다(README 2026-08-01 절대 규칙). 원본 영상 없이는
이걸 되살릴 수 없다고 판단했었는데, 낭독판 EPUB 자체가 전체 대사(ja/ko, 후리가나 포함)를
페이지마다 그대로 담고 있어서 원본 영상 없이도 여기서부터 학습카드 생성 파이프라인
(generate_summary.py → finalize_japanese_book.py → build_readaloud_epub.py)을 다시
돌릴 수 있다. 타이밍(start/end)은 원본 영상 기준이 아니라 추출 순서 기반 더미 값이며,
실제로 쓰이는 곳은 정렬 키뿐이라 문제 없다(build_readaloud_epub.py 확인).

사용법:
    python3 recover_study_cards_from_epub.py "<av완성작>/<제목>_낭독판.epub"
    → library/<제목>/ 생성(이미 있으면 --force 없이는 건너뜀)
"""

import argparse
import glob
import html
import os
import re
import sys
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LIBRARY_DIR = os.path.join(SCRIPT_DIR, "library")

PAGE_PATH_RE = re.compile(r"OEBPS/pages/page(\d+)\.xhtml$")
TITLE_TAG_RE = re.compile(r"<title>(\d+)편 장면 (\d+)")
PAIR_RE = re.compile(
    r'<div class="pair"><p id="line-\d+-\d+" class="ja[^"]*">(.*?)</p>'
    r'<p class="ko[^"]*">(.*?)</p></div>',
    re.S,
)
SCENE_THUMB_SRC_RE = re.compile(r'<img class="scene-thumb" src="\.\./images/([^"]+)"')
RUBY_RE = re.compile(r"<ruby>(.*?)<rt>(.*?)</rt></ruby>")

# subtitle_pipeline_body.sh의 create_epub_css()와 내용이 같아야 한다 —
# finalize_japanese_book.py가 pandoc으로 SUMMARY.md+transcript_part*.md를
# EPUB으로 묶을 때 이 스타일시트가 없으면 실패한다(p.ja/p.ko, 다크모드 규칙 등
# Apple Books 요구사항 검증까지 통과해야 함).
EPUB_STYLE_CSS = """:root {
    color-scheme: light dark;
}
body {
    font-family: "Hiragino Kaku Gothic Pro", "ヒラギノ角ゴ Pro", sans-serif;
    background-color: #ffffff;
    color: #1a1a1a;
    line-height: 1.6;
    padding: 1em;
}
h1 {
    color: #9a6a00;
    border-bottom: 2px solid #9a6a00;
    padding-bottom: 0.3em;
}
h2.scene {
    color: #9a6a00;
    font-size: 1.15em;
    margin-top: 1.8em;
    margin-bottom: 0.6em;
    padding: 0.3em 0.6em;
    background-color: #f2f2f2;
    border-left: 4px solid #9a6a00;
}
div.set {
    margin-bottom: 0.9em;
    padding-bottom: 0.7em;
    border-bottom: 1px solid #e0e0e0;
}
img.scene-thumb {
    width: 60%;
    max-width: 32em;
    border-radius: 4px;
    margin: 0.25em 1.1em 0.7em 0;
    float: left;
    opacity: 0.92;
}
.scene-end {
    clear: both;
}
p.scene-desc {
    font-style: italic;
    font-size: 0.92em;
    color: #555555;
    margin-top: 0.3em;
    margin-bottom: 1em;
}
p.ja {
    font-size: 1.2em;
    font-weight: bold;
    color: #000000;
    letter-spacing: 0.03em;
    margin-bottom: 0.1em;
    margin-top: 0.5em;
}
p.ko {
    font-size: 0.82em;
    color: #808080;
    margin-top: 0;
    margin-bottom: 0.15em;
    padding-left: 0.5em;
    border-left: 2px solid #cccccc;
}
div.overview {
    background-color: #f5f5f5;
    border: 1px solid #dddddd;
    border-radius: 8px;
    padding: 1.2em 1.4em;
    margin-bottom: 1.5em;
}
div.overview h2 {
    color: #9a6a00;
    margin-top: 0;
}
div.overview table {
    width: 100%;
    border-collapse: collapse;
}
div.overview td {
    padding: 0.3em 0.5em;
    border-bottom: 1px solid #e0e0e0;
}
div.overview td:first-child {
    color: #666666;
    width: 40%;
}
nav#toc a { color: #9a6a00; text-decoration: none; }

@media (prefers-color-scheme: dark) {
    body {
        background-color: #111111;
        color: #dddddd;
    }
    h1 {
        color: #f5c842;
        border-bottom-color: #f5c842;
    }
    h2.scene {
        color: #f5c842;
        background-color: #1c1c1c;
        border-left-color: #f5c842;
    }
    div.set {
        border-bottom-color: #2a2a2a;
    }
    p.scene-desc {
        color: #aaaaaa;
    }
    p.ja {
        color: #f5c842;
    }
    p.ko {
        color: #777777;
        border-left-color: #333333;
    }
    div.overview {
        background-color: #1a1a1a;
        border-color: #333333;
    }
    div.overview h2 {
        color: #f5c842;
    }
    div.overview td {
        border-bottom-color: #2a2a2a;
    }
    div.overview td:first-child {
        color: #999999;
    }
    nav#toc a { color: #f5c842; }
}
"""


def strip_ruby(text, keep_reading):
    if keep_reading:
        return RUBY_RE.sub(lambda m: f"{m.group(1)}({m.group(2)})", text)
    return RUBY_RE.sub(lambda m: m.group(1), text)


def clean_text(raw):
    return html.unescape(strip_ruby(raw, keep_reading=False)).strip()


def clean_furigana(raw):
    return html.unescape(strip_ruby(raw, keep_reading=True)).strip()


def derive_title_and_subtitle(epub_path):
    base = os.path.basename(epub_path)
    base = re.sub(r"_낭독판\.epub$", "", base)
    base = re.sub(r"\.epub$", "", base)
    if " — " in base:
        code, subtitle = base.split(" — ", 1)
        return code.strip(), subtitle.strip()
    return base.strip(), ""


def extract_pages(zf):
    """(part, scene, page_num) -> {"ja_pairs": [...], "thumb_src": "..."} 순서 보존."""
    names = sorted(
        (n for n in zf.namelist() if PAGE_PATH_RE.search(n)),
        key=lambda n: int(PAGE_PATH_RE.search(n).group(1)),
    )
    pages = []
    for name in names:
        content = zf.read(name).decode("utf-8")
        title_match = TITLE_TAG_RE.search(content)
        if not title_match:
            continue
        part = int(title_match.group(1))
        scene = int(title_match.group(2))
        thumb_match = SCENE_THUMB_SRC_RE.search(content)
        thumb_src = thumb_match.group(1) if thumb_match else None
        pairs = [
            (clean_text(ja_raw), clean_furigana(ja_raw), clean_text(ko_raw))
            for ja_raw, ko_raw in PAIR_RE.findall(content)
        ]
        pages.append({"part": part, "scene": scene, "thumb_src": thumb_src, "pairs": pairs})
    return pages


def write_transcripts(book_dir, base_name, pages):
    """part별 transcript_part{N}.jsonl(생성 파이프라인 입력)과
    transcript_part{N}.md(pandoc 입력, finalize_japanese_book.py 필수)를 만든다."""
    by_part = {}
    for page in pages:
        by_part.setdefault(page["part"], []).append(page)

    total_lines = 0
    for part, part_pages in sorted(by_part.items()):
        jsonl_path = os.path.join(book_dir, f"transcript_part{part}.jsonl")
        md_path = os.path.join(book_dir, f"transcript_part{part}.md")
        md_lines = [f"# {base_name} 제{part}편 전체 대사 {{.ibooks-dark-theme-use-custom-text-color}}\n"]
        import json as _json

        with open(jsonl_path, "w", encoding="utf-8") as jf:
            by_scene = {}
            for page in part_pages:
                by_scene.setdefault(page["scene"], []).append(page)
            for scene, scene_pages in sorted(by_scene.items()):
                thumb_src = next((p["thumb_src"] for p in scene_pages if p["thumb_src"]), None)
                thumb_name = f"part{part}_scene{scene:03d}.jpg"
                md_lines.append(f"## 장면 {scene} {{.scene .ibooks-dark-theme-use-custom-text-color}}\n")
                if thumb_src:
                    md_lines.append(
                        f'<img class="scene-thumb" src="images/{thumb_name}" alt="장면 {scene}" />\n'
                    )
                for page in scene_pages:
                    for ja_plain, ja_furigana, ko in page["pairs"]:
                        if not ja_plain or not ko:
                            continue
                        record = {
                            "part": part,
                            "scene": scene,
                            "start": float(total_lines),
                            "end": float(total_lines + 1),
                            "ja": ja_plain,
                            "furigana": ja_furigana,
                            "ko": ko,
                        }
                        jf.write(_json.dumps(record, ensure_ascii=False) + "\n")
                        md_lines.append(
                            f'<p class="ja ibooks-dark-theme-use-custom-text-color">{html.escape(ja_furigana)}</p>\n'
                            f'<p class="ko ibooks-dark-theme-use-custom-text-color">{html.escape(ko)}</p>\n'
                        )
                        total_lines += 1
        with open(md_path, "w", encoding="utf-8") as mf:
            mf.write("\n".join(md_lines) + "\n")
    return total_lines


def extract_images(zf, book_dir, pages):
    images_dir = os.path.join(book_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    seen_scenes = set()
    for page in pages:
        key = (page["part"], page["scene"])
        if key in seen_scenes or not page["thumb_src"]:
            continue
        seen_scenes.add(key)
        src_path = f"OEBPS/images/{page['thumb_src']}"
        if src_path not in zf.namelist():
            continue
        dest_name = f"part{page['part']}_scene{page['scene']:03d}.jpg"
        with open(os.path.join(images_dir, dest_name), "wb") as out:
            out.write(zf.read(src_path))


def extract_cover(zf, book_dir):
    candidates = [n for n in zf.namelist() if n.startswith("OEBPS/images/cover")]
    if not candidates:
        return
    with open(os.path.join(book_dir, "cover.jpg"), "wb") as out:
        out.write(zf.read(candidates[0]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("epub_path", help="av완성작의 <제목>_낭독판.epub 경로")
    parser.add_argument("--library-dir", default=DEFAULT_LIBRARY_DIR)
    parser.add_argument("--force", action="store_true", help="이미 있는 library 폴더를 덮어쓴다")
    args = parser.parse_args()

    if not os.path.isfile(args.epub_path):
        sys.exit(f"❌ EPUB을 찾지 못함: {args.epub_path}")

    base_name, subtitle = derive_title_and_subtitle(args.epub_path)
    book_dir = os.path.join(args.library_dir, base_name)
    # ★ 같은 코드(예: MIDA-764, PRED-870)로 부제만 다른 별개 회차가 여러 개
    # 있을 수 있다 — 코드만으로 된 폴더가 이미 있으면(이번 배치에서 먼저
    # 처리된 다른 회차일 수 있음) 부제까지 포함한 전체 제목을 폴더명으로
    # 써서 충돌을 피한다. 이 경우 BOOK_SUBTITLE.txt는 따로 안 만든다 —
    # 부제가 이미 폴더명에 들어있어 book_title.py가 또 붙이면 중복된다.
    if os.path.isdir(book_dir) and not args.force and subtitle:
        fallback_dir = os.path.join(args.library_dir, base_name + " — " + subtitle)
        if not os.path.isdir(fallback_dir):
            book_dir = fallback_dir
            subtitle = ""
    if os.path.isdir(book_dir) and not args.force:
        sys.exit(f"❌ 이미 존재함(--force로 덮어쓰기): {book_dir}")
    os.makedirs(book_dir, exist_ok=True)

    folder_name = os.path.basename(book_dir)
    with zipfile.ZipFile(args.epub_path) as zf:
        pages = extract_pages(zf)
        if not pages:
            sys.exit("❌ EPUB에서 대사 페이지를 찾지 못했습니다(형식이 다를 수 있음).")
        total_lines = write_transcripts(book_dir, folder_name, pages)
        extract_images(zf, book_dir, pages)
        extract_cover(zf, book_dir)

    with open(os.path.join(book_dir, "epub_style.css"), "w", encoding="utf-8") as f:
        f.write(EPUB_STYLE_CSS)

    if subtitle:
        with open(os.path.join(book_dir, "BOOK_SUBTITLE.txt"), "w", encoding="utf-8") as f:
            f.write(subtitle + "\n")

    parts = sorted({p["part"] for p in pages})
    scenes = sorted({(p["part"], p["scene"]) for p in pages})
    print(f"✅ {book_dir} 복구 완료 — {len(parts)}편, 장면 {len(scenes)}개, 대사 {total_lines}줄")
    print("   다음 단계: generate_summary.py로 학습카드 생성 → finalize_japanese_book.py → build_readaloud_epub.py")


if __name__ == "__main__":
    main()
