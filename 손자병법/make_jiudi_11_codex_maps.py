#!/usr/bin/env python3
"""구지편 11구절의 셔먼·손책 국가 위치도와 Codex 전략지형도를 만든다."""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, Polygon as MplPolygon
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
BASES = ROOT / "generated_bases"
NE = Path(
    "/opt/anaconda3/lib/python3.11/site-packages/pyogrio/tests/fixtures/"
    "naturalearth_lowres/naturalearth_lowres.shp"
)
FONT_CANDIDATES = [
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]
FONT_PATH = next(Path(p) for p in FONT_CANDIDATES if Path(p).exists())
font_manager.fontManager.addfont(str(FONT_PATH))
FONT_NAME = font_manager.FontProperties(fname=str(FONT_PATH)).get_name()
plt.rcParams["font.family"] = FONT_NAME
plt.rcParams["axes.unicode_minus"] = False


def pil_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    # Apple SD Gothic Neo 컬렉션은 굵기 인덱스가 환경마다 달라 기본 face를 사용한다.
    return ImageFont.truetype(str(FONT_PATH), size=size)


def label(draw, xy, text, *, size=42, fill="#fff8df", anchor="mm", box=True):
    font = pil_font(size)
    if box:
        box_xy = draw.textbbox(xy, text, font=font, anchor=anchor, stroke_width=1)
        pad = 10
        draw.rounded_rectangle(
            (box_xy[0] - pad, box_xy[1] - pad, box_xy[2] + pad, box_xy[3] + pad),
            radius=12,
            fill=(20, 25, 24, 205),
            outline=(240, 225, 175, 210),
            width=2,
        )
    draw.text(xy, text, font=font, fill=fill, anchor=anchor, stroke_width=1, stroke_fill="#171815")


