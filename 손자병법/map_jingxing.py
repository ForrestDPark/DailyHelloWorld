#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정형 전투(정형지전·井陘之戰, BCE 204) 전략지형도"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(7)

fig, ax, renderer = new_canvas()

MX0, MX1 = 0, 24
extent = (MX0, MX1, MAP_Y0, MAP_Y1)

# ── 지형 (문헌 기반: 서쪽 태항산맥/정형관 협로 → 동쪽 평지, 면만수) ──
lons = np.linspace(0, 1, 80)
lats = np.linspace(0, 1, 60)
LON, LAT = np.meshgrid(lons, lats)
elev = 120 - LON * 100  # 서쪽(태항산) 높고 동쪽(평지) 낮음
elev += 260 * np.exp(-(((LON - 0.12) ** 2) / 0.02 + ((LAT - 0.5) ** 2) / 0.35))  # 태항산 주능선
elev += 90 * np.exp(-(((LON - 0.25) ** 2) / 0.008 + ((LAT - 0.5) ** 2) / 0.5))   # 정형관 협로 어깨
elev -= 60 * np.exp(-(((LON - 0.72) ** 2) / 0.10 + ((LAT - 0.82) ** 2) / 0.10))  # 조군 배후 저지대(북측)
terrain_colors = [
    (0.0, '#c9b892'),
    (0.25, '#b8a878'),
    (0.55, '#8a9a5b'),
    (0.8, '#5f7a4a'),
    (1.0, '#3f5c38'),
]
draw_terrain(ax, elev, extent, terrain_colors)

# 정형관 협로 라벨
T(ax, '정형관 (애지·隘地)', 3.2, MAP_Y0 + 8.0, sz=38, c='#2a2010', bg='#e8dcc0')
marker_point(ax, 3.2, MAP_Y0 + 7.3, ms=30)

# ── 면만수(綿蔓水) 강 ──
draw_river(ax, base_x=9.2, y0=MAP_Y0, y1=MAP_Y1, amplitude=0.5, freq1=1.1,
           amp2=0.25, freq2=2.3, width=0.35, flow_up=False)
T(ax, '면만수', 9.9, MAP_Y0 + 9.5, sz=34, c='#0a3a5c', bg='#eef7fb')

# ── 한신 배수진 (강을 등지고 방어, 1만) ──
# 조군은 강 동쪽(x>river)에서 공격해오므로, 한군은 반드시 강의 동쪽 강변에
# 서서 "등 뒤가 강"이 되도록 배치해야 진짜 배수진이다. (강을 사이에 두고
# 마주보면 배수진이 아니라 서로를 가로막는 "전수진"이 되어버린다.)
n = 60
depth = np.random.uniform(0, 1.0, n)
spread = np.random.uniform(-1, 1, n)
hx = 9.6 + depth * 0.9
hy = MAP_Y0 + 5.2 + spread * 3.3
troops(ax, hx, hy, '#ee3333', ms=180)
T(ax, '한신 배수진 (1만)', 10.4, MAP_Y0 + 1.0, sz=36, c='#7a0000', bg='#fbeaea')

# ── 한군 본대: 정형관에서 나와 강을 건너 동쪽으로 진격 (깃발·북 과시, 미끼) ──
n2 = 40
depth2 = np.random.uniform(0, 1.0, n2)
spread2 = np.random.uniform(-0.5, 0.5, n2) * (1 - depth2 * 0.4)
hmx = 4.5 - depth2 * 1.2
hmy = MAP_Y0 + 5.5 + spread2 * 3.0
troops(ax, hmx, hmy, '#ee3333', ms=150, alpha=0.7)
T(ax, '한군 본대 (기만행군)', 3.6, MAP_Y0 + 2.2, sz=34, c='#7a0000', bg='#fbeaea')
arr(ax, 3.6, MAP_Y0 + 5.5, 9.9, MAP_Y0 + 5.4, '#ee2222', rad=0.05)

# ── 한신 경기병 2천 (샛길로 조군 배후 진영으로 잠입) ──
cav_x = [4.8, 7.5, 11.5, 15.5, 18.7]
cav_y = [MAP_Y0 + 8.6, MAP_Y0 + 9.3, MAP_Y0 + 9.6, MAP_Y0 + 9.3, MAP_Y0 + 9.0]
for cx, cy in zip(cav_x, cav_y):
    pe_em(ax, '🐎', cx, cy, zoom=0.20, z=15)
