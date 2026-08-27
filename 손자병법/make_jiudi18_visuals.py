#!/usr/bin/env python3
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated" / "jiudi18"
W, H = 1600, 1200
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
BLUE, RED = "#2166ac", "#b43c39"
INK, PAPER = "#27231f", "#eee3c8"

def font(size, bold=False):
    return ImageFont.truetype(FONT, size, index=2 if bold else 0)

def fit_bg(path):
    im = Image.open(path).convert("RGB")
    scale = max(W / im.width, H / im.height)
    im = im.resize((int(im.width*scale), int(im.height*scale)), Image.Resampling.LANCZOS)
    x, y = (im.width-W)//2, (im.height-H)//2
    return im.crop((x,y,x+W,y+H))

def overlay(im, alpha=185):
    wash = Image.new("RGBA", im.size, (238,227,200,alpha))
    return Image.alpha_composite(im.convert("RGBA"), wash)

def title(draw, text, subtitle=""):
    draw.rounded_rectangle((34,28,W-34,150), 22, fill=(25,23,21,225))
    draw.text((70,48), text, font=font(48,True), fill="white")
    if subtitle: draw.text((72,108), subtitle, font=font(25), fill="#ead9ad")

def label(draw, xy, text, color, anchor="mm", size=30):
    f=font(size,True); box=draw.textbbox(xy,text,font=f,anchor=anchor)
    pad=12
    draw.rounded_rectangle((box[0]-pad,box[1]-8,box[2]+pad,box[3]+8),12,fill=color,outline="white",width=2)
    draw.text(xy,text,font=f,fill="white",anchor=anchor)

def arrow(draw, a, b, color, width=12):
    draw.line((a,b),fill=color,width=width)
    import math
    ang=math.atan2(b[1]-a[1],b[0]-a[0]); s=24
    p1=(b[0]-s*math.cos(ang-.6),b[1]-s*math.sin(ang-.6))
    p2=(b[0]-s*math.cos(ang+.6),b[1]-s*math.sin(ang+.6))
    draw.polygon((b,p1,p2),fill=color)

def save(im,name):
    im.convert("RGB").save(OUT/name,quality=94)

def commanders(base,name,title_text,labels):
    im=fit_bg(base).convert("RGBA"); d=ImageDraw.Draw(im,"RGBA"); title(d,title_text,"공동 위험이 경쟁 세력을 한 작전으로 묶다")
    for x,y,text,color in labels: label(d,(x,y),text,color,size=31)
    save(im,name)

def structure(base,name,title_text,left,right):
    im=overlay(fit_bg(base),205); d=ImageDraw.Draw(im,"RGBA"); title(d,title_text,"명령·역할·상호지원 구조")
    for side,x,color,rows in [("승리 연합",100,BLUE,left),("패배 진영",870,RED,right)]:
        d.rounded_rectangle((x,190,x+630,1080),28,fill=(255,250,235,230),outline=color,width=7)
        label(d,(x+315,235),side,color,size=35)
        y=320
        for head,body in rows:
            d.text((x+38,y),head,font=font(31,True),fill=color)
            d.multiline_text((x+38,y+48),body,font=font(25),fill=INK,spacing=8)
            if y<900: arrow(d,(x+315,y+150),(x+315,y+205),color,7)
            y+=205
    save(im,name)

def power_map(base,name,title_text,places,water):
    im=overlay(fit_bg(base),170); d=ImageDraw.Draw(im,"RGBA"); title(d,title_text,"세력권·출발지·공동 위협")
    d.rounded_rectangle((70,185,1530,1110),35,fill=(224,211,177,220),outline="#665a45",width=5)
    # coast/river texture
    d.polygon(water,fill=(73,143,180,210),outline="#d7f0f5",width=5)
    for x,y,text,color in places:
        d.ellipse((x-28,y-28,x+28,y+28),fill=color,outline="white",width=5)
        label(d,(x,y-60),text,color,size=27)
    d.text((105,1030),"파랑은 승리 연합 · 빨강은 패배 진영 · 물길은 이동로이자 공동 위험",font=font(28,True),fill=INK)
    save(im,name)

def strategy(base,name,title_text,places,moves,notes):
    im=overlay(fit_bg(base),190); d=ImageDraw.Draw(im,"RGBA"); title(d,title_text,"병목·유인·결정적 기동")
    d.rounded_rectangle((55,180,1545,1105),30,fill=(242,232,203,225),outline="#625a4c",width=5)
    for x,y,text,color in places:
        d.ellipse((x-22,y-22,x+22,y+22),fill=color,outline="white",width=4); label(d,(x,y-50),text,color,size=26)
    for a,b,color in moves: arrow(d,a,b,color,13)
    y=850
    for n in notes:
        d.rounded_rectangle((95,y,1505,y+65),14,fill=(255,250,237,235),outline="#9b8c6b",width=2)
        d.text((120,y+14),n,font=font(27,True),fill=INK); y+=78
    save(im,name)

