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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book_dir", help="일본어자막추출/library/<작품명> 폴더")
    parser.add_argument("--output", help="출력 .m4b 경로")
    args = parser.parse_args()

    book_dir = os.path.abspath(args.book_dir)
    base_name = os.path.basename(book_dir)

    lines = load_lines(book_dir)
    if not lines:
        sys.exit(
            f"❌ transcript_part*.jsonl이 없습니다: {book_dir}\n"
            f"   완성된 EPUB이 모여있는 av완성작 폴더가 아니라, "
            f"일본어자막추출/library/<작품명> 폴더를 선택해야 합니다."
        )

    descriptions = load_scene_descriptions(book_dir)

    scenes = {}
    for r in lines:
        scenes.setdefault((r["part"], r["scene"]), []).append(r["ja"])
    scene_keys = sorted(scenes.keys())

    output = args.output or os.path.join(book_dir, f"{base_name}_오디오북.m4b")

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

    # ★ 2026-07-31: 처음엔 별도 av오디오북 폴더를 만들었는데, 사용자가 EPUB이
    # 이미 모여있는 av완성작 폴더에 오디오북도 같이 저장해달라고 요청해서 통일.
    completed_dir = "/Users/forrestdpark/Desktop/BlogImage/av완성작"
    os.makedirs(completed_dir, exist_ok=True)
    shutil.copy2(output, completed_dir)

    print(f"✅ 오디오북 생성 완료: {output} ({len(scene_keys)}챕터)")
    print(f"📚 av완성작 폴더로 복사 완료: {os.path.join(completed_dir, os.path.basename(output))}")


if __name__ == "__main__":
    main()
