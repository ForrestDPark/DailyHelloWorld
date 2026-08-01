#!/usr/bin/env python3
"""EPUB3 Media Overlay(SMIL)를 붙여서, Apple Books에서 오디오를 재생하며
지금 읽고 있는 일본어 대사 문단이 자동으로 하이라이트되는 "읽어주기 동기화"
EPUB을 만든다.

일반 EPUB(finalize_japanese_book.py가 만든 것)을 그대로 열어서, 대사
<p class="ja ...">마다:
  1. id를 부여
  2. 그 줄의 원문(ja, 후리가나 없는 순수 텍스트)을 edge-tts로 개별 합성
  3. SMIL(.smil) 파일에 그 문단 id ↔ 오디오 클립을 매핑
  4. content.opf에 media-overlay 연결 + media:duration 메타 추가
  5. 하이라이트 CSS 클래스 추가
하고 새 파일(<작품명>_읽어주기.epub)로 저장한다 — 프로토타입 단계라 원본
EPUB은 안 건드린다.
"""

import argparse
import asyncio
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

import edge_tts

VOICE = "ja-JP-NanamiNeural"
RATE = "-10%"
ACTIVE_CLASS = "-epub-media-overlay-active"

JA_P_RE = re.compile(r'(<p class="ja[^"]*"(?:\s+id="[^"]*")?)(>)(.*?)(</p>)', re.S)


def load_lines_by_part(book_dir):
    by_part = {}
    for path in sorted(glob.glob(os.path.join(book_dir, "transcript_part*.jsonl"))):
        part_num = int(path.split("part")[-1].split(".")[0])
        lines = []
        with open(path, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if raw:
                    lines.append(json.loads(raw))
        by_part[part_num] = lines
    return by_part


def find_part_number(xhtml_content):
    m = re.search(r"제\s*(\d+)\s*편", xhtml_content)
    return int(m.group(1)) if m else None


async def synth(text, out_path):
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
    await communicate.save(out_path)


def get_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def smil_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:01d}:{m:02d}:{s:06.3f}"


