from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
SRC = ROOT / "source"
QA = ROOT / "qa"
QA.mkdir(exist_ok=True)
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"


def font(size, bold=False):
    return ImageFont.truetype(FONT, size=size, index=7 if bold else 0)


def banner(im, title, subtitle):
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle((24, 18, im.width - 24, 128), 20,
                        fill=(7, 13, 24, 235), outline=(232, 196, 98, 255), width=3)
    d.text((im.width / 2, 50), title, font=font(42, True), fill="#ffd86b", anchor="mm",
           stroke_width=2, stroke_fill="#000")
    d.text((im.width / 2, 96), subtitle, font=font(23), fill="white", anchor="mm",
           stroke_width=2, stroke_fill="#000")
    return d


def label(d, x, y, text, color, size=22):
    f = font(size, True)
    bb = d.multiline_textbbox((x, y), text, font=f, anchor="mm", align="center", spacing=3,
                              stroke_width=2)
    pad = 10
    d.rounded_rectangle((bb[0]-pad, bb[1]-pad, bb[2]+pad, bb[3]+pad), 10,
                        fill=color, outline=(255, 222, 140, 255), width=2)
    d.multiline_text((x, y), text, font=f, fill="white", anchor="mm", align="center", spacing=3,
                     stroke_width=2, stroke_fill="#111")


def make(name, title, subtitle, labels):
    im = Image.open(SRC / name).convert("RGBA")
    d = banner(im, title, subtitle)
    for x, y, text, color, size in labels:
        label(d, x, y, text, color, size)
    out = ROOT / name
    im.convert("RGB").save(out, quality=96)
    small = im.convert("RGB")
    small.thumbnail((390, 390))
    small.save(QA / f"{Path(name).stem}_390.png", quality=92)


BLUE = (10, 62, 126, 232)
RED = (126, 22, 30, 232)
GOLD = (116, 74, 6, 235)
DARK = (12, 20, 31, 232)


make("culper_commanders.png", "컬퍼 첩보망 주요 인물", "대륙군 정보망 파랑 · 영국군 지휘부 빨강", [
    (280, 900, "워싱턴 · 톨매지\n우드헐 · 타운센드 · 스트롱 · 브루스터", BLUE, 21),
    (1250, 900, "헨리 클린턴\n영국군 뉴욕 지휘부", RED, 23),
])
make("culper_soldiers_weapons_life.png", "컬퍼망의 사람·장비·생활", "기병 전령 · 고래잡이 보트 · 농장 위장 · 암호·보이지 않는 잉크", [
    (210, 900, "기병 전령\n파견함·말·여행 장비", BLUE, 20),
    (590, 900, "브루스터의 보트\n머스킷·노·해협 횡단", BLUE, 20),
    (975, 900, "우드헐의 농장 위장\n채소 운반·현지 관찰", GOLD, 20),
    (1360, 900, "타운센드의 상점\n암호·잉크·장부", BLUE, 20),
])
make("culper_command_structure.png", "컬퍼망 지휘·운반 구조", "워싱턴 → 톨매지 │ 타운센드 → 로 → 우드헐·스트롱 → 브루스터", [
    (260, 170, "워싱턴\n최종 판단", BLUE, 21), (310, 410, "톨매지\n망 통제", BLUE, 20),
    (335, 760, "타운센드\n맨해튼 수집", BLUE, 19), (690, 430, "오스틴 로\n육로 전령", GOLD, 19),
    (1010, 500, "우드헐\n세토킷 접선", BLUE, 19), (1310, 530, "애나 스트롱\n해안 신호", GOLD, 19),
    (990, 785, "브루스터\n해협 보트", BLUE, 19),
])
make("culper_country_map.png", "1780년 뉴욕–뉴포트 전구", "영국 점령 뉴욕 · 대륙군 코네티컷 · 프랑스군 뉴포트", [
    (250, 760, "영국 점령 뉴욕", RED, 23), (805, 410, "코네티컷\n대륙군 연락축", BLUE, 21),
    (1245, 350, "뉴포트\n프랑스군 도착", GOLD, 21), (820, 570, "롱아일랜드 해협", DARK, 21),
])
make("culper_strategy_map.png", "컬퍼 첩보망 전략지형도", "맨해튼 → 세토킷 → 롱아일랜드 해협 → 코네티컷 → 워싱턴 본영", [
    (235, 760, "맨해튼\n타운센드", RED, 20), (690, 740, "세토킷\n우드헐·스트롱", BLUE, 20),
    (815, 515, "롱아일랜드 해협\n브루스터 보트", DARK, 20), (780, 295, "코네티컷\n톨매지 인계", BLUE, 20),
    (315, 145, "워싱턴 본영\n정보 통합", BLUE, 20), (1325, 145, "뉴포트\n프랑스군", GOLD, 20),
])
make("culper_sequence.png", "1780년 컬퍼망 4단계", "① 뉴욕 정보 수집 → ② 비밀 운반 → ③ 가짜 공격계획 → ④ 영국군 회군", [
    (360, 150, "1  클린턴의 뉴포트 공격계획 포착", RED, 19),
    (1140, 150, "2  육로·해로 분업으로 본영 전달", BLUE, 19),
    (360, 650, "3  워싱턴의 뉴욕 공격 허상", GOLD, 19),
    (1140, 650, "4  영국군 회군·프랑스군 회복", BLUE, 19),
])

