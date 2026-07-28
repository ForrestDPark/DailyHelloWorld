#!/usr/bin/env python3
"""구지편 11구절의 셔먼·손책 국가 위치도와 Codex 전략지형도를 만든다."""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Ellipse, FancyArrowPatch, Patch, Polygon as MplPolygon
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


def site(draw, xy, text, *, color="#f7dd9b", dx=18, dy=-8, size=27):
    """작은 거점 표식. 서사에 등장하는 지명을 지도에서 빠르게 찾게 한다."""
    x, y = xy
    draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=color, outline="#171815", width=3)
    label(draw, (x + dx, y + dy), text, size=size, fill="#fff8df", anchor="lm")


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
    site(draw, (455, 755), "메이컨", color="#f6b34f", dx=-25, dy=-35, size=28)
    site(draw, (790, 520), "오거스타", color="#f6b34f", dx=20, dy=-5, size=28)
    site(draw, (500, 820), "그리스월드빌", color="#e95d4f", dx=22, dy=12, size=27)
    site(draw, (815, 1185), "포트 맥앨리스터", color="#f6e09b", dx=-20, dy=-32, size=26)
    label(draw, (745, 1050), "오기치강(Ogeechee River)", size=25, fill="#d7edf4", box=False)
    label(draw, (675, 940), "철도·창고 파괴\n현지조달", size=31)
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
    site(draw, (750, 1130), "고릉 방어선", color="#f6b34f", dx=-18, dy=-28, size=26)
    site(draw, (820, 1210), "사독 우회로", color="#68c4b5", dx=-18, dy=18, size=26)
    site(draw, (875, 1310), "회계", color="#e95d4f", dx=-20, dy=-30, size=27)
    arrow(draw, [(735, 1110), (795, 1190), (875, 1310)], "#68c4b5", 12)
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


