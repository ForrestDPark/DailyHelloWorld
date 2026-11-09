from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

LABELS = {
    "fortitude_commanders.png": ("주요 인물 · 포티튜드", "연합군: 후안 푸홀(GARBO) · 토마스 해리스  |  독일군: 국방군 지휘부 · 아프베어 연락망"),
    "fortitude_soldiers_weapons_life.png": ("병사 · 장비 · 정보생활", "상륙 보병 · 무전병 · 암호요원 · 연락원  |  무전기 · 암호문 · 야전식량 · 해안 감시"),
    "fortitude_command_structure.png": ("지휘 · 정보 편제", "연합군 최고지휘부 → 이십위원회·MI5 → 담당관 → 이중간첩 → 독일 정보기관·최고지휘부"),
    "fortitude_country_map.png": ("1944 영국해협 세력·교통망", "영국 남부(연합군) ↔ 영국해협 ↔ 노르망디·파드칼레(독일 점령지)  |  도로·철도·항만·통신축"),
    "fortitude_strategy_map.png": ("포티튜드 전략지형", "파랑: 실제 노르망디 상륙  |  황색: 파드칼레 기만 신호  |  빨강: 독일 예비대의 판단·대응"),
    "fortitude_sequence.png": ("포티튜드 4단계", "① 이중간첩망 설계  ② 가상 부대·무선 흔적  ③ 노르망디 상륙  ④ 파드칼레 예비대 잔류"),
    "feishui_commanders.png": ("주요 인물 · 비수대전", "동진: 사안 · 사현 · 사석 · 유뢰지  |  전진: 부견 · 부융  |  정보의 관절: 주서"),
    "feishui_soldiers_weapons_life.png": ("병사 · 무기 · 생활", "동진 북부병 · 쇠뇌병 · 수상 정찰·전령  |  전진 보병·기병  |  군량·취사·북·깃발"),
    "feishui_command_structure.png": ("지휘 · 정보 편제", "동진 조정 → 사석·사현 → 유뢰지  |  전진 부견·부융 → 다민족 대군  |  주서의 비공식 정보 경로"),
    "feishui_country_map.png": ("383년 동진·전진 전역 세력도", "빨강: 전진 남하축  |  파랑: 동진 방어·반격축  |  회수·비수 수계와 수양·낙간·팔공산"),
    "feishui_strategy_map.png": ("비수대전 전략지형", "전진 서안 배치 → 제한 후퇴  |  동진 동안 도하  |  주서의 후방 신호 → 지휘·결속 붕괴"),
    "feishui_sequence.png": ("비수대전 4단계", "① 주서의 은밀한 조언  ② 낙간 선제공격  ③ 전진 후퇴·후방 신호  ④ 동진 도하·전진 퇴각"),
}

CALLOUTS = {
    "fortitude_commanders.png": [(0.18, 0.73, "토마스 해리스\nMI5 담당관", "blue"), (0.47, 0.69, "후안 푸홀 · GARBO\n이중간첩", "blue"), (0.78, 0.73, "독일 지휘부\n정보 수신·판단", "red")],
    "feishui_commanders.png": [(0.18, 0.72, "사안·사현\n동진 전략지휘", "blue"), (0.49, 0.61, "주서\n정보의 관절", "gold"), (0.79, 0.72, "부견·부융\n전진 지휘부", "red")],
    "fortitude_soldiers_weapons_life.png": [(0.18, 0.28, "상륙 보병\n소총·공병장비", "blue"), (0.20, 0.58, "무전병\n송수신·암호표", "gold"), (0.50, 0.57, "연락원\n문서·현장보고", "blue"), (0.80, 0.58, "해안 감시병\n관측·보고", "red")],
    "feishui_soldiers_weapons_life.png": [(0.18, 0.59, "동진 북부병\n장창·방패", "blue"), (0.43, 0.63, "쇠뇌병\n원거리 제압", "blue"), (0.76, 0.26, "전진 기병·보병\n대군 집결", "red"), (0.72, 0.78, "군량·취사\n전투 지속", "gold")],
    "fortitude_command_structure.png": [(0.24, 0.17, "연합군 최고지휘부", "blue"), (0.25, 0.38, "이십위원회 · MI5", "blue"), (0.24, 0.61, "담당관 · 이중간첩", "gold"), (0.76, 0.20, "독일 최고지휘부", "red"), (0.76, 0.46, "아프베어 연락망", "red")],
    "feishui_command_structure.png": [(0.22, 0.17, "동진 조정 · 사안", "blue"), (0.23, 0.40, "사석 · 사현", "blue"), (0.22, 0.66, "유뢰지 · 북부병", "blue"), (0.77, 0.20, "부견 · 부융", "red"), (0.77, 0.48, "전진 다민족 대군", "red"), (0.50, 0.53, "주서의 비공식 경로", "gold")],
    "fortitude_country_map.png": [(0.52, 0.18, "런던\n지휘·통신", "blue"), (0.78, 0.33, "도버·파드칼레\n가상 주공축", "gold"), (0.56, 0.73, "노르망디\n실제 상륙축", "blue")],
    "feishui_country_map.png": [(0.72, 0.80, "건강\n동진 중심", "blue"), (0.55, 0.56, "수양·비수\n결전 구간", "gold"), (0.34, 0.28, "전진 남하축", "red")],
    "fortitude_strategy_map.png": [(0.30, 0.33, "가상 제1미군집단\n무선·모형 신호", "gold"), (0.65, 0.25, "파드칼레\n독일 예비대 잔류", "red"), (0.48, 0.69, "노르망디\n실제 상륙", "blue")],
    "feishui_strategy_map.png": [(0.34, 0.51, "전진 서안\n제한 후퇴", "red"), (0.62, 0.60, "동진 동안\n도하·추격", "blue"), (0.65, 0.36, "주서 후방 신호", "gold")],
    "fortitude_sequence.png": [(0.18, 0.17, "① 이중간첩망", "blue"), (0.18, 0.40, "② 가상 부대·무선", "gold"), (0.18, 0.63, "③ 노르망디 상륙", "blue"), (0.18, 0.84, "④ 예비대 잔류", "red")],
    "feishui_sequence.png": [(0.18, 0.17, "① 주서의 조언", "gold"), (0.18, 0.40, "② 낙간 선제공격", "blue"), (0.18, 0.63, "③ 후퇴·후방 신호", "red"), (0.18, 0.84, "④ 도하·퇴각", "blue")],
}

