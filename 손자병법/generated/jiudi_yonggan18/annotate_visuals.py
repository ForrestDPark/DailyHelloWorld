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


def fit_font(draw, text, max_width, start):
    size = start
    while size > 28:
        font = ImageFont.truetype(FONT, size)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
        size -= 2
    return ImageFont.truetype(FONT, size)


for name, (title, detail) in LABELS.items():
    path = ROOT / name
    image = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    top_h = max(104, round(height * 0.075))
    bottom_h = max(132, round(height * 0.09))
    draw.rectangle((0, 0, width, top_h), fill=(8, 16, 27, 225))
    draw.rectangle((0, height - bottom_h, width, height), fill=(8, 16, 27, 225))
    title_font = fit_font(draw, title, width - 80, 68)
    detail_font = fit_font(draw, detail, width - 80, 46)
    draw.text((40, top_h / 2), title, font=title_font, fill=(255, 226, 145, 255), anchor="lm")
    draw.text((40, height - bottom_h / 2), detail, font=detail_font, fill=(255, 255, 255, 255), anchor="lm")
    image.save(path, "PNG", optimize=True)