def sequence(base,name,title_text,panels):
    im=overlay(fit_bg(base),215); d=ImageDraw.Draw(im,"RGBA"); title(d,title_text,"명령 → 갈등 → 결합 → 결과")
    coords=[(55,200,770,610),(830,200,1545,610),(55,655,770,1065),(830,655,1545,1065)]
    for i,(rect,(head,body,color)) in enumerate(zip(coords,panels),1):
        d.rounded_rectangle(rect,25,fill=(255,249,232,238),outline=color,width=6)
        d.ellipse((rect[0]+22,rect[1]+20,rect[0]+82,rect[1]+80),fill=color)
        d.text((rect[0]+52,rect[1]+50),str(i),font=font(30,True),fill="white",anchor="mm")
        d.text((rect[0]+105,rect[1]+25),head,font=font(33,True),fill=color)
        d.multiline_text((rect[0]+38,rect[1]+105),body,font=font(27),fill=INK,spacing=10)
    save(im,name)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    s=OUT/"salamis_commanders_base.png"; r=OUT/"redcliffs_commanders_base.png"
    commanders(s,"salamis_commanders.png","살라미스 해전 주요 인물",[(310,310,"테미스토클레스",BLUE),(315,920,"에우리비아데스",BLUE),(1280,300,"크세르크세스",RED),(1270,900,"아르테미시아",RED)])
    structure(s,"salamis_command_structure.png","살라미스 연합 지휘·편제",[("공동 지휘","에우리비아데스\n연합 함대 총지휘"),("주력·계책","테미스토클레스\n아테네 최대 함대"),("연합 전열","아이기나·메가라\n각 폴리스 삼단노선")],[("제국 지휘","크세르크세스\n해안에서 관전"),("함대 구성","페니키아·이오니아\n이집트 함대"),("취약점","언어·지휘 분산\n좁은 해협 과밀")])
    power_map(s,"salamis_country_map.png","기원전 480년 에게해 세력도",[(300,880,"펠로폰네소스",BLUE),(560,420,"살라미스",BLUE),(750,320,"아테네",BLUE),(1220,400,"페르시아 함대",RED)],[(80,250),(520,190),(930,240),(1520,220),(1500,800),(1050,950),(650,890),(250,1080),(80,900)])
    strategy(s,"salamis_strategy_map.png","살라미스 전략지형도",[(400,500,"살라미스섬",BLUE),(1020,470,"아티카 해안",RED),(620,850,"좁은 해협",BLUE),(1320,350,"팔레론",RED)], [((1320,420),(930,650),RED),((550,760),(850,620),BLUE),((680,800),(980,650),BLUE)], ["페르시아 대함대가 좁은 수역으로 들어오며 전열이 압축됨","그리스 연합은 짧은 선회 공간과 익숙한 수로에서 충각전을 수행","도주로가 막힌다는 공통 위험이 폴리스 간 논쟁을 실제 협동으로 전환"])
    sequence(s,"salamis_sequence.png","살라미스 해전 4단계",[("연합의 분열","코린토스 등은 이스트모스로\n이동하자고 주장",RED),("머물게 만든 계책","테미스토클레스가 적에게\n도주 정보를 흘려 봉쇄 유도",BLUE),("병목 속 협동","아테네·아이기나·메가라가\n역할을 나눠 해협에서 반격",BLUE),("공동 생존","페르시아 함대가 무너지고\n폴리스 연합이 보존됨",BLUE)])
    commanders(r,"redcliffs_commanders.png","적벽대전 주요 인물",[(300,300,"주유",BLUE),(290,670,"제갈량",BLUE),(420,970,"유비",BLUE),(1280,270,"조조",RED)])
    structure(r,"redcliffs_command_structure.png","손·유 연합 지휘·편제",[("손권의 결단","주유·정보에게\n수군 지휘권 부여"),("전장 지휘","주유·정보\n황개 화공대"),("연합 축","유비·관우·장비\n육상 추격·차단")],[("총지휘","조조\n북방군 통합"),("수군 전환","형주 수군과\n북방 보병 혼성"),("취약점","질병·수전 미숙\n밀집한 함선")])
    power_map(r,"redcliffs_country_map.png","208년 장강 중류 세력도",[(280,360,"유비군",BLUE),(650,720,"손권군",BLUE),(810,520,"적벽",BLUE),(1280,300,"조조군",RED)],[(40,660),(400,590),(720,610),(1000,560),(1560,650),(1520,820),(1050,760),(600,820),(200,790)])
    strategy(r,"redcliffs_strategy_map.png","적벽대전 전략지형도",[(360,430,"하구",BLUE),(760,620,"적벽",BLUE),(1110,560,"오림",RED),(1320,820,"화용도",RED)], [((1240,520),(880,590),RED),((420,470),(760,600),BLUE),((710,670),(1100,590),BLUE),((1130,640),(1330,820),RED)], ["조조군은 장강 북안 오림 부근에 밀집하고 손·유 연합은 남안에서 대치","황개의 투항 위장이 화선을 조조 함대 가까이 접근시킴","불길·바람·질병·육상 추격이 결합해 조조군의 철수를 붕괴시킴"])
    sequence(r,"redcliffs_sequence.png","적벽대전 4단계",[("공동 위험","조조가 형주를 장악하고\n장강 하류로 압박",RED),("불신 속 결합","손권은 항복론을 물리치고\n유비 세력과 연합",BLUE),("수륙 역할 분담","주유 함대의 화공과\n유비군의 육상 추격",BLUE),("위협 제거 뒤 긴장","조조는 북퇴하지만\n손·유의 이해충돌은 재개",BLUE)])

if __name__ == "__main__": main()
