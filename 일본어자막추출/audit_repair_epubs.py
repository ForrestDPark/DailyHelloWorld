#!/usr/bin/env python3
"""완성 EPUB의 Apple Books 색상 규칙을 검사하고 구형 파일을 안전하게 보정한다."""

import argparse
import os
import re
import shutil
import tempfile
import zipfile


CUSTOM_CLASS = "ibooks-dark-theme-use-custom-text-color"
STYLE_PATCH_MARKER = "/* LanguageStudy Apple Books color patch v1 */"
READALOUD_PATCH_MARKER = "/* LanguageStudy mobile readaloud patch v3 */"
STYLE_PATCH = f"""

{STYLE_PATCH_MARKER}
:root {{ color-scheme: light dark; }}
body {{ background-color: #ffffff; color: #1a1a1a; }}
h1 {{ color: #9a6a00; border-bottom-color: #9a6a00; }}
h2.scene {{
    color: #9a6a00;
    background-color: #f2f2f2;
    border-left-color: #9a6a00;
}}
p.scene-desc {{ color: #555555; }}
p.ja {{ color: #000000; font-weight: bold; }}
p.ko {{ color: #808080; border-left-color: #cccccc; }}
div.overview {{ background-color: #f5f5f5; border-color: #dddddd; }}
div.overview h2 {{ color: #9a6a00; }}
div.overview td:first-child {{ color: #666666; }}
nav#toc a {{ color: #9a6a00; }}
@media (prefers-color-scheme: dark) {{
    body {{ background-color: #111111; color: #dddddd; }}
    h1 {{ color: #f5c842; border-bottom-color: #f5c842; }}
    h2.scene {{
        color: #f5c842;
        background-color: #1c1c1c;
        border-left-color: #f5c842;
    }}
    p.scene-desc {{ color: #aaaaaa; }}
    p.ja {{ color: #f5c842; }}
    p.ko {{ color: #777777; border-left-color: #333333; }}
    div.overview {{ background-color: #1a1a1a; border-color: #333333; }}
    div.overview h2 {{ color: #f5c842; }}
    div.overview td:first-child {{ color: #999999; }}
    nav#toc a {{ color: #f5c842; }}
}}

{READALOUD_PATCH_MARKER}
.read-control {{
    display: block; width: 52%; margin: 0 auto 22px; padding: 13px 18px;
    text-align: center; font-size: 24px;
    -webkit-user-select: none; user-select: none; touch-action: manipulation;
}}
p.ja {{ font-size: 44px; line-height: 1.28; }}
p.ko {{ font-size: 27px; line-height: 1.3; }}
rt {{ font-size: 15px; }}
"""


def add_custom_class(match):
    before, classes, after = match.groups()
    tokens = classes.split()
    if CUSTOM_CLASS not in tokens:
        tokens.append(CUSTOM_CLASS)
    return before + " ".join(tokens) + after


def patch_xhtml(text):
    # 색을 직접 지정하는 본문 요소에는 Apple Books의 공식 opt-in 클래스를 붙인다.
    text = re.sub(
        r'(<(?:p|h1|h2)\b[^>]*\bclass=")([^"]*)(\")',
        lambda match: (
            add_custom_class(match)
            if set(match.group(2).split()) & {"ja", "ko", "scene", "scene-desc"}
            else match.group(0)
        ),
        text,
    )
    text = re.sub(
        r"<h1(\s+)(?![^>]*\bclass=)",
        f'<h1 class="{CUSTOM_CLASS}"\\1',
        text,
    )
    # 구형 본문의 `朝(あさ)` 표기도 한자 위에만 보이는 ruby로 승격한다.
    def patch_ja_paragraph(match):
        opening, body, closing = match.groups()
        body = re.sub(
            r"([一-鿿々〆ヵヶ]+)([ぁ-ゖァ-ヺー]*)\(([ぁ-ゖァ-ヺー]+)\)",
            lambda item: (
                f"<ruby>{item.group(1)}<rt>{item.group(3)[:max(1, len(item.group(3)) - len(item.group(2)))]}</rt></ruby>"
                f"{item.group(2)}"
            ),
            body,
        )
        return opening + body + closing
    text = re.sub(
        r'(<p\b[^>]*class="[^"]*\bja\b[^"]*"[^>]*>)(.*?)(</p>)',
        patch_ja_paragraph, text, flags=re.S,
    )
    return text


