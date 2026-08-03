#!/usr/bin/env python3
"""transcript_part*.jsonl을 Codex CLI 비대화형 모드로 요약한다.

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
import html
import json
import os
import re
import shutil
import subprocess
import sys

from book_title import clean_subtitle, display_title, load_book_subtitle


def load_lines(book_dir):
    lines = []
    for path in sorted(glob.glob(os.path.join(book_dir, "transcript_part*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if raw:
                    lines.append(json.loads(raw))
    return lines


def build_prompt(base_name, lines, existing_subtitle="", include_cards=True):
    scene_groups = {}
    for rec in lines:
        key = (rec["part"], rec["scene"])
        scene_groups.setdefault(key, []).append(rec)

    chunks = []
    line_ids = {id(record): f"L{index:04d}" for index, record in enumerate(lines, 1)}
    for (part, scene) in sorted(scene_groups.keys()):
        recs = scene_groups[(part, scene)]
        dialogue = "\n".join(
            f"- [{line_ids[id(r)]}] {r['ja']} → {r['ko']}" for r in recs
        )
        chunks.append(f"[{part}편 장면 {scene}]\n{dialogue}")
    transcript_text = "\n\n".join(chunks)
    card_example = json.dumps({
        "1-1": {
            "expressions": [
                {"ja": "핵심 표현", "reading": "후리가나 읽기", "ko": "뜻"},
                {"ja": "핵심 표현", "reading": "후리가나 읽기", "ko": "뜻"},
                {"ja": "핵심 표현", "reading": "후리가나 읽기", "ko": "뜻"},
            ],
            "vocabulary": [{
                "ja": "한자 단어", "reading": "일본어 읽기", "ko": "뜻",
                "hanja_sound": "한글 한자음",
                "hanja_hun": "각 한자의 훈(예: 맺을 약·묶을 속)",
            }],
            "grammar": ["문법·어미·뉘앙스 설명"],
            "shadowing": {"ja": "추천 일본어 문장", "reading": "후리가나 읽기", "ko": "뜻"},
        }
    }, ensure_ascii=False, separators=(",", ":"))

    card_request = f"""입력의 모든 장면을 아래 JSON 객체에 빠짐없이 넣어라. JSON 앞뒤에 코드 펜스를 쓰지 마라.
핵심 표현은 고정 3개가 아니다. 해당 장면 대사에 실제로 나온 학습 가치 있는 표현을
가능한 한 모두 살펴보고 장면당 8~10개(목표 10개)를 추려라. 짧은 장면에서도 표현을
지어내거나 중복해 수를 채우지 말고 실제 쓸 만한 표현을 최소 6개 이상 고른다.
expressions의 reading에는 문장 전체의 자연스러운 히라가나 읽기를 써서 후리가나로
표시할 수 있게 한다. shadowing에도 reading을 반드시 쓴다.
{card_example}
한자가 없는 단어는 hanja_sound와 hanja_hun을 빈 문자열로 써도 된다. 한자 단어에는
reading, hanja_sound, hanja_hun을 반드시 정확히 채워라.""" if include_cards else (
        "이 작품은 장면이 많아 학습카드를 별도 분할 생성한다. 여기서는 반드시 빈 JSON 객체 {}만 출력하라."
    )

    return f"""다음은 일본어 성인 영상 "{base_name}"의 whisper 자막에서 뽑은 대사
원문(ja)과 한국어 번역(ko)을 장면 순서대로 나열한 것이다. 이 대사만 보고 아래
형식 그대로 "추천 부제목", "전체 줄거리", "장면별 한 줄 설명", "번역 교정 JSON", "학습 카드 JSON"을 작성해라. 서론이나
설명 없이 지정된 형식 그대로만 출력해라(코드블록으로 감싸지 말 것).

형식:
## 추천 부제목

({f'기존에 확정된 다음 부제목을 글자 하나 바꾸지 말고 그대로 출력: {existing_subtitle}' if existing_subtitle else '전체 내용을 나타내는 한국어 부제목 하나. 10~25자, 소설·영화 제목처럼 자연스럽게, 인물 이름을 지어내거나 결말을 노출하거나 노골적인 표현을 쓰지 말 것'})

## 전체 줄거리

(전체 흐름을 3~6문장으로 요약)

## 장면별 설명

