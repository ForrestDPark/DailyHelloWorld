#!/usr/bin/env python3
"""알레시아의 생성형 원화 네 장에 정확한 한국어 정보 계층을 입힌다."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "generated" / "jiudi14"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"


def f(size, bold=False):
    return ImageFont.truetype(FONT, size, index=1 if bold else 0)


def fit(draw, text, width, size=30, bold=True):
    while size > 13 and draw.textbbox((0, 0), text, font=f(size, bold))[2] > width:
        size -= 1
    return f(size, bold)


def plaque(draw, xy, text, color="#342b20", fill="#f3e4c6e8", size=25):
    x, y, w = xy
    font = fit(draw, text, w - 20, size)
    bb = draw.textbbox((0, 0), text, font=font)
    h = bb[3] - bb[1] + 20
    draw.rounded_rectangle((x-w/2, y-h/2, x+w/2, y+h/2), 10,
                           fill=fill, outline=color, width=3)
    draw.text((x, y), text, font=font, fill=color, anchor="mm")


def country():
    im = Image.open(OUT / "alesia_country_map_source_v2.png").convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle((0, 0, im.width, 100), fill=(25, 34, 41, 225))
    d.text((im.width/2, 38), "알레시아 공방전 — 기원전 52년 갈리아 부족·로마 세력도",
           font=fit(d, "알레시아 공방전 — 기원전 52년 갈리아 부족·로마 세력도", im.width-100, 38),
           fill="#fff1d3", anchor="mm")
    d.text((im.width/2, 75), "부족 세력권은 지형을 따라 번지고, 화살표는 알레시아로 모인 두 작전축을 나타낸다",
           font=fit(d, "부족 세력권은 지형을 따라 번지고, 화살표는 알레시아로 모인 두 작전축을 나타낸다", im.width-120, 19, False),
           fill="#d2d9dd", anchor="mm")
    labels = [
        (820, 355, "알레시아(Alesia)", "#5c3519", 250),
        (665, 490, "비브락테(Bibracte)", "#5c3519", 270),
        (985, 450, "아르베르니", "#9b2d29", 210),
        (690, 245, "아이두이", "#8a6734", 180),
        (455, 230, "아르모리카 부족권", "#9b2d29", 250),
        (1290, 690, "로마 속주 나르보넨시스", "#1268aa", 350),
        (1320, 365, "라인강(Rhine)", "#1268aa", 220),
        (1005, 800, "론강(Rhone)", "#1268aa", 190),
        (770, 175, "센·마른 방면 구원군 집결", "#9b2d29", 340),
    ]
    for x, y, text, color, width in labels:
        plaque(d, (x, y, width), text, color, size=22)
    d.line((1260, 680, 850, 390), fill="#1268aa", width=9)
    d.polygon([(850,390),(875,392),(860,415)], fill="#1268aa")
    d.line((800, 205, 835, 330), fill="#aa342e", width=9)
    d.polygon([(835,330),(817,310),(844,307)], fill="#aa342e")
    d.rounded_rectangle((40, im.height-82, im.width-40, im.height-25), 12,
                        fill=(245,232,201,225), outline="#725c38", width=3)
    d.text((im.width/2, im.height-54),
           "붉은·적갈색: 반로마 연합 및 봉기 확산권  |  황갈색: 중립·동요 부족  |  파랑: 로마 속주와 카이사르 진격",
           font=fit(d, "붉은·적갈색: 반로마 연합 및 봉기 확산권  |  황갈색: 중립·동요 부족  |  파랑: 로마 속주와 카이사르 진격", im.width-120, 21),
           fill="#493921", anchor="mm")
    im.save(OUT / "alesia_country_map.png", quality=96)


def command():
    im = Image.open(OUT / "alesia_command_structure_source_v2.png").convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    title = "알레시아 — 장군 조직도와 안팎 공방 편제"
    d.rectangle((310, 8, im.width-310, 70), fill=(25,34,41,220))
    d.text((im.width/2, 39), title, font=fit(d,title,im.width-680,34),
           fill="#fff1d3",anchor="mm")
    for x,y,t,c,w in [
        (395,215,"율리우스 카이사르\n총사령관·기동예비 통제","#1268aa",290),
        (245,440,"티투스 라비에누스\n레아산 취약부 방어","#1268aa",260),
        (520,440,"가이우스 트레보니우스\n군단 진지 지휘","#1268aa",270),
        (1285,215,"베르킨게토릭스\n성내군 총지휘","#9b2d29",280),
        (1150,440,"코미우스\n외부 구원군 공동지휘","#9b2d29",240),
        (1435,440,"베르카시벨라우누스\n6만 정예·레아산 우회","#9b2d29",300),
        (240,785,"공병·토목대\n참호·목책·함정 유지","#1268aa",260),
        (535,785,"게르만 기병 예비\n구원군 측후방 타격","#1268aa",280),
        (1290,785,"부족별 구원군\n성내군과 통신 단절","#9b2d29",300),
    ]:
        plaque(d,(x,y,w),t,c,size=20)
    im.save(OUT / "alesia_command_structure.png", quality=96)


def strategy():
    im = Image.open(OUT / "alesia_strategy_source_v2.png").convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle((260, 8, im.width-260, 72), fill=(25,34,41,220))
    t = "알레시아 전략지형도 — 두 겹의 포위선과 레아산의 결정적 약점"
    d.text((im.width/2,40),t,font=fit(d,t,im.width-600,34),fill="#fff1d3",anchor="mm")
    for x,y,text,color,w in [
        (825,265,"알레시아 고지·성내군","#9b2d29",270),
        (620,470,"내향 포위선 — 성내 돌파 차단","#1268aa",330),
        (650,725,"외향 방어선 — 구원군 차단","#1268aa",330),
        (215,155,"레아산(Mont Rea)\n외벽이 능선까지 닿지 못한 취약부","#9b2d29",360),
        (1415,150,"게르만 기병의 대회전\n구원군 측후방 붕괴","#9b7a22",320),
        (1420,800,"카이사르·라비에누스 예비 투입","#1268aa",350),
        (300,855,"참호·목책·함정이 병력 열세를 대신함","#5b4729",390),
    ]:
        plaque(d,(x,y,w),text,color,size=20)
    im.save(OUT / "alesia_strategy_map.png", quality=96)


def sequence():
    im = Image.open(OUT / "alesia_sequence_source_v2.png").convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    headings = [
        ("1. 패전 뒤 알레시아 입성","기병을 밖으로 보내\n갈리아 전역에 구원을 청하다"),
        ("2. 포위선이 두 겹이 되다","안쪽은 성을 굶기고\n바깥쪽은 구원군을 막다"),
        ("3. 레아산에서 안팎이 맞물리다","베르카시벨라우누스의 우회와\n베르킨게토릭스의 출격"),
        ("4. 예비와 기병이 전선을 뒤집다","카이사르·라비에누스가 버티고\n게르만 기병이 후방을 치다"),
    ]
    panel = im.width/4
    for i,(h,b) in enumerate(headings):
        x=(i+.5)*panel
        d.text((x,66),h,font=fit(d,h,panel-55,23),fill="#4b3420",anchor="mm")
        d.multiline_text((x,im.height-73),b,font=fit(d,b.split("\n")[0],panel-55,18,False),
                         fill="#4b3420",anchor="mm",align="center",spacing=4)
    im.save(OUT / "alesia_sequence_map.png", quality=96)


if __name__ == "__main__":
    country()
    command()
    strategy()
    sequence()
