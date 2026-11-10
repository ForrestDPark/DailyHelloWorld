from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

def font(size, bold=False):
    return ImageFont.truetype(FONT, size=size, index=7 if bold else 0)

def box(draw, xy, text, fill=(18, 24, 34, 220), outline=(255, 220, 120, 255), size=31, anchor="mm"):
    x, y = xy
    f = font(size, True)
    bb = draw.multiline_textbbox((x, y), text, font=f, anchor=anchor, align="center", spacing=4, stroke_width=2)
    pad = 12
    draw.rounded_rectangle((bb[0]-pad, bb[1]-pad, bb[2]+pad, bb[3]+pad), 12, fill=fill, outline=outline, width=3)
    draw.multiline_text((x, y), text, font=f, fill="white", anchor=anchor, align="center", spacing=4, stroke_width=2, stroke_fill="#111111")

def title(im, text, subtitle):
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle((0, 0, im.width, 104), fill=(8, 12, 20, 235))
    d.text((im.width/2, 39), text, font=font(39, True), fill="#ffd86b", anchor="mm", stroke_width=2, stroke_fill="#000")
    d.text((im.width/2, 79), subtitle, font=font(24), fill="white", anchor="mm", stroke_width=2, stroke_fill="#000")
    return d

def legend(d, im, items):
    y = im.height - 90
    d.rounded_rectangle((22, y-26, im.width-22, im.height-18), 14, fill=(10, 15, 25, 225), outline="#e5c76b", width=3)
    x = 45
    for color, text in items:
        d.line((x, y+4, x+52, y+4), fill=color, width=9)
        d.text((x+62, y+4), text, font=font(22, True), fill="white", anchor="lm", stroke_width=1, stroke_fill="#000")
        x += 250

def arrow(d, pts, color, width=12):
    d.line(pts, fill=color, width=width, joint="curve")
    x1,y1=pts[-2]; x2,y2=pts[-1]
    import math
    a=math.atan2(y2-y1,x2-x1); L=28
    p1=(x2-L*math.cos(a-.6),y2-L*math.sin(a-.6)); p2=(x2-L*math.cos(a+.6),y2-L*math.sin(a+.6))
    d.polygon([(x2,y2),p1,p2], fill=color)

def annotate_people(name, title_text, subtitle, labels):
    im=Image.open(ROOT/name).convert("RGBA"); d=title(im,title_text,subtitle)
    for x,y,text,color in labels: box(d,(x,y),text,fill=color,size=25)
    im.convert("RGB").save(ROOT/name,quality=95)

def annotate_structure(name,title_text,subtitle,nodes,lines):
    im=Image.open(ROOT/name).convert("RGBA"); d=title(im,title_text,subtitle)
    for a,b,color in lines: arrow(d,[a,b],color,7)
    for x,y,text,color in nodes: box(d,(x,y),text,fill=color,size=22)
    legend(d,im,[("#4da3ff","승군 지휘·정보"),("#ff5a5a","패군 지휘"),("#ffd34d","정보 전달")])
    im.convert("RGB").save(ROOT/name,quality=95)

def annotate_map(name,title_text,subtitle,labels,arrows,items):
    im=Image.open(ROOT/name).convert("RGBA"); d=title(im,title_text,subtitle)
    for pts,color in arrows: arrow(d,pts,color,10)
    for x,y,text,color in labels: box(d,(x,y),text,fill=color,size=21)
    legend(d,im,items)
    im.convert("RGB").save(ROOT/name,quality=95)

def annotate_sequence(name,title_text,subtitle,labels):
    im=Image.open(ROOT/name).convert("RGBA"); d=title(im,title_text,subtitle)
    for x,y,text in labels: box(d,(x,y),text,size=22)
    im.convert("RGB").save(ROOT/name,quality=95)

BLUE=(15,70,130,225); RED=(125,25,30,225); GOLD=(115,75,10,230); DARK=(18,24,34,225)

annotate_people("yorktown_commanders.png","요크타운 주요 인물","정보가 육해군 포위로 바뀐 지휘 연쇄",[
 (220,360,"제임스 라파예트\n정보원",BLUE),(470,400,"라파예트\n버지니아군",BLUE),(850,390,"콘월리스\n영국군",RED),(990,560,"태를턴\n기동부대",RED)])
annotate_people("yorktown_soldiers_weapons_life.png","요크타운 병사·무기·생활","보병·전령·포병·보급이 함께 움직인 1781년 전역",[
 (260,275,"대륙군 보병\n머스킷·총검",BLUE),(820,280,"프랑스 보병\n공성 지원",BLUE),(265,650,"영국 보병\n요새 방어",RED),(815,650,"기마 전령\n정찰·보고",GOLD),(270,1050,"공성 포병\n중포·탄약",BLUE),(820,1080,"숙영·식량\n수레 보급",DARK)])
