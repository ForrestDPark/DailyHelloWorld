#!/usr/bin/env python3
"""Google 일본어→한국어 결과 중 이상 가능성이 높은 문장만 Codex(실패 시 Claude)로 보정한다."""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from ai_exec import run_ai_exec

SCRIPT_DIR = Path(__file__).resolve().parent
MEMORY_PATH = SCRIPT_DIR / "translation_memory.json"
JP_RE = re.compile(r"[ぁ-ゖァ-ヺ一-鿿々]")
KO_RE = re.compile(r"[가-힣]")
KNOWN_BAD = (
    "손이 식", "눈이 식", "금은 음경", "청소합니다", "입고 있지",
    "무엇을 사러 가", "취소량", "문장으로 헤이", "구아, 구아",
    "냉방을 놓아", "친친", "선 무", "니모 츠",
)


def load_records(book_dir):
    rows = []
    for path in sorted(book_dir.glob("transcript_part*.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if line.strip():
                rows.append({"path": path, "line": line_number, "data": json.loads(line)})
    return rows


def anomaly_score(ja, ko):
    ja, ko = (ja or "").strip(), (ko or "").strip()
    score, reasons = 0, []
    if not ko or ko == "[번역 실패]":
        score += 100; reasons.append("번역 실패")
    if JP_RE.search(ko):
        score += 8; reasons.append("한국어에 일본어 잔존")
    if ja and re.sub(r"\W", "", ja) == re.sub(r"\W", "", ko):
        score += 8; reasons.append("원문과 동일")
    hits = [phrase for phrase in KNOWN_BAD if phrase in ko]
    if hits:
        score += 7; reasons.append("누적 오역 패턴: " + ", ".join(hits))
    ja_len = max(1, len(re.sub(r"\s", "", ja)))
    ko_len = len(re.sub(r"\s", "", ko))
    if ja_len >= 8 and ko_len <= 2:
        score += 4; reasons.append("번역이 지나치게 짧음")
    if ja_len >= 4 and ko_len > ja_len * 4 + 15:
        score += 3; reasons.append("번역이 지나치게 김")
    if ja_len >= 5 and not KO_RE.search(ko):
        score += 6; reasons.append("한글 없음")
    if re.search(r"(.)\1{5,}", ko):
        score += 3; reasons.append("과도한 반복")
    return score, reasons


def load_memory():
    try:
        data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_rows(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["path"], []).append(row)
    for path, items in grouped.items():
        items.sort(key=lambda item: item["line"])
        path.write_text(
            "".join(json.dumps(item["data"], ensure_ascii=False) + "\n" for item in items),
            encoding="utf-8",
        )


def save_memory(memory):
    """중간 종료에도 사전 JSON이 반쪽만 기록되지 않도록 원자적으로 교체한다."""
    temp_path = MEMORY_PATH.with_suffix(MEMORY_PATH.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(memory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temp_path, MEMORY_PATH)


def codex_refine(book_dir, candidates):
    payload = []
    for item in candidates:
        payload.append({
            "id": item["id"], "reason": item["reasons"],
            "previous_ja": item["previous"], "ja": item["ja"],
            "next_ja": item["next"], "google_ko": item["ko"],
        })
    prompt = f"""일본어 영상 자막의 Google 한국어 번역 중 코드가 이상 가능성이 높다고 고른 문장만 검수한다.
앞뒤 일본어는 문맥 참고용이며 번역 대상은 ja 하나뿐이다. 원문의 의미·말투를 자연스러운 한국어로 옮기되
내용을 추가하거나 순화하거나 설명하지 마라. Google 번역이 이미 자연스럽고 맞으면 그대로 유지한다.
음성 인식 원문 자체가 불완전하면 문맥상 확실한 범위만 자연스럽게 고친다.
반드시 설명이나 마크다운 없이 {{"문장ID":"교정 한국어"}} JSON 객체 하나만 출력하라.

입력:
{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}
"""
    stdout, engine = run_ai_exec(prompt, book_dir, timeout=600)
    match = re.search(r"\{.*\}", stdout, re.S)
    if not match:
        raise RuntimeError(f"{engine} 응답에서 JSON 객체를 찾지 못함")
    data = json.loads(match.group(0))
    return {str(key): str(value).strip() for key, value in data.items() if str(value).strip()}


def codex_refine_with_retry(book_dir, batch):
    """★ 2026-09-08: "JSON 객체를 찾지 못함" 배치 실패(40개 단위로 한꺼번에
    버려짐)를 실제로 확인 — Claude가 큰 배치에서 응답을 도중에 끊거나 설명을
    덧붙여 JSON 파싱이 깨지는 사례가 있었다. 실패하면 배치를 절반으로 나눠
    재시도한다 — 배치가 작아질수록 한 번에 요청하는 출력 길이가 줄어 성공률이
    올라가고, 정말 안 되는 문장 하나만 남기고 나머지는 구제할 수 있다."""
    try:
        return codex_refine(book_dir, batch)
    except Exception as exc:
        if len(batch) <= 1:
            raise
        mid = len(batch) // 2
        refined = {}
        errors = []
        for half in (batch[:mid], batch[mid:]):
            try:
                refined.update(codex_refine_with_retry(book_dir, half))
            except Exception as half_exc:
                errors.append(str(half_exc))
        if errors and not refined:
            raise RuntimeError(f"{exc} (분할 재시도도 실패: {'; '.join(errors)})")
        return refined


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book_dir")
    parser.add_argument("--dry-run", action="store_true", help="탐지만 하고 파일과 메모리를 바꾸지 않음")
    parser.add_argument("--no-ai", action="store_true", help="영구 메모리만 적용하고 Codex/Claude 검수는 생략")
    parser.add_argument("--max-review", type=int, default=int(os.environ.get("JP_TRANSLATION_REVIEW_MAX", "60")),
                        help="번역 실패를 제외한 일반 이상 후보의 최대 검수 수")
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("JP_TRANSLATION_REVIEW_BATCH", "40")))
    args = parser.parse_args()

    book_dir = Path(args.book_dir).resolve()
    rows = load_records(book_dir)
    if not rows:
        sys.exit(f"❌ 대사 JSONL이 없습니다: {book_dir}")
    memory = load_memory()
    memory_hits = 0
    for row in rows:
        ja = row["data"].get("ja", "").strip()
        if ja in memory and memory[ja] and row["data"].get("ko") != memory[ja]:
            row["data"]["ko"] = memory[ja]
            memory_hits += 1

    ranked = []
    for index, row in enumerate(rows):
        ja, ko = row["data"].get("ja", ""), row["data"].get("ko", "")
        score, reasons = anomaly_score(ja, ko)
        if score:
            ranked.append({
                "id": str(index), "index": index, "score": score, "reasons": reasons,
                "ja": ja, "ko": ko,
                "previous": rows[index - 1]["data"].get("ja", "") if index else "",
                "next": rows[index + 1]["data"].get("ja", "") if index + 1 < len(rows) else "",
            })
    ranked.sort(key=lambda item: (-item["score"], item["index"]))
    # 번역 실패는 일반 품질 후보 한도와 무관하게 전부 복구한다. 실패가 60개를
    # 넘었다는 이유로 뒤쪽 문장을 그대로 EPUB에 흘려보내지 않도록 한다.
    failures = [item for item in ranked if "번역 실패" in item["reasons"]]
    other_candidates = [item for item in ranked if "번역 실패" not in item["reasons"]]
    candidates = failures + other_candidates[:max(0, args.max_review)]
    print(
        f"🔎 번역 품질 검사: 전체 {len(rows)}문장 · 메모리 적용 {memory_hits}문장 · "
        f"이상 후보 {len(ranked)}문장 · 번역 실패 {len(failures)}문장 · "
        f"이번 검수 {len(candidates)}문장"
    )
    if args.dry_run:
        for item in candidates:
            print(f"  [{item['id']}] {item['reasons']} | {item['ja']} → {item['ko']}")
        return

    changed = 0
    if candidates and not args.no_ai:
        refined = {}
        batch_size = max(1, args.batch_size)
        for start in range(0, len(candidates), batch_size):
            batch = candidates[start:start + batch_size]
            try:
                refined.update(codex_refine_with_retry(book_dir, batch))
            except Exception as exc:
                print(
                    f"⚠️ Codex/Claude 선택 검수 배치 실패 "
                    f"({start + 1}~{start + len(batch)}): {exc}"
                )
        for item in candidates:
            corrected = refined.get(item["id"], "")
            if corrected and KO_RE.search(corrected) and not JP_RE.search(corrected):
                row = rows[item["index"]]
                if corrected != row["data"].get("ko"):
                    row["data"]["ko"] = corrected
                    changed += 1
                # 변경 여부와 관계없이 검수 통과 결과를 영구 사전에 올린다.
                # 다음 작품에서는 Google 호출 전에 이 값을 바로 재사용한다.
                memory_key = item["ja"].strip()
                if memory_key:
                    memory[memory_key] = corrected
    save_rows(rows)
    save_memory(memory)
    remaining_failures = sum(
        1 for row in rows if row["data"].get("ko", "").strip() in ("", "[번역 실패]")
    )
    print(
        f"✅ 선택 번역 보정 완료: {changed}문장 수정 · 영구 메모리 {len(memory)}개 · "
        f"남은 번역 실패 {remaining_failures}문장"
    )
    if remaining_failures:
        sys.exit(f"❌ 번역 실패 {remaining_failures}문장이 남아 최종 EPUB 생성을 중단합니다.")


if __name__ == "__main__":
    main()
