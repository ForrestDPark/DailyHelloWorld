#!/usr/bin/env python3
"""transcript_part*.jsonl을 Claude Code CLI(헤드리스 -p 모드)로 요약해 SUMMARY.md를 채운다.

원래 이 자리는 "Codex가 transcript_part*.jsonl과 대표 이미지를 읽고 SUMMARY.md를
작성한다"는 수동 단계였는데, 자막·번역·Notion·EPUB까지 자동으로 끝난 뒤 이 요약만
사람이 별도 세션을 열어 해줘야 하는 게 병목이라 자동화했다. 대사 텍스트(ja/ko)만
보고 요약하며, 이미지는 넣지 않는다(빠르고 간단한 쪽을 선택 — 필요해지면 나중에
멀티모달로 확장 가능).
"""

import argparse
import glob
import json
import os
import subprocess
import sys


def load_lines(book_dir):
    lines = []
    for path in sorted(glob.glob(os.path.join(book_dir, "transcript_part*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if raw:
                    lines.append(json.loads(raw))
    return lines


def build_prompt(base_name, lines):
    scene_groups = {}
    for rec in lines:
        key = (rec["part"], rec["scene"])
        scene_groups.setdefault(key, []).append(rec)

    chunks = []
    for (part, scene) in sorted(scene_groups.keys()):
        recs = scene_groups[(part, scene)]
        dialogue = "\n".join(f"- {r['ja']} → {r['ko']}" for r in recs)
        chunks.append(f"[{part}편 장면 {scene}]\n{dialogue}")
    transcript_text = "\n\n".join(chunks)

    return f"""다음은 일본어 성인 영상 "{base_name}"의 whisper 자막에서 뽑은 대사
원문(ja)과 한국어 번역(ko)을 장면 순서대로 나열한 것이다. 이 대사만 보고 아래
마크다운 형식 그대로 "전체 줄거리"와 "장면별 목차"를 한국어로 작성해라. 서론이나
설명 없이 마크다운 본문만 출력해라(코드블록으로 감싸지 말 것).

형식:
## 전체 줄거리

(전체 흐름을 3~6문장으로 요약)

## 장면별 목차

- 장면 1: (한 줄 요약)
- 장면 2: (한 줄 요약)
(나열된 모든 장면 번호에 대해 빠짐없이 작성)

---

{transcript_text}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book_dir", help="일본어자막추출/library/<작품명> 폴더")
    args = parser.parse_args()

    book_dir = os.path.abspath(args.book_dir)
    base_name = os.path.basename(book_dir)
    summary_path = os.path.join(book_dir, "SUMMARY.md")

    lines = load_lines(book_dir)
    if not lines:
        sys.exit(f"❌ transcript_part*.jsonl이 없습니다: {book_dir}")

    prompt = build_prompt(base_name, lines)

    result = subprocess.run(
        ["claude", "-p", "--tools", "", "--output-format", "text"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=600,
    )
    body = result.stdout.strip()
    if result.returncode != 0 or not body:
        sys.exit(f"❌ Claude 요약 생성 실패({result.returncode}): {result.stderr.strip()}")

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"# {base_name} 줄거리·목차\n\n{body}\n")

    print(f"✅ 요약 생성 완료: {summary_path}")


if __name__ == "__main__":
    main()