annotate_structure("yorktown_command_structure.png","요크타운 지휘·정보 편제","제임스의 보고 → 라파예트 → 연합 최고지휘부 → 육해군 포위",[
 (280,190,"워싱턴\n미군 총사령관",BLUE),(820,190,"로샹보\n프랑스군",BLUE),(300,545,"라파예트\n버지니아 견제",BLUE),(810,545,"드 그라스\n체서피크 함대",BLUE),(540,785,"제임스 라파예트\n인적정보",GOLD),(550,1090,"콘월리스\n요크타운 주둔",RED)], [((540,760),(330,585),"#ffd34d"),((330,515),(290,230),"#4da3ff"),((330,515),(780,230),"#4da3ff"),((780,230),(810,505),"#4da3ff")])
annotate_map("yorktown_country_map.png","1781년 버지니아 전역 세력도","내륙 견제·남하·체서피크 봉쇄가 요크타운에서 합류",[
 (245,290,"워싱턴·로샹보\n남하축",BLUE),(230,665,"윌리엄스버그\n라파예트",BLUE),(640,735,"요크타운\n콘월리스",RED),(900,1110,"체서피크만\n드 그라스 함대",BLUE),(760,475,"요크강",DARK)], [([(170,210),(300,520),(560,700)],"#4da3ff"), ([(1010,1180),(820,920),(680,760)],"#4da3ff")],[("#4da3ff","미·프 연합 기동"),("#ff5a5a","영국 거점")])
annotate_map("yorktown_strategy_map.png","요크타운 전략지형도","요크강·글로스터·외곽보루·참호·해상 봉쇄",[
 (560,350,"글로스터 포인트\n영국 교두보",RED),(560,545,"요크타운\n영국 방어선",RED),(350,865,"제9·10 보루\n연합군 돌파",GOLD),(245,1140,"윌리엄스버그 길\n연합군 접근",BLUE),(875,230,"요크강 →\n체서피크만",DARK)], [([(180,1220),(260,930),(420,720)],"#4da3ff"), ([(1020,180),(880,300),(720,480)],"#4da3ff")],[("#4da3ff","연합군 접근·해상 차단"),("#ff5a5a","영국 방어·퇴로")])
annotate_sequence("yorktown_sequence.png","요크타운 전역 4단계","정보 → 견제 → 육해군 합류 → 항복",[(550,170,"1 정보\n제임스가 영국 이동을 보고"),(550,490,"2 견제\n라파예트가 내륙 이탈을 제한"),(550,820,"3 봉쇄\n주력 남하·프랑스 함대 차단"),(550,1160,"4 포위\n보루 점령·참호 완성")])

annotate_people("caizhou_commanders.png","설야입채주 주요 인물","항졸의 지식을 보호하고 9천의 행군으로 번역하다",[
 (310,390,"이소\n당군 총지휘",BLUE),(175,700,"이우\n항장·안내자",BLUE),(480,250,"오수림·정사량\n항장 정보망",BLUE),(850,420,"오원제\n회서 지휘",RED),(910,720,"동중질\n외곽 정예",RED)])
annotate_people("caizhou_soldiers_weapons_life.png","채주 병사·무기·생활","항졸 심문·정찰·야간신호·눈보라 행군·군량",[
 (250,300,"당군 보병\n창·쇠뇌",BLUE),(820,300,"정찰·현지 안내\n길·숙직 보고",GOLD),(250,680,"기마 전령\n기밀 명령",BLUE),(820,680,"야간 신호\n봉화·횃불",DARK),(270,1080,"눈보라 행군\n보온·대열",BLUE),(770,1080,"군량·말먹이\n전진기지",DARK)])
annotate_structure("caizhou_command_structure.png","채주 지휘·정보 편제","헌종·배도 승인 → 이소 결심 → 이우 정보·9천 행군",[
 (550,180,"헌종·배도\n전략 승인",BLUE),(550,455,"이소\n현장 총지휘",BLUE),(250,720,"이우\n길·허실·안내",GOLD),(800,720,"정사량·오수림\n항졸 정보망",GOLD),(350,1030,"9천 기습군\n선봉·중군·후군",BLUE),(820,1030,"오원제\n채주 본거지",RED)], [((550,220),(550,410),"#4da3ff"),((280,690),(500,490),"#ffd34d"),((770,690),(600,490),"#ffd34d"),((550,500),(380,990),"#4da3ff")])
annotate_map("caizhou_country_map.png","817년 당·회서 세력도","당 조정의 포위 압력과 회서 본거지·외곽 전선",[
 (260,300,"당 조정군\n문성책",BLUE),(760,720,"회서 세력\n채주",RED),(630,960,"회수 수계",DARK),(350,820,"회곡 전선\n회서 정예",RED)], [([(260,340),(380,560),(650,700)],"#4da3ff")],[("#4da3ff","당 조정 통제·진격"),("#ff5a5a","회서 영향권")])
