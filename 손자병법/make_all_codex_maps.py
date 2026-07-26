from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
BASES = ROOT / "generated_bases"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
RED = "#c63b36"
BLUE = "#2867b2"
AMBER = "#e39a22"


def font(size, bold=False):
    return ImageFont.truetype(FONT, size=size, index=7 if bold else 0)


def arrow(draw, points, color, width=30, head=62, dashed=False):
    if dashed:
        for a, b in zip(points[:-1], points[1:]):
            x1, y1 = a
            x2, y2 = b
            for i in range(0, 14, 2):
                t1, t2 = i / 14, min((i + 1) / 14, 1)
                draw.line(
                    (
                        x1 + (x2 - x1) * t1,
                        y1 + (y2 - y1) * t1,
                        x1 + (x2 - x1) * t2,
                        y1 + (y2 - y1) * t2,
                    ),
                    fill=color,
                    width=width,
                )
    else:
        draw.line(points, fill=color, width=width, joint="curve")
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    dx, dy = x2 - x1, y2 - y1
    mag = max((dx * dx + dy * dy) ** 0.5, 1)
    ux, uy = dx / mag, dy / mag
    px, py = -uy, ux
    draw.polygon(
        [
            (x2, y2),
            (x2 - ux * head + px * head * 0.55, y2 - uy * head + py * head * 0.55),
            (x2 - ux * head - px * head * 0.55, y2 - uy * head - py * head * 0.55),
        ],
        fill=color,
    )


def label(draw, xy, text, color, size=38, anchor="mm"):
    f = font(size, True)
    box = draw.multiline_textbbox(xy, text, font=f, anchor=anchor, align="center", spacing=6, stroke_width=2)
    pad = 14
    draw.rounded_rectangle(
        (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad),
        radius=18,
        fill=(15, 15, 15, 210),
        outline=color,
        width=4,
    )
    draw.multiline_text(
        xy,
        text,
        font=f,
        fill="white",
        anchor=anchor,
        align="center",
        spacing=6,
        stroke_width=2,
        stroke_fill="black",
    )


def canvas(slug, title, subtitle):
    src = Image.open(BASES / f"{slug}_codex_base.png").convert("RGB")
    src = src.resize((2300, 2740), Image.Resampling.LANCZOS)
    out = Image.new("RGB", (2400, 3200), "#e9e0cd")
    out.paste(src, (50, 230))
    draw = ImageDraw.Draw(out, "RGBA")
    draw.rectangle((0, 0, 2400, 230), fill="#17130e")
    draw.text((1200, 76), title, font=font(70, True), fill="#f5d36c", anchor="mm")
    draw.text((1200, 165), subtitle, font=font(35), fill="#f5f0e8", anchor="mm")
    draw.text((2270, 255), "N ↑", font=font(34, True), fill="white", anchor="ra",
              stroke_width=2, stroke_fill="black")
    return out, draw


def footer(draw, left, middle, right):
    y0, y1 = 2990, 3170
    for x0, x1, color, text in [
        (45, 780, RED, left),
        (820, 1580, "#6b5a3f", middle),
        (1620, 2355, BLUE, right),
    ]:
        draw.rounded_rectangle((x0, y0, x1, y1), 24, fill=(250, 247, 239, 246), outline=color, width=6)
        draw.multiline_text(
            ((x0 + x1) / 2, y0 + 90),
            text,
            font=font(31, True),
            fill="#1d1a16",
            anchor="mm",
            align="center",
            spacing=7,
        )


