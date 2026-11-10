from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent / "generated" / "jiudi_huogong12"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

LABELS = {
    "cer_commanders.png": ("체르 전투 주요 인물", "승군: 스테파노비치·푸트니크  |  패군: 포티오레크"),
    "cer_soldiers.png": ("1914년 병사·무기·생활", "소총·기관총·야포·정찰·전령·급양·야전의무"),
    "cer_command_structure.png": ("체르 전투 지휘·편제", "세르비아 최고사령부→제2군  |  발칸군사령부→제5군"),
    "cer_country_map.png": ("1914년 세르비아 전역 세력도", "북·서: 오스트리아-헝가리  |  남·동: 세르비아"),
    "cer_strategy_map.png": ("체르 전투 전략지형도", "드리나·사바 도하 → 체르산 집중 → 서쪽 퇴로 차단"),
    "cer_sequence_map.png": ("체르 전투 단계별 흐름", "① 도하  ② 강행군  ③ 산악 역습  ④ 드리나 방면 퇴각"),
    "yiling_commanders.png": ("이릉대전 주요 인물", "승군: 육손·주연·반장  |  패군: 유비·풍습·오반·마량"),
    "yiling_soldiers.png": ("222년 병사·무기·생활", "보병·쇠뇌·방패·수군·정찰·북·군량·화공 묶음"),
    "yiling_command_structure.png": ("이릉대전 지휘·편제", "손권→육손→오군 각부  |  유비→풍습·오반→연속 진영"),
    "yiling_country_map.png": ("이릉대전 시대 세력도", "서: 촉한·백제성  |  동: 손오·이릉·강릉  |  중앙: 장강 삼협"),
    "yiling_strategy_map.png": ("이릉대전 전략지형도", "자귀→효정 장거리 연영  |  육손의 지연·집중·화공"),
    "yiling_sequence_map.png": ("이릉대전 단계별 흐름", "① 동정  ② 여름 교착  ③ 시험 공격·화공  ④ 마안산·백제성 퇴각"),
}

for name, (title, subtitle) in LABELS.items():
    path = ROOT / name
    image = Image.open(path).convert("RGB")
    width, height = image.size
    bar_h = max(150, int(height * 0.115))
    canvas = Image.new("RGB", (width, height + bar_h), "#111821")
    canvas.paste(image, (0, bar_h))
    draw = ImageDraw.Draw(canvas)
    title_font = ImageFont.truetype(FONT, max(34, width // 25), index=1)
    sub_font = ImageFont.truetype(FONT, max(24, width // 38), index=0)
    draw.text((width // 2, bar_h * 0.36), title, font=title_font, fill="#f7d774", anchor="mm")
    draw.text((width // 2, bar_h * 0.72), subtitle, font=sub_font, fill="#f3f5f7", anchor="mm")
    canvas.save(path, optimize=True)