[1편 장면 1] (한 줄 요약)
[1편 장면 2] (한 줄 요약)
(입력에 나온 "[N편 장면 M]" 태그를 정확히 그대로 옮겨 적고, 빠짐없이 모든
장면에 대해 작성해라 — 태그 표기를 절대 바꾸지 말 것.)

## 번역 교정 JSON

전체 줄거리와 장면 문맥을 살펴 Google 한국어 번역이 의미상 명백히 틀리거나 매우
부자연스러운 문장만 {{"L0001":"자연스럽고 정확한 한국어"}} 형식으로 넣어라.
이미 맞거나 취향 차이에 불과한 번역은 넣지 말고, 교정할 것이 없으면 {{}}를 출력한다.
앞뒤 문맥으로 확실한 범위만 고치며 원문에 없는 내용을 추가하거나 순화하지 마라.

## 학습 카드 JSON

{card_request}

---

{transcript_text}
"""


def generate_cards_batched(book_dir, base_name, lines, batch_size=6):
    """출력 한도를 피하려고 큰 작품의 학습카드를 장면 묶음별로 생성한다."""
    grouped = {}
    for record in lines:
        grouped.setdefault((int(record["part"]), int(record["scene"])), []).append(record)
    scene_keys = sorted(grouped)
    partial_path = os.path.join(book_dir, "scene_study_cards.partial.json")
    try:
        all_cards = json.load(open(partial_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        all_cards = {}
    for start in range(0, len(scene_keys), batch_size):
        keys = scene_keys[start:start + batch_size]
        dialogue = "\n\n".join(
            f"[{part}편 장면 {scene}]\n" + "\n".join(
                f"- {record['ja']} → {record['ko']}" for record in grouped[(part, scene)]
            ) for part, scene in keys
        )
        expected = {f"{part}-{scene}" for part, scene in keys}
        batch_scenes = {(part, scene) for part, scene in keys}
        cached = {key: all_cards.get(key) for key in expected if key in all_cards}
        if valid_cards(cached, batch_scenes):
            print(f"   ↪️ 학습카드 묶음 {start // batch_size + 1} 중간 저장본 재사용")
            continue
        prompt = f"""다음은 {base_name}의 일부 장면 대사다. 이 묶음의 장면별 일본어 학습 카드만 만든다.
설명이나 코드 펜스 없이 JSON 객체 하나만 출력하라. 키는 {sorted(expected)}를 정확히 모두 사용한다.
각 카드 형식은 expressions(실제 대사에서 6~10개), vocabulary, grammar, shadowing이다.
expressions 각 항목과 shadowing은 ja, reading(자연스러운 히라가나), ko를 반드시 넣는다.
vocabulary 각 항목은 ja, reading, ko, hanja_sound, hanja_hun을 넣고, 한자 단어의 한글 한자음과 훈을 정확히 쓴다.
표현을 지어내거나 중복하지 않는다.

