from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
BASES = ROOT / "generated_bases"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"


def font(size, bold=False):
    return ImageFont.truetype(FONT, size=size, index=7 if bold else 0)


def arrow(draw, points, color, width=28, head=52, dash=False):
    if dash:
        for a, b in zip(points[:-1], points[1:]):
            x1, y1 = a
            x2, y2 = b
            steps = 12
            for i in range(0, steps, 2):
                t1, t2 = i / steps, min((i + 1) / steps, 1)
                draw.line(
                    (x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1,
                     x1 + (x2 - x1) * t2, y1 + (y2 - y1) * t2),
                    fill=color, width=width,
                )
    else:
        draw.line(points, fill=color, width=width, joint="curve")
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    dx, dy = x2 - x1, y2 - y1
    mag = max((dx * dx + dy * dy) ** 0.5, 1)
    ux, uy = dx / mag, dy / mag
    px, py = -uy, ux
    tip = (x2, y2)
    left = (x2 - ux * head + px * head * 0.55, y2 - uy * head + py * head * 0.55)
    right = (x2 - ux * head - px * head * 0.55, y2 - uy * head - py * head * 0.55)
    draw.polygon([tip, left, right], fill=color)


def label(draw, xy, text, fill, anchor="mm", size=42):
    f = font(size, True)
    box = draw.textbbox(xy, text, font=f, anchor=anchor, stroke_width=3)
    pad = 14
    draw.rounded_rectangle(
        (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad),
        radius=18, fill=(15, 15, 15, 205), outline=fill, width=4,
    )
    draw.text(xy, text, font=f, fill="white", anchor=anchor, stroke_width=2, stroke_fill="black")


def make_canvas(base_name, title, subtitle):
    base = Image.open(BASES / base_name).convert("RGB").resize((2300, 2740), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (2400, 3200), "#e8dfca")
    canvas.paste(base, (50, 230))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, 0, 2400, 230), fill="#17130e")
    draw.text((1200, 78), title, font=font(72, True), fill="#f5d36c", anchor="mm")
    draw.text((1200, 164), subtitle, font=font(37), fill="#f5f0e8", anchor="mm")
    return canvas, draw


def footer(draw, left, middle, right):
    y0, y1 = 2985, 3170
    items = [
        (45, 780, "#a72d2d", left),
        (820, 1580, "#5c4b36", middle),
        (1620, 2355, "#225ea8", right),
    ]
    for x0, x1, color, text in items:
        draw.rounded_rectangle((x0, y0, x1, y1), 24, fill=(250, 247, 239, 245), outline=color, width=6)
        draw.multiline_text(((x0 + x1) / 2, y0 + 92), text, font=font(34, True), fill="#1d1a16",
                            anchor="mm", align="center", spacing=8)


def tannenberg():
    im, d = make_canvas(
        "tannenberg_codex_base.png",
        "탄넨베르크 전투 전략지형도",
        "1914년 8월 26–30일 · 동프로이센 · Codex판 개략도",
    )
    red, blue, amber = "#bd3030", "#225ea8", "#e49a22"
    # Russian Second Army advances north into the pocket.
    arrow(d, [(1050, 2760), (1080, 2350), (1120, 1940), (1160, 1580)], red, 34, 68)
    arrow(d, [(770, 2640), (820, 2260), (900, 1900)], red, 25, 54)
    label(d, (980, 2470), "삼소노프 제2군\n북상·전선 신장", red, size=39)
    # German I Corps closes from southwest; XVII and I Reserve close from northeast.
    arrow(d, [(280, 2260), (560, 2360), (850, 2250), (1020, 2110)], blue, 35, 70)
    arrow(d, [(1880, 760), (1710, 1060), (1510, 1370), (1310, 1690)], blue, 35, 70)
    arrow(d, [(1900, 1250), (1680, 1510), (1450, 1810), (1260, 2040)], blue, 29, 62)
    label(d, (510, 2180), "프랑수아 제1군단\n나이덴부르크 차단", blue, size=35)
    label(d, (1720, 1170), "독일 북익\n포위망 폐쇄", blue, size=36)
    # Rennenkampf remains separated beyond lake belt.
    arrow(d, [(2110, 480), (2050, 690), (2010, 860)], red, 23, 48, dash=True)
    label(d, (1990, 440), "레넨캄프 제1군\n호수대 너머 분리", red, size=34)
    d.ellipse((920, 1830, 1410, 2340), outline=amber, width=18)
    label(d, (1160, 2085), "포위·지휘 붕괴", amber, size=42)
    footer(
        d,
        "패군\n상하불상수\n통신·군단 결집 실패",
        "핵심\n마수리안 호수대와 철도\n독일군 내선 집중",
        "승군\n합어리이동\n노출된 제2군만 선택 타격",
    )
    im.save(ROOT / "tannenberg_codex_map.png", quality=95)


def maling():
    im, d = make_canvas(
        "maling_codex_base.png",
        "마릉 전투 전략지형도",
        "기원전 342년경 · 전통적 협곡설 기반 · Codex판 개략도",
    )
    red, blue, amber = "#b83535", "#2469a8", "#e9a126"
    # Qi feigned retreat deeper into pass.
    arrow(d, [(1950, 2700), (1660, 2440), (1400, 2110), (1190, 1740), (980, 1390)], blue, 25, 54, dash=True)
    label(d, (1710, 2480), "제군 위장후퇴\n감소한 아궁이", blue, size=38)
    # Wei elite pursuit.
    arrow(d, [(2090, 2820), (1780, 2530), (1510, 2220), (1260, 1840), (1080, 1510)], red, 36, 72)
    label(d, (1860, 2790), "방연의 정예 추격대\n보병과 분리", red, size=38)
    # Crossbow ambush from both ridges into kill zone.
    for start in [(480, 1180), (560, 1450), (1770, 1000), (1690, 1320)]:
        arrow(d, [start, (1110, 1500)], blue, 22, 48)
    label(d, (520, 1040), "제군 복병·노수", blue, size=36)
    label(d, (1760, 890), "제군 복병·노수", blue, size=36)
    d.ellipse((900, 1320, 1320, 1730), outline=amber, width=18)
    label(d, (1110, 1530), "협곡 살상지대", amber, size=42)
    footer(
        d,
        "패군\n졸리이부집\n정예 선행·본대 분리",
        "주의\n정확한 전장 위치는 논쟁적\n전통 사료의 협곡 묘사",
        "승군\n합어리이동\n밤·협로·매복 조건 완성 후 공격",
    )
    im.save(ROOT / "maling_codex_map.png", quality=95)


if __name__ == "__main__":
    tannenberg()
    maling()
