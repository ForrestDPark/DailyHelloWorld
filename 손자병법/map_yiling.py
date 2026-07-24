#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""이릉대전(夷陵之戰/猇亭之戰, 222년) 전략지형도

前後不相及·衆寡不相恃·貴賤不相救 실증 사례: 유비는 장강 삼협 인근 산림지대에
수십 개의 진영을 700리(과장, 실제 수백 리)에 걸쳐 길게 늘어뜨렸다(연영).
육손은 장기 대치로 유비군의 예기를 소진시킨 뒤, 무더위 속에 산림 진영으로
옮긴 촉군을 화공으로 하나씩 연쇄적으로 태워 전후·좌우가 서로 구원할 수
없는 상태로 만들어 궤멸시켰다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(222)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 남쪽=장강(동서로 흐름), 북쪽=산림·협곡지대(촉군 연영 진지) ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 46.0
elev += 42 * np.exp(-((LAT - 0.72) ** 2) / 0.05) * (1 + 0.22 * np.sin(LON * 9.0 + 0.6))   # 북쪽 산림지대(굴곡)
elev -= 16 * np.exp(-((LAT - 0.12) ** 2) / 0.014)                                          # 남쪽 장강 저지
terrain_colors = [
    (0.0, '#6a7a48'),
    (0.30, '#83925a'),
    (0.58, '#96a066'),
    (0.82, '#6f7d48'),
    (1.0, '#465a2e'),
]
draw_terrain(ax, elev, extent, terrain_colors)

T(ax, hj('連營七百里', '연영칠백리') + '·' + hj('險形', '험형'),
  0.2, MAP_Y1 - 0.6, sz=24, c='#2a2010', bg='#ece4c0', ha='left')
T(ax, hj('猇亭·夷道', '효정·이도') + ' 산림지대', 20.5, MAP_Y1 - 0.6, sz=21, c='#1e2a12', bg='#dfe6cc')

# 장강(남쪽, 동서로 흐름)
ry = np.linspace(0, 24, 300)
rx_c = MAP_Y0 + 1.9 + 0.22 * np.sin(ry * 0.4)
rx_l, rx_r = rx_c - 0.5, rx_c + 0.5
from matplotlib.patches import Polygon as _Poly
ax.add_patch(_Poly(list(zip(ry, rx_l)) + list(zip(ry[::-1], rx_r[::-1])),
    fc='#c9a24a', ec='#9c7a2e', lw=2, zorder=5, alpha=0.9))
T(ax, hj('長江', '장강'), 3.0, MAP_Y0 + 1.0, sz=22, c='#5a3f0a', bg='#f6ecd6', ha='left')

Y_RIVER = MAP_Y0 + 1.9
Y_WU = MAP_Y0 + 4.0        # 육손 오군 본진(강 남안 방어선)
Y_CAMPS = MAP_Y1 - 5.0     # 유비 연영 진지(산림, 동서로 길게)
Y_FIRE = MAP_Y1 - 2.3      # 화공 확산 지점

# ── 유비 촉군: 산림에 40여 개 진영을 동서로 길게 분산(연영) ──
camp_centers = np.linspace(2.5, 21.5, 9)
for i, cx in enumerate(camp_centers):
    n = 16
    gx = cx + np.random.uniform(-0.8, 0.8, n)
    gy = Y_CAMPS + np.random.uniform(-1.6, 1.6, n)
    troops(ax, gx, gy, '#2255dd', ms=85, alpha=0.8)
pe_em(ax, '⚔️', 12.0, Y_CAMPS + 1.2, zoom=0.20, z=17)
T(ax, '유비(劉備) 본대 — 산림 40여 진영에 분산(연영)', 12.0, Y_CAMPS + 2.1, sz=18, c='#0a1a6b', bg='#e8ecfb')

# ── 육손 오군: 강 남안에 집결(방어 후 화공 준비) ──
n_wu = 130
wu_theta = np.random.uniform(0, 2 * np.pi, n_wu)
wu_r = np.random.uniform(0.8, 2.6, n_wu)
wu_x = 12.0 + wu_r * np.cos(wu_theta)
wu_y = Y_WU + wu_r * 0.4 * np.sin(wu_theta)
troops(ax, wu_x, wu_y, '#ee3333', ms=95, alpha=0.85)
pe_em(ax, '⚔️', 12.0, Y_WU - 2.3, zoom=0.20, z=17)
T(ax, '육손(陸遜) 오군 — 강안 집결, 지구전 후 총공세', 12.0, Y_WU - 3.1, sz=22, c='#7a0000', bg='#fbeaea')

