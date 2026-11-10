from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent / "generated" / "jiudi_huogong9"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

LABELS = {
    "armada_commanders.png": ("칼레·그라블린 주요 인물", "승군: 하워드·드레이크·호킨스  |  패군: 메디나 시도니아"),
    "armada_soldiers.png": ("1588년 병사·함포·항해 생활", "선원·해병·함포·화약·정찰·신호·비스킷·식수"),
    "armada_command_structure.png": ("잉글랜드 함대와 스페인 무적함대 지휘 구조", "하워드의 4개 전대  |  메디나 시도니아·파르마 연결 실패"),
    "armada_country_map.png": ("1588년 영국해협·플랑드르 세력도", "도버－칼레－그라블린－제일란트 얕은 바다"),
    "armada_strategy_map.png": ("칼레 화선·그라블린 전략지형도", "풍상 잉글랜드 함대 → 야간 화선 → 닻 절단·분산 → 추격"),
    "armada_sequence_map.png": ("칼레·그라블린 단계별 전역", "① 파르마 대기  ② 화선  ③ 닻 절단  ④ 그라블린 포격·풍향 전환"),
    "chibi_commanders.png": ("적벽대전 주요 인물", "승군: 주유·황개·정보·유비  |  패군: 조조와 북군 지휘부"),
    "chibi_soldiers.png": ("208년 병사·무기·수군 생활", "수군·보병·궁노·방패·노·북·군량·기름 먹인 섶"),
    "chibi_command_structure.png": ("적벽대전 지휘·편제", "손권→주유·정보→황개 화선  |  유비 연합  |  조조→수륙군"),
    "chibi_country_map.png": ("208년 형주·강동 세력도", "북: 조조  |  동: 손권  |  하구: 유비·유기  |  중앙: 장강"),
    "chibi_strategy_map.png": ("적벽·오림 전략지형도", "동남풍 → 황개 화선 → 오림 선단·안영 연소 → 화용 퇴각"),
    "chibi_sequence_map.png": ("적벽대전 단계별 흐름", "① 강북·강남 대치  ② 화선 준비  ③ 풍급·연소  ④ 수륙 추격"),
}

for name, (title, subtitle) in LABELS.items():
    path = ROOT / name
    image = Image.open(path).convert("RGB")
    width, height = image.size
    bar_h = 150
    canvas = Image.new("RGB", (width, height + bar_h), "#111821")
    canvas.paste(image, (0, bar_h))
    draw = ImageDraw.Draw(canvas)
    draw.text((width // 2, 48), title, font=ImageFont.truetype(FONT, 48, index=1), fill="#f7d774", anchor="mm")
    draw.text((width // 2, 104), subtitle, font=ImageFont.truetype(FONT, 31), fill="#f3f5f7", anchor="mm")
    canvas.save(path, optimize=True)
