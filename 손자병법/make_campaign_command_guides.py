from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
FONT = "/Library/Fonts/NanumGothic.ttf"
FONT_BOLD = "/Library/Fonts/NanumGothicBold.ttf"
WIN_FILLS = {"#b9d7ea", "#d7ebf6", "#e5f1f7", "#e7b8a7", "#f1d2c6", "#f6e5df"}
LOSS_FILLS = {"#e4c7b5", "#edd9cb", "#f2e3d9", "#f5e9df", "#b7d7d3", "#d6e8e5", "#e7eee1"}


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def centered(draw, xy, text, fnt, fill):
    box = draw.multiline_textbbox((0, 0), text, font=fnt, spacing=8, align="center")
    w, h = box[2] - box[0], box[3] - box[1]
    draw.multiline_text((xy[0] - w / 2, xy[1] - h / 2), text, font=fnt, fill=fill, spacing=8, align="center")


def label_portrait(source, output, title, left_title, left_names, right_title, right_names):
    base = Image.open(source).convert("RGBA")
    width, height = base.size
    canvas = Image.new("RGBA", (width, height + 260), "#efe3c6")
    canvas.alpha_composite(base, (0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, 0, width, 100), fill=(23, 31, 39, 225))
    centered(draw, (width / 2, 50), title, font(48, True), "white")

    half = width // 2
    panels = [
        (0, half, left_title, left_names, (34, 58, 82, 255), "#79bfff"),
        (half, width, right_title, right_names, (80, 63, 48, 255), "#ff8b7d"),
    ]
    for x1, x2, group_title, names, color, name_color in panels:
        draw.rectangle((x1, height, x2, height + 260), fill=color)
        centered(draw, ((x1 + x2) / 2, height + 55), group_title, font(36, True), name_color)
        centered(draw, ((x1 + x2) / 2, height + 165), names, font(29, True), name_color)
    canvas.convert("RGB").save(output, quality=95)


def box(draw, xy, size, title, subtitle, fill, outline="#263238", title_color=None):
    x, y = xy
    w, h = size
    draw.rounded_rectangle((x, y, x + w, y + h), radius=22, fill=fill, outline=outline, width=4)
    if title_color is None:
        title_color = "#145da0" if fill in WIN_FILLS else "#b3261e" if fill in LOSS_FILLS else "#5a4630"
    centered(draw, (x + w / 2, y + 48), title, font(30, True), title_color)
    centered(draw, (x + w / 2, y + 112), subtitle, font(23), "#263238")
    return (x + w / 2, y), (x + w / 2, y + h)


def arrow(draw, start, end, color="#455a64", width=6, dashed=False):
    if dashed:
        steps = 18
        for i in range(0, steps, 2):
            t1, t2 = i / steps, min((i + 1) / steps, 1)
            p1 = (start[0] + (end[0] - start[0]) * t1, start[1] + (end[1] - start[1]) * t1)
            p2 = (start[0] + (end[0] - start[0]) * t2, start[1] + (end[1] - start[1]) * t2)
            draw.line((p1, p2), fill=color, width=width)
    else:
        draw.line((start, end), fill=color, width=width)
    ex, ey = end
    draw.polygon([(ex, ey), (ex - 14, ey - 22), (ex + 14, ey - 22)], fill=color)


def org_canvas(title, subtitle):
    im = Image.new("RGB", (2200, 1500), "#f5eedc")
    draw = ImageDraw.Draw(im)
    draw.rectangle((0, 0, 2200, 150), fill="#263238")
    centered(draw, (1100, 55), title, font(52, True), "white")
    centered(draw, (1100, 112), subtitle, font(27), "#d7e3e8")
    draw.line((1100, 180, 1100, 1430), fill="#b0a58d", width=4)
    return im, draw


def make_sherman_org():
    im, draw = org_canvas("셔먼의 바다로의 진군 — 장군 조직도와 작전 편제", "왼쪽 북군 · 오른쪽 남군 │ 실선: 지휘 · 점선: 별도 임무/유인")
    centered(draw, (535, 205), "북군(Union)", font(38, True), "#173f5f")
    centered(draw, (1665, 205), "남군(Confederacy)", font(38, True), "#6b3f2a")

    _, sh_b = box(draw, (310, 255), (450, 155), "윌리엄 T. 셔먼", "조지아 횡단 원정 총지휘", "#b9d7ea")
    _, sl_b = box(draw, (70, 520), (430, 155), "헨리 슬로컴", "좌익: 제14·20군단", "#d7ebf6")
    _, ho_b = box(draw, (570, 520), (430, 155), "올리버 하워드", "우익: 제15·17군단", "#d7ebf6")
    arrow(draw, sh_b, (285, 520))
    arrow(draw, sh_b, (785, 520))
    _, ki_b = box(draw, (70, 800), (430, 155), "저드슨 킬패트릭", "기병 엄호·정찰", "#e5f1f7")
    _, ha_b = box(draw, (570, 800), (430, 155), "윌리엄 헤이즌", "포트 맥앨리스터(Fort McAllister) 돌격", "#e5f1f7")
    arrow(draw, sl_b, (285, 800))
    arrow(draw, ho_b, (785, 800))
    box(draw, (310, 1110), (450, 170), "조지 H. 토머스", "테네시에 남아 후드군 저지\n셔먼 원정대와 분리된 임무", "#f1e3b9")
    arrow(draw, (535, 410), (535, 1110), color="#8a6d3b", dashed=True)

    _, hd_b = box(draw, (1440, 255), (450, 155), "존 벨 후드", "테네시로 북상한 남군 주력", "#e4c7b5")
    _, ha2_b = box(draw, (1440, 520), (450, 155), "윌리엄 하디", "조지아 방어·사바나(Savannah) 지휘", "#edd9cb")
    arrow(draw, hd_b, (1665, 520), color="#7b4b32", dashed=True)
    _, wh_b = box(draw, (1190, 800), (430, 155), "조지프 휠러", "기병 추적·교란", "#f2e3d9")
    _, sm_b = box(draw, (1690, 800), (430, 155), "조지아 민병대", "주 방위 전력", "#f2e3d9")
    arrow(draw, ha2_b, (1405, 800), color="#7b4b32")
    arrow(draw, ha2_b, (1905, 800), color="#7b4b32")
    box(draw, (1440, 1110), (450, 170), "플레전트 필립스", "그리스월드빌(Griswoldville)\n정면 공격 지휘·북군 진지 오판", "#f5e9df")
    arrow(draw, sm_b, (1665, 1110), color="#7b4b32")
    im.save(ROOT / "sherman_campaign_command_structure.png")


