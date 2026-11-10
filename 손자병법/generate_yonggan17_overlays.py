from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated" / "jiudi_yonggan17"
SRC = Path.home() / ".codex" / "generated_images" / "01a1c4ac-bed7-7741-8995-4387dbe89c51"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"


def font(size: int, bold: bool = False):
    return ImageFont.truetype(FONT, size=size, index=8 if bold else 0)


def box(draw, xy, text, fill, anchor="mm", size=42):
    f = font(size, True)
    bbox = draw.textbbox(xy, text, font=f, anchor=anchor, stroke_width=2)
    pad = 12
    draw.rounded_rectangle(
        (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad),
        radius=12,
        fill=(15, 20, 28, 220),
        outline=fill,
        width=4,
    )
    draw.text(xy, text, font=f, fill="white", anchor=anchor, stroke_width=2, stroke_fill="black")


def commanders():
    src = SRC / "exec-e7f3c876-5bc1-4eb9-8b3b-7293fc7c176f.png"
    im = Image.open(src).convert("RGBA")
    draw = ImageDraw.Draw(im, "RGBA")
    box(draw, (310, 70), "HMS 세라프 · 빌 주얼", "#4aa3ff", anchor="ma")
    box(draw, (420, im.height - 55), "이언 몬태규 · 찰스 촐먼들리 · 해군정보부 17M", "#4aa3ff", anchor="ms")
    box(draw, (im.width - 360, 70), "스페인 당국 · 독일 정보 분석망", "#ff5a5a", anchor="ma")
    im.convert("RGB").save(OUT / "mincemeat_commanders.png", quality=95)


def label_map(name, labels, legend):
    path = OUT / name
    im = Image.open(path).convert("RGBA")
    draw = ImageDraw.Draw(im, "RGBA")
    for x, y, text, color in labels:
        box(draw, (x, y), text, color, size=34)
    legend_y = im.height - 58
    draw.rounded_rectangle((28, legend_y - 35, im.width - 28, im.height - 18), radius=16, fill=(10, 14, 22, 225))
    draw.text((im.width // 2, legend_y), legend, font=font(32, True), fill="white", anchor="mm")
    im.convert("RGB").save(path, quality=95)


def main():
    commanders()
    label_map(
        "mincemeat_country_map.png",
        [
            (230, 430, "우엘바", "#4aa3ff"),
            (960, 470, "사르데냐", "#ff5a5a"),
            (1120, 690, "시칠리아 · 실제 목표", "#4aa3ff"),
            (1390, 520, "그리스 · 거짓 목표", "#ff5a5a"),
        ],
        "청색 실선: 실제 허스키 상륙축  ·  청색 점선: 문서 전달 경로  ·  적색 점선: 거짓 목표",
    )
    label_map(
        "mincemeat_strategy_map.png",
        [
            (210, 505, "우엘바 · 문서 회수", "#4aa3ff"),
            (835, 500, "사르데냐 · 거짓 목표", "#ff5a5a"),
            (1040, 665, "시칠리아 · 실제 상륙", "#4aa3ff"),
            (1390, 585, "그리스 · 거짓 목표", "#ff5a5a"),
        ],
        "문서 투입과 전달(점선) / 실제 시칠리아 상륙(청색) / 독일이 믿은 거짓 목표(적색)",
    )


if __name__ == "__main__":
    main()
