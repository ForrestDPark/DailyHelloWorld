from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated" / "jiudi_yonggan8"
OUT.mkdir(parents=True, exist_ok=True)
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

def f(size, bold=False):
    return ImageFont.truetype(FONT, size=size, index=1 if bold else 0)

def banner(path, title, subtitle, labels=()):
    im = Image.open(path).convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle((24, 20, im.width-24, 146), 24, fill=(10,18,30,225), outline=(230,190,90,255), width=3)
    d.text((im.width//2, 48), title, font=f(46, True), fill="white", anchor="ma")
    d.text((im.width//2, 105), subtitle, font=f(25), fill=(230,232,238), anchor="ma")
    if labels:
        y = im.height - 150
        d.rounded_rectangle((28,y,im.width-28,im.height-24),20,fill=(5,10,18,218))
        col = (im.width-80)//len(labels)
        for i,(head,body,color) in enumerate(labels):
            x=50+i*col
            d.text((x,y+24),head,font=f(27,True),fill=color)
            d.multiline_text((x,y+62),body,font=f(20),fill="white",spacing=7)
    return im

def map_overlay(path,title,subtitle,points,arrows):
    im=banner(path,title,subtitle)
    d=ImageDraw.Draw(im,"RGBA")
    for x,y,label,color in points:
        d.ellipse((x-13,y-13,x+13,y+13),fill=color,outline="white",width=3)
        box=d.textbbox((0,0),label,font=f(25,True)); w=box[2]-box[0]
        d.rounded_rectangle((x+16,y-22,x+w+36,y+20),10,fill=(8,12,18,220))
        d.text((x+25,y-17),label,font=f(25,True),fill="white")
    for x1,y1,x2,y2,color,label in arrows:
        d.line((x1,y1,x2,y2),fill=color,width=12)
        d.polygon([(x2,y2),(x2-25,y2-12),(x2-20,y2+18)],fill=color)
        d.text(((x1+x2)//2,(y1+y2)//2-36),label,font=f(23,True),fill=color,stroke_width=4,stroke_fill="black")
    return im

def save(src,name,title,subtitle,labels=()):
    banner(src,title,subtitle,labels).save(OUT/name,optimize=True)

def main():
    g=Path("/Users/forrestdpark/.codex/generated_images/01a1c698-5dac-7773-9bb6-ad043591c383")
    save(g/"exec-6d4eb125-1b99-41a6-9bde-303d99a028f5.png","fortitude_commanders.png","포티튜드 작전 주요 인물","승군 파랑 · 패군 빨강",[("연합군","후안 푸욜 · 토머스 해리스\n존 비번 · 드와이트 아이젠하워","#68a9ff"),("독일군","게르트 폰 룬트슈테트\n아프베어·국방군 지휘부","#ff7474")])
    save(g/"exec-c02b96a1-b9cf-412d-8697-a399cf6c4e86.png","fortitude_soldiers_weapons_life.png","포티튜드의 병사·장비·생활","무선·가짜 장비·정찰·암호·보급",[("보인 전력","무선 교신 · 모형 전차\n가짜 상륙정 · 패튼의 FUSAG","#68a9ff"),("실제 전력","노르망디 상륙군과 함대\n관측·검증은 제한된 채 유지","#f4d06f")])
    save(g/"exec-abed0e6d-f137-458a-ab52-fe9eedff905d.png","fortitude_command_structure.png","포티튜드 지휘·정보 구조","LCS·MI5 → 반간망 → 아프베어 → 독일 지휘부",[("연합 지휘","런던 통제부(LCS)\nMI5 B1A · 가르보·브루투스","#68a9ff"),("독일 수신","아프베어 무선망\nOB West · 최고사령부","#ff7474")])
    map_overlay(g/"exec-f7f4dae0-d70f-4c3a-90f2-5633fd7d24b7.png","포티튜드 시대 세력도","영국 남부에서 프랑스 북부로 이어진 기만 공간",[(480,300,"켄트·FUSAG",(60,130,255,255)),(1000,530,"파드칼레",(230,70,70,255)),(560,1030,"노르망디",(60,130,255,255))],[(500,360,920,520,"#ffcf4d","가상 주공"),(560,930,570,1060,"#68a9ff","실제 상륙")]).save(OUT/"fortitude_country_map.png",optimize=True)
    map_overlay(g/"exec-42c0d7cd-2ca4-4115-94ab-ab8aa33d132a.png","포티튜드 전략지형도","가장 짧은 도버 해협을 보이되 노르망디로 실제 전력을 집중",[(340,250,"도버",(60,130,255,255)),(1140,300,"칼레",(230,70,70,255)),(740,760,"노르망디",(60,130,255,255))],[(370,290,1080,330,"#ffcf4d","거짓 상륙축"),(520,540,740,735,"#68a9ff","실제 오버로드")]).save(OUT/"fortitude_strategy_map.png",optimize=True)
    save(g/"exec-7ead10c1-0514-444e-ad69-129414acec3b.png","fortitude_sequence.png","포티튜드 4단계 흐름","① 가상군 → ② 반간 송신 → ③ 파드칼레 고착 → ④ 노르망디 교두보")
    save(g/"exec-7dc558e0-eb17-4634-b0d7-582560ea2929.png","guandu_commanders.png","관도대전 주요 인물","조조군 파랑 · 원소군 빨강",[("조조군","조조 · 순유 · 허유\n조홍 · 악진","#68a9ff"),("원소군","원소 · 곽도 · 순우경\n장합 · 고람","#ff7474")])
    save(g/"exec-1b36ff2f-03d0-4916-8a56-0a7acd3208f3.png","guandu_soldiers_weapons_life.png","관도대전 병사·무기·생활","보병·쇠뇌·기병·군량차·취사·신호",[("전투 편제","보병·쇠뇌병·기병\n북·봉화·전령","#68a9ff"),("보급의 핵심","군량차와 창고\n오소 소실이 전군을 흔듦","#f4d06f")])
    save(g/"exec-be7afe2f-e68b-4f09-9233-262a811809f7.png","guandu_command_structure.png","관도대전 지휘·편제","허유의 이탈로 원소군 내부 정보가 조조에게 이동",[("조조군","조조 총지휘\n조홍·순유 본영 / 악진 기습","#68a9ff"),("원소군","원소 총지휘\n순우경 오소 / 장합·고람 관도","#ff7474")])
    map_overlay(g/"exec-d1d897d8-a062-4166-9097-83e6a3625918.png","후한 말 시대 세력도","황하 북쪽 원소권과 남쪽 조조권의 충돌",[(620,620,"업·원소권",(230,70,70,255)),(650,830,"관도",(60,130,255,255)),(610,1050,"허도·조조권",(60,130,255,255))],[(640,650,650,820,"#ff7474","남진"),(625,1020,650,850,"#68a9ff","방어선")]).save(OUT/"guandu_country_map.png",optimize=True)
    map_overlay(g/"exec-551cffbb-a259-4eb2-bc78-ed7dff60ae4a.png","관도대전 전략지형도","오소 군량창과 관도 본영을 가른 야간 기습",[(610,230,"오소 군량창",(230,70,70,255)),(720,520,"황하",(60,150,220,255)),(820,760,"관도",(60,130,255,255)),(820,1040,"허도",(60,130,255,255))],[(810,780,625,260,"#68a9ff","5천 야간 기습"),(630,260,810,760,"#ff7474","원소 주력 분산")]).save(OUT/"guandu_strategy_map.png",optimize=True)
    save(g/"exec-d47dba59-0ae6-4285-9e40-f1a7907b35e7.png","guandu_sequence.png","관도대전 4단계 흐름","① 관도 교착 → ② 허유 전향 → ③ 야간 오소 기습 → ④ 군량 소실·붕괴")

if __name__ == "__main__": main()
