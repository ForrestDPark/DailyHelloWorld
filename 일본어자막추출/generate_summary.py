#!/usr/bin/env python3
"""transcript_part*.jsonl을 Claude Code CLI(헤드리스 -p 모드)로 요약한다.

원래 이 자리는 "Codex가 transcript_part*.jsonl과 대표 이미지를 읽고 SUMMARY.md를
작성한다"는 수동 단계였는데, 자막·번역·Notion·EPUB까지 자동으로 끝난 뒤 이 요약만
사람이 별도 세션을 열어 해줘야 하는 게 병목이라 자동화했다. 대사 텍스트(ja/ko)만
보고 요약하며, 이미지는 넣지 않는다(빠르고 간단한 쪽을 선택 — 필요해지면 나중에
멀티모달로 확장 가능).

★ 2026-07-31: 장면별 한 줄 설명을 "전체 줄거리" 뒤에 목차처럼 몰아서 SUMMARY.md에
넣던 걸, 각 장면의 실제 위치(제목+대표 이미지 다음, 대사 시작 전)에 바로 끼워
넣도록 바꿨다(사용자 요청 — "장면 1, 사진 나오고, 그 다음 설명" 순서를 원함).
그래서 SUMMARY.md에는 이제 "전체 줄거리"만 남고, 장면별 설명은
inject_scene_descriptions()가 transcript_part*.md 안의 해당 장면 자리에
직접 써넣는다.
"""

import argparse
import glob
import json
import os
import re
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
형식 그대로 "전체 줄거리"와 "장면별 한 줄 설명"을 한국어로 작성해라. 서론이나
설명 없이 지정된 형식 그대로만 출력해라(코드블록으로 감싸지 말 것).

형식:
## 전체 줄거리

(전체 흐름을 3~6문장으로 요약)

## 장면별 설명

[1편 장면 1] (한 줄 요약)
[1편 장면 2] (한 줄 요약)
(입력에 나온 "[N편 장면 M]" 태그를 정확히 그대로 옮겨 적고, 빠짐없이 모든
장면에 대해 작성해라 — 태그 표기를 절대 바꾸지 말 것.)

---

{transcript_text}
"""


def parse_response(body):
    """Claude 응답을 "전체 줄거리" 본문과 {(part, scene): 설명} 딕셔너리로 나눈다."""
    overview_match = re.search(
        r"## 전체 줄거리\s*\n(.*?)(?=\n##|\Z)", body, re.S
    )
    overview = overview_match.group(1).strip() if overview_match else body.strip()

    descriptions = {}
    for m in re.finditer(r"\[(\d+)편\s*장면\s*(\d+)\]\s*(.+)", body):
        part, scene, desc = int(m.group(1)), int(m.group(2)), m.group(3).strip()
        descriptions[(part, scene)] = desc
    return overview, descriptions


def inject_scene_descriptions(book_dir, descriptions):
    """transcript_part{N}.md 안의 각 "## 장면 M {.scene ...}" 헤더 + 대표 이미지
    다음, 대사가 시작되기 전에 그 장면의 한 줄 설명을 끼워 넣는다."""
    scene_header_re = re.compile(
        r'(^## 장면 (\d+) \{[^\n]*\.scene[^\n]*\}\n\n'
        r'<img class="scene-thumb"[^\n]*/>\n\n)',
        re.M,
    )
    for md_path in sorted(glob.glob(os.path.join(book_dir, "transcript_part*.md"))):
        part_num = int(md_path.split("part")[-1].split(".")[0])
        with open(md_path, encoding="utf-8") as f:
            content = f.read()

        def _replace(m):
            scene_num = int(m.group(2))
            desc = descriptions.get((part_num, scene_num))
            if not desc:
                return m.group(1)
            return (
                m.group(1)
                + f'<p class="scene-desc ibooks-dark-theme-use-custom-text-color">'
                f'{desc}</p>\n\n'
            )

        new_content = scene_header_re.sub(_replace, content)
        if new_content != content:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(new_content)


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

    # ★ 2026-07-31: Claude가 가끔 "[N편 장면 M]" 태그 형식을 안 지키고 다른
    # 방식(예: "장면 M:")으로 답하는 경우가 있어(실제로 DLDSS-217에서 발생),
    # 형식이 하나도 안 지켜지면 "태그 형식을 반드시 지키라"고 한 번 더 강조해서
    # 재시도한다.
    overview, descriptions = None, {}
    for attempt in range(2):
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

        overview, descriptions = parse_response(body)
        if descriptions:
            break
        prompt += (
            "\n\n★ 방금 응답에 \"[N편 장면 M]\" 태그가 하나도 없었다. "
            "반드시 대괄호 태그 형식 그대로 지켜서 다시 작성해라."
        )

    if not descriptions:
        sys.exit("❌ 장면별 설명을 하나도 못 찾았습니다(재시도 포함) — Claude 응답 형식을 확인하세요.")

    # 다른 스크립트(오디오북 챕터 제목 등)가 재사용할 수 있게 저장해둔다.
    with open(os.path.join(book_dir, "scene_descriptions.json"), "w", encoding="utf-8") as f:
        json.dump(
            {f"{part}-{scene}": desc for (part, scene), desc in descriptions.items()},
            f, ensure_ascii=False, indent=2,
        )

    with open(summary_path, "w", encoding="utf-8") as f:
        # {.ibooks-dark-theme-use-custom-text-color}: Apple Books가 다크 테마에서
        # h1 커스텀 색상을 흰색으로 강제 대체하지 않도록 하는 공식 클래스.
        f.write(
            f"# {base_name} 줄거리 {{.ibooks-dark-theme-use-custom-text-color}}\n\n"
            f"## 전체 줄거리\n\n{overview}\n"
        )

    inject_scene_descriptions(book_dir, descriptions)

    print(f"✅ 전체 줄거리 저장 + 장면별 설명 {len(descriptions)}개 삽입 완료: {summary_path}")


if __name__ == "__main__":
    main()