def build_smil(chapter_href, pairs):
    """pairs: [(text_id, audio_href, duration), ...] 순서대로."""
    lines = [
        '<smil xmlns="http://www.w3.org/ns/SMIL" '
        'xmlns:epub="http://www.idpf.org/2007/ops" version="3.0">',
        "  <body>",
        f'    <seq epub:textref="{chapter_href}">',
    ]
    for text_id, audio_href, duration in pairs:
        lines.append(
            f'      <par><text src="{chapter_href}#{text_id}"/>'
            f'<audio src="{audio_href}" clipBegin="0:00:00.000" '
            f'clipEnd="{smil_time(duration)}"/></par>'
        )
    lines += ["    </seq>", "  </body>", "</smil>"]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book_dir", help="일본어자막추출/library/<작품명> 폴더")
    args = parser.parse_args()

    book_dir = os.path.abspath(args.book_dir)
    base_name = os.path.basename(book_dir)
    src_epub = os.path.join(book_dir, f"{base_name}.epub")
    if not os.path.isfile(src_epub):
        sys.exit(f"❌ 기본 EPUB이 없습니다: {src_epub} (먼저 finalize_japanese_book.py 실행)")

    lines_by_part = load_lines_by_part(book_dir)
    if not lines_by_part:
        sys.exit(f"❌ transcript_part*.jsonl이 없습니다: {book_dir}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        with zipfile.ZipFile(src_epub) as z:
            z.extractall(tmp_dir)

        opf_path = os.path.join(tmp_dir, "EPUB", "content.opf")
        with open(opf_path, encoding="utf-8") as f:
            opf = f.read()

        audio_dir = os.path.join(tmp_dir, "EPUB", "audio")
        os.makedirs(audio_dir, exist_ok=True)

        manifest_additions = []
        duration_meta = []
        global_idx = 0
        total_duration = 0.0

        text_dir = os.path.join(tmp_dir, "EPUB", "text")
        for xhtml_name in sorted(os.listdir(text_dir)):
            if not xhtml_name.endswith(".xhtml"):
                continue
            xhtml_path = os.path.join(text_dir, xhtml_name)
            with open(xhtml_path, encoding="utf-8") as f:
                content = f.read()

            part_num = find_part_number(content)
            if part_num is None or part_num not in lines_by_part:
                continue  # 요약(전체 줄거리) 챕터 등 대사가 없는 파일은 건너뜀

            ja_lines = lines_by_part[part_num]
            matches = list(JA_P_RE.finditer(content))
            if len(matches) != len(ja_lines):
                print(
                    f"⚠️  {xhtml_name}: 문단 수({len(matches)})와 JSONL 줄 수"
                    f"({len(ja_lines)})가 안 맞습니다 — 이 챕터는 건너뜁니다."
                )
                continue

            print(f"🎙️  {xhtml_name} ({part_num}편, {len(matches)}줄) 음성 합성 중...")
            pairs = []
            new_content_parts = []
            cursor = 0
            for i, (m, rec) in enumerate(zip(matches, ja_lines)):
                global_idx += 1
                text_id = f"ov{global_idx:05d}"
                audio_name = f"{text_id}.mp3"
                audio_path = os.path.join(audio_dir, audio_name)

                asyncio.run(synth(rec["ja"], audio_path))
                duration = get_duration(audio_path)
                total_duration += duration

                open_tag, gt, inner, close_tag = m.groups()
                # 이미 id가 있으면 교체, 없으면 새로 붙인다.
                open_tag_no_id = re.sub(r'\s+id="[^"]*"', "", open_tag)
                new_open = f'{open_tag_no_id} id="{text_id}"'
                new_content_parts.append(content[cursor:m.start()])
                new_content_parts.append(f"{new_open}{gt}{inner}{close_tag}")
                cursor = m.end()

                pairs.append((text_id, f"../audio/{audio_name}", duration))
                manifest_additions.append(
                    f'<item id="{text_id}_audio" href="audio/{audio_name}" media-type="audio/mpeg" />'
                )
            new_content_parts.append(content[cursor:])
            content = "".join(new_content_parts)

            with open(xhtml_path, "w", encoding="utf-8") as f:
                f.write(content)

            smil_name = xhtml_name.replace(".xhtml", ".smil")
            smil_path = os.path.join(text_dir, smil_name)
            with open(smil_path, "w", encoding="utf-8") as f:
                f.write(build_smil(xhtml_name, pairs))

            smil_id = xhtml_name.replace(".xhtml", "") + "_smil"
            manifest_additions.append(
                f'<item id="{smil_id}" href="text/{smil_name}" media-type="application/smil+xml" />'
            )
            chapter_duration = sum(d for _, _, d in pairs)
            duration_meta.append((smil_id, chapter_duration))

            # 원래 챕터 item에 media-overlay 속성을 붙인다.
            # ★ 처음엔 "[^/]*"를 썼는데 media-type 값(application/xhtml+xml) 안에
            # 슬래시가 들어있어서 매칭이 실패했다(re.sub는 매칭 실패해도 조용히
            # 원본을 그대로 반환하므로 에러 없이 누락됨 — epubcheck로 발견함).
            # "/"는 허용하고 ">"만 제외하는 "[^>]*?"로 고쳐야 한다.
            item_id = xhtml_name.replace(".xhtml", "") + "_xhtml"
            opf, n_subs = re.subn(
                rf'(<item id="{item_id}"[^>]*?)\s*/>',
                rf'\1 media-overlay="{smil_id}" />',
                opf,
            )
            if n_subs != 1:
                sys.exit(f"❌ content.opf에서 {item_id} 항목을 못 찾았습니다(치환 {n_subs}회).")

        if global_idx == 0:
            sys.exit("❌ 대사 문단을 하나도 못 찾았습니다 — EPUB 구조를 확인하세요.")

        # manifest에 smil/audio 아이템 추가
        opf = opf.replace("</manifest>", "\n    " + "\n    ".join(manifest_additions) + "\n  </manifest>")

        # media:duration 메타 추가 + 활성 하이라이트 클래스 지정
        meta_lines = [
            f'<meta property="media:duration" refines="#{smil_id}">{smil_time(dur)}</meta>'
            for smil_id, dur in duration_meta
        ]
        meta_lines.append(f'<meta property="media:duration">{smil_time(total_duration)}</meta>')
        meta_lines.append(f'<meta property="media:active-class">{ACTIVE_CLASS}</meta>')
        opf = opf.replace("</metadata>", "\n    " + "\n    ".join(meta_lines) + "\n  </metadata>")

        with open(opf_path, "w", encoding="utf-8") as f:
            f.write(opf)

        # 하이라이트 CSS 추가
        css_path = os.path.join(tmp_dir, "EPUB", "styles", "stylesheet1.css")
        with open(css_path, "a", encoding="utf-8") as f:
            f.write(f"\n.{ACTIVE_CLASS} {{\n  background-color: #4a3a00;\n}}\n")

        # ── 다시 압축(mimetype은 반드시 첫 항목·비압축이어야 EPUB 표준을 지킨다) ──
        output = os.path.join(book_dir, f"{base_name}_읽어주기.epub")
        if os.path.exists(output):
            os.remove(output)
        with zipfile.ZipFile(output, "w") as zf:
            zf.write(os.path.join(tmp_dir, "mimetype"), "mimetype", compress_type=zipfile.ZIP_STORED)
            for root, _dirs, files in os.walk(tmp_dir):
                for name in files:
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, tmp_dir)
                    if rel == "mimetype":
                        continue
                    zf.write(full, rel, compress_type=zipfile.ZIP_DEFLATED)

    print(f"✅ 읽어주기 동기화 EPUB 생성 완료: {output} ({global_idx}개 문단, 총 {total_duration:.1f}초)")


if __name__ == "__main__":
    main()