make("yongzheng_commanders.png", "옹정제의 주접 정보망 주요 인물", "황제 직통 비밀보고와 누층 관료제의 대조", [
    (500, 900, "옹정제\n친필 주비·최종 통합", BLUE, 22),
    (840, 900, "총독·순무·포정사·도원·제독\n서로 다른 지역·직위의 보고", GOLD, 20),
    (1270, 900, "내각·통상 문서 경로\n지연·누설·상급자 필터 위험", RED, 19),
])
make("yongzheng_soldiers_weapons_life.png", "주접의 사람·장비·운반", "친필 보고 · 밀봉함 · 역참 말 · 변방 지도 · 건청문 접수", [
    (300, 450, "지방관 친필\n인장·봉함", BLUE, 20), (800, 450, "신임 가인\n잠금 상자·열쇠", GOLD, 20),
    (1280, 450, "역참 기마\n말 교체·여행 식량", GOLD, 20), (390, 875, "변방 장수\n지도·명부 첨부", BLUE, 20),
    (1170, 875, "건청문 접수\n황제에게 직송", BLUE, 20),
])
make("yongzheng_command_structure.png", "옹정 주접 지휘·정보 구조", "독립 보고자 → 봉함·역참 → 건청문 → 황제 친람·주비 → 회송", [
    (760, 185, "옹정제\n친람·주비·비교", BLUE, 21), (760, 430, "건청문·주사처\n봉함 확인·직송", BLUE, 19),
    (160, 920, "순무", GOLD, 20), (450, 920, "포정사", GOLD, 20), (760, 920, "도원", GOLD, 20),
    (1060, 920, "제독", GOLD, 20), (1370, 920, "변방 장군", GOLD, 20),
    (1375, 430, "통상 상신·내각 경로\n여러 층의 검토", RED, 18),
])
make("yongzheng_country_map.png", "1723~1735년 청 제국 주접망", "광대한 지방의 독립 보고가 북경 황궁으로 수렴", [
    (910, 340, "북경·자금성\n정보 통합 중심", BLUE, 21), (1060, 690, "강남·절강·복건·광동\n민정·물가·관료 행태", GOLD, 18),
    (590, 620, "사천·운남\n산악 역로", GOLD, 19), (470, 300, "서북 변방\n군정·보급", RED, 19),
])
make("yongzheng_strategy_map.png", "옹정 주접망 전략지형도", "대운하·장강·황하·산악 역로를 거쳐 건청문으로 직송", [
    (765, 150, "북경 자금성\n건청문→양심전", BLUE, 20), (970, 470, "대운하·동부 역로", DARK, 18),
    (760, 620, "장강 중하류", DARK, 18), (420, 500, "사천 분지·산악로", GOLD, 18),
    (330, 250, "서북 변경 역로", RED, 18), (1270, 650, "강남·복건·광동 보고축", GOLD, 18),
])
make("yongzheng_sequence.png", "옹정 주접망 4단계", "① 독립 관찰·친필 → ② 밀봉·역참 → ③ 황제 친람·교차 → ④ 회송·보관과 통제 위험", [
    (360, 150, "1  지방의 군정·민정·관료 행태 관찰", GOLD, 18),
    (1140, 150, "2  황지·황견·잠금 상자로 비밀 운반", BLUE, 18),
    (360, 650, "3  건청문 직송·황제 친필 주비", BLUE, 18),
    (1140, 650, "4  회송·궁중 보관 / 과잉집권의 위험", RED, 18),
])
