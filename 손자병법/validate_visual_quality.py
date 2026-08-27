#!/usr/bin/env python3
"""손자병법 전역 이미지가 기준본보다 현저히 단순한지 정량·구조 검수한다."""

from __future__ import annotations

import argparse
import io
import math
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlparse

from PIL import Image, ImageChops, ImageFilter, ImageStat

REPO = Path(__file__).absolute().parent.parent
ROOT = next(
    child for child in REPO.iterdir()
    if unicodedata.normalize("NFC", child.name) == "손자병법"
)
REQUIRED_CATEGORIES = (
    "commanders", "soldiers", "command_structure", "country_map", "strategy_map", "sequence"
)
BENCHMARKS = {
    "commanders": ("jiudi12/cowpens_commanders.png", "jiudi12/caizhou_commanders.png"),
    "soldiers": ("jiudi17/alesia_soldiers_weapons_life.png", "jiudi17/feiriver_soldiers_weapons_life.png"),
    "command_structure": ("jiudi12/cowpens_command_structure.png", "jiudi12/caizhou_command_structure.png"),
    "country_map": ("jiudi12/cowpens_country_map.png", "jiudi12/caizhou_country_map.png"),
    "strategy_map": ("jiudi12/cowpens_strategy_map.png", "jiudi12/caizhou_strategy_map.png"),
    "sequence": ("jiudi12/cowpens_sequence_map.png", "jiudi12/caizhou_sequence_map.png"),
}


def category(name: str) -> str | None:
    lowered = name.lower()
    if "soldier" in lowered or "weapons_life" in lowered:
        return "soldiers"
    if "command_structure" in lowered:
        return "command_structure"
    if "commanders" in lowered and "base" not in lowered and "source" not in lowered:
        return "commanders"
    if "country" in lowered:
        return "country_map"
    if "strategy" in lowered:
        return "strategy_map"
    if "sequence" in lowered:
        return "sequence"
    return None


def git_image(relative: str) -> Image.Image:
    repo_path = f"손자병법/generated/{relative}"
    completed = subprocess.run(
        ["git", "show", f"origin/main:{repo_path}"], cwd=REPO, check=True, capture_output=True
    )
    return Image.open(io.BytesIO(completed.stdout)).convert("RGB")


def metrics(image: Image.Image) -> dict[str, float]:
    sample = image.convert("RGB")
    sample.thumbnail((480, 320), Image.Resampling.LANCZOS)
    gray = sample.convert("L")
    histogram = gray.histogram()
    total = sum(histogram)
    entropy = -sum((count / total) * math.log2(count / total) for count in histogram if count)
    edge = gray.filter(ImageFilter.FIND_EDGES)
    edge_density = sum(count for value, count in enumerate(edge.histogram()) if value > 35) / total
    color_std = sum(ImageStat.Stat(sample).stddev) / 3
    return {"entropy": entropy, "edge_density": edge_density, "color_std": color_std}


def structural_similarity(left: Image.Image, right: Image.Image) -> float:
    """글자와 작은 표식을 흐린 뒤 남는 공통 배경·대형 면의 유사도를 잰다."""
    prepared = []
    for image in (left, right):
        sample = image.convert("L").resize((96, 72), Image.Resampling.LANCZOS)
        prepared.append(sample.filter(ImageFilter.GaussianBlur(3)))
    difference = ImageChops.difference(*prepared)
    return 1.0 - (ImageStat.Stat(difference).mean[0] / 255.0)


def battle_prefix(name: str) -> str:
    lowered = name.lower()
    markers = ("_commanders", "_soldiers", "_weapons_life", "_command_structure",
               "_country", "_strategy", "_sequence")
    positions = [lowered.find(marker) for marker in markers if marker in lowered]
    return lowered[:min(positions)] if positions else lowered


