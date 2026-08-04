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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book_dir")
    parser.add_argument("--dry-run", action="store_true", help="탐지만 하고 파일과 메모리를 바꾸지 않음")
    parser.add_argument("--no-ai", action="store_true", help="영구 메모리만 적용하고 Codex/Claude 검수는 생략")
    parser.add_argument("--max-review", type=int, default=int(os.environ.get("JP_TRANSLATION_REVIEW_MAX", "60")))
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
    candidates = ranked[:max(0, args.max_review)]
    print(
        f"🔎 번역 품질 검사: 전체 {len(rows)}문장 · 메모리 적용 {memory_hits}문장 · "
        f"이상 후보 {len(ranked)}문장 · 이번 검수 {len(candidates)}문장"
    )
    if args.dry_run:
        for item in candidates:
            print(f"  [{item['id']}] {item['reasons']} | {item['ja']} → {item['ko']}")
        return

    changed = 0
    if candidates and not args.no_ai:
        try:
            refined = codex_refine(book_dir, candidates)
        except Exception as exc:
            print(f"⚠️ Codex/Claude 선택 검수 모두 실패 — Google 번역 유지: {exc}")
            refined = {}
        for item in candidates:
            corrected = refined.get(item["id"], "")
            if corrected and KO_RE.search(corrected) and not JP_RE.search(corrected):
                row = rows[item["index"]]
                if corrected != row["data"].get("ko"):
                    row["data"]["ko"] = corrected
                    memory[item["ja"].strip()] = corrected
                    changed += 1
    save_rows(rows)
    MEMORY_PATH.write_text(
        json.dumps(memory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"✅ 선택 번역 보정 완료: {changed}문장 수정 · 영구 메모리 {len(memory)}개")


if __name__ == "__main__":
    main()