def make_sun_ce_org():
    im, draw = org_canvas("손책의 강동 평정 — 장군 조직도와 작전 편제", "왼쪽 손책군 · 오른쪽 유요·왕랑 측 │ 점선: 명목상 관계 또는 진영 이동")
    centered(draw, (535, 205), "손책군", font(38, True), "#7b2f24")
    centered(draw, (1665, 205), "유요·왕랑 측", font(38, True), "#245b5e")

    _, sc_b = box(draw, (310, 255), (450, 155), "손책", "강동 원정 총지휘", "#e7b8a7")
    box(draw, (40, 255), (220, 155), "원술", "병력 제공\n명목상 상급자", "#eadfc5")
    arrow(draw, (260, 332), (310, 332), color="#8a6d3b", dashed=True)
    _, zy_b = box(draw, (70, 520), (430, 165), "주유", "병력·선박·군량 지원\n도강 기반 마련", "#f1d2c6")
    _, sj_b = box(draw, (570, 520), (430, 165), "손정", "고릉(高陵) 교착 뒤 사독(查瀆) 우회 제안", "#f1d2c6")
    arrow(draw, sc_b, (285, 520), color="#8c3d2d")
    arrow(draw, sc_b, (785, 520), color="#8c3d2d")
    box(draw, (70, 820), (430, 170), "전방 공격대", "횡강(橫江)·당리(當利) 나루 돌파\n우저(牛渚) 군수 거점 확보", "#f6e5df")
    box(draw, (570, 820), (430, 170), "태사자", "유요의 정찰대 → 손책의 장수\n잔병 1만여 명 수습", "#eadbbf")
    arrow(draw, zy_b, (285, 820), color="#8c3d2d")
    arrow(draw, sj_b, (785, 820), color="#8c3d2d")

    _, ly_b = box(draw, (1440, 255), (450, 155), "유요", "곡아 중심 강동 방어", "#b7d7d3")
    _, zy2_b = box(draw, (1160, 540), (390, 165), "장영", "당리구(當利口) 방어", "#d6e8e5")
    _, fy_b = box(draw, (1590, 540), (500, 165), "번능·우미", "횡강진(橫江津) 방어", "#d6e8e5")
    arrow(draw, ly_b, (1355, 540), color="#2f6f73")
    arrow(draw, ly_b, (1840, 540), color="#2f6f73")
    box(draw, (1160, 840), (390, 175), "태사자", "능력은 있었으나\n대군 지휘권을 받지 못함", "#e7eee1")
    box(draw, (1590, 840), (500, 175), "왕랑", "회계(會稽)·고릉(高陵) 방어선 지휘", "#d6e8e5")
    arrow(draw, ly_b, (1355, 840), color="#2f6f73", dashed=True)
    arrow(draw, (1840, 705), (1840, 840), color="#2f6f73")
    arrow(draw, (1355, 1015), (785, 820), color="#8a6d3b", dashed=True)
    centered(draw, (1100, 1225), "태사자: 유요가 권한을 주지 못한 장수 → 손책이 신뢰와 재량을 주어 편입", font(30, True), "#514735")
    centered(draw, (1100, 1320), "핵심 대비: 손책군은 사람·선박·군량을 결합했고, 유요군은 나루별 분산 배치와 인재 운용 실패로 각개 격파됐다.", font(26), "#514735")
    im.save(ROOT / "sun_ce_campaign_command_structure.png")


def main():
    label_portrait(
        ROOT / "sherman_campaign_commanders_source.png",
        ROOT / "sherman_campaign_commanders.png",
        "셔먼의 바다로의 진군 — 주요 인물",
        "북군: 셔먼의 원정 지휘부",
        "왼쪽부터 토머스 · 하워드 · 셔먼 · 슬로컴 · 헤이즌",
        "남군: 추격 유도와 조지아 방어",
        "왼쪽부터 후드 · 하디 · 필립스",
    )
    label_portrait(
        ROOT / "sun_ce_campaign_commanders_source.png",
        ROOT / "sun_ce_campaign_commanders.png",
        "손책의 강동 평정 — 주요 인물",
        "손책군과 합류한 인물들",
        "왼쪽부터 주유 · 손책 · 손정 · 태사자",
        "유요·왕랑 측 방어 지휘부",
        "왼쪽부터 유요 · 왕랑 · 장영 · 번능 · 우미",
    )
    make_sherman_org()
    make_sun_ce_org()


if __name__ == "__main__":
    main()