def generator_source_errors(page: Path, image_paths: list[str]) -> list[str]:
    """한 PIL 베이스로 여러 종류를 찍어내는 일괄 템플릿을 소스에서 차단한다."""
    errors: list[str] = []
    names = {Path(path).name for path in image_paths}
    verse = re.search(r"jiudi(\d+)", page.stem.lower())
    candidates = list(ROOT.glob("*.py"))
    if verse:
        candidates = [p for p in candidates if verse.group(0) in p.name.lower()] + candidates
    checked: set[Path] = set()
    for script in candidates:
        if script in checked:
            continue
        checked.add(script)
        source = script.read_text(encoding="utf-8", errors="ignore")
        emitted = {name for name in names if name in source}
        emitted_categories = {category(name) for name in emitted if category(name)}
        if len(emitted_categories) < 3:
            continue
        shared_base_template = bool(
            re.search(r"def\s+\w+\s*\(\s*base\b", source)
            and re.search(r"(?:fit_bg|Image\.open)\s*\(\s*base\b", source)
        )
        primitive_heavy = len(re.findall(
            r"\.\s*(?:polygon|ellipse|rectangle|rounded_rectangle|line)\s*\(", source
        )) >= 5
        generic_map_factories = bool(re.search(r"def\s+(?:power_map|strategy)\s*\(", source))
        if shared_base_template and primitive_heavy and generic_map_factories:
            errors.append(
                f"{script.name}: 같은 인물/배경 베이스와 PIL 도형 팩토리로 "
                f"{len(emitted_categories)}종 도판을 일괄 생성합니다"
            )
    return errors


def referenced_images(page: Path) -> list[str]:
    text = page.read_text(encoding="utf-8")
    urls = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    paths: list[str] = []
    for url in urls:
        if "raw.githubusercontent.com/ForrestDPark/DailyHelloWorld/main/" in url:
            decoded = unquote(urlparse(url).path)
            marker = "/DailyHelloWorld/main/"
            relative = decoded.split(marker, 1)[1]
            if relative.startswith("손자병법/"):
                paths.append(relative)
        elif url.startswith("generated/"):
            paths.append(f"손자병법/{url}")
    return paths


def target_image(repo_relative: str) -> Image.Image:
    local = ROOT / repo_relative.split("/", 1)[1]
    if local.exists():
        return Image.open(local).convert("RGB")
    completed = subprocess.run(
        ["git", "show", f"origin/main:{repo_relative}"], cwd=REPO, check=True, capture_output=True
    )
    return Image.open(io.BytesIO(completed.stdout)).convert("RGB")


def validate(page: Path) -> list[str]:
    errors: list[str] = []
    images = [(path, category(Path(path).name)) for path in referenced_images(page)]
    images = [(path, kind) for path, kind in images if kind]
    counts = Counter(kind for _, kind in images)
    for kind in REQUIRED_CATEGORIES:
        if counts[kind] != 2:
            errors.append(f"{kind} 이미지가 {counts[kind]}장입니다(정상: 서양·동양 각 1장, 총 2장)")

    baseline = {
        kind: [metrics(git_image(relative)) for relative in relatives]
        for kind, relatives in BENCHMARKS.items()
    }
    loaded: list[tuple[str, str, Image.Image]] = []
    for path, kind in images:
        image = target_image(path)
        loaded.append((path, kind, image))
        current = metrics(image)
        entropy_floor = min(item["entropy"] for item in baseline[kind]) * 0.72
        edge_floor = min(item["edge_density"] for item in baseline[kind]) * 0.60
        if current["entropy"] < entropy_floor:
            errors.append(
                f"{Path(path).name}: 정보량 엔트로피 {current['entropy']:.2f}가 "
                f"{kind} 기준 하한 {entropy_floor:.2f}보다 낮습니다"
            )
        if current["edge_density"] < edge_floor:
            errors.append(
                f"{Path(path).name}: 지형·사물 경계 밀도 {current['edge_density']:.3f}가 "
                f"{kind} 기준 하한 {edge_floor:.3f}보다 낮습니다"
            )
    for index, (left_path, left_kind, left_image) in enumerate(loaded):
        for right_path, right_kind, right_image in loaded[index + 1:]:
            if left_kind == right_kind or battle_prefix(Path(left_path).name) != battle_prefix(Path(right_path).name):
                continue
            similarity = structural_similarity(left_image, right_image)
            if similarity >= 0.95:
                errors.append(
                    f"{Path(left_path).name} ↔ {Path(right_path).name}: 서로 다른 도판인데 "
                    f"공통 배경·대형 면 유사도 {similarity:.3f}가 0.950 이상입니다"
                )
    errors.extend(generator_source_errors(page, [path for path, _ in images]))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("page", type=Path)
    args = parser.parse_args()
    errors = validate(args.page.resolve())
    if errors:
        print("VISUAL_QUALITY_FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("VISUAL_QUALITY_PASS — 이미지 12장, 기준본 정보량, 도판 간 배경 재사용, 생성 소스를 확인했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
