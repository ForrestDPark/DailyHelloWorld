#!/usr/bin/env python3
"""구지편 `是故其兵不修而戒…` 페이지의 10종 시각 자료를 만든다."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated" / "jiudi14"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
W, H = 1600, 1000


def f(size, bold=False):
    return ImageFont.truetype(FONT, size, index=1 if bold else 0)


def fit(draw, text, width, size=34, bold=True):
    while size > 15 and draw.textbbox((0, 0), text, font=f(size, bold))[2] > width:
        size -= 1
    return f(size, bold)


def header(draw, title, subtitle=""):
    draw.rectangle((0, 0, W, 118), fill="#202c35")
    draw.text((W // 2, 46), title, font=fit(draw, title, W - 120, 42),
              fill="#fff3d7", anchor="mm")
    if subtitle:
        draw.text((W // 2, 89), subtitle, font=fit(draw, subtitle, W - 150, 21, False),
                  fill="#cbd7df", anchor="mm")


def save(im, name):
    im.save(OUT / name, quality=96)


def commanders(source, output, title, blue, red):
    im = Image.open(OUT / source).convert("RGB").resize((W, H))
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle((0, 0, W, 118), fill=(25, 35, 43, 225))
    d.rectangle((0, 838, W // 2, H), fill=(7, 66, 111, 220))
    d.rectangle((W // 2, 838, W, H), fill=(117, 34, 31, 220))
    d.text((W // 2, 53), title, font=fit(d, title, W - 100, 42),
           fill="#fff3d7", anchor="mm")
    d.multiline_text((W // 4, 910), blue, font=fit(d, blue.split("\n")[0], 690, 29),
                     fill="#d8efff", anchor="mm", align="center", spacing=15)
    d.multiline_text((W * 3 // 4, 910), red, font=fit(d, red.split("\n")[0], 690, 29),
                     fill="#ffe0da", anchor="mm", align="center", spacing=15)
    save(im, output)


def box(d, xy, title, body, color, fill):
    d.rounded_rectangle(xy, 18, fill=fill, outline=color, width=4)
    cx = (xy[0] + xy[2]) // 2
    d.text((cx, xy[1] + 36), title, font=fit(d, title, xy[2] - xy[0] - 24, 25),
           fill=color, anchor="mm")
    d.multiline_text((cx, xy[1] + 93), body, font=f(18),
                     fill="#31373b", anchor="mm", align="center", spacing=5)


def arrow(d, a, b, color, width=6):
    d.line((*a, *b), fill=color, width=width)
    d.polygon([(b[0] - 11, b[1] - 18), (b[0] + 11, b[1] - 18), b], fill=color)


def org(output, heading, left_root, left_nodes, right_root, right_nodes, insight):
    im = Image.new("RGB", (W, H), "#f2ead8")
    d = ImageDraw.Draw(im)
    header(d, heading, "실선은 지휘·명령, 세로 배열은 작전 기능과 예하 관계")
    d.line((800, 138, 800, 965), fill="#b7aa90", width=4)
    box(d, (185, 165, 615, 300), *left_root, "#1268aa", "#bcdcf0")
    box(d, (985, 165, 1415, 300), *right_root, "#b52d29", "#efcfc4")
    xs = [(35, 370, 275, 535), (290, 370, 530, 535), (545, 370, 785, 535)]
    ys = [(815, 370, 1055, 535), (1070, 370, 1310, 535), (1325, 370, 1565, 535)]
    for xy, item in zip(xs, left_nodes):
        box(d, xy, *item, "#1268aa", "#deedf5")
        arrow(d, (400, 300), ((xy[0] + xy[2]) // 2, 370), "#47768e")
    for xy, item in zip(ys, right_nodes):
        box(d, xy, *item, "#b52d29", "#f3dfd7")
        arrow(d, (1200, 300), ((xy[0] + xy[2]) // 2, 370), "#8b5044")
    d.rounded_rectangle((160, 715, 1440, 920), 20, fill="#fff8e9", outline="#806b43", width=4)
    d.text((800, 763), "이 구절과 만나는 편제 차이", font=f(27, True),
           fill="#5d4b25", anchor="mm")
    d.multiline_text((800, 835), insight, font=f(22), fill="#413b32",
                     anchor="mm", align="center", spacing=10)
    save(im, output)


def map_canvas(title, subtitle):
    im = Image.new("RGB", (W, H), "#e8dfc8")
    d = ImageDraw.Draw(im)
    header(d, title, subtitle)
    return im, d


def node(d, x, y, text, color, w=250):
    d.rounded_rectangle((x-w//2, y-34, x+w//2, y+34), 13,
                        fill="#fff7e7", outline=color, width=4)
    d.text((x, y), text, font=fit(d, text, w-20, 21), fill=color, anchor="mm")


def alesia_country():
    im, d = map_canvas("알레시아 공방전 — 기원전 52년 갈리아 세력도",
                       "로마 속주·카이사르의 진격축·갈리아 봉기권을 한눈에 보기")
    d.polygon([(180,180),(590,145),(940,230),(1260,180),(1450,410),(1320,760),
               (1000,860),(650,815),(270,650),(110,390)], fill="#d5c5a2", outline="#776443", width=5)
    d.ellipse((420,230,1260,790), fill="#d5857c80", outline="#a93631", width=5)
    d.polygon([(1040,600),(1510,545),(1510,890),(1110,870)], fill="#9fc9df", outline="#1268aa", width=4)
    for x, y, t, c in [(1290,735,"나르보넨시스 속주","#1268aa"),
                       (1110,690,"아르베르니","#a93631"),(790,410,"알레시아(Alesia)","#6c4a20"),
                       (930,275,"센·마른 방면 구원군 집결","#a93631"),(500,650,"비브락테(Bibracte)","#6c4a20")]:
        node(d,x,y,t,c,300)
    arrow(d,(1280,690),(835,440),"#1268aa",8)
    arrow(d,(970,300),(825,390),"#a93631",8)
    d.text((85,945),"붉은 번짐: 베르킨게토릭스의 반로마 연합 영향권  |  파랑: 로마 속주와 카이사르의 병참 기반",
           font=f(22,True),fill="#463a2d",anchor="lm")
    save(im,"alesia_country_map.png")


def alesia_strategy():
    im, d = map_canvas("알레시아 전략지형도 — 포위군을 다시 둘러싼 두 번째 벽",
                       "안쪽 알레시아 수비군과 바깥 구원군 사이에서 로마군이 지킨 이중 전선")
    d.ellipse((560,275,1040,650),fill="#b9a277",outline="#6a4b26",width=5)
    d.text((800,430),"알레시아 고지\n베르킨게토릭스",font=f(28,True),fill="#7c2925",anchor="mm",align="center")
    d.ellipse((430,180,1170,740),outline="#1268aa",width=18)
    d.ellipse((255,90,1345,850),outline="#2d617f",width=18)
    d.text((800,715),"내향 포위선 약 15km",font=f(24,True),fill="#1268aa",anchor="mm")
    d.text((800,875),"외향 방어선 약 21km",font=f(24,True),fill="#2d617f",anchor="mm")
    for a,b in [((800,355),(800,205)),((630,440),(435,440)),((970,450),(1170,450))]:
        arrow(d,a,b,"#a93631",8)
    for a,b in [((800,95),(800,255)),((260,450),(430,450)),((1340,450),(1170,450))]:
        arrow(d,a,b,"#a93631",8)
    node(d,310,180,"레아산(Mont Réa) 취약 구간","#6c4a20",330)
    node(d,1280,230,"갈리아 구원군","#a93631",230)
    save(im,"alesia_strategy_map.png")


def sequence(output, title, panels):
    im = Image.new("RGB",(W,H),"#eee4cf"); d=ImageDraw.Draw(im)
    header(d,title,"명령과 선택이 다음 장면을 낳는 순서")
    colors=["#d9eaf4","#eee0bb","#f0d4cc","#dbe7d1"]
    for i,(h,b) in enumerate(panels):
        x1=35+i*390; x2=x1+360
        d.rounded_rectangle((x1,180,x2,850),22,fill=colors[i],outline="#635944",width=4)
        d.ellipse((x1+128,210,x1+232,314),fill=("#1268aa" if i in (0,2) else "#a93631"))
        d.text((x1+180,262),str(i+1),font=f(41,True),fill="white",anchor="mm")
        d.text((x1+180,370),h,font=fit(d,h,320,27),fill="#332d25",anchor="mm")
        d.multiline_text((x1+180,540),b,font=f(21),fill="#443d33",anchor="mm",align="center",spacing=12)
        if i<3: arrow(d,(x2+5,515),(x2+30,515),"#7d6a42",5)
    save(im,output)


def fei_country():
    im,d=map_canvas("비수대전 — 383년 전진과 동진의 대치",
                    "북방 통일 뒤 남하한 전진과 장강 하류를 지키는 동진")
    d.polygon([(80,155),(1510,155),(1450,555),(970,610),(640,535),(140,590)],fill="#dfaaa0",outline="#a93631",width=5)
    d.polygon([(110,650),(610,590),(980,655),(1490,585),(1510,910),(90,910)],fill="#a9ccdf",outline="#1268aa",width=5)
    d.line((70,620,1530,600),fill="#2c8cb8",width=14)
    d.text((1320,636),"장강(長江)",font=f(24,True),fill="#075b82",anchor="mm")
    for x,y,t,c in [(440,300,"장안(長安)·전진 수도","#a93631"),(760,400,"항성(項城)·대군 집결","#a93631"),
                    (1040,550,"수양(壽陽)·비수","#6c4a20"),(1220,790,"건강(建康)·동진 수도","#1268aa"),
                    (1320,690,"광릉(廣陵)·북부병 기반","#1268aa")]:
        node(d,x,y,t,c,300)
    arrow(d,(520,340),(990,530),"#a93631",9)
    arrow(d,(1260,735),(1060,585),"#1268aa",9)
    save(im,"feiriver_country_map.png")


def fei_strategy():
    im,d=map_canvas("비수대전 전략지형도 — ‘조금 물러나라’가 만든 전군의 후퇴",
                    "동진군의 도하 요청, 전진군의 오판, 부융의 전사와 붕괴")
    d.rectangle((0,520,W,H),fill="#b9d7e5")
    d.polygon([(0,465),(W,430),(W,620),(0,655)],fill="#3995bd")
    d.text((800,545),"비수(淝水)",font=f(34,True),fill="white",anchor="mm")
    for i in range(11): d.ellipse((130+i*105,260+(i%2)*38,185+i*105,315+(i%2)*38),fill="#a93631")
    for i in range(7): d.ellipse((360+i*120,760+(i%2)*28,415+i*120,815+(i%2)*28),fill="#1268aa")
    node(d,800,185,"전진군: 강가에서 잠시 후퇴","#a93631",400)
    node(d,800,890,"동진 북부병: 도하 뒤 즉시 돌격","#1268aa",420)
    arrow(d,(800,325),(800,405),"#a93631",8)
    arrow(d,(800,750),(800,625),"#1268aa",8)
    node(d,1290,365,"주서(朱序): ‘秦兵敗矣’ 외침","#6c4a20",390)
    node(d,310,390,"부융(苻融) 낙마·전사","#6c4a20",320)
    save(im,"feiriver_strategy_map.png")


if __name__=="__main__":
    commanders("alesia_commanders_source.png","alesia_commanders.png","알레시아 공방전 — 주요 인물",
               "로마군(승)\n카이사르 · 라비에누스 · 트레보니우스",
               "갈리아 연합(패)\n베르킨게토릭스 · 코미우스 · 베르카시벨라우누스")
    org("alesia_command_structure.png","알레시아 — 장군 조직도와 공방 편제",
        ("율리우스 카이사르","총사령관\n이중 포위선·기동예비 통제"),
        [("라비에누스","북서 취약부 방어\n기병 반격"),("트레보니우스","군단 진지 지휘\n내·외선 방어"),("게르만 기병","외선 기동예비\n구원군 측후방 타격")],
        ("베르킨게토릭스","알레시아 성내 총지휘\n식량 통제·동시 돌파 시도"),
        [("코미우스","외부 구원군 공동지휘\n정면 압박"),("베르카시벨라우누스","6만 정예\n레아산 야습"),("성내 수비군","안쪽 포위선 돌파\n외군과 호응")],
        "로마군은 각 군단이 자기 구간을 알아 별도 명령 없이도 버티고, 카이사르는 붉은 망토로 모습을 드러내 예비를 결집했다.\n갈리아군은 안팎의 수가 더 많았지만 공격 시각과 지휘가 갈라졌다.")
    alesia_country(); alesia_strategy()
    sequence("alesia_sequence_map.png","알레시아 공방전 — 네 번의 선택",
             [("기병전 패배와 입성","베르킨게토릭스가\n알레시아로 물러남"),("두 겹의 토목선","카이사르가 성내와\n외부를 동시에 막음"),("레아산 총공세","안팎 갈리아군이\n취약부를 함께 압박"),("예비의 측후방 반격","라비에누스·게르만 기병이\n구원군을 붕괴시킴")])
    commanders("feiriver_commanders_source.png","feiriver_commanders.png","비수대전 — 주요 인물",
               "동진군(승)\n사현 · 사석 · 사염",
               "전진군(패)\n부견 · 부융 · 모용수")
    org("feiriver_command_structure.png","비수대전 — 장군 조직도와 작전 편제",
        ("사현(謝玄)","선봉도독·북부병 핵심\n낙간 기습·도하 결전"),
        [("사석(謝石)","정토대도독\n전군 명목 지휘"),("유뢰지(劉牢之)","정예 5천\n낙간 선제기습"),("사염·환이","보병·지원군\n도하 후 추격")],
        ("부견(苻堅)","전진 황제·총지휘\n대군 남정 결정"),
        [("부융(苻融)","전선 총지휘\n후퇴 중 낙마·전사"),("양성·양평공","낙간 전초군\n선제기습에 붕괴"),("모용수·요장 등","다민족 예하군\n충성·목표 불일치")],
        "동진 북부병은 소수라도 동일한 훈련과 지휘망으로 움직였다.\n전진군은 병력은 컸지만 새로 복속한 여러 집단과 장수의 이해가 갈려 ‘물러나라’는 명령이 패주로 번졌다.")
    fei_country(); fei_strategy()
    sequence("feiriver_sequence_map.png","비수대전 — 의심이 패주로 바뀐 네 장면",
             [("낙간 선제기습","유뢰지의 5천 정예가\n전진 전초군을 격파"),("팔공산의 동요","부견이 멀리 본 동진 진영을\n초목까지 병사로 의심"),("도하 요청 수락","전진군이 승부를 위해\n강가에서 후퇴"),("거짓 패전과 붕괴","주서의 외침·부융 전사로\n후퇴가 전군 패주로 변함")])
