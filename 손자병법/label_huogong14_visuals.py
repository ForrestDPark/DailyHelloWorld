from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

ROOT = Path(__file__).parent / "generated" / "jiudi_huogong14"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

LABELS = {
    "armada_commanders.png": ("1588 칼레·그라블린 │ 주요 인물", ["영국: 찰스 하워드 · 프랜시스 드레이크", "스페인: 메디나 시도니아 · 파르마 공작"]),
    "armada_soldiers_weapons_life.png": ("1588 무적함대 │ 병사·무기·함상생활", ["포술 · 화선 · 닻과 케이블 · 야간 당직", "식수통 · 건빵 · 수리와 신호"]),
    "armada_command_structure.png": ("1588 무적함대 │ 지휘·편제", ["영국 4개 전대 — 풍상에서 기동", "스페인 함대 ⋯ 파르마군 — 연락·합류 단절"]),
    "armada_country_map.png": ("1588 서유럽 │ 시대 세력과 침공로", ["스페인 → 비스케이만 → 영국해협", "칼레 외항 · 플랑드르 봉쇄 · 잉글랜드"]),
    "armada_strategy_map.png": ("칼레 화선 공격–그라블린 │ 전략지형", ["풍상 영국 함대 → 화선 8척 → 정박 스페인 함대", "칼레 · 그라블린 · 플랑드르 사주 · 북해 퇴로"]),
    "armada_sequence_map.png": ("1588 전역 4단계", ["① 합류 대기  ② 야간 화선", "③ 닻 절단·분산  ④ 그라블린·북해 퇴로"]),
    "redcliffs_commanders.png": ("208 적벽 │ 주요 인물", ["손·유 연합: 주유 · 황개 · 손권 · 유비", "조조군: 조조와 북방·형주 지휘층"]),
    "redcliffs_soldiers_weapons_life.png": ("208 적벽 │ 병사·무기·수군생활", ["강동 수군 · 북방 보병 · 형주 수군", "몽충·두함 · 화선 · 활·노 · 질병과 군량"]),
    "redcliffs_command_structure.png": ("208 적벽 │ 지휘·편제", ["손권 → 주유·정보 / 황개 화선 + 유비 협동", "조조 → 북방 육군 + 새로 흡수한 형주 수군"]),
    "redcliffs_country_map.png": ("208 후한 말 │ 시대 세력도", ["조조 북방·형주 / 손권 강동 / 유비·유기 강하", "한수 · 장강 · 양양 · 강릉 · 하구"]),
    "redcliffs_strategy_map.png": ("적벽 전투 │ 전략지형 개략", ["장강 중류 후보 구역 — 정확 전투점은 논쟁적", "황개 화선 → 조조 함대·강안 진영 / 강릉 퇴로"]),
    "redcliffs_sequence_map.png": ("208 적벽 전역 4단계", ["① 남하·질병  ② 첫 수전의 약점", "③ 황개 화선·강풍  ④ 연소 확산·철수"]),
}


def font(size, bold=False):
    index = 1 if bold else 0
    return ImageFont.truetype(FONT, size=size, index=index)


for name, (title, lines) in LABELS.items():
    path = ROOT / name
    image = Image.open(path).convert("RGB")
    if name == "armada_country_map.png":
        # 대륙 세력도는 해전 장면보다 저채도·고명암의 지도 톤으로 분리한다.
        image = ImageEnhance.Color(image).enhance(0.62)
        image = ImageEnhance.Contrast(image).enhance(1.28)
    width, height = image.size
    draw = ImageDraw.Draw(image, "RGBA")
    top_h = max(118, height // 11)
    bottom_h = max(150, height // 9)
    draw.rectangle((0, 0, width, top_h), fill=(10, 18, 27, 220))
    draw.rectangle((0, height - bottom_h, width, height), fill=(10, 18, 27, 218))
    title_font = font(max(34, width // 25), True)
    body_font = font(max(25, width // 36), False)
    draw.text((width // 2, top_h // 2), title, font=title_font, anchor="mm", fill=(255, 221, 112, 255), stroke_width=1, stroke_fill=(0, 0, 0, 255))
    y = height - bottom_h + 35
    for line in lines:
        draw.text((width // 2, y), line, font=body_font, anchor="ma", fill=(245, 248, 250, 255), stroke_width=1, stroke_fill=(0, 0, 0, 255))
        y += body_font.size + 18
    if name == "armada_country_map.png":
        # 시대 세력도만의 대서양-해협 이동축을 넣어 전략지형도와 시각 역할을 분리한다.
        route = [(int(width * .18), int(height * .72)), (int(width * .34), int(height * .57)),
                 (int(width * .51), int(height * .48)), (int(width * .69), int(height * .39)),
                 (int(width * .79), int(height * .31))]
        draw.line(route, fill=(255, 208, 76, 235), width=max(9, width // 90), joint="curve")
        for x, y0 in route:
            r = max(10, width // 75)
            draw.ellipse((x-r, y0-r, x+r, y0+r), fill=(17, 35, 53, 235), outline=(255, 221, 112, 255), width=4)
    image.save(path, quality=95)
