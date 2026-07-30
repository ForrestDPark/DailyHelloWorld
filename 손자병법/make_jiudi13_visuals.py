#!/usr/bin/env python3
"""구지편 `死焉不得…` 페이지의 전투별 시각 자료를 합성한다."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated" / "jiudi13"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"


def font(size, bold=False):
    return ImageFont.truetype(FONT, size, index=1 if bold else 0)


def fit(draw, text, width, size, bold=True):
    while size > 16 and draw.textbbox((0, 0), text, font=font(size, bold))[2] > width:
        size -= 2
    return font(size, bold)


def title(draw, width, text, y=48, size=44):
    draw.text((width // 2, y), text,
              font=fit(draw, text, width - 100, size),
              fill="#f7f0df", anchor="mm")


def label_box(draw, x, y, text, color, max_width=260):
    f = fit(draw, text, max_width - 18, 21)
    box = draw.textbbox((0, 0), text, font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    draw.rounded_rectangle((x-w/2-9, y-h/2-6, x+w/2+9, y+h/2+6),
                           8, fill="#f5ecd9", outline=color, width=3)
    draw.text((x, y), text, font=f, fill=color, anchor="mm")


def commanders(source, output, heading, left_title, left_names, right_title, right_names):
    im = Image.open(OUT / source).convert("RGB")
    d = ImageDraw.Draw(im)
    title(d, im.width, heading)
    y1, y2 = im.height - 125, im.height - 54
    d.text((im.width*.25, y1), left_title, font=font(31, True),
           fill="#72bdff", anchor="mm")
    d.text((im.width*.25, y2), left_names,
           font=fit(d, left_names, im.width//2-95, 23),
           fill="#b9ddff", anchor="mm")
    d.text((im.width*.75, y1), right_title, font=font(31, True),
           fill="#ff8177", anchor="mm")
    d.text((im.width*.75, y2), right_names,
           font=fit(d, right_names, im.width//2-95, 23),
           fill="#ffb2a9", anchor="mm")
    im.save(OUT / output, quality=96)


def rounded_box(d, xy, heading, body, fill, color):
    d.rounded_rectangle(xy, 16, fill=fill, outline="#333b40", width=4)
    cx = (xy[0] + xy[2]) // 2
    d.text((cx, xy[1]+34), heading,
           font=fit(d, heading, xy[2]-xy[0]-22, 25),
           fill=color, anchor="mm")
    d.multiline_text((cx, xy[1]+82), body, font=font(18),
                     fill="#40464a", anchor="mm", align="center", spacing=4)


def link(d, a, b, color, dashed=False):
    if dashed:
        for i in range(0, 8, 2):
            x1 = a[0] + (b[0]-a[0])*i/8
            y1 = a[1] + (b[1]-a[1])*i/8
            x2 = a[0] + (b[0]-a[0])*(i+1)/8
            y2 = a[1] + (b[1]-a[1])*(i+1)/8
            d.line((x1, y1, x2, y2), fill=color, width=5)
    else:
        d.line((*a, *b), fill=color, width=6)
    d.polygon([(b[0]-10, b[1]-17), (b[0]+10, b[1]-17), b], fill=color)


def org_chart(output, heading, left_title, left_root, left_body, left_nodes,
              right_title, right_root, right_body, right_nodes, takeaway):
    im = Image.new("RGB", (1600, 1020), "#f3ead5")
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 1600, 112), fill="#202b34")
    title(d, 1600, heading)
    d.text((800, 84), "실선: 지휘  ·  점선: 독립 임무·후속 합류",
           font=font(21), fill="#cbd3d8", anchor="mm")
    d.line((800, 135, 800, 970), fill="#b7aa90", width=4)
    d.text((390, 155), left_title, font=font(32, True),
           fill="#176bac", anchor="mm")
    d.text((1210, 155), right_title, font=font(32, True),
           fill="#b62c28", anchor="mm")
    rounded_box(d, (190, 195, 590, 315), left_root, left_body, "#bcd9ec", "#1268aa")
    rounded_box(d, (1010, 195, 1410, 315), right_root, right_body, "#e9c9bd", "#b52d29")
    lx = [(40, 390, 280, 525), (300, 390, 540, 525), (560, 390, 780, 525)]
    rx = [(835, 390, 1065, 525), (1085, 390, 1315, 525), (1335, 390, 1570, 525)]
    for box, (h, body) in zip(lx, left_nodes):
        rounded_box(d, box, h, body, "#dcebf3", "#1268aa")
        link(d, (390, 315), ((box[0]+box[2])//2, 390), "#315f78")
    for box, (h, body) in zip(rx, right_nodes):
        rounded_box(d, box, h, body, "#f1ddd4", "#b52d29")
        link(d, (1210, 315), ((box[0]+box[2])//2, 390), "#7b4033")
    d.rounded_rectangle((160, 845, 1440, 955), 16,
                        fill="#fff8e8", outline="#816d49", width=4)
    d.text((800, 882), "승패를 가른 편제 차이", font=font(25, True),
           fill="#554525", anchor="mm")
    d.multiline_text((800, 925), takeaway,
                     font=fit(d, takeaway, 1210, 21, False),
                     fill="#45413a", anchor="mm", align="center")
    im.save(OUT / output, quality=96)


def watling_country():
    im = Image.open(OUT / "watling_country_map_source.png").convert("RGB")
    d = ImageDraw.Draw(im)
    title(d, im.width, "워틀링 스트리트 전투 — 서기 60~61년 브리타니아 반란 전역")
    for x, y, text_, color in [
        (275, 195, "모나섬(Mona)", "#1268aa"),
        (1450, 480, "카물로두눔(Camulodunum)", "#9d2b28"),
        (1195, 665, "론디니움(Londinium)", "#9d2b28"),
        (800, 520, "베룰라미움(Verulamium)", "#9d2b28"),
        (885, 330, "결전지 추정 범위", "#6b5130"),
    ]:
        label_box(d, x, y, text_, color, 320)
    d.text((88, im.height-42),
           "파랑: 로마군 회군  |  빨강: 부디카 연합의 공격로  |  사선: 정확한 결전지는 미확정",
           font=font(21, True), fill="#463927", anchor="lm")
    im.save(OUT / "watling_country_map.png", quality=96)


def watling_strategy():
    im = Image.open(OUT / "watling_strategy_source.png").convert("RGB")
    d = ImageDraw.Draw(im)
    title(d, im.width, "워틀링 스트리트 전략지형도 — 좁은 정면과 수레벽")
    label_box(d, 810, 610, "로마군: 군단병 중심·보조병과 기병 양익", "#1268aa", 430)
    label_box(d, 810, 210, "브리튼 연합: 대군의 밀집 정면 돌격", "#9d2b28", 420)
    label_box(d, 805, 125, "후방 수레벽 — 패주 때 퇴로 차단", "#9d2b28", 390)
    captions = [
        ("지형 선택", "숲·양측 고지로 포위를 막고 정면 폭을 축소"),
        ("결정타", "필룸 일제투척 뒤 쐐기 대형 반격"),
        ("붕괴", "후퇴한 브리튼군이 자기 수레벽에 막힘"),
    ]
    for i, (h, body) in enumerate(captions):
        x = int((i+.5)*im.width/3)
        d.text((x, im.height-91), h, font=font(25, True),
               fill=("#78bfff", "#ffd17a", "#ff8177")[i], anchor="mm")
        d.text((x, im.height-48), body,
               font=fit(d, body, im.width//3-45, 19),
               fill="#edf1f3", anchor="mm")
    im.save(OUT / "watling_strategy_map.png", quality=96)


def sequence(source, output, heading, labels):
    im = Image.open(OUT / source).convert("RGB")
    d = ImageDraw.Draw(im)
    title(d, im.width, heading, y=48)
    for i, text_ in enumerate(labels):
        x = int((i+.5)*im.width/4)
        d.text((x, im.height-64), text_,
               font=fit(d, text_, im.width//4-42, 20),
               fill="#493921", anchor="mm")
    im.save(OUT / output, quality=96)


def ship(draw, x, y, color, scale=1.0, direction=-1):
    """판옥선/왜선을 추상화한 정확히 셀 수 있는 함선 표식."""
    w, h = int(30*scale), int(54*scale)
    draw.polygon([(x-w//2, y-h//2), (x+w//2, y-h//2),
                  (x+int(w*.35), y+h//2), (x-int(w*.35), y+h//2)],
                 fill=color, outline="#f4dfad")
    draw.line((x, y-h//2, x, y+h//2), fill="#f4dfad", width=max(2, int(2*scale)))
    sail_y = y - int(8*direction)
    draw.polygon([(x, sail_y), (x+direction*int(18*scale), sail_y-int(16*scale)),
                  (x+direction*int(18*scale), sail_y+int(16*scale))],
                 fill=color, outline="#f4dfad")


def myeongnyang_strategy():
    im = Image.open(OUT / "myeongnyang_strategy_source.png").convert("RGB")
    d = ImageDraw.Draw(im)
    title(d, im.width, "명량 해전 전략지형도 — 13척과 울돌목의 조류")
    # 위쪽 조선 판옥선은 정확히 13척이다.
    blue_positions = [(836, 310)] + [(550+i*52, 250+(i%2)*24) for i in range(12)]
    for i, (x, y) in enumerate(blue_positions):
        ship(d, x, y, "#155f9d", 1.05 if i == 0 else .82, direction=-1)
    # 아래쪽 일본 선단은 다수·혼잡을 나타내는 표식이다.
    for row, count in enumerate((9, 8, 7)):
        for i in range(count):
            ship(d, 610+i*58+(row%2)*25, 470+row*70, "#9d2b28", .72, direction=1)
    label_box(d, 835, 185, "조선 수군 판옥선 13척", "#1268aa", 300)
    label_box(d, 835, 395, "울돌목 — 좁은 물목·격한 조류", "#1268aa", 340)
    label_box(d, 835, 690, "일본 수군 선봉 — 좁은 수로에서 혼잡", "#9d2b28", 390)
    captions = [
        ("초기", "이순신 기함이 먼저 물목을 막고 원거리 포격"),
        ("합류", "나머지 12척이 전열에 붙어 화력을 집중"),
        ("반전", "조류가 바뀌며 일본 선단의 충돌·퇴로 혼선"),
    ]
    for i, (h, body) in enumerate(captions):
        x = int((i+.5)*im.width/3)
        d.text((x, im.height-91), h, font=font(25, True),
               fill=("#78bfff", "#ffd17a", "#78bfff")[i], anchor="mm")
        d.text((x, im.height-48), body,
               font=fit(d, body, im.width//3-45, 19),
               fill="#edf1f3", anchor="mm")
    im.save(OUT / "myeongnyang_strategy_map.png", quality=96)


def myeongnyang_country():
    im = Image.open(OUT / "myeongnyang_country_map_source.png").convert("RGB")
    d = ImageDraw.Draw(im)
    title(d, im.width, "명량 해전 — 1597년 조선 남해 전역 세력도")
    for x, y, text_, color in [
        (1245, 610, "부산포(釜山浦)", "#9d2b28"),
        (765, 665, "어란진(於蘭鎭)", "#9d2b28"),
        (635, 635, "울돌목(鳴梁)", "#1268aa"),
        (520, 605, "벽파진(碧波津)", "#1268aa"),
        (680, 590, "우수영(右水營)", "#1268aa"),
        (565, 690, "진도(珍島)", "#1268aa"),
    ]:
        label_box(d, x, y, text_, color, 260)
    d.text((88, im.height-42),
           "파랑: 조선 수군 재건·이동  |  빨강: 일본 수군의 남해 서진  |  울돌목: 진도와 해남 사이",
           font=font(21, True), fill="#463927", anchor="lm")
    im.save(OUT / "myeongnyang_country_map.png", quality=96)


if __name__ == "__main__":
    commanders("watling_commanders_source.png", "watling_commanders.png",
               "워틀링 스트리트 전투 — 주요 인물",
               "로마 브리타니아군",
               "수에토니우스 파울리누스 · 제14군단 지휘관 · 보조군 지휘관",
               "브리튼 부족 연합",
               "부디카 · 이케니 부족장 · 트리노반테스 부족장")
    org_chart(
        "watling_command_structure.png", "워틀링 스트리트 — 장군 조직도와 작전 편제",
        "로마 브리타니아군", "수에토니우스 파울리누스",
        "속주 총독·야전군 총지휘\n결전지 선택·전열 통합",
        [("제14군단", "정면 중핵\n필룸·쐐기 반격"),
         ("제20군단 분견대", "군단 보병\n중앙 전열 보강"),
         ("보조병·기병", "양익 방호\n붕괴 뒤 추격")],
        "브리튼 부족 연합", "부디카",
        "반란 연합의 상징·총지휘\n도시 공격 뒤 정면 결전",
        [("이케니 전사", "부디카의 기반\n보병·전차"),
         ("트리노반테스", "동부 부족 연합\n대규모 보병"),
         ("가족·수레대", "후방 관전선\n패주 때 퇴로 차단")],
        "로마군은 병종을 한 지휘 아래 좁은 정면에 겹쳤고,\n브리튼 연합은 수는 많았지만 부족별 전사와 수레대가 하나의 전투 체계가 되지 못했다.")
    watling_country()
    watling_strategy()
    sequence("watling_sequence_source.png", "watling_sequence_map.png",
             "워틀링 스트리트 전역 — 단계별 흐름",
             ["1. 세 도시 함락·로마 야전군 회군", "2. 숲을 등진 좁은 목 선점",
              "3. 필룸 일제투척·쐐기 반격", "4. 수레벽에 막힌 브리튼 퇴각"])

    commanders("myeongnyang_commanders_source.png", "myeongnyang_commanders.png",
               "명량 해전 — 주요 인물",
               "조선 수군",
               "이순신 · 김억추 · 안위 · 송여종",
               "일본 수군",
               "구루시마 미치후사 · 도도 다카토라 · 가토 요시아키 · 와키자카 야스하루")
    org_chart(
        "myeongnyang_command_structure.png", "명량 해전 — 장군 조직도와 작전 편제",
        "조선 수군", "이순신",
        "삼도수군통제사\n기함 선두·포격전·조류 활용",
        [("김억추", "전라우수사\n후속 전열 지휘"),
         ("안위", "전열 합류\n선봉 전투 지속"),
         ("송여종", "중군장\n함대 질서 유지")],
        "일본 수군", "도도 다카토라 등",
        "다수 다이묘의 연합 지휘\n해협 돌파·접현전 시도",
        [("구루시마 미치후사", "선봉 지휘\n전투 중 전사"),
         ("가토 요시아키", "수군 지휘\n후속 선단"),
         ("와키자카 야스하루", "수군 지휘\n다이묘별 함대")],
        "조선 수군은 13척을 이순신의 단일 결심과 포격 전술로 묶었고,\n일본 수군은 많은 함선이 좁은 물목에 몰려 다이묘별 지휘와 접현전의 장점을 잃었다.")
    myeongnyang_country()
    myeongnyang_strategy()
    sequence("myeongnyang_sequence_source.png", "myeongnyang_sequence_map.png",
             "명량 해전 — 단계별 흐름",
             ["1. 칠천량 이후 13척 수습", "2. 울돌목 선택·조류 관찰",
              "3. 기함 단독 전진·함대 합류", "4. 조류 역전·일본 선봉 붕괴"])
