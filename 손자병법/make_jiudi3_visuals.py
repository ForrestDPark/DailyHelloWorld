#!/usr/bin/env python3
"""구지편 3구절 시각 자료의 정확한 한글 레이어를 만든다."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated" / "jiudi3"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"


def font(size, bold=False):
    return ImageFont.truetype(FONT, size, index=1 if bold else 0)


def fit(draw, text, width, size):
    while size > 20 and draw.textbbox((0, 0), text, font=font(size, True))[2] > width:
        size -= 2
    return font(size, True)


def label_breitenfeld_commanders():
    src = Image.open(OUT / "breitenfeld_commanders_source.png").convert("RGB")
    d = ImageDraw.Draw(src)
    d.text(
        (src.width // 2, 54),
        "브라이텐펠트 전투 — 주요 인물",
        font=fit(d, "브라이텐펠트 전투 — 주요 인물", src.width - 120, 47),
        fill="#f7f0df",
        anchor="mm",
    )
    y1, y2 = src.height - 125, src.height - 56
    d.text((src.width * 0.25, y1), "스웨덴·작센 연합군", font=font(32, True),
           fill="#72bdff", anchor="mm")
    d.text((src.width * 0.25, y2), "구스타브 2세 아돌프 · 호른 · 바네르 · 요한 게오르크 1세",
           font=fit(d, "구스타브 2세 아돌프 · 호른 · 바네르 · 요한 게오르크 1세",
                    src.width // 2 - 100, 24), fill="#b9ddff", anchor="mm")
    d.text((src.width * 0.75, y1), "가톨릭 동맹군", font=font(32, True),
           fill="#ff8177", anchor="mm")
    d.text((src.width * 0.75, y2), "틸리 백작 · 파펜하임 · 퓌르스텐베르크",
           font=fit(d, "틸리 백작 · 파펜하임 · 퓌르스텐베르크",
                    src.width // 2 - 100, 24), fill="#ffb2a9", anchor="mm")
    src.save(OUT / "breitenfeld_commanders.png", quality=96)


def box(d, xy, title, subtitle, fill, title_fill):
    d.rounded_rectangle(xy, 18, fill=fill, outline="#303942", width=4)
    cx = (xy[0] + xy[2]) // 2
    d.text((cx, xy[1] + 38), title, font=fit(d, title, xy[2] - xy[0] - 30, 28),
           fill=title_fill, anchor="mm")
    d.multiline_text((cx, xy[1] + 82), subtitle, font=font(19),
                     fill="#3f4549", anchor="mm", align="center", spacing=5)


def arrow(d, start, end, fill, dashed=False):
    if dashed:
        y = start[1]
        while y < end[1] - 14:
            d.line((start[0], y, end[0], min(y + 16, end[1])), fill=fill, width=5)
            y += 29
    else:
        d.line((*start, *end), fill=fill, width=6)
    d.polygon([(end[0] - 10, end[1] - 18), (end[0] + 10, end[1] - 18), end], fill=fill)


def breitenfeld_command_structure():
    im = Image.new("RGB", (1600, 1050), "#f3ead5")
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 1600, 115), fill="#202b34")
    d.text((800, 45), "브라이텐펠트 전투 — 장군 조직도와 작전 편제",
           font=fit(d, "브라이텐펠트 전투 — 장군 조직도와 작전 편제", 1480, 45),
           fill="#f7f1e3", anchor="mm")
    d.text((800, 88), "실선: 지휘  ·  점선: 독단 행동/동맹 협조",
           font=font(22), fill="#cbd3d8", anchor="mm")
    d.line((800, 140, 800, 990), fill="#b6a88c", width=4)
    d.text((390, 160), "스웨덴·작센 연합군", font=font(34, True), fill="#1667aa", anchor="mm")
    d.text((1210, 160), "가톨릭 동맹군", font=font(34, True), fill="#b52927", anchor="mm")
    box(d, (190, 205, 590, 330), "구스타브 2세 아돌프", "연합군 총지휘\n스웨덴군 중앙·예비대 통제", "#bcd9ec", "#1268aa")
    box(d, (1010, 205, 1410, 330), "틸리 백작", "가톨릭 동맹군 총사령관\n테르시오 중앙 지휘", "#e9c9bd", "#b52d29")
    for x in (300, 480):
        arrow(d, (390, 330), (x, 405), "#315f78")
    box(d, (85, 405, 405, 540), "구스타브 호른", "좌익 지휘\n작센군 붕괴 뒤 측면 방어", "#d9e9f2", "#1268aa")
    box(d, (430, 405, 750, 540), "요한 바네르", "기병·예비 전력\n전열 재편과 반격 지원", "#d9e9f2", "#1268aa")
    arrow(d, (390, 330), (390, 650), "#8b6d34", True)
    box(d, (190, 650, 590, 785), "요한 게오르크 1세", "작센 선제후\n동맹군 좌익·정치적 결합", "#f3dfaa", "#73581f")
    arrow(d, (1210, 330), (1060, 405), "#7b4033", True)
    arrow(d, (1210, 330), (1360, 405), "#7b4033")
    box(d, (875, 405, 1195, 540), "파펜하임", "좌익 기병 지휘\n명령 전 반복 돌격", "#f1ddd4", "#b52d29")
    box(d, (1220, 405, 1540, 540), "퓌르스텐베르크", "우익 지휘\n작센군을 밀어냄", "#f1ddd4", "#b52d29")
    arrow(d, (1035, 540), (1035, 665), "#7b4033")
    box(d, (855, 665, 1215, 800), "좌익 기병 7회 돌격", "스웨덴 우익을 무너뜨리지 못하고\n전열에서 멀어짐", "#f7e7de", "#b52d29")
    arrow(d, (1380, 540), (1380, 665), "#7b4033")
    box(d, (1230, 665, 1530, 800), "우익·테르시오", "작센군 추격에 치우쳐\n중앙과 간격 발생", "#f7e7de", "#b52d29")
    d.rounded_rectangle((150, 875, 1450, 970), 18, fill="#fff8e8", outline="#816d49", width=4)
    d.text((800, 910), "승패를 가른 지휘 차이", font=font(26, True), fill="#554525", anchor="mm")
    d.text((800, 948), "연합군은 예비대로 무너진 측면을 바꿔 세웠고, 동맹군은 독단 돌격과 추격으로 지휘 연결이 끊겼다.",
           font=fit(d, "연합군은 예비대로 무너진 측면을 바꿔 세웠고, 동맹군은 독단 돌격과 추격으로 지휘 연결이 끊겼다.", 1200, 23),
           fill="#45413a", anchor="mm")
    im.save(OUT / "breitenfeld_command_structure.png", quality=96)


if __name__ == "__main__":
    label_breitenfeld_commanders()
    breitenfeld_command_structure()
