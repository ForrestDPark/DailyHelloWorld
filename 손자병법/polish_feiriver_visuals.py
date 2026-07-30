#!/usr/bin/env python3
"""비수대전 생성형 원화 네 장에 정확한 한국어 정보 계층을 입힌다."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "generated" / "jiudi14"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"


def font(size, bold=False):
    return ImageFont.truetype(FONT, size, index=1 if bold else 0)


def fitted(draw, text, width, size=30, bold=True):
    while size > 13 and draw.textbbox((0, 0), text, font=font(size, bold))[2] > width:
        size -= 1
    return font(size, bold)


def plaque(draw, x, y, width, text, color="#392b1d", size=22):
    lines = text.split("\n")
    face = fitted(draw, max(lines, key=len), width - 24, size)
    line_h = face.size + 5
    height = line_h * len(lines) + 18
    draw.rounded_rectangle(
        (x - width / 2, y - height / 2, x + width / 2, y + height / 2),
        10, fill="#f4e7c9e8", outline=color, width=3,
    )
    draw.multiline_text(
        (x, y), text, font=face, fill=color, anchor="mm",
        align="center", spacing=5,
    )


def title(draw, image, main, sub):
    draw.rounded_rectangle(
        (280, 10, image.width - 280, 96), 12,
        fill=(24, 31, 36, 225), outline="#b99a60", width=3,
    )
    draw.text(
        (image.width / 2, 40), main,
        font=fitted(draw, main, image.width - 640, 34),
        fill="#fff0cf", anchor="mm",
    )
    draw.text(
        (image.width / 2, 73), sub,
        font=fitted(draw, sub, image.width - 650, 18, False),
        fill="#d7d0c0", anchor="mm",
    )


def command():
    image = Image.open(OUT / "feiriver_command_structure_source_v2.png").convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    title(
        draw, image,
        "비수대전 — 장군 조직도와 작전 편제",
        "동진의 짧고 단단한 지휘망과 전진의 거대하지만 분산된 혼성군",
    )
    entries = [
        (382, 325, 270, "사안(謝安)\n정치·전략 총괄", "#1268aa"),
        (107, 565, 195, "사석(謝石)\n정토대도독", "#1268aa"),
        (320, 565, 205, "사현(謝玄)\n북부병 지휘", "#1268aa"),
        (522, 565, 205, "유뢰지(劉牢之)\n정예 5천 선봉", "#1268aa"),
        (720, 565, 205, "북부병 장수단\n도하·추격", "#1268aa"),
        (1282, 325, 250, "부견(苻堅)\n전진 황제·총지휘", "#9b2d29"),
        (963, 565, 190, "부융(苻融)\n전선 총지휘", "#9b2d29"),
        (1112, 565, 190, "양성(梁成)\n낙간 전초군", "#9b2d29"),
        (1260, 565, 190, "모용수(慕容垂)\n선비계 병력", "#9b2d29"),
        (1410, 565, 190, "요장(姚萇)\n강족계 병력", "#9b2d29"),
        (1562, 565, 190, "징발·항복군\n다민족 혼성군", "#9b2d29"),
    ]
    for x, y, width, text, color in entries:
        plaque(draw, x, y, width, text, color, 19)
    plaque(
        draw, 835, 905, 760,
        "동진: 같은 훈련·신호·지휘망으로 움직인 소수 정예  |  전진: 병력은 컸지만 후퇴 이유와 정지선을 공유하지 못한 연합군",
        "#72592f", 18,
    )
    image.save(OUT / "feiriver_command_structure_v2.png", quality=96)


def country():
    image = Image.open(OUT / "feiriver_country_map_source_v2.png").convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    title(
        draw, image,
        "비수대전 — 383년 전진·동진 세력도와 남정로",
        "붉은 전진군은 북방에서 수양으로 집결하고, 푸른 동진 북부병은 광릉에서 비수 전선으로 나아갔다",
    )
    entries = [
        (490, 332, 190, "장안(長安)\n전진 수도", "#9b2d29"),
        (755, 420, 190, "항성(項城)\n부견의 대군", "#9b2d29"),
        (1010, 385, 185, "낙양(洛陽)", "#9b2d29"),
        (1260, 345, 190, "전진 북동군", "#9b2d29"),
        (840, 565, 210, "수양(壽陽)\n비수 전선", "#6b4c22"),
        (1275, 660, 210, "광릉(廣陵)\n북부병 기반", "#1268aa"),
        (1320, 855, 210, "건강(建康)\n동진 수도", "#1268aa"),
        (355, 555, 190, "양쯔강 상류", "#1268aa"),
    ]
    for x, y, width, text, color in entries:
        plaque(draw, x, y, width, text, color, 19)
    plaque(
        draw, 830, 905, 720,
        "붉은 영역: 전진(前秦)  |  푸른 영역: 동진(東晉)  |  경계는 현대 국경선이 아니라 383년 무렵의 대략적 세력권",
        "#5e492d", 18,
    )
    image.save(OUT / "feiriver_country_map_v2.png", quality=96)


def strategy():
    image = Image.open(OUT / "feiriver_strategy_source_v2.png").convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    title(
        draw, image,
        "비수대전 전략지형도 — ‘조금 물러나라’가 전군의 패주가 된 순간",
        "낙간 선제기습 → 팔공산의 동요 → 비수의 부분 후퇴 → 주서의 외침과 부융 전사 → 북부병 추격",
    )
    entries = [
        (180, 258, 210, "① 낙간(洛澗)\n유뢰지 야간기습", "#1268aa"),
        (455, 205, 210, "② 수양(壽陽)\n전진군 본영", "#9b2d29"),
        (980, 205, 220, "③ 팔공산(八公山)\n초목개병의 동요", "#6f532b"),
        (795, 470, 190, "④ 비수(淝水)\n결전 도하점", "#1268aa"),
        (780, 710, 245, "⑤ 사현·북부병\n도하 즉시 돌격", "#1268aa"),
        (1340, 680, 230, "⑥ 동진 기병\n측면 추격", "#1268aa"),
        (1385, 440, 245, "⑦ 부융 전사\n후퇴 통제 붕괴", "#9b2d29"),
        (1450, 150, 200, "⑧ 전진군 패주\n북쪽으로 붕괴", "#9b2d29"),
    ]
    for x, y, width, text, color in entries:
        plaque(draw, x, y, width, text, color, 18)
    image.save(OUT / "feiriver_strategy_map_v2.png", quality=96)


def sequence():
    image = Image.open(OUT / "feiriver_sequence_source_v2.png").convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    title(
        draw, image,
        "비수대전 — 의심이 패주로 바뀐 네 장면",
        "같은 후퇴 명령도 신뢰와 편제가 없으면 전군 붕괴의 신호가 된다",
    )
    captions = [
        (210, 455, "1. 낙간 선제기습\n유뢰지의 정예 5천이\n양성의 전초군을 격파", "#1268aa"),
        (1040, 455, "2. 팔공산의 동요\n부견은 초목까지\n동진군으로 의심", "#9b2d29"),
        (220, 855, "3. 도하 요청 수락\n전진군이 승부를 위해\n강가에서 잠시 후퇴", "#9b2d29"),
        (1055, 855, "4. 거짓 패전과 붕괴\n주서의 외침·부융 전사 뒤\n북부병이 도하해 추격", "#6f532b"),
    ]
    for x, y, text, color in captions:
        plaque(draw, x, y, 330, text, color, 18)
    image.save(OUT / "feiriver_sequence_map_v2.png", quality=96)


if __name__ == "__main__":
    command()
    country()
    strategy()
    sequence()