CONNECTIONS = {
    "fortitude_command_structure.png": [(0.24, 0.22, 0.25, 0.34, "blue"), (0.25, 0.44, 0.24, 0.56, "blue"), (0.31, 0.60, 0.68, 0.45, "gold"), (0.76, 0.25, 0.76, 0.40, "red")],
    "feishui_command_structure.png": [(0.22, 0.22, 0.23, 0.35, "blue"), (0.23, 0.46, 0.22, 0.61, "blue"), (0.50, 0.50, 0.31, 0.39, "gold"), (0.50, 0.50, 0.69, 0.22, "gold"), (0.77, 0.25, 0.77, 0.43, "red")],
}


def fit_font(draw, text, max_width, start):
    size = start
    while size > 42:
        font = ImageFont.truetype(FONT, size)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
        size -= 2
    return ImageFont.truetype(FONT, 42)


def wrap_two_lines(draw, text, font, max_width):
    tokens = text.split()
    lines = [""]
    for token in tokens:
        candidate = token if not lines[-1] else f"{lines[-1]} {token}"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            lines[-1] = candidate
        elif len(lines) == 1:
            lines.append(token)
        else:
            lines[-1] = f"{lines[-1]} {token}"
    return lines


COLORS = {"blue": (28, 96, 175, 238), "red": (156, 42, 42, 238), "gold": (142, 104, 24, 238)}


def callout(draw, width, height, x, y, text, color):
    font = ImageFont.truetype(FONT, max(42, round(width * 0.032)))
    lines = text.split("\n")
    boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    box_w = max(box[2] for box in boxes) + 30
    box_h = len(lines) * round(font.size * 1.16) + 22
    cx, cy = round(width * x), round(height * y)
    left = max(10, min(width - box_w - 10, cx - box_w // 2))
    top = max(10, min(height - box_h - 10, cy - box_h // 2))
    draw.rounded_rectangle((left, top, left + box_w, top + box_h), radius=14, fill=COLORS[color], outline=(255, 255, 255, 235), width=3)
    for idx, line in enumerate(lines):
        draw.text((left + 15, top + 10 + idx * round(font.size * 1.16)), line, font=font, fill=(255, 255, 255, 255))


for name, (title, detail) in LABELS.items():
    path = ROOT / name
    image = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    top_h = max(104, round(height * 0.075))
    bottom_h = max(184, round(height * 0.13))
    draw.rectangle((0, 0, width, top_h), fill=(8, 16, 27, 225))
    draw.rectangle((0, height - bottom_h, width, height), fill=(8, 16, 27, 225))
    title_font = fit_font(draw, title, width - 80, 68)
    detail_font = ImageFont.truetype(FONT, max(42, round(width * 0.031)))
    detail_lines = wrap_two_lines(draw, detail, detail_font, width - 80)
    draw.text((40, top_h / 2), title, font=title_font, fill=(255, 226, 145, 255), anchor="lm")
    line_gap = round(detail_font.size * 1.22)
    detail_y = height - bottom_h / 2 - (len(detail_lines) - 1) * line_gap / 2
    for index, line in enumerate(detail_lines):
        draw.text((40, detail_y + index * line_gap), line, font=detail_font, fill=(255, 255, 255, 255), anchor="lm")
    for x1, y1, x2, y2, color in CONNECTIONS.get(name, []):
        draw.line((width * x1, height * y1, width * x2, height * y2), fill=COLORS[color], width=max(8, round(width * 0.008)))
    for x, y, text, color in CALLOUTS.get(name, []):
        callout(draw, width, height, x, y, text, color)
    image.save(path, "PNG", optimize=True)