def plot_sun_ce_warlord_map():
    """195년 무렵 후한 말의 군웅 근거지를 개략 세력권으로 보여준다."""
    world = gpd.read_file(NE)
    china = world[world["iso_a3"] == "CHN"]
    fig, ax = plt.subplots(figsize=(14, 10), dpi=220)
    fig.patch.set_facecolor("#efe7d2")
    ax.set_facecolor("#dce7e2")
    china.plot(ax=ax, color="#e3dcc8", edgecolor="#7c725f", linewidth=1.0, alpha=.58)

    # 정확한 행정 경계가 아니라 195년 전후 주요 군벌의 근거지·활동권을 겹쳐 그린 개략도다.
    powers = [
        ("원소(袁紹)\n기주·하북", 115.3, 38.1, 7.4, 4.5, "#d7a642"),
        ("공손찬(公孫瓚)\n유주", 118.0, 40.5, 5.0, 3.2, "#a7c96a"),
        ("조조(曹操)\n연주·예주", 114.6, 34.8, 5.4, 3.8, "#5a91c8"),
        ("여포(呂布)\n서주 일대", 118.1, 34.1, 3.2, 2.8, "#9c75b7"),
        ("원술(袁術)\n회남·수춘", 116.4, 32.0, 4.9, 3.0, "#cf675c"),
        ("유표(劉表)\n형주", 111.8, 30.8, 6.0, 5.1, "#70a66f"),
        ("유장(劉璋)\n익주", 104.5, 30.3, 7.4, 6.5, "#b08a62"),
        ("이각·곽사\n관중", 108.8, 34.5, 5.0, 3.0, "#9a9a72"),
        ("마등·한수\n양주", 103.0, 36.4, 6.4, 4.5, "#c28caa"),
        ("유요(劉繇)\n곡아", 119.4, 31.6, 3.4, 2.5, "#6d9e99"),
        ("왕랑(王朗)\n회계", 120.3, 29.3, 2.6, 2.4, "#8597bd"),
    ]
    for name, x, y, w, h, color in powers:
        ax.add_patch(Ellipse((x, y), w, h, facecolor=color, edgecolor="#4a4032", alpha=.68, linewidth=1.5, zorder=2))
        ax.text(x, y, name, ha="center", va="center", fontsize=10.5, weight="bold", color="#211d17", zorder=3)

    # 손책의 출발과 강동 진출은 별도의 화살표로 표시한다.
    route = [(116.9, 31.7), (118.35, 31.72), (118.49, 31.58), (119.58, 32.0), (120.58, 30.0)]
    ax.add_patch(
        FancyArrowPatch(
            route[0], route[-1], arrowstyle="-|>", mutation_scale=25, linewidth=4.0,
            color="#b3261e", connectionstyle="arc3,rad=.12", zorder=5,
        )
    )
    ax.scatter([p[0] for p in route[1:]], [p[1] for p in route[1:]], s=55, color="#b3261e",
               edgecolor="white", linewidth=1.3, zorder=6)
    ax.annotate(
        "손책(孫策)\n역양 → 우저 → 곡아 → 회계",
        xy=route[-1], xytext=(116.5, 26.2), fontsize=12.5, weight="bold",
        color="#8d1d18", ha="center", zorder=7,
        bbox=dict(boxstyle="round,pad=.4", facecolor="#fff0dc", edgecolor="#b3261e"),
        arrowprops=dict(arrowstyle="-", color="#b3261e", linewidth=1.8),
    )

    ax.set_xlim(96, 124.5)
    ax.set_ylim(20, 43.5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("손책의 강동 평정 — 195년 무렵 후한 말 군웅 세력도", fontsize=24, weight="bold", color="#262117", pad=22)
    ax.text(
        .5, 1.01,
        "원술 휘하에서 출발한 손책이 유요·왕랑의 강동으로 진출하던 당시의 정치적 배경",
        transform=ax.transAxes, ha="center", va="bottom", fontsize=13, color="#574c38",
    )
    ax.legend(
        handles=[
            Patch(facecolor="#e3dcc8", edgecolor="#7c725f", label="현대 중국 외곽선(위치 참조용)"),
            Patch(facecolor="#b3261e", edgecolor="#b3261e", label="손책의 강동 진출 방향"),
        ],
        loc="upper left", frameon=True, facecolor="#fff7e6", edgecolor="#8e8068", fontsize=10,
    )
    ax.text(
        .5, .012,
        "색 영역은 195년 무렵의 정확한 국경이 아니라 각 군벌의 근거지·주요 활동권을 단순화한 개략도입니다.",
        transform=ax.transAxes, ha="center", va="bottom", fontsize=11, color="#6b342b",
        bbox=dict(boxstyle="round,pad=.45", facecolor="#fff4df", edgecolor="#b48961"),
    )
    fig.savefig(ROOT / "sun_ce_jiangdong_country_map.png", bbox_inches="tight", facecolor=fig.get_facecolor())
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
    plot_sun_ce_warlord_map()


def sequence_panel(draw, box, title):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=20, fill="#f7eed9", outline="#554a38", width=4)
    draw.text((x0 + 24, y0 + 18), title, font=pil_font(34), fill="#211d17")
    return x0, y0, x1, y1


def node(draw, xy, text, color, *, size=26):
    x, y = xy
    draw.ellipse((x - 18, y - 18, x + 18, y + 18), fill=color, outline="#201b16", width=3)
    draw.text((x, y + 28), text, font=pil_font(size), fill="#211d17", anchor="ma")


def make_sequence_canvas(title, overview_path):
    canvas = Image.new("RGB", (2400, 1600), "#e9ddc2")
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, 0, 2400, 95), fill="#102235")
    draw.text((40, 43), title, font=pil_font(50), fill="#fff1cf", anchor="lm")
    overview = Image.open(overview_path).convert("RGB")
    overview.thumbnail((970, 1460), Image.Resampling.LANCZOS)
    canvas.paste(overview, (20, 115))
    return canvas, draw


