#!/usr/bin/env python3
"""구지편 `謹養而勿勞…` 페이지의 Codex 시각 자료를 후처리한다."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated" / "jiudi12"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
FONT_CJK = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"


def font(size, bold=False):
    return ImageFont.truetype(FONT, size, index=1 if bold else 0)


def cjk_font(size):
    """Apple SD Gothic에 없는 희귀 한자(愬 등)를 포함한 문자열용."""
    return ImageFont.truetype(FONT_CJK, size)


def fit(draw, text, width, size):
    while size > 19 and draw.textbbox((0, 0), text, font=font(size, True))[2] > width:
        size -= 2
    return font(size, True)


def cowpens_commanders():
    im = Image.open(OUT / "cowpens_commanders_source.png").convert("RGB")
    d = ImageDraw.Draw(im)
    d.text((im.width // 2, 45), "카우펜스 전투 — 주요 인물",
           font=fit(d, "카우펜스 전투 — 주요 인물", im.width - 100, 44),
           fill="#f7f0df", anchor="mm")
    y1, y2 = im.height - 125, im.height - 54
    d.text((im.width * .25, y1), "미 대륙군·민병대", font=font(31, True),
           fill="#72bdff", anchor="mm")
    d.text((im.width * .25, y2), "대니얼 모건 · 존 이거 하워드 · 앤드루 피켄스 · 윌리엄 워싱턴",
           font=fit(d, "대니얼 모건 · 존 이거 하워드 · 앤드루 피켄스 · 윌리엄 워싱턴",
                    im.width // 2 - 100, 23), fill="#b9ddff", anchor="mm")
    d.text((im.width * .75, y1), "영국군", font=font(31, True),
           fill="#ff8177", anchor="mm")
    d.text((im.width * .75, y2), "배너스터 탈턴 · 조지 행어 · 아치볼드 맥아더",
           font=fit(d, "배너스터 탈턴 · 조지 행어 · 아치볼드 맥아더",
                    im.width // 2 - 100, 23), fill="#ffb2a9", anchor="mm")
    im.save(OUT / "cowpens_commanders.png", quality=96)


def title(d, width, text, y=44, size=43, fill="#f7f0df"):
    d.text((width // 2, y), text, font=fit(d, text, width - 100, size),
           fill=fill, anchor="mm")


def cowpens_country_map():
    im = Image.open(OUT / "cowpens_country_map_source.png").convert("RGB")
    d = ImageDraw.Draw(im)
    title(d, im.width, "카우펜스 전투 — 1781년 미국 독립전쟁 남부 전역 세력도")
    # 생성형 베이스의 지형 위에 실제 전역을 읽는 데 필요한 거점을 직접 얹는다.
    # 좌표는 장식용 정밀 경계가 아니라 남부 전역의 상대적 위치와 기동축 안내용이다.
    places = [
        (600, 448, "★ 카우펜스(Cowpens)", "#1268aa"),
        (650, 330, "킹스마운틴(Kings Mountain)", "#1268aa"),
        (815, 348, "샬럿(Charlotte)", "#1268aa"),
        (732, 548, "나인티식스(Ninety Six)", "#9d2b28"),
        (930, 505, "캠던(Camden)", "#9d2b28"),
        (1215, 667, "찰스턴(Charleston)", "#9d2b28"),
    ]
    for x, y, label, color in places:
        box = d.textbbox((0, 0), label, font=font(20, True))
        tw, th = box[2] - box[0], box[3] - box[1]
        d.rounded_rectangle((x - tw / 2 - 10, y - th / 2 - 7,
                             x + tw / 2 + 10, y + th / 2 + 7),
                            radius=8, fill="#f6eddacc", outline=color, width=3)
        d.text((x, y), label, font=font(20, True), fill=color, anchor="mm")
    d.text((90, im.height - 45), "파랑: 대륙군·애국파  |  빨강: 영국군·왕당파  |  화살표: 모건과 탈턴의 기동",
           font=font(22, True), fill="#463927", anchor="lm")
    im.save(OUT / "cowpens_country_map.png", quality=96)


def cowpens_strategy_map():
    im = Image.open(OUT / "cowpens_strategy_map_source.png").convert("RGB")
    d = ImageDraw.Draw(im)
    title(d, im.width, "카우펜스 전투 전략지형도 — 세 겹 방어와 역포위")
    labels = [
        ("모건의 설계", "척후·민병대 두 발 사격 뒤 철수"),
        ("결정적 오해", "영국군은 계획된 후퇴를 패주로 판단"),
        ("반격", "대륙군 선회·일제사격, 기병·민병대 포위"),
    ]
    for i, (h, body) in enumerate(labels):
        x = int((i + .5) * im.width / 3)
        d.text((x, im.height - 92), h, font=font(25, True),
               fill=("#78bfff", "#ffd17a", "#78bfff")[i], anchor="mm")
        d.text((x, im.height - 48), body, font=fit(d, body, im.width // 3 - 45, 20),
               fill="#edf1f3", anchor="mm")
    im.save(OUT / "cowpens_strategy_map.png", quality=96)


def cowpens_sequence():
    im = Image.open(OUT / "cowpens_sequence_source.png").convert("RGB")
    d = ImageDraw.Draw(im)
    title(d, im.width, "카우펜스 전투 — 단계별 흐름", y=48)
    labels = ["1. 휴식·세 겹 방어 준비", "2. 두 발 사격 뒤 계획 철수",
              "3. 선회 명령의 오해·돌아서 반격", "4. 기병·민병대의 이중 포위"]
    for i, label in enumerate(labels):
        x = int((i + .5) * im.width / 4)
        d.text((x, 163), label, font=fit(d, label, im.width // 4 - 55, 21),
               fill="#493921", anchor="mm")
    im.save(OUT / "cowpens_sequence_map.png", quality=96)


def rounded_box(d, xy, heading, body, fill, color):
    d.rounded_rectangle(xy, 16, fill=fill, outline="#333b40", width=4)
    cx = (xy[0] + xy[2]) // 2
    d.text((cx, xy[1] + 35), heading, font=fit(d, heading, xy[2]-xy[0]-25, 26),
           fill=color, anchor="mm")
    d.multiline_text((cx, xy[1] + 82), body, font=font(18), fill="#40464a",
                     anchor="mm", align="center", spacing=4)


def link(d, a, b, color, dashed=False):
    if dashed:
        steps = 6
        for i in range(steps):
            if i % 2 == 0:
                x1 = a[0] + (b[0]-a[0]) * i/steps
                y1 = a[1] + (b[1]-a[1]) * i/steps
                x2 = a[0] + (b[0]-a[0]) * (i+1)/steps
                y2 = a[1] + (b[1]-a[1]) * (i+1)/steps
                d.line((x1,y1,x2,y2), fill=color, width=5)
    else:
        d.line((*a,*b), fill=color, width=6)
    d.polygon([(b[0]-10,b[1]-17),(b[0]+10,b[1]-17),b], fill=color)


def cowpens_command_structure():
    im = Image.new("RGB", (1600, 1020), "#f3ead5")
    d = ImageDraw.Draw(im)
    d.rectangle((0,0,1600,112), fill="#202b34")
    title(d, 1600, "카우펜스 전투 — 장군 조직도와 작전 편제")
    d.text((800,84),"실선: 지휘  ·  점선: 유인·철수 후 재결합",font=font(21),fill="#cbd3d8",anchor="mm")
    d.line((800,135,800,970),fill="#b7aa90",width=4)
    d.text((390,155),"미 대륙군·민병대",font=font(32,True),fill="#176bac",anchor="mm")
    d.text((1210,155),"영국군",font=font(32,True),fill="#b62c28",anchor="mm")
    rounded_box(d,(190,195,590,315),"대니얼 모건","전체 설계·세 겹 방어\n민병대의 퇴로를 미리 허용","#bcd9ec","#1268aa")
    for x in (180,390,600): link(d,(390,315),(x,390),"#315f78")
    rounded_box(d,(40,390,320,520),"척후 사수대","맥도웰·커닝엄\n첫 타격 뒤 철수","#dcebf3","#1268aa")
    rounded_box(d,(340,390,620,520),"앤드루 피켄스","민병대 제2선\n두 발 사격 뒤 후퇴","#dcebf3","#1268aa")
    rounded_box(d,(640,390,780,520),"존 하워드","대륙군 제3선\n주 방어·총검 반격","#dcebf3","#1268aa")
    rounded_box(d,(220,650,600,775),"윌리엄 워싱턴","후방 구릉에 숨긴 기병\n측후방 반격·추격","#cce1ef","#1268aa")
    link(d,(390,315),(410,650),"#315f78",True)
    rounded_box(d,(1010,195,1410,315),"배너스터 탈턴","영국군 총지휘\n도착 직후 전개·연속 공격","#e9c9bd","#b52d29")
    for x in (990,1210,1430): link(d,(1210,315),(x,390),"#7b4033")
    rounded_box(d,(835,390,1125,520),"영국군 제7연대","정면 주공\n민병대 추격","#f1ddd4","#b52d29")
    rounded_box(d,(1140,390,1430,520),"맥아더·71연대","예비대\n미군 측면 압박","#f1ddd4","#b52d29")
    rounded_box(d,(1310,650,1570,775),"영국군단 기병","측면·추격 임무\n워싱턴 기병과 교전","#f1ddd4","#b52d29")
    link(d,(1210,315),(1440,650),"#7b4033")
    d.rounded_rectangle((160,865,1440,955),16,fill="#fff8e8",outline="#816d49",width=4)
    d.text((800,900),"승패를 가른 편제 차이",font=font(25,True),fill="#554525",anchor="mm")
    d.text((800,935),"모건은 약한 민병대를 ‘두 발 뒤 철수’라는 역할로 살렸고, 탈턴은 지친 부대를 한꺼번에 추격에 밀어 넣었다.",
           font=fit(d,"모건은 약한 민병대를 ‘두 발 뒤 철수’라는 역할로 살렸고, 탈턴은 지친 부대를 한꺼번에 추격에 밀어 넣었다.",1200,22),
           fill="#45413a",anchor="mm")
    im.save(OUT / "cowpens_command_structure.png", quality=96)


def caizhou_commanders():
    im = Image.open(OUT / "caizhou_commanders_source.png").convert("RGB")
    d = ImageDraw.Draw(im)
    title(d, im.width, "이소의 설야입채주 — 주요 인물")
    y1, y2 = im.height - 125, im.height - 54
    d.text((im.width * .25, y1), "당 조정군", font=font(31, True),
           fill="#72bdff", anchor="mm")
    d.text((im.width * .25, y2), "이소(李愬) · 이우(李祐) · 오수림(吳秀琳) · 정사량(丁士良)",
           font=cjk_font(22), fill="#b9ddff", anchor="mm")
    d.text((im.width * .75, y1), "회서 번진", font=font(31, True),
           fill="#ff8177", anchor="mm")
    d.text((im.width * .75, y2), "오원제(吳元濟) · 동중질(董重質) · 채주 수비군",
           font=fit(d, "오원제(吳元濟) · 동중질(董重質) · 채주 수비군",
                    im.width // 2 - 100, 23), fill="#ffb2a9", anchor="mm")
    im.save(OUT / "caizhou_commanders.png", quality=96)


def caizhou_country_map():
    im = Image.open(OUT / "caizhou_country_map_source.png").convert("RGB")
    d = ImageDraw.Draw(im)
    title(d, im.width, "설야입채주 — 817년 당·회서 전역 세력도")
    places = [
        (205, 352, "장안(長安)", "#5e5546"),
        (345, 226, "낙양(洛陽)", "#5e5546"),
        (438, 548, "당주(唐州)", "#1268aa"),
        (615, 455, "문성책(文城柵)", "#1268aa"),
        (880, 505, "장시촌(張柴村)", "#1268aa"),
        (1225, 470, "★ 채주(蔡州)", "#9d2b28"),
        (1455, 286, "회곡(洄曲)", "#9d2b28"),
    ]
    for x, y, label, color in places:
        box = d.textbbox((0, 0), label, font=font(20, True))
        tw, th = box[2] - box[0], box[3] - box[1]
        d.rounded_rectangle((x - tw / 2 - 10, y - th / 2 - 7,
                             x + tw / 2 + 10, y + th / 2 + 7),
                            radius=8, fill="#f6edda", outline=color, width=3)
        d.text((x, y), label, font=font(20, True), fill=color, anchor="mm")
    d.text((90, im.height - 45),
           "파랑: 당 조정군  |  빨강: 오원제의 회서 번진  |  화살표: 문성책→장시촌→채주 비밀 행군",
           font=font(22, True), fill="#463927", anchor="lm")
    im.save(OUT / "caizhou_country_map.png", quality=96)


def caizhou_strategy_map():
    im = Image.open(OUT / "caizhou_strategy_map_source.png").convert("RGB")
    d = ImageDraw.Draw(im)
    title(d, im.width, "설야입채주 전략지형도 — 비밀 행군과 무방비한 중심")
    points = [
        (150, 445, "문성책(文城柵)", "#72bdff"),
        (845, 435, "장시촌(張柴村)", "#72bdff"),
        (1465, 250, "채주성(蔡州城)", "#ff8177"),
        (1240, 575, "거위·오리 못", "#72bdff"),
        (1460, 675, "회곡(洄曲) 방면", "#ff8177"),
    ]
    for x, y, label, color in points:
        d.rounded_rectangle((x - 92, y - 23, x + 92, y + 23),
                            radius=8, fill="#172532", outline=color, width=3)
        d.text((x, y), label, font=fit(d, label, 168, 19), fill=color, anchor="mm")
    labels = [
        ("정보와 기밀", "귀순 장수를 길잡이로 삼고 목적지는 출발 뒤 공개"),
        ("증원 차단", "장시촌 확보·회곡 방향 교량 파괴"),
        ("중심 급습", "외곽 주력이 비운 채주를 눈보라 속에서 돌파"),
    ]
    for i, (h, body) in enumerate(labels):
        x = int((i + .5) * im.width / 3)
        d.text((x, im.height - 92), h, font=font(25, True),
               fill=("#78bfff", "#ffd17a", "#78bfff")[i], anchor="mm")
        d.text((x, im.height - 48), body,
               font=fit(d, body, im.width // 3 - 45, 20),
               fill="#edf1f3", anchor="mm")
    im.save(OUT / "caizhou_strategy_map.png", quality=96)


def caizhou_sequence():
    im = Image.open(OUT / "caizhou_sequence_source.png").convert("RGB")
    d = ImageDraw.Draw(im)
    title(d, im.width, "이소의 설야입채주 — 단계별 흐름", y=48)
    labels = [
        "1. 귀순 장수를 살려 정보망 완성",
        "2. 문성책 출발·목표 비공개",
        "3. 장시촌 장악·교량 차단",
        "4. 눈보라 속 채주성 돌입",
    ]
    for i, label in enumerate(labels):
        x = int((i + .5) * im.width / 4)
        d.text((x, 163), label, font=fit(d, label, im.width // 4 - 55, 21),
               fill="#493921", anchor="mm")
    im.save(OUT / "caizhou_sequence_map.png", quality=96)


def caizhou_command_structure():
    im = Image.new("RGB", (1600, 1020), "#f3ead5")
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 1600, 112), fill="#202b34")
    title(d, 1600, "설야입채주 — 장군 조직도와 작전 편제")
    d.text((800, 84), "실선: 지휘  ·  점선: 귀순·정보 제공·재편입",
           font=font(21), fill="#cbd3d8", anchor="mm")
    d.line((800, 135, 800, 970), fill="#b7aa90", width=4)
    d.text((390, 155), "당 조정군", font=font(32, True),
           fill="#176bac", anchor="mm")
    d.text((1210, 155), "회서 번진", font=font(32, True),
           fill="#b62c28", anchor="mm")
    rounded_box(d, (190, 195, 590, 315), "이소(李愬)",
                "당수등절도사\n포로 회유·정보 통합·비밀 기습",
                "#bcd9ec", "#1268aa")
    # rounded_box의 기본 한글 글꼴에는 愬가 없어 제목만 완전한 CJK 글꼴로 덮는다.
    d.rectangle((205, 211, 575, 252), fill="#bcd9ec")
    d.text((390, 231), "이소(李愬)", font=cjk_font(25),
           fill="#1268aa", anchor="mm")
    rounded_box(d, (40, 390, 320, 520), "이우(李祐)",
                "회서 출신 귀순장\n선봉·길 안내·성벽 돌파",
                "#dcebf3", "#1268aa")
    rounded_box(d, (340, 390, 620, 520), "오수림(吳秀琳)",
                "문성책 귀순\n이우를 써야 한다고 천거",
                "#dcebf3", "#1268aa")
    rounded_box(d, (640, 390, 780, 520), "정사량(丁士良)",
                "포로에서 귀순\n회서 내부 정보 제공",
                "#dcebf3", "#1268aa")
    for x in (180, 480, 710):
        link(d, (390, 315), (x, 390), "#315f78")
    rounded_box(d, (220, 650, 600, 775), "분견대",
                "장시촌 주둔·증원 차단\n회곡 방향 교량 파괴",
                "#cce1ef", "#1268aa")
    link(d, (390, 315), (410, 650), "#315f78")
    rounded_box(d, (1010, 195, 1410, 315), "오원제(吳元濟)",
                "회서 지배자·채주 본거지\n외곽 전선 의존·도성 경계 소홀",
                "#e9c9bd", "#b52d29")
    rounded_box(d, (875, 390, 1165, 520), "채주 수비군",
                "본거지 방어\n눈보라 속 기습에 대비 못함",
                "#f1ddd4", "#b52d29")
    rounded_box(d, (1200, 390, 1490, 520), "동중질(董重質)",
                "회곡 외곽 주력\n채주 구원로와 떨어짐",
                "#f1ddd4", "#b52d29")
    link(d, (1210, 315), (1020, 390), "#7b4033")
    link(d, (1210, 315), (1345, 390), "#7b4033")
    d.rounded_rectangle((160, 865, 1440, 955), 16,
                        fill="#fff8e8", outline="#816d49", width=4)
    d.text((800, 900), "승패를 가른 지휘 구조", font=font(25, True),
           fill="#554525", anchor="mm")
    d.text((800, 935),
           "이소는 귀순자를 처벌 대상이 아니라 정보·선봉 체계로 편입했고, 오원제는 외곽 주력과 본거지 경계를 분리한 채 기습 가능성을 낮게 보았다.",
           font=fit(d, "이소는 귀순자를 처벌 대상이 아니라 정보·선봉 체계로 편입했고, 오원제는 외곽 주력과 본거지 경계를 분리한 채 기습 가능성을 낮게 보았다.",
                    1200, 22), fill="#45413a", anchor="mm")
    im.save(OUT / "caizhou_command_structure.png", quality=96)


if __name__ == "__main__":
    cowpens_commanders()
    cowpens_command_structure()
    cowpens_country_map()
    cowpens_strategy_map()
    cowpens_sequence()
    caizhou_commanders()
    caizhou_command_structure()
    caizhou_country_map()
    caizhou_strategy_map()
    caizhou_sequence()
