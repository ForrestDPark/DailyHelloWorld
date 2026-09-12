#!/usr/bin/env python3
"""Build the browser-side Japanese kanji reading index from KANJIDIC2."""

from __future__ import annotations

import argparse
import gzip
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def build(source: Path) -> tuple[dict[str, object], dict[str, dict[str, list[str]]]]:
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
    entries: dict[str, dict[str, list[str]]] = {}
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
            entries[literal] = {"on": on, "kun": kun}
    return metadata, entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    metadata, entries = build(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"metadata": metadata, "entries": entries}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"wrote {len(entries)} kanji to {args.output}")


if __name__ == "__main__":
    main()
