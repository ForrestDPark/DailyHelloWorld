#!/usr/bin/env python3
"""구지편 18구절의 독립 생성 원본 12장에 정확한 한국어 라벨만 합성한다."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent / "generated" / "jiudi18"
SIZE = (2400, 1600)
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"


def font(size, bold=True):
    return ImageFont.truetype(FONT, size, index=2 if bold else 0)


def put(draw, xy, text, size=50, fill="white", anchor="mm", box=True):
    x, y = xy
    f = font(size)
    if box:
        bounds = draw.multiline_textbbox((x, y), text, font=f, anchor=anchor, spacing=8, align="center")
        pad_x, pad_y = 18, 12
        draw.rounded_rectangle(
            (bounds[0] - pad_x, bounds[1] - pad_y, bounds[2] + pad_x, bounds[3] + pad_y),
            radius=14, fill=(12, 15, 20, 210), outline=(238, 213, 150, 230), width=3,
        )
    draw.multiline_text((x, y), text, font=f, fill=fill, anchor=anchor, spacing=8, align="center",
                        stroke_width=2, stroke_fill=(0, 0, 0, 220))


def title(draw, text):
    draw.rectangle((0, 0, SIZE[0], 135), fill=(8, 10, 14, 235))
    put(draw, (SIZE[0] // 2, 68), text, 67, box=False)


def finish(source, output, heading, labels):
    image = Image.open(ROOT / source).convert("RGB").resize(SIZE, Image.Resampling.LANCZOS).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    title(draw, heading)
    for x, y, text, size in labels:
        put(draw, (int(x * SIZE[0]), int(y * SIZE[1])), text, size)
    image.convert("RGB").save(ROOT / output, quality=95)


def main():
    jobs = [
        ("salamis_commanders_source_v2.png", "salamis_commanders.png", "살라미스 해전 주요 인물 · 기원전 480년", [
            (.19,.47,"테미스토클레스\n아테네 전략가",46),(.32,.78,"에우리비아데스\n연합함대 총지휘",43),
            (.69,.70,"아르테미시아\n할리카르나소스 지휘관",40),(.85,.47,"크세르크세스 1세\n페르시아 대왕",46)]),
        ("redcliffs_commanders_source_v2.png", "redcliffs_commanders.png", "적벽대전 주요 인물 · 208년", [
            (.14,.79,"주유\n연합 수군 총지휘",44),(.31,.48,"황개\n화공 선봉",43),(.35,.89,"유비\n육상 협동군",42),
            (.60,.82,"제갈량\n유비 측 사절·참모",40),(.84,.79,"조조\n북방 원정군 총지휘",45)]),
        ("salamis_soldiers_source_v2.png", "salamis_soldiers_weapons_life.png", "살라미스의 병사·무기·식량·정찰", [
            (.17,.48,"그리스 해병\n창·아스피스",42),(.48,.48,"삼단노선\n충각·3단 노꾼",42),(.82,.48,"페르시아 해병\n활·비늘갑옷",40),
            (.20,.89,"노꾼의 피로가 기동 한계",38),(.52,.89,"보리빵·무화과·염장어",38),(.83,.89,"척후선·방패·깃발 신호",38)]),
        ("redcliffs_soldiers_source_v2.png", "redcliffs_soldiers_weapons_life.png", "적벽의 병사·무기·식량·정찰", [
            (.18,.45,"강동 수군\n장창·층갑",41),(.48,.45,"한대 쇠뇌병\n쇠뇌·화살통",41),(.80,.45,"북방 보병\n수전에 미숙",41),
            (.20,.88,"황개 화선대\n갈대·기름·점화구",37),(.51,.88,"쌀·조·건량·생선",38),(.82,.88,"쾌속 정찰선·기치 신호",37)]),
        ("salamis_command_structure_source_v2.png", "salamis_command_structure.png", "살라미스 지휘·작전 편제", [
            (.24,.30,"에우리비아데스\n연합 총지휘",43),(.24,.49,"테미스토클레스\n아테네 주력·계책",41),
            (.20,.69,"아이기나·메가라\n폴리스별 함대",38),(.73,.28,"크세르크세스\n제국의 결전 명령",43),
            (.69,.50,"페니키아·이집트·이오니아\n다민족 함대",38),(.72,.72,"언어·지휘 분산\n좁은 수역 과밀",38)]),
        ("redcliffs_command_structure_source_v2.png", "redcliffs_command_structure.png", "적벽 손·유 연합과 조조군의 지휘 구조", [
            (.25,.27,"손권\n결전 승인",42),(.20,.49,"주유·정보\n연합 수군 지휘",39),(.31,.67,"황개\n화선대",39),
            (.18,.81,"유비군\n별도 육상 협동",37),(.74,.27,"조조\n북방군 총지휘",43),(.72,.51,"형주 수군 + 북방 보병\n혼성 편제",38),
            (.75,.74,"질병·수전 미숙\n밀집 선단",38)]),
        ("salamis_country_map_source_v2.png", "salamis_country_map.png", "기원전 480년 에게해 세력도 · 북쪽이 위", [
            (.18,.69,"그리스 연합\n펠로폰네소스",39),(.36,.56,"살라미스",42),(.48,.48,"아테네·팔레론",39),
            (.70,.35,"페르시아 제국\n이오니아·아나톨리아",39),(.45,.76,"코린토스 지협",37)]),
        ("redcliffs_country_map_source_v2.png", "redcliffs_country_map.png", "208년 장강 중류 세력도 · 북쪽이 위", [
            (.31,.32,"조조군\n형주 남하축",40),(.52,.57,"적벽·오림",43),(.67,.67,"손권의 강동",40),
            (.76,.48,"시상",37),(.43,.65,"하구·유비군",38),(.58,.78,"장강",40)]),
        ("salamis_strategy_map_source_v2.png", "salamis_strategy_map.png", "살라미스 전략지형도 · 해협이 수적 우위를 압축하다", [
            (.23,.37,"살라미스섬",43),(.52,.31,"아티카 해안",42),(.52,.61,"좁은 해협\n그리스 반격선",39),
            (.72,.47,"페르시아 진입축",39),(.39,.49,"프시탈레이아섬",36),(.80,.30,"팔레론",38)]),
        ("redcliffs_strategy_map_source_v2.png", "redcliffs_strategy_map.png", "적벽 전략지형도 · 화선 접근과 화용 퇴로", [
            (.23,.62,"적벽 절벽\n연합군 대기",40),(.58,.34,"오림\n조조군 밀집 선단",40),(.45,.52,"황개 화선 접근",39),
            (.74,.67,"화용도\n진흙 퇴로",39),(.34,.33,"하구 방면\n손·유 연합 접근",38)]),
        ("salamis_sequence_source_v2.png", "salamis_sequence.png", "살라미스 해전 · 선택과 기만이 만든 네 단계", [
            (.24,.48,"1. 연합 내부의 철수 논쟁",36),(.74,.48,"2. 시킨노스의 거짓 전갈",36),
            (.24,.91,"3. 좁은 해협의 협동 반격",36),(.74,.91,"4. 페르시아 함대의 붕괴·철수",36)]),
        ("redcliffs_sequence_source_v2.png", "redcliffs_sequence.png", "적벽대전 · 결전 승인에서 화용 철수까지", [
            (.24,.48,"1. 손권이 항복론을 물리치다",36),(.74,.48,"2. 황개의 거짓 항복과 화선",36),
            (.24,.91,"3. 밀집 선단과 오림 영채로 번진 불",35),(.74,.91,"4. 화용의 진흙길로 무너진 철수",35)]),
    ]
    for job in jobs:
        finish(*job)


if __name__ == "__main__":
    main()
