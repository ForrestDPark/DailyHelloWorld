#!/usr/bin/env python3
"""용간편 3구절의 생성형 베이스에 검증된 한글 정보를 결정론적으로 합성한다."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "generated" / "jiudi_yonggan3"
SOURCE_DIR = ASSET_DIR / "source"
MANIFEST_PATH = ROOT / "yonggan3_visual_manifest.json"
FONT_PATH = Path("/System/Library/Fonts/AppleSDGothicNeo.ttc")
CANVAS = (2400, 3600)
PREVIEW = (390, 585)

BLUE = (52, 121, 219)
RED = (193, 56, 48)
GOLD = (224, 183, 91)
CREAM = (248, 242, 225)
INK = (18, 20, 24)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size=size, index=7 if bold else 3)


def rounded_label(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    color: tuple[int, int, int],
    max_width: int = 820,
) -> None:
    x, y = xy
    label_font = font(55, True)
    box = draw.textbbox((0, 0), text, font=label_font)
    width = min(max_width, box[2] - box[0] + 72)
    height = 96
    draw.rounded_rectangle((x, y, x + width, y + height), radius=26, fill=(*INK, 225), outline=(*color, 255), width=5)
    draw.text((x + 34, y + 18), text, font=label_font, fill=CREAM)


def draw_header(layer: Image.Image, title: str, subtitle: str, battle: str) -> None:
    draw = ImageDraw.Draw(layer)
    accent = BLUE if battle == "midway" else GOLD
    draw.rectangle((0, 0, CANVAS[0], 300), fill=(*INK, 226))
    draw.rectangle((0, 0, 28, 300), fill=(*accent, 255))
    draw.text((90, 48), title, font=font(104, True), fill=CREAM)
    draw.text((94, 180), subtitle, font=font(52), fill=(225, 225, 220, 255))


def draw_footer(layer: Image.Image, lines: list[str], battle: str) -> None:
    draw = ImageDraw.Draw(layer)
    accent = BLUE if battle == "midway" else GOLD
    top = 3100
    draw.rounded_rectangle((55, top, 2345, 3545), radius=38, fill=(*INK, 228), outline=(*accent, 255), width=5)
    body = font(55, True)
    y = top + 42
    for line in lines[:5]:
        color = BLUE if line.startswith("미군") or line.startswith("조조군") or line.startswith("정보 지원") else RED if line.startswith("일본군") or line.startswith("원소군") else CREAM
        draw.ellipse((100, y + 20, 124, y + 44), fill=(*color, 255))
        draw.text((150, y), line, font=body, fill=CREAM)
        y += 76


def draw_markers(layer: Image.Image, markers: list[list[object]], battle: str) -> None:
    draw = ImageDraw.Draw(layer)
    accent = BLUE if battle == "midway" else GOLD
    for nx, ny, text in markers:
        x = int(float(nx) * CANVAS[0])
        y = int(float(ny) * CANVAS[1])
        draw.line((x, y, x + 55, y - 55), fill=(*accent, 255), width=8)
        draw.ellipse((x - 14, y - 14, x + 14, y + 14), fill=(*accent, 255), outline=(255, 255, 255, 255), width=4)
        rounded_label(draw, (min(x + 42, 1510), max(315, y - 125)), str(text), accent)


def side_color(name: str) -> tuple[int, int, int]:
    return BLUE if name == "blue" else RED


def draw_plaques(layer: Image.Image, plaques: list[list[object]]) -> None:
    draw = ImageDraw.Draw(layer)
    for nx1, ny1, nx2, ny2, text, side in plaques:
        x1, y1 = int(float(nx1) * CANVAS[0]), int(float(ny1) * CANVAS[1])
        x2, y2 = int(float(nx2) * CANVAS[0]), int(float(ny2) * CANVAS[1])
        color = side_color(str(side))
        draw.rounded_rectangle((x1, y1, x2, y2), radius=24, fill=(*INK, 235), outline=(*color, 255), width=6)
        label_font = font(58, True)
        box = draw.textbbox((0, 0), str(text), font=label_font)
        tx = x1 + ((x2 - x1) - (box[2] - box[0])) // 2
        ty = y1 + ((y2 - y1) - (box[3] - box[1])) // 2 - box[1]
        draw.text((tx, ty), str(text), font=label_font, fill=CREAM)


def draw_badges(layer: Image.Image, badges: list[list[object]]) -> None:
    draw = ImageDraw.Draw(layer)
    badge_font = font(48, True)
    for nx, ny, text, side in badges:
        x, y = int(float(nx) * CANVAS[0]), int(float(ny) * CANVAS[1])
        color = side_color(str(side))
        draw.rounded_rectangle((x - 55, y - 105, x + 55, y + 105), radius=24, fill=(*INK, 242), outline=(*color, 255), width=7)
        box = draw.textbbox((0, 0), str(text), font=badge_font)
        draw.text((x - (box[2] - box[0]) // 2, y - (box[3] - box[1]) // 2 - box[1]), str(text), font=badge_font, fill=CREAM)


def draw_stages(layer: Image.Image, stages: list[str], battle: str) -> None:
    draw = ImageDraw.Draw(layer)
    accent = BLUE if battle == "midway" else GOLD
    for y, text in zip((350, 1130, 1910, 2690), stages):
        draw.rounded_rectangle((70, y, 1340, y + 115), radius=28, fill=(*INK, 222), outline=(*accent, 255), width=5)
        draw.text((105, y + 22), text, font=font(62, True), fill=CREAM)


def source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_contact_sheet(battle: str) -> None:
    """휴대폰 390px 축소본 6장을 한 화면에 모아 실제 가독성을 검수한다."""
    categories = (
        "commanders", "soldiers_weapons_life", "command_structure",
        "country_map", "strategy_map", "sequence",
    )
    margin = 24
    sheet = Image.new(
        "RGB",
        (PREVIEW[0] * 3 + margin * 4, PREVIEW[1] * 2 + margin * 3),
        (25, 26, 28),
    )
    for index, category in enumerate(categories):
        image = Image.open(ASSET_DIR / f"{battle}_{category}.png").convert("RGB")
        image = image.resize(PREVIEW, Image.Resampling.LANCZOS)
        x = margin + (index % 3) * (PREVIEW[0] + margin)
        y = margin + (index // 3) * (PREVIEW[1] + margin)
        sheet.paste(image, (x, y))
    qa_dir = ASSET_DIR / "qa"
    qa_dir.mkdir(exist_ok=True)
    sheet.save(qa_dir / f"{battle}_contact_sheet_390.png", compress_level=6)


def render_one(battle: str, category: str, spec: dict[str, object], forbidden: list[str]) -> dict[str, object]:
    filename = f"{battle}_{category}.png"
    source = SOURCE_DIR / filename
    target = ASSET_DIR / filename
    if not source.exists():
        raise FileNotFoundError(source)

    base = Image.open(source).convert("RGB").resize(CANVAS, Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    if spec.get("plaques"):
        draw_plaques(overlay, spec["plaques"])
    if spec.get("badges"):
        draw_badges(overlay, spec["badges"])
    draw_header(overlay, str(spec["title"]), str(spec["subtitle"]), battle)
    if spec.get("markers"):
        draw_markers(overlay, spec["markers"], battle)
    if spec.get("stages"):
        draw_stages(overlay, spec["stages"], battle)
    draw_footer(overlay, list(spec["lines"]), battle)
    final = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")

    metadata = PngImagePlugin.PngInfo()
    required = [str(spec["title"]), str(spec["subtitle"]), *map(str, spec["lines"])]
    required.extend(map(str, spec.get("stages", [])))
    required.extend(str(item[2]) for item in spec.get("markers", []))
    required.extend(str(item[4]) for item in spec.get("plaques", []))
    required.extend(str(item[2]) for item in spec.get("badges", []))
    metadata.add_text("sunzi_visual_pipeline", "yonggan3-v2-deterministic-overlay")
    metadata.add_text("sunzi_source_sha256", source_sha256(source))
    metadata.add_text("sunzi_required_labels", json.dumps(required, ensure_ascii=False))
    metadata.add_text("sunzi_forbidden_objects", json.dumps(forbidden, ensure_ascii=False))
    # 고해상도 12장을 야간 파이프라인 제한 시간 안에 재현할 수 있도록
    # 느린 전역 PNG 최적화는 생략한다. 무손실 픽셀과 메타데이터는 동일하다.
    final.save(target, pnginfo=metadata, compress_level=6)
    return {
        "file": filename,
        "source_sha256": source_sha256(source),
        "output_sha256": source_sha256(target),
        "required_labels": required,
        "forbidden_objects": forbidden,
        "size": list(final.size),
    }


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    report: dict[str, object] = {"pipeline": "yonggan3-v2-deterministic-overlay", "images": []}
    for battle, battle_spec in manifest["battles"].items():
        forbidden = battle_spec["forbidden_objects"]
        for category, spec in battle_spec["images"].items():
            report["images"].append(render_one(battle, category, spec, forbidden))
        make_contact_sheet(battle)
    (ASSET_DIR / "visual_build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"YONGGAN3_VISUALS_OK — {len(report['images'])}장 합성 완료 ({CANVAS[0]}×{CANVAS[1]})")


if __name__ == "__main__":
    main()
