#!/usr/bin/env python3
"""Build the browser-side Japanese kanji reading index from KANJIDIC2."""

from __future__ import annotations

import argparse
import gzip
import json
import xml.etree.ElementTree as ET
from pathlib import Path


CURATED_KOREAN_MEANINGS = {
    "既": "이미·다하다", "教": "가르치다·가르침", "娯": "즐기다·즐겁게 하다",
    "込": "들어가다·넣다", "咲": "피다·웃다", "尚": "오히려·높이다",
    "清": "맑다·깨끗하다", "青": "푸르다", "挿": "꽂다·끼우다",
    "捗": "일이 진척되다", "働": "일하다·움직이다", "枠": "틀·테두리",
    "丼": "덮밥·우물", "毀": "헐다·무너뜨리다", "惧": "두려워하다",
}


def build(
    source: Path,
    korean_source: Path | None = None,
    japanese_variants_source: Path | None = None,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    opener = gzip.open if source.suffix == ".gz" else open
    with opener(source, "rb") as stream:
        root = ET.parse(stream).getroot()

    header = root.find("header")
    metadata = {
        "source": "KANJIDIC2",
        "database_version": header.findtext("database_version", "") if header is not None else "",
        "date_of_creation": header.findtext("date_of_creation", "") if header is not None else "",
        "license": "CC BY-SA 4.0",
        "project_url": "https://www.edrdg.org/wiki/KANJIDIC_Project.html",
    }
    code_to_literal: dict[tuple[str, str], str] = {}
    for character in root.findall("character"):
        literal = character.findtext("literal", "")
        for code in character.findall("./codepoint/cp_value"):
            if literal and code.text:
                code_to_literal[(code.get("cp_type", ""), code.text.lower())] = literal
    variants: dict[str, list[str]] = {}
    for character in root.findall("character"):
        literal = character.findtext("literal", "")
        if not literal:
            continue
        targets: list[str] = []
        for variant in character.findall("./misc/variant"):
            kind = variant.get("var_type", "")
            value = (variant.text or "").lower()
            target = chr(int(value, 16)) if kind == "ucs" and value else code_to_literal.get((kind, value))
            if target and target not in targets:
                targets.append(target)
        variants[literal] = targets
    if japanese_variants_source:
        for line in japanese_variants_source.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            literal, separator, target_text = line.partition("\t")
            if not separator or len(literal) != 1:
                continue
            targets = variants.setdefault(literal, [])
            for target in target_text.split():
                if len(target) == 1 and target != literal and target not in targets:
                    targets.append(target)
    entries: dict[str, dict[str, object]] = {}
    for character in root.findall("character"):
        literal = character.findtext("literal", "")
        if not literal:
            continue
        on: list[str] = []
        kun: list[str] = []
        for reading in character.findall("./reading_meaning/rmgroup/reading"):
            value = (reading.text or "").strip()
            kind = reading.get("r_type")
            if value and kind == "ja_on" and value not in on:
                on.append(value)
            elif value and kind == "ja_kun" and value not in kun:
                kun.append(value)
        if on or kun:
            entries[literal] = {"on": on, "kun": kun, "sound": "", "meaning": ""}
    if korean_source:
        korean: dict[str, dict[str, list[str]]] = {}
        for line in korean_source.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            sound, separator, remainder = line.partition(":")
            if not separator:
                continue
            hanja, separator, definition = remainder.partition(":")
            if not separator or len(hanja) != 1 or not ("\u3400" <= hanja <= "\u9fff" or "\uf900" <= hanja <= "\ufaff"):
                continue
            meaning = definition.strip()
            if meaning.endswith(f" {sound}"):
                meaning = meaning[: -(len(sound) + 1)].strip()
            item = korean.setdefault(hanja, {"sounds": [], "meanings": []})
            if sound and sound not in item["sounds"]:
                item["sounds"].append(sound)
            if meaning and meaning not in item["meanings"]:
                item["meanings"].append(meaning)
        for literal, korean_item in korean.items():
            entry = entries.setdefault(literal, {"on": [], "kun": [], "sound": "", "meaning": ""})
            entry["sound"] = "·".join(korean_item["sounds"])
            entry["meaning"] = "; ".join(korean_item["meanings"])
        # KANJIDIC2의 JIS/Unicode variant 연결을 따라 일본 신자체가 한국
        # 정자체의 뜻·음을 이어받게 한다(예: 悪→惡, 亜→亞, 駅→驛).
        for _ in range(2):
            for literal, targets in variants.items():
                entry = entries.get(literal)
                if not entry or (entry["sound"] and entry["meaning"]):
                    continue
                for target in targets:
                    source_entry = entries.get(target)
                    if not source_entry:
                        continue
                    if not entry["sound"] and source_entry["sound"]:
                        entry["sound"] = source_entry["sound"]
                    if not entry["meaning"] and source_entry["meaning"]:
                        entry["meaning"] = source_entry["meaning"]
                    if entry["sound"] and entry["meaning"]:
                        break
        for literal, meaning in CURATED_KOREAN_MEANINGS.items():
            if literal in entries and not entries[literal]["meaning"]:
                entries[literal]["meaning"] = meaning
        metadata["korean_source"] = "libhangul data/hanja/hanja.txt"
        metadata["korean_license"] = "BSD-3-Clause"
        if japanese_variants_source:
            metadata["japanese_variants_source"] = "OpenCC JPShinjitaiCharacters.txt"
            metadata["japanese_variants_license"] = "Apache-2.0"
    return metadata, entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--korean-source", type=Path)
    parser.add_argument("--japanese-variants-source", type=Path)
    args = parser.parse_args()
    metadata, entries = build(args.source, args.korean_source, args.japanese_variants_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"metadata": metadata, "entries": entries}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"wrote {len(entries)} kanji to {args.output}")


if __name__ == "__main__":
    main()