def sherman_sequence():
    canvas, draw = make_sequence_canvas(
        "셔먼의 바다로의 진군 단계별 전략지형도",
        ROOT / "sherman_march_codex_map.png",
    )
    panels = [
        (1015, 115, 1695, 800),
        (1710, 115, 2390, 800),
        (1015, 815, 1695, 1500),
        (1710, 815, 2390, 1500),
    ]
    # 1. 후드가 내민 추격전 거부
    x0, y0, _, _ = sequence_panel(draw, panels[0], "1. 후드 추격 거부")
    node(draw, (x0 + 175, y0 + 230), "애틀랜타", "#d94a3d")
    node(draw, (x0 + 485, y0 + 170), "후드·테네시", "#164d86")
    node(draw, (x0 + 475, y0 + 480), "조지아 내부", "#d94a3d")
    arrow(draw, [(x0 + 210, y0 + 215), (x0 + 425, y0 + 175)], "#164d86", 13)
    arrow(draw, [(x0 + 205, y0 + 245), (x0 + 430, y0 + 450)], "#d94a3d", 15)
    draw.text((x0 + 55, y0 + 570), "토머스는 후드를 맡고\n셔먼은 반대 방향으로 진군", font=pil_font(28), fill="#3b3022")

    # 2. 양익 기만
    x0, y0, _, _ = sequence_panel(draw, panels[1], "2. 양익 기만·목표 은폐")
    node(draw, (x0 + 120, y0 + 230), "애틀랜타", "#d94a3d", size=24)
    node(draw, (x0 + 330, y0 + 430), "메이컨", "#f0a33a", size=24)
    node(draw, (x0 + 500, y0 + 210), "오거스타", "#f0a33a", size=24)
    node(draw, (x0 + 560, y0 + 520), "사바나", "#d94a3d", size=24)
    arrow(draw, [(x0 + 145, y0 + 240), (x0 + 300, y0 + 405), (x0 + 535, y0 + 500)], "#d94a3d", 13)
    arrow(draw, [(x0 + 145, y0 + 220), (x0 + 460, y0 + 220), (x0 + 550, y0 + 495)], "#f0a33a", 13)
    draw.text((x0 + 45, y0 + 575), "하디: 메이컨 → 오거스타로 판단 변경\n병력이 움직일수록 사바나가 비었다", font=pil_font(26), fill="#3b3022")

    # 3. 그리스월드빌
    x0, y0, _, _ = sequence_panel(draw, panels[2], "3. 그리스월드빌의 오판")
    draw.rectangle((x0 + 355, y0 + 240, x0 + 580, y0 + 285), fill="#164d86")
    draw.text((x0 + 465, y0 + 310), "월컷 여단·방어진지", font=pil_font(25), fill="#211d17", anchor="ma")
    for off in (0, 90, 180):
        arrow(draw, [(x0 + 120 + off, y0 + 500), (x0 + 380 + off // 3, y0 + 300)], "#d94a3d", 12)
    draw.text((x0 + 75, y0 + 190), "필립스는 숙련 보병을\n소규모 하마 기병으로 오판", font=pil_font(27), fill="#6b2821")
    draw.text((x0 + 75, y0 + 580), "세 차례 정면 공격\n남군 약 650명 손실", font=pil_font(27), fill="#3b3022")

    # 4. 보급로와 결말
    x0, y0, _, _ = sequence_panel(draw, panels[3], "4. 포트 맥앨리스터·사바나")
    node(draw, (x0 + 230, y0 + 400), "포트 맥앨리스터", "#f0a33a", size=23)
    node(draw, (x0 + 500, y0 + 300), "사바나", "#d94a3d", size=25)
    arrow(draw, [(x0 + 90, y0 + 500), (x0 + 210, y0 + 420)], "#d94a3d", 14)
    arrow(draw, [(x0 + 570, y0 + 550), (x0 + 280, y0 + 430)], "#2b91b1", 14)
    arrow(draw, [(x0 + 505, y0 + 280), (x0 + 590, y0 + 150)], "#164d86", 13)
    draw.text((x0 + 55, y0 + 145), "하디 철수", font=pil_font(26), fill="#164d86")
    draw.text((x0 + 55, y0 + 570), "헤이즌이 요새 점령\n함대의 정규 보급로가 열림", font=pil_font(27), fill="#3b3022")
    canvas.save(ROOT / "sherman_march_codex_sequence_map.png", quality=95)


def sun_ce_sequence():
    canvas, draw = make_sequence_canvas(
        "손책의 강동 평정 단계별 전략지형도",
        ROOT / "sun_ce_jiangdong_codex_map.png",
    )
    panels = [
        (1015, 115, 1695, 800),
        (1710, 115, 2390, 800),
        (1015, 815, 1695, 1500),
        (1710, 815, 2390, 1500),
    ]
    # 1. 원술의 제한된 지원과 주유의 보강
    x0, y0, _, _ = sequence_panel(draw, panels[0], "1. 작은 출발·주유 합류")
    node(draw, (x0 + 150, y0 + 300), "손책 1,000여 명", "#d94a3d", size=24)
    node(draw, (x0 + 500, y0 + 300), "주유", "#f0a33a", size=25)
    arrow(draw, [(x0 + 460, y0 + 300), (x0 + 210, y0 + 300)], "#f0a33a", 14)
    draw.text((x0 + 75, y0 + 450), "병력·선박·군량이 합쳐져\n도강 가능한 원정군이 됐다", font=pil_font(28), fill="#3b3022")

    # 2. 나루와 창고
    x0, y0, _, _ = sequence_panel(draw, panels[1], "2. 횡강·당리 도하, 우저 장악")
    draw.line((x0 + 50, y0 + 300, x0 + 630, y0 + 300), fill="#4e9bb2", width=55)
    node(draw, (x0 + 180, y0 + 300), "횡강", "#f0a33a", size=23)
    node(draw, (x0 + 360, y0 + 300), "당리", "#f0a33a", size=23)
    node(draw, (x0 + 540, y0 + 470), "우저 창고", "#d94a3d", size=23)
    arrow(draw, [(x0 + 90, y0 + 160), (x0 + 210, y0 + 340), (x0 + 510, y0 + 440)], "#d94a3d", 14)
    draw.text((x0 + 55, y0 + 575), "나루를 연 뒤 유요의 군량·병기를\n다음 공격의 보급으로 전환", font=pil_font(27), fill="#3b3022")

    # 3. 유요와 태사자
    x0, y0, _, _ = sequence_panel(draw, panels[2], "3. 유요가 쓰지 못한 태사자")
    node(draw, (x0 + 160, y0 + 310), "유요", "#164d86", size=25)
    node(draw, (x0 + 500, y0 + 310), "태사자", "#f0a33a", size=25)
    draw.line((x0 + 220, y0 + 310, x0 + 440, y0 + 310), fill="#7a7368", width=8)
    draw.line((x0 + 320, y0 + 260, x0 + 340, y0 + 360), fill="#a5322a", width=10)
    draw.line((x0 + 340, y0 + 260, x0 + 320, y0 + 360), fill="#a5322a", width=10)
    draw.text((x0 + 65, y0 + 455), "허소의 평판을 의식해\n대장 대신 정찰 임무만 맡김", font=pil_font(28), fill="#3b3022")
    draw.text((x0 + 65, y0 + 570), "인재가 없었던 것이 아니라\n권한을 주지 못했다", font=pil_font(27), fill="#6b2821")

    # 4. 사독 우회와 흡수
    x0, y0, _, _ = sequence_panel(draw, panels[3], "4. 손정의 사독 우회·세력 흡수")
    node(draw, (x0 + 150, y0 + 300), "고릉 방어선", "#164d86", size=23)
    node(draw, (x0 + 350, y0 + 500), "사독", "#68c4b5", size=24)
    node(draw, (x0 + 545, y0 + 280), "회계", "#d94a3d", size=25)
    arrow(draw, [(x0 + 90, y0 + 250), (x0 + 330, y0 + 470), (x0 + 520, y0 + 300)], "#68c4b5", 14)
    draw.text((x0 + 65, y0 + 120), "횃불로 정면에 남은 듯 속이고\n사독으로 우회해 왕랑의 후방을 공격", font=pil_font(26), fill="#3b3022")
    draw.text((x0 + 65, y0 + 590), "태사자에게 재량을 줘\n유요 잔병까지 편입", font=pil_font(27), fill="#6b2821")
    canvas.save(ROOT / "sun_ce_jiangdong_codex_sequence_map.png", quality=95)


if __name__ == "__main__":
    sherman_strategy()
    sun_ce_strategy()
    country_maps()
    sherman_sequence()
    sun_ce_sequence()
    print("MAPS_OK: 전략지형도 2장 + 국가 위치도 2장 + 단계판 2장")