for i in range(len(cav_x) - 1):
    arr(ax, cav_x[i], cav_y[i], cav_x[i + 1], cav_y[i + 1], '#ff8800',
        rad=0.08, hw=3.0, tw=1.4, dash=True, z=14)
T(ax, '기병 2000 (샛길 우회)', 12.5, MAP_Y0 + 7.6, sz=32, c='#8a4400', bg='#fff3e0')

# ── 조군 본대 (20만, 정형관 방향으로 넓게 포진) ──
n3 = 130
depth3 = np.random.uniform(0, 1.0, n3)
spread3 = np.random.uniform(-1, 1, n3) * (0.6 + depth3 * 0.4)
zx = 13.5 + depth3 * 6.5
zy = MAP_Y0 + 5.5 + spread3 * 3.6
troops(ax, zx, zy, '#2255dd', ms=140)
T(ax, '조나라 진여군 (20만)', 19.0, MAP_Y0 + 1.4, sz=38, c='#0a1a6b', bg='#e8ecfb')

# 조군 본영(배후 진영, 기습 대상)
zcamp_x = 19.2
zcamp_y = MAP_Y0 + 9.6
marker_point(ax, zcamp_x, zcamp_y, ms=34, color='#ff2200')
T(ax, '조군 본영', zcamp_x, zcamp_y + 0.7, sz=32, c='#7a0000', bg='#fff0e8')
pe_em(ax, '🔥', zcamp_x + 0.6, zcamp_y - 0.3, zoom=0.15, z=16)

# 조군 돌격 (배수진 향해 전군 투입)
arr(ax, 14.5, MAP_Y0 + 5.5, 10.6, MAP_Y0 + 5.4, '#2255dd', rad=-0.08, hw=4.5, tw=2.6)

# 조군 궤멸/패주 (본영 함락 소식에 사방으로 붕괴)
arr(ax, 15.0, MAP_Y0 + 4.0, 20.5, MAP_Y0 + 2.0, '#2255dd', rad=0.1, dash=True, hw=3.0, tw=1.6)
arr(ax, 16.0, MAP_Y0 + 6.5, 21.5, MAP_Y0 + 8.0, '#2255dd', rad=-0.1, dash=True, hw=3.0, tw=1.6)

# ── 지휘관 표식 ──
pe_em(ax, '⚔️', 10.8, MAP_Y0 + 6.6, zoom=0.24, z=17)
pe_em(ax, '🛡️', 19.2, MAP_Y0 + 5.8, zoom=0.24, z=17)

draw_title(ax, ['정형 전투 전략도  ', '井陘之戰', '  (BCE 204)'])

legend_items = [
    ('arr', '#ee2222', '한군 진격'),
    ('arr', '#2255dd', '조군 돌격'),
    ('dash', '#2255dd', '조군 패주'),
    ('dash', '#ff8800', '기병 잠입로'),
    ('emoji', '🐎', '경기병(기병)'),
    ('emoji', '🔥', '진영 습격'),
    ('dot_r', '#ee3333', '한군 보병'),
    ('dot_b', '#2255dd', '조군 보병'),
    ('dot', '#ffaa00', '요충지·본영'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items, title='범례 · 애지(隘地)/사지(死地)')

패군_rows = [
    ('전력+배치+보급', '20만 대군, 진여 단독 지휘. 방어전이라 보급은 넉넉했으나 병력을 과신.'),
    ('지피(知彼)', '한군을 얕보고 이좌거의 매복 건의를 원칙론으로 거부. 염결가욕(廉潔可辱).'),
    ('지기(知己)', '수적 우위만 믿고 본영 방어는 소홀히 함.'),
    ('지지(知地)', '애지(정형관)를 선점 매복해야 했으나 개활지 정면대결을 택함.'),
    ('결과', '본영 함락 소식에 전군 붕괴, 진여는 지수에서 전사.'),
]
draw_analysis_box(ax, renderer, LX, '패군', '진여 (성안군)', 패군_rows, '#1a3a7a')

승군_rows = [
    ('전력+배치+보급', '3만, 다수가 신병. 한신 단독 전권으로 기만작전을 신속 실행.'),
    ('지피(知彼)', '진여가 정공법을 택하리라 확신하고 배수진으로 유인.'),
    ('지기(知己)', '신병이 도주하지 않도록 스스로 사지(死地)를 만들어 사기를 끌어냄.'),
    ('지지(知地)', '애지 통과 후 샛길로 배후 기습, 강으로 사지 조성 — 기정(奇正)의 결합.'),
    ('결과', '본영 탈취로 조군 붕괴. 열세를 뒤집은 완승.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '한신', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jingxing_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
