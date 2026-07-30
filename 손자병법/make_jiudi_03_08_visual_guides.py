#!/usr/bin/env python3
"""구지편 3~8구절의 인물 안내판·지휘 편제·전투 흐름도를 만든다."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "jiudi_03_08_commanders_source.png"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

CASES = [
    ("breitenfeld", "브라이텐펠트 전투", "틸리 백작", "구스타브 2세 아돌프",
     ["작센 침공·동맹 촉발", "파펜하임 조기 돌격", "스웨덴 전열 전환", "가톨릭 동맹군 붕괴"]),
    ("bi", "필 전투", "순림보", "초 장왕",
     ["진군 지휘부 분열", "선곡의 독단 도하", "초군의 집중 타격", "진군 패주"]),
    ("teutoburg_forest", "토이토부르크 숲 전투", "바루스", "아르미니우스",
     ["거짓 반란 정보", "로마군 장대 종대", "숲·늪 사이 매복", "세 군단 궤멸"]),
    ("fucha_1619", "심하 전투", "양호", "누르하치",
     ["명군 분진합격", "연락·지원 단절", "후금군 각개 집중", "명군 순차 격파"]),
    ("cannae", "칸나에 전투", "바로", "한니발",
     ["로마군 중앙 압박", "카르타고 중앙 후퇴", "기병의 배후 장악", "이중 포위 완성"]),
    ("julu", "거록 전투", "왕리", "항우",
     ["진군의 거록 포위", "항우의 파부침주", "아홉 차례 격전", "제후군 결집·진군 붕괴"]),
    ("anabasis", "만인대의 귀환", "티사페르네스", "크세노폰",
     ["그리스 지휘부 암살", "새 장군단 선출", "산악·강 협로 돌파", "흑해 도달"]),
    ("jieting", "가정 전투", "마속", "장합",
     ["마속의 산상 포진", "장합의 수원 차단", "촉군 대오 붕괴", "북벌 철수"]),
    ("austerlitz", "아우스터리츠 전투", "쿠투조프", "나폴레옹",
     ["프라첸 고지 유인", "연합군 남진", "프랑스군 중앙 돌파", "연합군 양분·패주"]),
    ("yiling", "이릉 전투", "유비", "육손",
     ["촉군 장기 주둔", "육손의 지구전", "건조기에 화공", "진영 연쇄 붕괴"]),
    ("tannenberg", "타넨베르크 전투", "삼소노프", "힌덴부르크",
     ["러시아군 분산 진입", "독일군 철도 재배치", "통신 감청·집중", "제2군 포위"]),
    ("maling", "마릉 전투", "방연", "손빈",
     ["감조계로 추격 유도", "위군의 경무장 추격", "마릉 협로 매복", "위군 지휘부 붕괴"]),
]


def font(size, bold=False):
    return ImageFont.truetype(FONT, size, index=1 if bold else 0)


def fit(draw, text, width, size=44):
    while size > 22 and draw.textbbox((0, 0), text, font=font(size, True))[2] > width:
        size -= 2
    return font(size, True)


def portrait_board(sheet, row, pair, slug, title, loser, winner):
    cw, ch = sheet.width // 4, sheet.height // 6
    a = pair * 2
    portraits = [sheet.crop(((a + i) * cw, row * ch, (a + i + 1) * cw, (row + 1) * ch)) for i in range(2)]
    out = Image.new("RGB", (1600, 760), "#11161c")
    d = ImageDraw.Draw(out)
    d.text((800, 42), f"{title} — 주요 인물 안내판", font=fit(d, title, 1450, 52),
           fill="#f7e8be", anchor="mm")
    for i, (im, name, color, result) in enumerate(zip(
        portraits, [loser, winner], ["#b5333e", "#2774c7"], ["패군", "승군"]
    )):
        im = im.resize((700, 430), Image.Resampling.LANCZOS)
        x = 60 + i * 780
        out.paste(im, (x, 120))
        d.rectangle((x, 570, x + 700, 700), fill=color)
        d.text((x + 350, 610), name, font=fit(d, name, 640, 43), fill="white", anchor="mm")
        d.text((x + 350, 665), result, font=font(27, True), fill="#f4e8d0", anchor="mm")
    out.save(ROOT / f"{slug}_commanders.png", quality=95)


def org_chart(slug, title, loser, winner):
    out = Image.new("RGB", (1600, 820), "#f2ead8")
    d = ImageDraw.Draw(out)
    d.text((800, 52), f"{title} — 장군 조직도·편제", font=fit(d, title, 1450, 50),
           fill="#222", anchor="mm")
    for i, (name, color, result) in enumerate(zip(
        [loser, winner], ["#a62e38", "#2469a8"], ["패군 지휘 체계", "승군 지휘 체계"]
    )):
        x = 90 + i * 780
        d.rounded_rectangle((x, 130, x + 640, 255), 18, fill=color)
        d.text((x + 320, 175), name, font=fit(d, name, 590, 38), fill="white", anchor="mm")
        d.text((x + 320, 220), result, font=font(25, True), fill="#f8ead2", anchor="mm")
        d.line((x + 320, 255, x + 320, 340), fill="#444", width=7)
        for j, label in enumerate(["본대·주력", "기동·별동", "보급·연락"]):
            bx = x + 10 + j * 215
            d.rounded_rectangle((bx, 340, bx + 190, 460), 14, fill="white", outline=color, width=5)
            d.text((bx + 95, 385), label, font=font(24, True), fill="#222", anchor="mm")
            d.text((bx + 95, 425), "역할 분담", font=font(20), fill="#555", anchor="mm")
        d.line((x + 320, 460, x + 320, 555), fill="#444", width=7)
        d.rounded_rectangle((x + 85, 555, x + 555, 685), 16, fill="#fff9ec", outline=color, width=5)
        d.text((x + 320, 602), "명령·정보·군량 전달", font=font(28, True), fill="#222", anchor="mm")
        d.text((x + 320, 648), "지휘관 → 예하 부대 → 전선", font=font(22), fill="#555", anchor="mm")
    d.text((800, 770), "※ 정확한 병력 수와 세부 직책은 본문의 法 표에서 사료 범위에 따라 확인",
           font=font(22), fill="#555", anchor="mm")
    out.save(ROOT / f"{slug}_command_structure.png", quality=95)


def sequence(slug, title, steps):
    bg_path = ROOT / f"{slug}_codex_map.png"
    bg = Image.open(bg_path).convert("RGB").resize((1600, 900), Image.Resampling.LANCZOS)
    shade = Image.new("RGBA", bg.size, (8, 12, 18, 120))
    bg = Image.alpha_composite(bg.convert("RGBA"), shade)
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle((50, 35, 1550, 145), 20, fill=(16, 20, 26, 225))
    d.text((800, 90), f"{title} — 전투 흐름", font=fit(d, title, 1400, 48),
           fill="#fff1c7", anchor="mm")
    colors = ["#344f78", "#7b4d2d", "#8c2f3b", "#286b55"]
    for i, step in enumerate(steps):
        x = 70 + i * 380
        d.rounded_rectangle((x, 610, x + 320, 810), 18, fill=colors[i], outline="#f4dfaa", width=4)
        d.text((x + 160, 650), str(i + 1), font=font(38, True), fill="#ffd86d", anchor="mm")
        d.multiline_text((x + 160, 725), step, font=fit(d, step, 285, 27),
                         fill="white", anchor="mm", align="center", spacing=8)
        if i < 3:
            d.polygon([(x + 335, 705), (x + 365, 725), (x + 335, 745)], fill="#ffd86d")
    bg.convert("RGB").save(ROOT / f"{slug}_codex_sequence_map.png", quality=95)


def main():
    sheet = Image.open(SOURCE).convert("RGB")
    for i, (slug, title, loser, winner, steps) in enumerate(CASES):
        portrait_board(sheet, i // 2, i % 2, slug, title, loser, winner)
        org_chart(slug, title, loser, winner)
        sequence(slug, title, steps)
    print(f"완료: {len(CASES) * 3}개 시각 자료")


if __name__ == "__main__":
    main()