annotate_map("caizhou_strategy_map.png","설야입채주 전략지형도","문성책 → 장시촌 → 아압지 → 채주, 눈보라 70리",[
 (250,1190,"문성책\n9천 출발",BLUE),(350,880,"장시촌\n봉화·교통 차단",BLUE),(480,640,"아압지\n거위·오리 소음",GOLD),(630,250,"채주\n상대적 공허",RED),(900,730,"회곡\n회서 정예 집중",RED)], [([(250,1150),(340,900),(470,660),(600,300)],"#4da3ff"), ([(850,680),(940,520)],"#ff5a5a")],[("#4da3ff","당군 비밀 행군"),("#ff5a5a","회서 정예 외곽 배치")])
annotate_sequence("caizhou_sequence.png","설야입채주 4단계","항졸 심문 → 이우 보호·검증 → 눈보라 70리 → 채주 진입",[(550,175,"1 직접 심문\n험이·원근·허실을 분리"),(550,500,"2 정보 결심\n회곡 정예·채주 공허 대조"),(550,820,"3 9천 행군\n목적지 제한 공개·대열 유지"),(550,1170,"4 성벽 진입\n새벽 지휘권 전환")])

# 세력도는 전술 지형도와 달리 영향권을 면으로 읽게 한다.
for filename, zones in {
    "yorktown_country_map.png": [([(30,150),(520,150),(600,1320),(30,1320)],(35,105,220,48)), ([(520,350),(1090,350),(1090,900),(580,900)],(220,55,55,48))],
    "caizhou_country_map.png": [([(20,120),(650,120),(520,900),(20,1250)],(35,105,220,52)), ([(430,300),(1100,250),(1100,1320),(370,1150)],(220,55,55,52))],
}.items():
    im=Image.open(ROOT/filename).convert("RGBA")
    overlay=Image.new("RGBA", im.size, (0,0,0,0))
    d=ImageDraw.Draw(overlay,"RGBA")
    for points,color in zones:
        d.polygon(points,fill=color)
    im=Image.alpha_composite(im, overlay)
    im.convert("RGB").save(ROOT/filename,quality=95)

# 버지니아 세력도에는 전술 지도와 다른 ‘전역 관계’ 삽입도를 둔다.
# 개별 보루·참호가 아니라 북부 주력의 남하와 해상 봉쇄의 결합을 읽게 한다.
im=Image.open(ROOT/"yorktown_country_map.png").convert("RGBA")
overlay=Image.new("RGBA", im.size, (0,0,0,0))
d=ImageDraw.Draw(overlay,"RGBA")
d.rounded_rectangle((710,800,1090,1245),24,fill=(6,24,52,232),outline=(255,216,107,255),width=5)
d.text((900,840),"전역 관계 축소도",font=font(25,True),fill="#ffd86b",anchor="mm")
d.text((755,910),"뉴욕 주력",font=font(22,True),fill="white",anchor="lm")
d.text((755,1030),"버지니아 육군",font=font(22,True),fill="white",anchor="lm")
d.text((755,1150),"체서피크 함대",font=font(22,True),fill="white",anchor="lm")
arrow(d,[(875,935),(875,995)],"#4da3ff",7)
arrow(d,[(940,1130),(940,1065)],"#49d4ff",7)
d.text((900,1210),"요크타운에서 합류·봉쇄",font=font(20,True),fill="#ffe89a",anchor="mm")
im=Image.alpha_composite(im,overlay)
im.convert("RGB").save(ROOT/"yorktown_country_map.png",quality=95)

# 영향권 면이 라벨과 범례를 덮지 않도록 마지막에 정보 레이어를 다시 올린다.
annotate_map("yorktown_country_map.png","1781년 버지니아 전역 세력도","내륙 견제·남하·체서피크 봉쇄가 요크타운에서 합류",[
 (245,290,"워싱턴·로샹보\n남하축",BLUE),(230,665,"윌리엄스버그\n라파예트",BLUE),(640,735,"요크타운\n콘월리스",RED),(900,1110,"체서피크만\n드 그라스 함대",BLUE),(760,475,"요크강",DARK)], [([(170,210),(300,520),(560,700)],"#4da3ff"), ([(1010,1180),(820,920),(680,760)],"#4da3ff")],[("#4da3ff","미·프 연합 기동"),("#ff5a5a","영국 거점")])
annotate_map("caizhou_country_map.png","817년 당·회서 세력도","당 조정의 포위 압력과 회서 본거지·외곽 전선",[
 (260,300,"당 조정군\n문성책",BLUE),(760,720,"회서 세력\n채주",RED),(630,960,"회수 수계",DARK),(350,820,"회곡 전선\n회서 정예",RED)], [([(260,340),(380,560),(650,700)],"#4da3ff")],[("#4da3ff","당 조정 통제·진격"),("#ff5a5a","회서 영향권")])
