#!/usr/bin/env python3
"""영상 표지 캡처 실패 시 기존 장면 이미지로 세로 EPUB 표지를 만든다."""

import argparse
import glob
import os
import secrets

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


WIDTH, HEIGHT = 960, 1440
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"


def fitted_font(draw, text, max_size=88, min_size=38, max_width=860):
    for size in range(max_size, min_size - 1, -2):
        font = ImageFont.truetype(FONT_PATH, size)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
    return ImageFont.truetype(FONT_PATH, min_size)


def build_cover(book_dir, output, title):
    candidates = sorted(glob.glob(os.path.join(book_dir, "images", "*.jpg")))
    candidates = [path for path in candidates if os.path.getsize(path) > 0]
    if not candidates:
        raise RuntimeError(f"표지로 사용할 장면 이미지가 없습니다: {book_dir}/images")
    source_path = secrets.choice(candidates)

    with Image.open(source_path) as source:
        source = source.convert("RGB")
        background = ImageOps.fit(source, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
        background = background.filter(ImageFilter.GaussianBlur(28))
        dark = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 72))
        canvas = Image.alpha_composite(background.convert("RGBA"), dark)

        foreground = source.copy()
        foreground.thumbnail((900, 920), Image.Resampling.LANCZOS)
        x = (WIDTH - foreground.width) // 2
        y = max(70, (1040 - foreground.height) // 2)
        canvas.paste(foreground, (x, y))

    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, 1080, WIDTH, HEIGHT), fill=(0, 0, 0, 190))
    font = fitted_font(draw, title)
    title_box = draw.textbbox((0, 0), title, font=font)
    title_width = title_box[2] - title_box[0]
    draw.text(((WIDTH - title_width) / 2, 1170), title, font=font,
              fill=(255, 255, 255, 255))
    caption = "Japanese Subtitle Study"
    caption_font = ImageFont.truetype(FONT_PATH, 34)
    caption_box = draw.textbbox((0, 0), caption, font=caption_font)
    draw.text(((WIDTH - (caption_box[2] - caption_box[0])) / 2, 1325), caption,
              font=caption_font, fill=(210, 210, 210, 255))

    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    canvas.convert("RGB").save(output, "JPEG", quality=92, optimize=True)
    print(f"✅ 장면 이미지 대체 표지 생성: {output}")
    print(f"   선택 이미지: {source_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book_dir")
    parser.add_argument("output")
    parser.add_argument("title")
    args = parser.parse_args()
    build_cover(os.path.abspath(args.book_dir), os.path.abspath(args.output), args.title)


if __name__ == "__main__":
    main()