MAPS = {
    "jingxing": {
        "title": "정형 전투 전략지형도",
        "subtitle": "기원전 204년 · 정형관–면만수 전장 · Codex판 개략도",
        "arrows": [
            ([(2050, 1250), (1650, 1350), (1320, 1540)], RED, False),
            ([(420, 2600), (650, 2250), (900, 1900), (1140, 1640)], BLUE, False),
            ([(380, 900), (720, 820), (1500, 720), (1900, 850)], BLUE, True),
        ],
        "labels": [
            ((1880, 1170), "조군 본대\n정면 추격", RED),
            ((770, 2250), "한신 배수진\n강을 등진 결전", BLUE),
            ((1320, 690), "한군 2천 경기병\n조군 본영 우회", BLUE),
        ],
        "focus": (1050, 1350, 1450, 1750, "본영 탈취·조군 붕괴"),
        "foot": ("패군\n본영 방치·원칙주의", "핵심\n협로·강·빈 본영", "승군\n배수진+우회기습"),
    },
    "agincourt": {
        "title": "아쟁쿠르 전투 전략지형도",
        "subtitle": "1415년 10월 25일 · 숲 사이 진창 회랑 · Codex판 개략도",
        "arrows": [
            ([(700, 600), (850, 1050), (1000, 1500), (1130, 2050)], RED, False),
            ([(1700, 600), (1530, 1100), (1400, 1550), (1260, 2050)], RED, False),
            ([(900, 2550), (1050, 2250), (1160, 2050)], BLUE, False),
            ([(1500, 2550), (1350, 2250), (1240, 2050)], BLUE, False),
        ],
        "labels": [
            ((700, 850), "프랑스 중장병\n진창 속 밀집", RED),
            ((1450, 2520), "잉글랜드 장궁병\n측사·말뚝 방어", BLUE),
        ],
        "focus": (980, 1750, 1430, 2200, "숲과 진창의 병목"),
        "foot": ("패군\n대군 밀집·기동 상실", "핵심\n좁은 회랑·깊은 진창", "승군\n장궁 교차사격"),
    },
    "gettysburg": {
        "title": "게티즈버그 전투 전략지형도",
        "subtitle": "1863년 7월 1–3일 · 세미너리–묘지 능선 · Codex판 개략도",
        "arrows": [
            ([(430, 900), (800, 1050), (1120, 1250)], RED, False),
            ([(500, 1900), (900, 1850), (1250, 1800)], RED, False),
            ([(500, 2520), (950, 2400), (1400, 2280)], RED, False),
            ([(1800, 2500), (1720, 2200), (1600, 1800), (1550, 1200)], BLUE, False),
        ],
        "labels": [
            ((690, 1700), "남군\n피켓 돌격", RED),
            ((1680, 1850), "북군\n묘지능선 방어", BLUE),
            ((1660, 2490), "리틀 라운드 톱", AMBER),
        ],
        "focus": (1220, 1550, 1700, 2050, "개활지 돌격의 종점"),
        "foot": ("패군\n정면돌격·과신", "핵심\n두 능선과 개활지", "승군\n고지·내선 방어"),
    },
    "changping": {
        "title": "장평대전 전략지형도",
        "subtitle": "기원전 260년 · 단하 계곡·포위전 · Codex판 개략도",
        "arrows": [
            ([(1900, 650), (1600, 1000), (1350, 1450), (1200, 1900)], RED, False),
            ([(380, 900), (700, 1150), (980, 1500)], BLUE, False),
            ([(420, 2550), (750, 2250), (1050, 2050)], BLUE, False),
        ],
        "labels": [
            ((1740, 850), "조괄의 조군\n계곡 깊이 진입", RED),
            ((630, 1130), "백기 주력\n전면 차단", BLUE),
            ((720, 2320), "진군 별동대\n보급로 절단", BLUE),
        ],
        "focus": (900, 1650, 1380, 2150, "조군 포위·보급 단절"),
        "foot": ("패군\n추격 과신·퇴로 상실", "핵심\n계곡·협로·보급선", "승군\n유인 후 양단 포위"),
    },
    "breitenfeld": {
        "title": "브라이텐펠트 전투 전략지형도",
        "subtitle": "1631년 9월 17일 · 작센 평원 · Codex판 개략도",
        "arrows": [
            ([(650, 850), (850, 1250), (1000, 1700)], RED, False),
            ([(1700, 850), (1500, 1250), (1350, 1700)], RED, False),
            ([(450, 2500), (850, 2250), (1200, 2000), (1600, 1750)], BLUE, False),
            ([(1900, 2500), (1650, 2250), (1450, 2000)], BLUE, False),
        ],
        "labels": [
            ((720, 1100), "틸리·파펜하임\n중앙·우익 공격", RED),
            ((650, 2420), "구스타브 아돌프\n유연한 예비대", BLUE),
            ((1750, 2350), "스웨덴 기병\n재집결·측면 전환", BLUE),
        ],
        "focus": (1050, 1550, 1550, 2050, "제국군 측면 붕괴"),
        "foot": ("패군\n반복 돌격·경직 전열", "핵심\n넓은 평원·기동 공간", "승군\n예비대·측면 전환"),
    },
    "bi": {
        "title": "필(邲) 전투 전략지형도",
        "subtitle": "기원전 597년 · 황하 남안 · Codex판 개략도",
        "arrows": [
            ([(1200, 2700), (1150, 2250), (1100, 1850), (1120, 1450)], RED, False),
            ([(450, 2300), (760, 2050), (980, 1750)], RED, False),
            ([(450, 900), (800, 1100), (1050, 1450)], BLUE, False),
            ([(1900, 900), (1600, 1150), (1300, 1450)], BLUE, False),
        ],
        "labels": [
            ((1050, 2450), "초 장왕\n일관된 북상", RED),
            ((500, 950), "진군 상군·하군\n명령 불일치", BLUE),
        ],
        "focus": (900, 1300, 1450, 1800, "황하 도하로·지휘 혼선"),
        "foot": ("패군\n상하 명령 충돌", "핵심\n황하·도하로·평원", "승군\n통일 지휘·집중"),
    },
    "teutoburg_forest": {
        "title": "토이토부르크 숲 전투 전략지형도",
        "subtitle": "서기 9년 · 칼크리제 회랑 · Codex판 개략도",
        "arrows": [
            ([(1250, 2800), (1220, 2350), (1200, 1900), (1180, 1300), (1150, 650)], RED, False),
            ([(2050, 850), (1700, 1050), (1300, 1250)], BLUE, False),
            ([(2050, 1500), (1700, 1650), (1300, 1800)], BLUE, False),
            ([(2050, 2200), (1700, 2250), (1300, 2350)], BLUE, False),
        ],
        "labels": [
            ((980, 2500), "바루스 군단\n행군대형 장기화", RED),
            ((1750, 1050), "게르만 매복\n숲·토루에서 반복 타격", BLUE),
        ],
        "focus": (900, 1450, 1450, 2050, "습지–숲 사이 병목"),
        "foot": ("패군\n정찰 실패·긴 종대", "핵심\n숲·습지·좁은 길", "승군\n분절 타격·퇴로 차단"),
    },
    "fucha_1619": {
        "title": "부차·심하전투 전략지형도",
        "subtitle": "1619년 · 혼하 상류 산악계곡 · Codex판 개략도",
        "arrows": [
            ([(500, 650), (850, 1000), (1050, 1450)], RED, False),
            ([(1900, 700), (1650, 1050), (1350, 1450)], RED, False),
            ([(1900, 2500), (1550, 2200), (1250, 1800)], BLUE, False),
            ([(500, 2400), (800, 2100), (1100, 1800)], BLUE, False),
        ],
        "labels": [
            ((720, 900), "명군 분진\n산악로로 분산", RED),
            ((1650, 2320), "후금군\n내선 집중", BLUE),
        ],
        "focus": (950, 1400, 1500, 1900, "강안 진영 각개격파"),
        "foot": ("패군\n4로 분산·상호지원 실패", "핵심\n산악계곡·강 도하", "승군\n집중기동·순차 격파"),
    },
    "cannae": {
        "title": "칸나에 전투 전략지형도",
        "subtitle": "기원전 216년 · 아우피두스 강 평원 · Codex판 개략도",
        "arrows": [
            ([(1200, 650), (1200, 1100), (1200, 1650)], RED, False),
            ([(650, 900), (850, 1250), (1050, 1550)], BLUE, False),
            ([(1750, 900), (1550, 1250), (1350, 1550)], BLUE, False),
            ([(400, 1900), (750, 1900), (1050, 1750)], BLUE, False),
            ([(2000, 1900), (1650, 1900), (1350, 1750)], BLUE, False),
        ],
        "labels": [
            ((1200, 850), "로마군 깊은 중앙\n전진·압축", RED),
            ((600, 1850), "카르타고 기병\n후방 폐쇄", BLUE),
        ],
        "focus": (950, 1450, 1450, 2000, "이중포위 완성"),
        "foot": ("패군\n밀집 중앙·측후방 노출", "핵심\n개활평원·강·먼지", "승군\n탄력 중앙·양익 포위"),
    },
    "julu": {
        "title": "거록대전 전략지형도",
        "subtitle": "기원전 207년 · 장하 도하·구원전 · Codex판 개략도",
        "arrows": [
            ([(500, 650), (750, 1000), (1000, 1400)], RED, False),
            ([(1900, 700), (1600, 1050), (1350, 1400)], RED, False),
            ([(1200, 2750), (1180, 2350), (1160, 1950), (1150, 1550)], BLUE, False),
        ],
        "labels": [
            ((650, 900), "진군 포위망·보급로", RED),
            ((1100, 2450), "항우 초군\n파부침주 후 도하", BLUE),
        ],
        "focus": (900, 1250, 1450, 1750, "진군 보급선 절단"),
        "foot": ("패군\n장기 포위·보급선 노출", "핵심\n장하 도하·습지 평원", "승군\n결사항전·집중 돌파"),
    },
    "anabasis": {
        "title": "크세노폰 만인대 원정 전략지형도",
        "subtitle": "기원전 401–400년 · 티그리스 북상로 · Codex판 개략도",
        "arrows": [
            ([(1100, 2750), (1050, 2350), (1000, 1900), (950, 1450), (900, 700)], BLUE, False),
            ([(1900, 1800), (1550, 1700), (1250, 1650)], RED, False),
            ([(400, 1300), (650, 1450), (900, 1550)], RED, False),
        ],
        "labels": [
            ((850, 2350), "만인대\n북쪽 귀환행군", BLUE),
            ((1650, 1700), "페르시아 추격·압박", RED),
        ],
        "focus": (750, 1250, 1200, 1800, "강·산 사이 생존로"),
        "foot": ("위기\n지휘부 상실·적지 고립", "핵심\n강·산악·장거리 보급", "생존\n재편·규율·북상"),
    },
    "jieting": {
        "title": "가정 전투 전략지형도",
        "subtitle": "서기 228년 · 산상 진영과 수원 · Codex판 개략도",
        "arrows": [
            ([(1000, 700), (1050, 1100), (1100, 1500)], RED, False),
            ([(500, 1900), (850, 1800), (1100, 1700)], BLUE, False),
            ([(1900, 2000), (1550, 1850), (1250, 1700)], BLUE, False),
        ],
        "labels": [
            ((980, 1000), "마속 촉군\n고립된 산상 진영", RED),
            ((1600, 1850), "장합 위군\n수원·도로 차단", BLUE),
        ],
        "focus": (900, 1450, 1400, 1950, "산 아래 수원 봉쇄"),
        "foot": ("패군\n명령 위반·산상 고립", "핵심\n도로·수원·고립고지", "승군\n포위·갈증 유도"),
    },
    "austerlitz": {
        "title": "아우스터리츠 전투 전략지형도",
        "subtitle": "1805년 12월 2일 · 프라첸 고지 · Codex판 개략도",
        "arrows": [
            ([(700, 650), (800, 1050), (900, 1500), (850, 2200)], RED, False),
            ([(1800, 700), (1550, 1100), (1300, 1500)], RED, False),
            ([(500, 2200), (850, 2000), (1150, 1650)], BLUE, False),
            ([(1900, 2400), (1600, 2050), (1300, 1750)], BLUE, False),
        ],
        "labels": [
            ((720, 900), "연합군 좌익\n고지 이탈·남진", RED),
            ((650, 2150), "술트 군단\n프라첸 중앙 돌파", BLUE),
        ],
        "focus": (950, 1350, 1450, 1850, "약해진 중앙 절단"),
        "foot": ("패군\n유인에 반응·중앙 약화", "핵심\n프라첸 고지·남쪽 호수", "승군\n약한 우익 연출·중앙돌파"),
    },
    "yiling": {
        "title": "이릉대전 전략지형도",
        "subtitle": "서기 222년 · 장강 산악회랑 · Codex판 개략도",
        "arrows": [
            ([(600, 650), (750, 1050), (900, 1500), (1050, 2300)], RED, False),
            ([(1900, 2300), (1600, 2100), (1300, 1900)], BLUE, False),
            ([(1800, 1450), (1500, 1600), (1200, 1750)], BLUE, False),
            ([(1700, 800), (1450, 1100), (1150, 1400)], BLUE, False),
        ],
        "labels": [
            ((700, 1050), "유비 촉군\n긴 산림 진영선", RED),
            ((1600, 2050), "육손 오군\n대기 후 화공·분절", BLUE),
        ],
        "focus": (900, 1500, 1450, 2050, "연속 진영 붕괴"),
        "foot": ("패군\n장기 주둔·진영 분산", "핵심\n산림·협곡·강 회랑", "승군\n인내·화공·분절 타격"),
    },
    "tannenberg": {
        "title": "탄넨베르크 전투 전략지형도",
        "subtitle": "1914년 8월 26–30일 · 마수리안 호수대 · Codex판 개략도",
        "arrows": [
            ([(1050, 2800), (1100, 2350), (1150, 1900), (1200, 1450)], RED, False),
            ([(350, 2300), (700, 2150), (1000, 1950)], BLUE, False),
            ([(1950, 750), (1700, 1100), (1450, 1550), (1250, 1900)], BLUE, False),
        ],
        "labels": [
            ((900, 2500), "삼소노프 제2군\n북상·전선 신장", RED),
            ((600, 2150), "독일 제1군단\n남서 차단", BLUE),
            ((1650, 1100), "독일 북익\n철도 집중·포위", BLUE),
        ],
        "terrain_labels": [
            ((520, 670), "동프로이센 철도망\n독일군 내선기동 축", AMBER),
            ((1880, 1740), "마수리안 호수대\n제1·2군 사이의 기동 장벽", AMBER),
        ],
        "focus": (950, 1650, 1450, 2200, "제2군 포위망"),
        "foot": ("패군\n통신·군단 결집 실패", "핵심\n호수대·철도·내선", "승군\n고립된 제2군만 타격"),
    },
    "maling": {
        "title": "마릉 전투 전략지형도",
        "subtitle": "기원전 342년경 · 전통적 협곡설 · Codex판 개략도",
        "arrows": [
            ([(1200, 2800), (1180, 2400), (1150, 2000), (1120, 1600)], RED, False),
            ([(400, 1200), (750, 1350), (1050, 1550)], BLUE, False),
            ([(2000, 1150), (1650, 1350), (1300, 1550)], BLUE, False),
            ([(1150, 700), (1130, 1050), (1120, 1400)], BLUE, True),
        ],
        "labels": [
            ((980, 2450), "방연 정예군\n본대와 분리 추격", RED),
            ((550, 1150), "제군 노수 복병", BLUE),
            ((1760, 1100), "제군 노수 복병", BLUE),
        ],
        "focus": (900, 1400, 1400, 1850, "야간 협곡 살상지대"),
        "foot": ("패군\n고정관념·조급한 추격", "핵심\n협로·밤·양측 고지", "승군\n감조계·매복 일제사격"),
    },
}


def build(slug, cfg):
    image, draw = canvas(slug, cfg["title"], cfg["subtitle"])
    for points, color, dashed in cfg["arrows"]:
        arrow(draw, points, color, dashed=dashed)
    for xy, text, color in cfg["labels"]:
        label(draw, xy, text, color)
    for xy, text, color in cfg.get("terrain_labels", []):
        label(draw, xy, text, color, size=34)
    x0, y0, x1, y1, text = cfg["focus"]
    draw.ellipse((x0, y0, x1, y1), outline=AMBER, width=18)
    label(draw, ((x0 + x1) / 2, (y0 + y1) / 2), text, AMBER, size=40)
    footer(draw, *cfg["foot"])
    image.save(ROOT / f"{slug}_codex_map.png", optimize=True)


if __name__ == "__main__":
    for slug, cfg in MAPS.items():
        build(slug, cfg)
        print(f"created {slug}_codex_map.png")
