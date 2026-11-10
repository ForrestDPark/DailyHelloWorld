from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

def f(size, bold=False):
    return ImageFont.truetype(FONT, size=size, index=7 if bold else 0)

def label(draw, x, y, text, color=(14, 25, 40, 225), size=27):
    font = f(size, True)
    bb = draw.multiline_textbbox((x, y), text, font=font, anchor="mm", align="center", spacing=4, stroke_width=2)
    p = 12
    draw.rounded_rectangle((bb[0]-p, bb[1]-p, bb[2]+p, bb[3]+p), 12, fill=color, outline=(255, 220, 130, 255), width=3)
    draw.multiline_text((x, y), text, font=font, anchor="mm", align="center", fill="white", spacing=4, stroke_width=2, stroke_fill="#111")

def title(im, text, sub):
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle((0, 0, im.width, 116), fill=(7, 12, 22, 238))
    d.text((im.width/2, 48), text, font=f(40, True), fill="#ffd86b", anchor="mm", stroke_width=2, stroke_fill="#000")
    d.text((im.width/2, 91), sub, font=f(24), fill="white", anchor="mm", stroke_width=2, stroke_fill="#000")
    return d

def arrow(d, points, color, width=12):
    import math
    d.line(points, fill=color, width=width, joint="curve")
    x1, y1 = points[-2]; x2, y2 = points[-1]
    a = math.atan2(y2-y1, x2-x1); L = 30
    d.polygon([(x2,y2),(x2-L*math.cos(a-.6),y2-L*math.sin(a-.6)),(x2-L*math.cos(a+.6),y2-L*math.sin(a+.6))], fill=color)

def make(name, heading, sub, labels, arrows=()):
    im = Image.open(ROOT/name).convert("RGBA")
    d = title(im, heading, sub)
    for pts, color in arrows:
        arrow(d, pts, color)
    for x,y,text,color,size in labels:
        label(d,x,y,text,color,size)
    im.convert("RGB").save(ROOT/name, quality=96)
    q = im.convert("RGB"); q.thumbnail((390,390)); q.save(ROOT/"qa"/(Path(name).stem+"_390.png"), quality=92)

BLUE=(12,70,135,228); RED=(130,25,30,228); GOLD=(120,78,8,232); DARK=(15,22,34,232)

make("tate_commanders.png","TATE 반간 작전 주요 인물","적 무전수를 포착해 통제된 정보 통로로 뒤집다",[
 (510,190,"MI5 감독·무전 감청",BLUE,25),(790,720,"울프 슈미트\nTATE",GOLD,28),(265,760,"로니 리드\nMI5 담당관",BLUE,25),(1320,760,"독일군 정보부\n아프베어",RED,25)])
make("tate_soldiers_weapons_life.png","TATE 장비·생활·감시 체계","낙하 장비·여행용 무전기·암호표·통제 숙소",[
 (280,170,"독일 파견 무전원",RED,24),(680,590,"여행용 무전기·모스키",GOLD,24),(1325,230,"통제 숙소·경비",BLUE,24),(1280,760,"영국 무전 감청·기록",BLUE,24)])
make("tate_command_structure.png","TATE 지휘·정보 편제","XX위원회 승인 → MI5 담당관 → 통제 무전 → 아프베어",[
 (300,175,"XX위원회\n기만 승인",BLUE,24),(250,650,"MI5 담당관",BLUE,24),(760,650,"TATE\n통제 송신",GOLD,24),(1320,650,"아프베어\n수신·지시",RED,24)], [([(300,230),(300,540),(700,620)],"#4da3ff"), ([(830,650),(1210,650)],"#ffd34d")])
make("tate_country_map.png","1940~44년 북서유럽 정보전 세력도","영국의 통제망과 독일 정보부의 장거리 무전 연결",[
 (430,600,"영국\nMI5 통제망",BLUE,25),(1240,620,"독일·점령지\n아프베어",RED,25),(780,420,"북해",DARK,24)])
