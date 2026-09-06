#!/usr/bin/env python3
"""av완성작의 학습카드 없는 낭독판을 전부 찾아 recover_study_cards_from_epub.py →
generate_summary.py → finalize_japanese_book.py → build_readaloud_epub.py를 순서대로
돌리고, 성공하면 av완성작의 기존 파일을 바로 교체한다.

★ 2026-09-06: "다 되면 av완성작에 바로 교체해줘" 요청 — SNOS-311로 검증한 EPUB 역추출
복구(recover_study_cards_from_epub.py)를 나머지 회차 전체에 순회 적용한다. 회차 하나가
실패해도 나머지는 계속 진행하고, 결과는 backfill_log.txt에 전부 남긴다.
"""

import glob
import os
import re
import shutil
import subprocess
import sys
import unicodedata

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_DIR = os.path.join(SCRIPT_DIR, "library")
COMPLETED_DIR = "/Users/forrestdpark/Desktop/BlogImage/av완성작"
PY = "/opt/anaconda3/bin/python3"
LOG_PATH = os.path.join(SCRIPT_DIR, "backfill_log.txt")


def _has_valid_cards(book_dir):
    cards_path = os.path.join(book_dir, "scene_study_cards.json")
    if not os.path.isfile(cards_path) or os.path.getsize(cards_path) == 0:
        return False
    try:
        import json
        with open(cards_path, encoding="utf-8") as f:
            data = json.load(f)
        return isinstance(data, dict) and bool(data)
    except (OSError, ValueError):
        return False


def _epub_code_and_subtitle(epub_path):
    # ★ 2026-09-06: macOS NFD 파일명 정규화 문제 — recover_study_cards_from_epub.py
    # 참고 주석과 동일한 이유로 NFC 정규화 후 처리한다.
    base = unicodedata.normalize("NFC", os.path.basename(epub_path))
    base = re.sub(r"_낭독판\.epub$", "", base)
    if " — " in base:
        code, subtitle = base.split(" — ", 1)
        return code.strip(), subtitle.strip()
    return base.strip(), ""


def _folder_matches_subtitle(folder_path, subtitle):
    """MIDA-764·PRED-870처럼 같은 코드로 부제만 다른 회차가 여러 개 있을 때,
    코드 접두사만으로는 어느 폴더가 이 epub의 것인지 구분이 안 된다 — 폴더명에
    부제가 그대로 들어있거나(recover 스크립트의 충돌 회피 네이밍) BOOK_SUBTITLE.txt
    내용이 일치할 때만 "이 epub은 이미 처리됐다"고 판단한다."""
    if not subtitle:
        return True
    folder_name = os.path.basename(folder_path)
    if subtitle in folder_name:
        return True
    subtitle_file = os.path.join(folder_path, "BOOK_SUBTITLE.txt")
    if os.path.isfile(subtitle_file):
        try:
            return open(subtitle_file, encoding="utf-8").read().strip() == subtitle
        except OSError:
            return False
    return False


def find_missing():
    """학습카드(scene_study_cards.json)가 없는 낭독판을 찾는다.
    ★ 배치가 중간에 죽었다가 재실행될 때, recover 단계는 끝났지만
    generate_summary.py가 못 끝난 폴더(폴더는 있는데 카드는 없음)를
    "이미 있으니 스킵"해버리면 영원히 완성 못 한다 — 폴더 존재 여부가
    아니라 카드 유무로 판정해야 재실행이 실제로 이어서 처리한다."""
    existing = os.listdir(LIBRARY_DIR) if os.path.isdir(LIBRARY_DIR) else []
    missing = []
    for epub in sorted(glob.glob(os.path.join(COMPLETED_DIR, "*_낭독판.epub"))):
        code, subtitle = _epub_code_and_subtitle(epub)
        candidates = [
            d for d in existing
            if (d == code or d.startswith(code)) and _folder_matches_subtitle(os.path.join(LIBRARY_DIR, d), subtitle)
        ]
        if not candidates:
            missing.append(epub)
            continue
        if not any(_has_valid_cards(os.path.join(LIBRARY_DIR, d)) for d in candidates):
            missing.append(epub)
    return missing


def run(cmd, log):
    log.write(f"$ {' '.join(cmd)}\n")
    log.flush()
    result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
    log.flush()
    return result.returncode == 0


def run_capture(cmd, log):
    log.write(f"$ {' '.join(cmd)}\n")
    log.flush()
    result = subprocess.run(cmd, capture_output=True, text=True)
    log.write(result.stdout)
    log.write(result.stderr)
    log.flush()
    return result.returncode == 0, result.stdout


BOOK_DIR_LINE_RE = re.compile(r"^✅ (.+?) 복구 완료 —")