def arrow(draw, points, color, width=18):
    for a, b in zip(points, points[1:]):
        draw.line((a, b), fill=color, width=width, joint="curve")
    a, b = points[-2], points[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = max((dx * dx + dy * dy) ** 0.5, 1)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    tip = b
    back = (b[0] - ux * 42, b[1] - uy * 42)
    draw.polygon(
        [tip, (back[0] + px * 24, back[1] + py * 24), (back[0] - px * 24, back[1] - py * 24)],
        fill=color,
    )


def header(img, title, subtitle):
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rectangle((0, 0, img.width, 190), fill=(17, 23, 23, 225))
    draw.text((img.width // 2, 48), title, font=pil_font(43), fill="#fff4d2", anchor="ma")
    draw.text((img.width // 2, 122), subtitle, font=pil_font(20), fill="#d9e3d3", anchor="ma")
    return draw


def sherman_strategy():
    img = Image.open(BASES / "sherman_march_codex_base.png").convert("RGBA")
    draw = header(
        img,
        "셔먼의 바다로의 진군 — Codex 전략지형도",
        "애틀랜타에서 사바나까지 두 갈래로 넓게 전진해 남부의 보급 기반을 끊다 · 전역 개략도, 축척 아님",
    )
    west = [(300, 330), (390, 520), (470, 720), (590, 940), (760, 1160), (990, 1390)]
    east = [(300, 330), (540, 470), (700, 680), (820, 890), (940, 1120), (990, 1390)]
    arrow(draw, west, "#e04b3f", 19)
    arrow(draw, east, "#f2a33a", 19)
    for xy, txt in [
        ((300, 300), "애틀랜타\n출발"),
        ((500, 690), "좌익 · 슬로컴"),
        ((820, 670), "우익 · 하워드"),
        ((865, 1280), "사바나\n도착"),
    ]:
        label(draw, xy, txt, size=39)
    label(draw, (760, 1080), "철도·창고 파괴\n현지 조달", size=35)
    label(draw, (850, 1450), "대서양 연안·습지", size=27, fill="#d7edf4")
    draw.rounded_rectangle((45, 1350, 705, 1510), 18, fill=(16, 22, 21, 220), outline="#ead7a6", width=3)
    draw.text((75, 1380), "읽는 순서", font=pil_font(30), fill="#ffe4a5")
    draw.text(
        (75, 1425),
        "① 퇴로를 끊고 전진  ② 두 축으로 넓게 압박\n③ 현지 조달로 60,000여 명의 행군 지속",
        font=pil_font(27),
        fill="#f5f1df",
        spacing=10,
    )
    img.convert("RGB").save(ROOT / "sherman_march_codex_map.png", quality=95)


def sun_ce_strategy():
    img = Image.open(BASES / "sun_ce_jiangdong_codex_base.png").convert("RGBA")
    draw = header(
        img,
        "손책의 강동 평정 — Codex 전략지형도",
        "소수의 출발 병력이 도강과 연승을 거치며 스스로 불어난 전역 · 전역 개략도, 축척 아님",
    )
    route = [(280, 300), (400, 470), (580, 600), (520, 790), (640, 990), (810, 1190), (930, 1430)]
    arrow(draw, route, "#d6493f", 20)
    for xy, txt in [
        ((280, 270), "역양\n출발"),
        ((440, 460), "횡강·당리\n도강"),
        ((600, 610), "우저\n장악"),
        ((500, 820), "말릉"),
        ((670, 1010), "곡아\n유요 격파"),
        ((865, 1300), "회계로 확대"),
    ]:
        label(draw, xy, txt, size=37)
    label(draw, (900, 500), "장강", size=43, fill="#d7edf4", box=False)
    label(draw, (765, 880), "승전 소문 →\n병력·호응 증가", size=35)
    draw.rounded_rectangle((45, 1350, 780, 1510), 18, fill=(16, 22, 21, 220), outline="#ead7a6", width=3)
    draw.text((75, 1380), "읽는 순서", font=pil_font(30), fill="#ffe4a5")
    draw.text(
        (75, 1425),
        "① 원술에게 병력을 받아 출발  ② 장강 도하\n③ 거점 연쇄 장악  ④ 현지 호응으로 전력이 증폭",
        font=pil_font(26),
        fill="#f5f1df",
        spacing=10,
    )
    img.convert("RGB").save(ROOT / "sun_ce_jiangdong_codex_map.png", quality=95)


def plot_country(
    code, title, subtitle, points, route_color, output, region_poly=None, note=None,
    annotate_points=True, region_label=None
):
    world = gpd.read_file(NE)
    country = world[world["iso_a3"] == code]
    geom = country.geometry.iloc[0]
    if code == "USA" and geom.geom_type == "MultiPolygon":
        # 국가 위치도의 주제는 조지아 전역이므로 알래스카·하와이를 제외한 본토만 확대한다.
        geom = max(geom.geoms, key=lambda part: part.area)
        country = gpd.GeoDataFrame({"geometry": [geom]}, crs=world.crs)
    fig, ax = plt.subplots(figsize=(12, 10), dpi=220)
    fig.patch.set_facecolor("#efe7d2")
    ax.set_facecolor("#dce7e2")
    country.plot(ax=ax, color="#d8c59e", edgecolor="#564c3a", linewidth=1.4)
    if region_poly:
        ax.add_patch(MplPolygon(region_poly, closed=True, facecolor="#d9784d", edgecolor="#8b3025", alpha=.62, linewidth=2))
    xs, ys = zip(*[(p[1], p[2]) for p in points])
    ax.add_patch(
        FancyArrowPatch(
            (xs[0], ys[0]), (xs[-1], ys[-1]),
            arrowstyle="-|>", mutation_scale=22, linewidth=3.2, color=route_color,
            connectionstyle="arc3,rad=-0.12", zorder=5,
        )
    )
    ax.scatter(xs, ys, s=65, c=route_color, edgecolors="white", linewidths=1.5, zorder=6)
    if annotate_points:
        for name, x, y in points:
            ax.annotate(name, (x, y), xytext=(7, 7), textcoords="offset points", fontsize=12, weight="bold", color="#252018")
    if region_label:
        ax.annotate(
            region_label, (sum(xs) / len(xs), sum(ys) / len(ys)),
            xytext=(18, 18), textcoords="offset points", fontsize=14, weight="bold", color="#702a21",
        )
    minx, miny, maxx, maxy = geom.bounds
    ax.set_xlim(minx - 2, maxx + 2)
    ax.set_ylim(miny - 2, maxy + 2)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, fontsize=25, weight="bold", color="#262117", pad=24)
    ax.text(.5, 1.01, subtitle, transform=ax.transAxes, ha="center", va="bottom", fontsize=13, color="#574c38")
    if note:
        ax.text(.5, .015, note, transform=ax.transAxes, ha="center", va="bottom", fontsize=11, color="#6b342b",
                bbox=dict(boxstyle="round,pad=.45", facecolor="#fff4df", edgecolor="#b48961"))
    fig.savefig(ROOT / output, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def country_maps():
    plot_country(
        "USA",
        "셔먼의 바다로의 진군 — 미국 내 위치",
        "조지아주 애틀랜타에서 대서양 연안 사바나까지, 약 460km의 전역",
        [("애틀랜타", -84.3880, 33.7490), ("사바나", -81.0998, 32.0809)],
        "#c53f35",
        "sherman_march_country_map.png",
        region_poly=[(-85.6, 35.0), (-80.8, 35.0), (-80.8, 30.4), (-82.1, 30.4), (-85.6, 31.0)],
    )
    plot_country(
        "CHN",
        "손책의 강동 평정 — 중국 내 위치",
        "장강 하류를 건너 오늘날 장쑤·안후이·저장 일대로 세력을 넓힌 전역",
        [("역양", 118.35, 31.72), ("우저", 118.49, 31.58), ("말릉", 118.80, 32.06), ("곡아", 119.58, 32.00), ("회계", 120.58, 30.00)],
        "#c53f35",
        "sun_ce_jiangdong_country_map.png",
        region_poly=[(117.5, 33.0), (121.8, 33.0), (122.0, 28.5), (118.0, 28.5)],
        note="현대 중국 국경선은 전역의 현재 위치를 보여주기 위한 참조이며, 2세기 정치적 경계가 아닙니다.",
        annotate_points=False,
        region_label="장강 하류·강동 전역",
    )


if __name__ == "__main__":
    sherman_strategy()
    sun_ce_strategy()
    country_maps()
    print("MAPS_OK: 전략지형도 2장 + 국가 위치도 2장")
