#!/usr/bin/env python3
"""Edge/OpenAI TTS로 미연시 일본어 대사를 중단·재개 가능한 MP3 캐시로 생성한다."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

CHATAPP_DIR = Path(__file__).resolve().parents[1]
if str(CHATAPP_DIR) not in sys.path:
    sys.path.insert(0, str(CHATAPP_DIR))

from server import dating_audio  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--delay", type=float, default=0.15)
    parser.add_argument("--provider", choices=("edge", "openai"), default="edge")
    args = parser.parse_args()

    catalog = dating_audio.build_catalog()
    if args.limit is not None:
        catalog = catalog[:max(0, args.limit)]
    output_dir = CHATAPP_DIR / "dating_sim_web" / "audio"
    existing = {}
    manifest_path = output_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8")).get("clips", {})
            if isinstance(loaded, dict) and all(isinstance(value, dict) for value in loaded.values()):
                existing = loaded
        except (OSError, json.JSONDecodeError):
            existing = {}

    print(f"미연시 일본어 음성 {len(catalog)}개를 확인합니다.", flush=True)
    if args.dry_run:
        total_chars = sum(len(text) for _role, text in catalog)
        print(f"중복 제거 후 {len(catalog)}개, 일본어 {total_chars}자", flush=True)
        for role in ("female", "male"):
            count = sum(1 for item_role, _text in catalog if item_role == role)
            voices = dating_audio.EDGE_VOICES if args.provider == "edge" else dating_audio.VOICES
            print(f"{role}: {count}개 · {voices[role]}", flush=True)
        return 0

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if args.provider == "openai" and not api_key:
        print("OPENAI_API_KEY가 설정되지 않았습니다.", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    clips = {"female": dict(existing.get("female", {})), "male": dict(existing.get("male", {}))}
    for index, (role, text) in enumerate(catalog, 1):
        filename = dating_audio.clip_name(role, text)
        target = output_dir / filename
        if target.is_file() and target.stat().st_size > 0:
            clips[role][text] = f"/dating-sim/audio/{filename}"
            print(f"[{index}/{len(catalog)}] {role} 기존 파일 사용", flush=True)
            continue
        try:
            audio = (
                dating_audio.request_edge_speech(role, text)
                if args.provider == "edge"
                else dating_audio.request_speech(api_key, role, text)
            )
        except RuntimeError as error:
            dating_audio.write_manifest(output_dir, clips, provider=args.provider)
            print(str(error), file=sys.stderr, flush=True)
            completed = sum(len(items) for items in clips.values())
            print(f"{completed}개까지 저장했습니다. 다시 실행하면 이어집니다.", file=sys.stderr, flush=True)
            return 1
        temporary = target.with_suffix(".mp3.tmp")
        temporary.write_bytes(audio)
        temporary.replace(target)
        clips[role][text] = f"/dating-sim/audio/{filename}"
        dating_audio.write_manifest(output_dir, clips, provider=args.provider)
        print(f"[{index}/{len(catalog)}] {role} 생성 완료 · {len(audio) / 1024:.0f} KiB", flush=True)
        if args.delay > 0:
            time.sleep(args.delay)
    dating_audio.write_manifest(output_dir, clips, provider=args.provider)
    print(f"전체 {len(catalog)}개 생성 완료", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