def _existing_transcript_dir(epub_path):
    """이전 실행이 recover까지는 끝내고 generate_summary.py 도중 죽은 경우
    (대사 원재료는 있는데 학습카드는 없음) 그 폴더를 그대로 재사용한다 —
    recover_study_cards_from_epub.py는 폴더가 이미 있으면 --force 없이는
    실패하므로, 재시도 때마다 매번 실패로 오판되는 걸 막는다."""
    code, subtitle = _epub_code_and_subtitle(epub_path)
    existing = os.listdir(LIBRARY_DIR) if os.path.isdir(LIBRARY_DIR) else []
    for d in existing:
        if not (d == code or d.startswith(code)):
            continue
        folder_path = os.path.join(LIBRARY_DIR, d)
        if not _folder_matches_subtitle(folder_path, subtitle):
            continue
        if glob.glob(os.path.join(folder_path, "transcript_part*.jsonl")):
            return folder_path
    return None


def process_one(epub_path, log):
    log.write(f"\n===== {os.path.basename(epub_path)} =====\n")

    book_dir = _existing_transcript_dir(epub_path)
    if book_dir:
        log.write(f"♻️  이전 실행에서 복구된 원재료 재사용: {book_dir}\n")
    else:
        # ★ 같은 코드(MIDA-764, PRED-870 등)로 부제만 다른 회차가 여러 개 있을
        # 수 있어, recover_study_cards_from_epub.py가 실제로 만든 폴더 경로를
        # 그 스크립트 stdout에서 그대로 읽는다(코드만으로 추측하면 이미 배치
        # 안에서 먼저 처리된 동일 코드 폴더와 충돌할 수 있음).
        ok, stdout = run_capture([PY, os.path.join(SCRIPT_DIR, "recover_study_cards_from_epub.py"), epub_path], log)
        if not ok:
            log.write("❌ 대사 복구 실패\n")
            return False
        for line in stdout.splitlines():
            m = BOOK_DIR_LINE_RE.match(line)
            if m:
                book_dir = m.group(1)
                break
    if not book_dir or not os.path.isdir(book_dir):
        log.write("❌ 복구된 library 폴더 경로를 찾지 못함\n")
        return False

    if not run([PY, os.path.join(SCRIPT_DIR, "generate_summary.py"), book_dir], log):
        log.write("❌ 학습카드 생성 실패(쿼터 소진 등) — 원재료는 보존됨, 다음 실행에서 재시도 가능\n")
        return False

    if not run([PY, os.path.join(SCRIPT_DIR, "finalize_japanese_book.py"), book_dir], log):
        log.write("❌ 일반 EPUB 재빌드 실패\n")
        return False

    folder_name = os.path.basename(book_dir)
    tmp_out = f"/tmp/_recover_{folder_name}_낭독판.epub"
    if not run([PY, os.path.join(SCRIPT_DIR, "build_readaloud_epub.py"), book_dir, "--output", tmp_out], log):
        log.write("❌ 낭독판 EPUB 재생성 실패\n")
        return False

    title_proc = subprocess.run(
        [PY, os.path.join(SCRIPT_DIR, "book_title.py"), book_dir, "--base-name", folder_name, "--filename"],
        capture_output=True, text=True,
    )
    display_title = title_proc.stdout.strip() or folder_name
    final_name = f"{display_title}_낭독판.epub"

    # ★ 같은 코드로 회차가 여러 개인 경우(MIDA-764, PRED-870 등 부제만 다른
    # 별개 작품)가 있어 "{code}*_낭독판.epub" 같은 prefix glob으로 지우면
    # 아직 처리 안 된 다른 회차까지 같이 지워질 위험이 있다. 지금 실제로
    # 대체하는 그 파일(epub_path) 하나만 정확히 지운다.
    if os.path.abspath(epub_path) != os.path.abspath(os.path.join(COMPLETED_DIR, final_name)):
        os.remove(epub_path)
    shutil.move(tmp_out, os.path.join(COMPLETED_DIR, final_name))
    log.write(f"✅ av완성작 교체 완료: {final_name}\n")
    return True


def main():
    missing = find_missing()
    ok, fail = [], []
    with open(LOG_PATH, "a", encoding="utf-8") as log:
        log.write(f"\n\n########## 일괄 복구 시작 — 대상 {len(missing)}개 ##########\n")
        for epub in missing:
            try:
                if process_one(epub, log):
                    ok.append(epub)
                else:
                    fail.append(epub)
            except Exception as exc:
                log.write(f"❌ 예외 발생: {exc}\n")
                fail.append(epub)
        log.write(f"########## 완료 — 성공 {len(ok)}개, 실패 {len(fail)}개 ##########\n")
        if fail:
            log.write("실패 목록:\n" + "\n".join(f"  - {os.path.basename(f)}" for f in fail) + "\n")

    print(f"성공 {len(ok)}개, 실패 {len(fail)}개 — 로그: {LOG_PATH}")
    for f in fail:
        print(f"  실패: {os.path.basename(f)}")


if __name__ == "__main__":
    sys.exit(main())