def inspect_epub(path):
    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
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
        opf = "\n".join(
            archive.read(name).decode("utf-8", errors="replace")
            for name in archive.namelist()
            if name.endswith(".opf")
        )
    ja_total = len(re.findall(r'class="[^"]*\bja\b[^"]*"', xhtml))
    ko_total = len(re.findall(r'class="[^"]*\bko\b[^"]*"', xhtml))
    ja_custom = len(re.findall(
        rf'class="[^"]*\bja\b[^"]*\b{CUSTOM_CLASS}\b[^"]*"'
        rf'|class="[^"]*\b{CUSTOM_CLASS}\b[^"]*\bja\b[^"]*"',
        xhtml,
    ))
    ko_custom = len(re.findall(
        rf'class="[^"]*\bko\b[^"]*\b{CUSTOM_CLASS}\b[^"]*"'
        rf'|class="[^"]*\b{CUSTOM_CLASS}\b[^"]*\bko\b[^"]*"',
        xhtml,
    ))
    return {
        "zip_ok": bad_member is None,
        "ja": ja_total,
        "ja_custom": ja_custom,
        "ko": ko_total,
        "ko_custom": ko_custom,
        "scenes": len(re.findall(r'<h2[^>]*class="[^"]*\bscene\b', xhtml)),
        "descriptions": len(re.findall(r'class="[^"]*\bscene-desc\b', xhtml)),
        "dark_css": "@media (prefers-color-scheme: dark)" in css,
        "color_scheme": bool(re.search(r"color-scheme\s*:\s*light dark", css)),
        "readaloud_patch": READALOUD_PATCH_MARKER in css,
        "cover": "cover-image" in opf or 'name="cover"' in opf,
    }


def repair_epub(path, backup_dir=None):
    path = os.path.abspath(path)
    current = inspect_epub(path)
    already_compliant = (
        current["zip_ok"]
        and current["ja_custom"] == current["ja"]
        and current["ko_custom"] == current["ko"]
        and current["dark_css"]
        and current["color_scheme"]
        and current["readaloud_patch"]
    )
    if already_compliant:
        return current
    if backup_dir:
        os.makedirs(backup_dir, exist_ok=True)
        backup = os.path.join(backup_dir, os.path.basename(path))
        if not os.path.exists(backup):
            shutil.copy2(path, backup)

    fd, temp_path = tempfile.mkstemp(
        prefix=".epub_repair_", suffix=".epub", dir=os.path.dirname(path)
    )
    os.close(fd)
    try:
        with zipfile.ZipFile(path) as source, zipfile.ZipFile(temp_path, "w") as target:
            names = source.namelist()
            ordered = (["mimetype"] if "mimetype" in names else []) + [
                name for name in names if name != "mimetype"
            ]
            for name in ordered:
                info = source.getinfo(name)
                data = source.read(name)
                if name.endswith((".xhtml", ".html")):
                    data = patch_xhtml(
                        data.decode("utf-8", errors="replace")
                    ).encode("utf-8")
                elif name.endswith(".css"):
                    text = data.decode("utf-8", errors="replace")
                    if (
                        STYLE_PATCH_MARKER not in text
                        or READALOUD_PATCH_MARKER not in text
                    ):
                        text += STYLE_PATCH
                    data = text.encode("utf-8")
                compression = (
                    zipfile.ZIP_STORED if name == "mimetype"
                    else info.compress_type
                )
                target.writestr(info, data, compress_type=compression)

        result = inspect_epub(temp_path)
        if not result["zip_ok"]:
            raise RuntimeError("ZIP 무결성 검사 실패")
        if result["ja_custom"] != result["ja"] or result["ko_custom"] != result["ko"]:
            raise RuntimeError("일본어/한국어 커스텀 색상 클래스 보정 실패")
        if not result["dark_css"] or not result["color_scheme"]:
            raise RuntimeError("라이트/다크 CSS 보정 실패")
        os.replace(temp_path, path)
        return result
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def format_result(path, result):
    return (
        f"{os.path.basename(path)} | zip={'OK' if result['zip_ok'] else 'FAIL'}"
        f" | ja={result['ja_custom']}/{result['ja']}"
        f" | ko={result['ko_custom']}/{result['ko']}"
        f" | scene={result['scenes']} | desc={result['descriptions']}"
        f" | dark={'OK' if result['dark_css'] and result['color_scheme'] else 'FAIL'}"
        f" | cover={'YES' if result['cover'] else 'NO'}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="EPUB 파일 또는 EPUB이 든 폴더")
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--backup-dir")
    args = parser.parse_args()

    epubs = []
    for raw_path in args.paths:
        path = os.path.abspath(raw_path)
        if os.path.isdir(path):
            epubs.extend(
                os.path.join(path, name)
                for name in sorted(os.listdir(path))
                if name.lower().endswith(".epub")
            )
        elif path.lower().endswith(".epub"):
            epubs.append(path)

    failed = 0
    for epub in epubs:
        try:
            result = (
                repair_epub(epub, args.backup_dir)
                if args.repair else inspect_epub(epub)
            )
            print(format_result(epub, result))
        except Exception as exc:
            failed += 1
            print(f"{os.path.basename(epub)} | FAIL | {exc}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