# ── 오반의 유인 별동대(소규모, 청색) ──
n_wb = 12
wb_x = 5.0 + np.random.uniform(-0.6, 0.6, n_wb)
wb_y = Y_RIVER + 1.2 + np.random.uniform(-0.4, 0.4, n_wb)
troops(ax, wb_x, wb_y, '#2255dd', ms=90, alpha=0.9)
T(ax, '오반(吳班) 유인대(8천)', 7.5, MAP_Y0 + 0.5, sz=17, c='#0a1a6b', bg='#e8ecfb')

# ── 화살표 ──
# 육손 화공이 진영들을 동쪽에서 서쪽으로 연쇄적으로 태움
for cx in camp_centers:
    pe_em(ax, '🔥', cx, Y_FIRE, zoom=0.13, z=18)
arr(ax, 12.0, Y_WU + 2.2, 12.0, Y_FIRE - 0.5, '#ff6600', rad=0.0, hw=4.0, tw=2.0, z=13)
T(ax, '강 남안에서 화공 부대 침투·점화', 12.0, Y_FIRE + 1.4, sz=19, c='#7a0000', bg='#fff0e8')

# 화공 확산(동서 연쇄, 점선 화살표 여러 개)
for i in range(len(camp_centers) - 1):
    arr(ax, camp_centers[i], Y_FIRE - 0.3, camp_centers[i + 1], Y_FIRE - 0.3, '#ff8800', rad=0.15, dash=True, hw=2.0, tw=1.0, z=10)
T(ax, '진영 40여 개소 연쇄 화공 — 전후·좌우 구원 단절', 12.0, Y_FIRE - 1.4, sz=18, c='#7a0000', bg='#fff0e8')

# 촉군 붕괴·패주(북쪽 산악로로 흩어짐)
arr(ax, 8.0, Y_CAMPS + 0.5, 4.0, MAP_Y1 - 0.8, '#2255dd', rad=0.1, dash=True, hw=2.4, tw=1.2, z=9)
arr(ax, 17.0, Y_CAMPS + 0.5, 21.5, MAP_Y1 - 0.8, '#2255dd', rad=-0.1, dash=True, hw=2.4, tw=1.2, z=9)
T(ax, '촉군 각개 궤멸 — 백제성으로 패주', 3.6, MAP_Y1 - 1.6, sz=16, c='#0a1a6b', bg='#e8ecfb', ha='left')

# 유인대 붕괴(오반)
arr(ax, 5.0, Y_RIVER + 1.9, 8.0, Y_CAMPS - 1.0, '#2255dd', rad=0.1, dash=True, hw=2.0, tw=1.1, z=9)

draw_title(ax, ['이릉대전 전략도 ', hj('夷陵之戰', '이릉지전'), ' (222)'])

legend_items = [
    ('arr', '#ff6600', '화공 침투·점화'),
    ('dash', '#ff8800', '화공 연쇄 확산'),
    ('dash', '#2255dd', '촉군 궤멸·패주'),
    ('emoji', '⚔️', '지휘관'),
    ('emoji', '🔥', '화공 지점'),
    ('dot_r', '#ee3333', '오(吳)군'),
    ('dot_b', '#2255dd', '촉한군'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items, title=hj('連營', '연영') + '·' + hj('火攻', '화공'))

패군_rows = [
    ('道(지기)', '관우 복수를 명분으로 유비 개인의 감정적 결단 — 조운의 반대 묵살, 신하 집단과 뜻이 어긋남.'),
    ('天(지피)', '육손을 무명 애송이로 얕보고 속전속결을 기대, 지구전에 말려듦.'),
    ('地(지형)', '산림 밀집 진영(險形)이 화공 앞에서 死地로 급변, 700리 연영으로 상호지원 단절.'),
    ('將', '勇은 넘쳤으나 智·信 부족 — 忿速可侮형, 분노로 조급하게 개전.'),
    ('法(전력배치)', '본대 수만+강북 별동대(황권), 40여 진영에 분산.'),
    ('결과', '전군 궤멸 — 陷(화공 앞 대오 연쇄 붕괴), 백제성 패주 후 병사.'),
]
draw_analysis_box(ax, renderer, LX, '패군', '유비', 패군_rows, '#1a3a7a')

승군_rows = [
    ('道(지기)', '부장들의 공격 압박(원망)에도 지구전 원칙을 관철 — 손권의 전권 위임이 뒷받침.'),
    ('天(지피)', '유비의 산림 이진(移陣)이라는 결정적 실수를 즉시 포착해 화공으로 전환.'),
    ('地(지형)', '험지·산림을 오히려 화공 확산에 유리한 조건으로 역이용.'),
    ('將', '智(장기 지구전 구상)·嚴(부장 반발에도 원칙 고수)이 뚜렷.'),
    ('法(전력배치)', '오군 5만, 주연·반장·한당·서성 등 부장 분산 배속.'),
    ('결과', '촉군 궤멸, 유비 백제성 퇴각 — 知可以戰與不可以戰者勝·以虞待不虞者勝.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '육손', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'yiling_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
