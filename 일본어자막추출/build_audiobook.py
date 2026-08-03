#!/usr/bin/env python3
"""transcript_part*.jsonl의 일본어 대사를 edge-tts로 읽어서, 장면마다 챕터가
나뉜 진짜 오디오북(.m4b)을 만든다 — Apple Books의 '오디오북' 카테고리로
바로 들어가서 오디오북 앱처럼 재생/배속/챕터 이동이 된다.

한국어 번역은 안 읽는다 — EPUB으로 이미 읽고 있으므로 오디오북은 일본어
발음만 듣는 용도(이전에 있었다가 제거된 TTS 기능과 같은 목소리 설정 사용).
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

import edge_tts

VOICE = "ja-JP-NanamiNeural"
RATE = "-10%"


def load_lines(book_dir):
    lines = []
    for path in sorted(glob.glob(os.path.join(book_dir, "transcript_part*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if raw:
                    lines.append(json.loads(raw))
    return lines


def load_scene_descriptions(book_dir):
    path = os.path.join(book_dir, "scene_descriptions.json")
    if not os.path.isfile(path):
        return {}
    raw = json.load(open(path, encoding="utf-8"))
    descriptions = {}
    for key, desc in raw.items():
        part, scene = key.split("-")
        descriptions[(int(part), int(scene))] = desc
    return descriptions


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


def build_book(book_dir, output):
    base_name = os.path.basename(book_dir)
    lines = load_lines(book_dir)
    if not lines:
        raise RuntimeError(f"대사 원본이 없습니다: {book_dir}")

    descriptions = load_scene_descriptions(book_dir)

    scenes = {}
    for r in lines:
        scenes.setdefault((r["part"], r["scene"]), []).append(r["ja"])
    scene_keys = sorted(scenes.keys())

    output = os.path.abspath(output)
    os.makedirs(os.path.dirname(output), exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        clip_paths = []
        for i, key in enumerate(scene_keys):
            part, scene = key
            text = "。".join(scenes[key])
            clip_path = os.path.join(tmp_dir, f"scene_{i:04d}.mp3")
            print(f"🎙️  {part}편 장면 {scene} 음성 합성 중... ({i + 1}/{len(scene_keys)})")
            asyncio.run(synth(text, clip_path))
            if not os.path.isfile(clip_path) or os.path.getsize(clip_path) == 0:
                sys.exit(f"❌ TTS 합성 실패: {part}편 장면 {scene}")
            clip_paths.append((key, clip_path))

        concat_list = os.path.join(tmp_dir, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for _, p in clip_paths:
                f.write(f"file '{p}'\n")

        combined = os.path.join(tmp_dir, "combined.m4a")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
             "-c:a", "aac", "-b:a", "64k", combined, "-loglevel", "error"],
            check=True,
        )

        chapters_path = os.path.join(tmp_dir, "chapters.txt")
        cursor = 0.0
        with open(chapters_path, "w", encoding="utf-8") as f:
            f.write(";FFMETADATA1\n")
            for key, p in clip_paths:
                dur = get_duration(p)
                part, scene = key
                desc = descriptions.get(key, "")
                title = f"{part}편 장면 {scene}" + (f" — {desc}" if desc else "")
                start_ms = int(cursor * 1000)
                end_ms = int((cursor + dur) * 1000)
                f.write("[CHAPTER]\nTIMEBASE=1/1000\n")
                f.write(f"START={start_ms}\nEND={end_ms}\n")
                f.write(f"title={title}\n")
                cursor += dur

        subprocess.run(
            ["ffmpeg", "-y", "-i", combined, "-i", chapters_path,
             "-map_metadata", "1", "-c", "copy",
             "-metadata", f"title={base_name}",
             "-metadata", "artist=LanguageStudy",
             "-metadata", "genre=Audiobooks",
             output, "-loglevel", "error"],
            check=True,
        )

    # ★ stik(미디어 종류) 아톰을 Audiobook으로 표시해야 Apple Books/Music이
    # 오디오북 전용 카테고리(배속·수면 타이머·챕터 이동 등)로 인식한다.
    if shutil.which("AtomicParsley"):
        subprocess.run(
            ["AtomicParsley", output, "--stik", "Audiobook", "--overWrite"],
            capture_output=True, text=True,
        )
    else:
        print("⚠️  AtomicParsley가 없어 오디오북 전용 표시(stik)를 못 붙였습니다 "
              "— brew install atomicparsley 후 다시 실행하면 붙습니다.")
    print(f"✅ 오디오북 생성 완료: {output} ({len(scene_keys)}챕터)")
    return output


def resolve_books(selected_path):
    """사용자가 고른 완성 EPUB 폴더를 내부 library 원본과 자동 연결한다."""
    selected_path = os.path.abspath(selected_path)
    if glob.glob(os.path.join(selected_path, "transcript_part*.jsonl")):
        return [(selected_path, os.path.basename(selected_path))]

    if not os.path.isdir(selected_path):
        raise RuntimeError(f"폴더가 아닙니다: {selected_path}")

    epub_paths = sorted(glob.glob(os.path.join(selected_path, "*.epub")))
    if not epub_paths:
        raise RuntimeError(f"선택한 폴더에 EPUB 파일이 없습니다: {selected_path}")

    library_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library")
    jobs = {}
    unmatched = []
    for epub_path in epub_paths:
        stem = os.path.splitext(os.path.basename(epub_path))[0]
        if stem.endswith(("읽어주기", "낭독판")):
            continue
        candidates = [
            stem,
            stem.replace(" ", "_"),
            re.sub(r"\s+J$", "_J", stem),
        ]
        book_dir = next(
            (
                os.path.join(library_root, candidate)
                for candidate in candidates
                if os.path.isdir(os.path.join(library_root, candidate))
                and glob.glob(
                    os.path.join(library_root, candidate, "transcript_part*.jsonl")
                )
            ),
            None,
        )
        if book_dir:
            # 같은 작품의 구형/신형 EPUB이 둘 다 있어도 TTS는 한 번만 만든다.
            jobs[os.path.realpath(book_dir)] = (book_dir, os.path.basename(book_dir))
        else:
            unmatched.append(stem)

    if unmatched:
        print(
            "ℹ️  대사 원본이 없어 오디오북을 만들 수 없는 EPUB "
            f"{len(unmatched)}개는 건너뜁니다: {', '.join(unmatched)}"
        )
    if not jobs:
        raise RuntimeError(
            "선택한 EPUB들과 연결되는 대사 원본이 없습니다. "
            "이 EPUB들은 예전 방식으로 만들어져 오디오북용 일본어 대사 데이터가 남아있지 않습니다."
        )
    return list(jobs.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "source",
        help="완성 EPUB이 들어 있는 폴더(권장) 또는 내부 작품 원본 폴더",
    )
    parser.add_argument("--output", help="단일 작품일 때 출력 .m4b 경로")
    parser.add_argument("--output-dir", help="오디오북을 저장할 폴더")
    args = parser.parse_args()

    source = os.path.abspath(args.source)
    jobs = resolve_books(source)
    if args.output and len(jobs) != 1:
        sys.exit("❌ --output은 단일 작품을 처리할 때만 사용할 수 있습니다.")

    if args.output_dir:
        output_dir = os.path.abspath(args.output_dir)
    elif glob.glob(os.path.join(source, "*.epub")):
        output_dir = source
    else:
        output_dir = jobs[0][0]

    failures = []
    for index, (book_dir, output_name) in enumerate(jobs, 1):
        output = (
            os.path.abspath(args.output)
            if args.output else
            os.path.join(output_dir, f"{output_name}_오디오북.m4b")
        )
        print(f"\n📚 [{index}/{len(jobs)}] {output_name} 오디오북 생성 시작")
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