{dialogue}"""
        batch = None
        last_error = ""
        for attempt in range(3):
            result = subprocess.run(
                [
                    "/opt/homebrew/bin/codex", "exec", "--ephemeral", "--sandbox", "read-only",
                    "--skip-git-repo-check", "-C", book_dir, "-",
                ],
                input=prompt, capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                last_error = result.stderr.strip()
            else:
                match = re.search(r"\{.*\}", result.stdout, re.S)
                try:
                    candidate = json.loads(match.group(0)) if match else None
                except json.JSONDecodeError as exc:
                    candidate = None
                    last_error = str(exc)
                if candidate is not None and valid_cards(candidate, batch_scenes):
                    batch = candidate
                    break
                last_error = last_error or "필수 필드·표현 개수·장면 키 형식 오류"
            prompt += (
                "\n\n★ 이전 결과가 형식 검사를 통과하지 못했다. 각 장면 expressions는 반드시 "
                "6~10개이고 모든 필수 필드가 비어 있지 않아야 하며, 지정한 키만 빠짐없이 넣어 전체 JSON을 다시 출력하라."
            )
            if attempt < 2:
                print(f"   ↻ 학습카드 묶음 {start // batch_size + 1} 재시도 {attempt + 2}/3")
        if batch is None:
            raise RuntimeError(f"카드 묶음 {start // batch_size + 1} 3회 실패: {last_error}")
        all_cards.update(batch)
        with open(partial_path, "w", encoding="utf-8") as file:
            json.dump(all_cards, file, ensure_ascii=False, indent=2)
        print(f"   🗂️ 학습카드 묶음 {start // batch_size + 1}/{(len(scene_keys) + batch_size - 1) // batch_size} 완료")
    try:
        os.remove(partial_path)
    except FileNotFoundError:
        pass
    return all_cards


def parse_response(body):
    """Claude 응답에서 부제목·줄거리·장면별 설명을 분리한다."""
    subtitle_match = re.search(
        r"## 추천 부제목\s*\n([^\n]+)", body
    )
    subtitle = clean_subtitle(subtitle_match.group(1)) if subtitle_match else ""
    overview_match = re.search(
        r"## 전체 줄거리\s*\n(.*?)(?=\n##|\Z)", body, re.S
    )
    overview = overview_match.group(1).strip() if overview_match else body.strip()

    descriptions = {}
    for m in re.finditer(r"\[(\d+)편\s*장면\s*(\d+)\]\s*(.+)", body):
        part, scene, desc = int(m.group(1)), int(m.group(2)), m.group(3).strip()
        descriptions[(part, scene)] = desc
    corrections = {}
    correction_match = re.search(
        r"## 번역 교정 JSON\s*\n(\{.*?\})\s*(?=\n##)", body, re.S
    )
    if correction_match:
        try:
            parsed = json.loads(correction_match.group(1))
            corrections = {
                str(key): str(value).strip() for key, value in parsed.items()
                if re.fullmatch(r"L\d{4,}", str(key)) and str(value).strip()
            }
        except (json.JSONDecodeError, AttributeError):
            corrections = {}
    cards = {}
    card_match = re.search(r"## 학습 카드 JSON\s*\n(\{.*\})\s*$", body, re.S)
    if card_match:
        try:
            cards = json.loads(card_match.group(1))
        except json.JSONDecodeError:
            cards = {}
    return subtitle, overview, descriptions, cards, corrections


def apply_translation_corrections(book_dir, lines, corrections):
    """요약 호출이 발견한 의미 오역만 JSONL과 영구 메모리에 반영한다."""
    memory_path = os.path.join(os.path.dirname(__file__), "translation_memory.json")
    try:
        memory = json.load(open(memory_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        memory = {}
    changed = 0
    for line_id, corrected in corrections.items():
        index = int(line_id[1:]) - 1
        if not 0 <= index < len(lines) or not re.search(r"[가-힣]", corrected):
            continue
        record = lines[index]
        if corrected != record.get("ko"):
            record["ko"] = corrected
            memory[record.get("ja", "").strip()] = corrected
            changed += 1
    if changed:
        by_part = {}
        for record in lines:
            by_part.setdefault(int(record["part"]), []).append(record)
        for part, records in by_part.items():
            path = os.path.join(book_dir, f"transcript_part{part}.jsonl")
            with open(path, "w", encoding="utf-8") as file:
                for record in records:
                    file.write(json.dumps(record, ensure_ascii=False) + "\n")
        with open(memory_path, "w", encoding="utf-8") as file:
            json.dump(memory, file, ensure_ascii=False, indent=2)
            file.write("\n")
    return changed


def valid_cards(cards, expected_scenes):
    expected_keys = {f"{part}-{scene}" for part, scene in expected_scenes}
    if set(cards) != expected_keys:
        return False
    for card in cards.values():
        expressions = card.get("expressions", []) if isinstance(card, dict) else []
        if not 6 <= len(expressions) <= 10:
            return False
        if (
            not isinstance(card.get("vocabulary"), list)
            or not card["vocabulary"]
            or not isinstance(card.get("grammar"), list)
            or not card["grammar"]
            or not isinstance(card.get("shadowing"), dict)
        ):
            return False
        if any(
            not isinstance(item, dict)
            or not all(item.get(field) for field in ("ja", "reading", "ko"))
            for item in expressions
        ):
            return False
        if not all(card["shadowing"].get(field) for field in ("ja", "reading", "ko")):
            return False
        for word in card["vocabulary"]:
            if not isinstance(word, dict) or not all(word.get(field) for field in ("ja", "reading", "ko")):
                return False
            if re.search(r"[一-鿿]", word.get("ja", "")) and not all(
                word.get(field) for field in ("reading", "hanja_sound", "hanja_hun")
            ):
                return False
    return True


def update_cover(book_dir, base_name, subtitle):
    """기존 세로 표지 하단을 원본명+부제목으로 다시 그린다."""
    if not subtitle:
        return
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("⚠️ Pillow가 없어 표지 부제목은 생략합니다.")
        return
    cover = os.path.join(book_dir, "cover.jpg")
    original = os.path.join(book_dir, "cover_original.jpg")
    if not os.path.isfile(cover):
        return
    if not os.path.isfile(original):
        shutil.copy2(cover, original)

    def fitted_font(draw, text, max_size, min_size, max_width, font_path):
        for size in range(max_size, min_size - 1, -2):
            font = ImageFont.truetype(font_path, size)
            if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
                return font
        return ImageFont.truetype(font_path, min_size)

    font_path = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
    try:
        with Image.open(original) as source:
            image = source.convert("RGB")
        draw = ImageDraw.Draw(image, "RGBA")
        width, height = image.size
        box_top = int(height * 0.76)
        draw.rectangle((0, box_top, width, height), fill=(0, 0, 0, 178))
        title_font = fitted_font(draw, base_name, 82, 42, width - 100, font_path)
        subtitle_font = fitted_font(draw, subtitle, 48, 30, width - 100, font_path)
        title_box = draw.textbbox((0, 0), base_name, font=title_font)
        subtitle_box = draw.textbbox((0, 0), subtitle, font=subtitle_font)
        draw.text(((width - (title_box[2] - title_box[0])) / 2, box_top + 45),
                  base_name, font=title_font, fill=(255, 255, 255, 255))
        draw.text(((width - (subtitle_box[2] - subtitle_box[0])) / 2, box_top + 145),
                  subtitle, font=subtitle_font, fill=(245, 200, 66, 255))
        image.save(cover, "JPEG", quality=92, optimize=True)
    except Exception as exc:
        print(f"⚠️ 표지 부제목 반영 실패: {exc}")


def inject_scene_descriptions(book_dir, descriptions):
    """transcript_part{N}.md 안의 각 "## 장면 M {.scene ...}" 헤더 + 대표 이미지
    다음, 대사가 시작되기 전에 그 장면의 한 줄 설명을 끼워 넣는다."""
    scene_header_re = re.compile(
        r'(^## 장면 (\d+) \{[^\n]*\.scene[^\n]*\}\n\n'
        r'<img class="scene-thumb"[^\n]*/>\n\n)',
        re.M,
    )
    existing_description_re = re.compile(
        r'<p class="scene-desc ibooks-dark-theme-use-custom-text-color">'
        r'.*?</p>\n\n',
        re.S,
    )
    for md_path in sorted(glob.glob(os.path.join(book_dir, "transcript_part*.md"))):
        part_match = re.search(r"transcript_part(\d+)\.md$", os.path.basename(md_path))
        if not part_match:
            continue
        part_num = int(part_match.group(1))
        with open(md_path, encoding="utf-8") as f:
            content = f.read()
        # 재실행 시 기존 설명을 먼저 제거해야 같은 문단이 계속 누적되지 않는다.
        content = existing_description_re.sub("", content)

        def _replace(m):
            scene_num = int(m.group(2))
            desc = descriptions.get((part_num, scene_num))
            if not desc:
                return m.group(1)
            return (
                m.group(1)
                + f'<p class="scene-desc ibooks-dark-theme-use-custom-text-color">'
                f'{html.escape(desc)}</p>\n\n'
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
    existing_subtitle = load_book_subtitle(book_dir)

    lines = load_lines(book_dir)
    if not lines:
        sys.exit(f"❌ transcript_part*.jsonl이 없습니다: {book_dir}")

    expected_scenes = {(int(rec["part"]), int(rec["scene"])) for rec in lines}
    use_batched_cards = len(expected_scenes) > 12
    prompt = build_prompt(
        base_name, lines, existing_subtitle, include_cards=not use_batched_cards
    )

    # 모델이 가끔 "[N편 장면 M]" 태그 형식을 안 지키고 다른
    # 방식(예: "장면 M:")으로 답하는 경우가 있어(실제로 DLDSS-217에서 발생),
    # 형식이 하나도 안 지켜지면 "태그 형식을 반드시 지키라"고 한 번 더 강조해서
    # 재시도한다.
    generated_subtitle, overview, descriptions, cards, corrections = "", None, {}, {}, {}
    for attempt in range(2):
        result = subprocess.run(
            [
                "/opt/homebrew/bin/codex", "exec",
                "--ephemeral", "--sandbox", "read-only",
                "--skip-git-repo-check", "-C", book_dir, "-",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=600,
        )
        body = result.stdout.strip()
        if result.returncode != 0 or not body:
            sys.exit(f"❌ Codex 요약 생성 실패({result.returncode}): {result.stderr.strip()}")

        generated_subtitle, overview, descriptions, cards, corrections = parse_response(body)
        missing_scenes = expected_scenes - set(descriptions)
        cards_ready = use_batched_cards or valid_cards(cards, expected_scenes)
        if not missing_scenes and (existing_subtitle or generated_subtitle) and cards_ready:
            descriptions = {
                key: descriptions[key] for key in sorted(expected_scenes)
            }
            break
        retry_problem = (
            "부제목 또는 장면 설명이 빠졌다"
            if use_batched_cards
            else "부제목·장면 설명 또는 유효한 학습 카드 JSON이 빠졌다"
        )
        prompt += (
            f"\n\n★ 방금 응답에서 {retry_problem}. "
            "다음 태그를 모두 써라: "
            + ", ".join(
                f"[{part}편 장면 {scene}]"
                for part, scene in sorted(missing_scenes)
            )
            + ". 반드시 입력의 모든 대괄호 태그를 빠짐없이 써서 전체 결과를 다시 작성해라."
        )

    missing_scenes = expected_scenes - set(descriptions)
    if missing_scenes:
        sys.exit(
            "❌ 장면별 설명이 일부 누락되었습니다(재시도 포함): "
            + ", ".join(
                f"{part}편 장면 {scene}"
                for part, scene in sorted(missing_scenes)
            )
        )
    corrected_count = apply_translation_corrections(book_dir, lines, corrections)
    if use_batched_cards:
        print(f"🗂️ 장면 {len(expected_scenes)}개 — 학습카드를 6장면씩 나눠 생성합니다.")
        try:
            cards = generate_cards_batched(book_dir, base_name, lines)
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            sys.exit(f"❌ 분할 학습 카드 생성 실패: {exc}")
    if not valid_cards(cards, expected_scenes):
        sys.exit("❌ 장면별 학습 카드가 누락됐거나 형식이 잘못되었습니다(재시도 포함).")

    subtitle = existing_subtitle or generated_subtitle
    if not subtitle:
        sys.exit("❌ 내용 기반 추천 부제목이 누락되었습니다(재시도 포함).")
    subtitle_path = os.path.join(book_dir, "BOOK_SUBTITLE.txt")
    if not existing_subtitle:
        with open(subtitle_path, "w", encoding="utf-8") as f:
            f.write(subtitle + "\n")

    # 다른 스크립트(오디오북 챕터 제목 등)가 재사용할 수 있게 저장해둔다.
    with open(os.path.join(book_dir, "scene_descriptions.json"), "w", encoding="utf-8") as f:
        json.dump(
            {f"{part}-{scene}": desc for (part, scene), desc in descriptions.items()},
            f, ensure_ascii=False, indent=2,
        )
    with open(os.path.join(book_dir, "scene_study_cards.json"), "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)

    with open(summary_path, "w", encoding="utf-8") as f:
        # {.ibooks-dark-theme-use-custom-text-color}: Apple Books가 다크 테마에서
        # h1 커스텀 색상을 흰색으로 강제 대체하지 않도록 하는 공식 클래스.
        f.write(
            f"# {display_title(book_dir, base_name)} 줄거리 {{.ibooks-dark-theme-use-custom-text-color}}\n\n"
            f"## 전체 줄거리\n\n{overview}\n"
        )

    inject_scene_descriptions(book_dir, descriptions)
    update_cover(book_dir, base_name, subtitle)

    print(f"✅ 부제목 확정: {base_name} — {subtitle}")
    print(f"✅ 요약 호출에서 의미 오역 선택 교정: {corrected_count}문장")
    print(f"✅ 전체 줄거리 + 장면별 학습 카드 {len(cards)}개 생성 완료: {summary_path}")


if __name__ == "__main__":
    main()