make("tate_strategy_map.png","TATE 전략지형도","케임브리지셔 → 런던·캠프020 → 북해 무전망",[
 (280,460,"케임브리지셔\n투입·포착",GOLD,24),(300,760,"런던·캠프020\n심문·전향",BLUE,24),(1280,560,"독일 수신망\n보고·지시",RED,24),(690,820,"영국해협",DARK,23)], [([(300,500),(300,690)],"#4da3ff"), ([(420,720),(900,600),(1180,560)],"#ffd34d")])
make("tate_sequence.png","TATE 반간 작전 4단계","투입 → 포착·평가 → 통제 송신 → 장기 기만망",[
 (390,450,"1 투입\n1940년 낙하",RED,24),(1190,450,"2 평가\n협력 조건 확정",BLUE,24),(390,925,"3 導·舍\n통제 무전 운용",GOLD,24),(1190,925,"4 되먹임\n적 신뢰·반응 확인",BLUE,24)])

make("eyu_commanders.png","알여 전투 주요 인물","조사·허력·진나라 첩자·진장 호양",[
 (515,210,"조사\n조나라 총지휘",BLUE,27),(240,610,"허력\n고지 선점 건의",BLUE,24),(1020,690,"진나라 첩자\n후대 후 귀환",GOLD,23),(1370,230,"호양\n진나라 지휘",RED,25)])
make("eyu_soldiers_weapons_life.png","알여 병사·무기·생활","보병·쇠뇌·전차·척후·산악 행군 보급",[
 (260,290,"조나라 보병·쇠뇌",BLUE,23),(1280,290,"진나라 보병·전차",RED,23),(720,640,"척후·전령",GOLD,22),(260,920,"삿갓·갑옷·방패",DARK,22),(760,930,"검·창·쇠뇌",DARK,22),(1260,930,"군량·취사·말먹이",DARK,22)])
make("eyu_command_structure.png","알여 지휘·정보 편제","조왕 승인 → 조사 결심 → 허력 고지 건의 │ 호양·진나라 첩자",[
 (270,220,"조 혜문왕\n구원 승인",BLUE,23),(460,530,"조사\n총지휘",BLUE,25),(740,230,"허력\n북산 건의",BLUE,23),(1130,530,"호양\n진군 지휘",RED,24),(1400,390,"진나라 첩자\n허상 보고",GOLD,22)], [([(300,280),(430,470)],"#4da3ff"), ([(700,280),(510,480)],"#4da3ff"), ([(1340,430),(1180,500)],"#ffd34d")])
make("eyu_country_map.png","기원전 269년 전국 세력도","진·조·한 접경과 태항산맥의 전략 압력",[
 (310,520,"진(秦)",RED,28),(690,280,"조(趙)",BLUE,28),(650,690,"한(韓)",GOLD,27),(990,330,"태항산맥",DARK,24),(1160,520,"위(魏)·연(燕) 주변 세력",DARK,22)])
make("eyu_strategy_map.png","알여 전투 전략지형도","한단·무안의 정지 허상 → 2일 1야 급행군 → 북산 고지",[
 (1290,660,"한단(邯鄲)\n조나라 출발",BLUE,23),(840,620,"무안(武安)\n28일 보루",BLUE,23),(270,480,"알여(閼與)\n진군 포위",RED,23),(540,240,"북산 고지\n조군 선점",GOLD,23)], [([(1260,650),(900,620),(600,460),(350,470)],"#4da3ff"), ([(590,430),(560,290)],"#ffd34d")])
make("eyu_sequence.png","알여 전역 4단계","보루 정지 → 첩자 후대·귀환 → 급행군 → 고지 선점·격파",[
 (390,450,"1 허상\n28일 보루 구축",BLUE,23),(1190,450,"2 舍\n진 첩자를 후대·귀환",GOLD,23),(390,925,"3 반전\n갑옷을 말아 급행군",BLUE,23),(1190,925,"4 결전\n북산 선점·진군 격파",BLUE,23)])
