#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""아쟁쿠르 전투(Battle of Agincourt, 1415) 전략지형도"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(11)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 남북으로 좁아지는 진창밭, 양옆 숲(아쟁쿠르 숲 서/트라메쿠르 숲 동) ──
lons = np.linspace(0, 1, 80)
lats = np.linspace(0, 1, 60)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 40.0
elev += 140 * np.exp(-(((LON - 0.06) ** 2) / 0.010))  # 서쪽 숲 (아쟁쿠르 숲)
elev += 140 * np.exp(-(((LON - 0.94) ** 2) / 0.010))  # 동쪽 숲 (트라메쿠르 숲)
elev -= 25 * np.exp(-(((LON - 0.5) ** 2) / 0.05))     # 중앙 진창 저지대
terrain_colors = [
    (0.0, '#5b4326'),
    (0.25, '#7a6236'),
    (0.5, '#8f7a45'),
    (0.75, '#3c5a2e'),
    (1.0, '#28401f'),
]
draw_terrain(ax, elev, extent, terrain_colors)

T(ax, '아쟁쿠르 숲 (애형·隘形)', 2.6, MAP_Y1 - 0.5, sz=32, c='#eef7e0', bg='#28401f')
T(ax, '트라메쿠르 숲', 21.4, MAP_Y1 - 0.5, sz=34, c='#eef7e0', bg='#28401f')
T(ax, '진창 개활지', 12.0, MAP_Y0 + 5.0, sz=34, c='#3a2c10', bg='#e8dcbf')

# ── y 구역 배분 (남=하단 잉글랜드 → 북=상단 프랑스) ──
Y_ENG = MAP_Y0 + 1.6          # 잉글랜드군 중심
Y_STAKE = MAP_Y0 + 2.9        # 말뚝 방어선
Y_FIELD = MAP_Y0 + 5.8        # 진창 개활지 중앙
Y_VAN = MAP_Y0 + 7.6          # 프랑스 선봉
Y_MAIN = MAP_Y0 + 9.1         # 프랑스 본대
Y_REAR = MAP_Y0 + 10.4        # 프랑스 후위

# ── 잉글랜드군: 남쪽(하단), 좁은 지점을 먼저 점거, 말뚝 방어 ──
n_bow = 90
bow_x_l = np.random.uniform(3.2, 6.0, n_bow // 2)
bow_y_l = Y_ENG + np.random.uniform(-1.0, 1.0, n_bow // 2)
bow_x_r = np.random.uniform(18.0, 20.8, n_bow // 2)
bow_y_r = Y_ENG + np.random.uniform(-1.0, 1.0, n_bow // 2)
troops(ax, np.concatenate([bow_x_l, bow_x_r]), np.concatenate([bow_y_l, bow_y_r]),
       '#ee3333', ms=95, alpha=0.85)

# 말뚝(사항) 방어선 표시 - 얇은 원형점선 라인
stake_x = np.linspace(6.2, 17.8, 26)
for sx in stake_x:
    marker_point(ax, sx, Y_STAKE, ms=9, color='#5c3a1a', z=13)

# 잉글랜드 중장병 (중앙, 헨리 5세)
n_mid = 45
mid_x = np.random.uniform(9.0, 15.0, n_mid)
mid_y = Y_ENG + np.random.uniform(-0.9, 0.9, n_mid)
troops(ax, mid_x, mid_y, '#ee3333', ms=150, alpha=0.85)

T(ax, '장궁병 좌익 (카모이스)', 4.6, Y_ENG - 1.3, sz=28, c='#7a0000', bg='#fbeaea')
T(ax, '장궁병 우익 (요크)', 19.4, Y_ENG - 1.3, sz=28, c='#7a0000', bg='#fbeaea')
T(ax, '헨리 5세 중군', 12.0, Y_ENG - 1.3, sz=32, c='#7a0000', bg='#fbeaea')
pe_em(ax, '⚔️', 12.0, Y_ENG + 0.3, zoom=0.20, z=17)

# 장궁 사격 부채꼴 (가는 화살 다수, 진창 개활지를 향해)
np.random.seed(3)
for i in range(14):
    x0 = np.random.uniform(4.0, 19.5)
    y0 = Y_ENG + np.random.uniform(0.3, 1.2)
    x1 = x0 + np.random.uniform(-0.8, 0.8)
    y1 = y0 + np.random.uniform(2.6, 4.2)
    arr(ax, x0, y0, x1, y1, '#cc1111', rad=0.0, hw=1.0, tw=0.35, alpha=0.55, z=9)

# ── 프랑스군: 북쪽(상단), 3제대(선봉/본대/후위), 다수이나 좁은 폭에 밀집 ──
n_van = 130
spread_v = np.random.uniform(-1, 1, n_van)
van_x = 12.0 + spread_v * 8.3
van_y = Y_VAN + np.random.uniform(-0.55, 0.55, n_van)
troops(ax, van_x, van_y, '#2255dd', ms=110)
T(ax, '선봉 (4800)', 12.0, Y_VAN + 0.9, sz=32, c='#0a1a6b', bg='#e8ecfb')

n_main = 85
main_x = 12.0 + np.random.uniform(-1, 1, n_main) * 7.8
main_y = Y_MAIN + np.random.uniform(-0.4, 0.4, n_main)
troops(ax, main_x, main_y, '#2255dd', ms=130)
T(ax, '본대 (3000)', 12.0, Y_MAIN + 0.7, sz=32, c='#0a1a6b', bg='#e8ecfb')

n_rear = 95
rear_x = 12.0 + np.random.uniform(-1, 1, n_rear) * 8.2
rear_y = Y_REAR + np.random.uniform(-0.35, 0.35, n_rear)
troops(ax, rear_x, rear_y, '#2255dd', ms=100, alpha=0.7)
T(ax, '후위 (기마·종자)', 12.0, Y_REAR + 0.45, sz=28, c='#0a1a6b', bg='#e8ecfb')
pe_em(ax, '🛡️', 12.0, Y_MAIN, zoom=0.20, z=17)

# 프랑스 측면 기병대(양익) - 좁은 숲 사이로 돌격 시도
cav_l = [(6.3, Y_VAN + 0.3), (5.0, Y_FIELD + 0.4)]
cav_r = [(17.7, Y_VAN + 0.3), (19.0, Y_FIELD + 0.4)]
for (x0, y0), (x1, y1) in [(cav_l[0], cav_l[1]), (cav_r[0], cav_r[1])]:
    pe_em(ax, '🐎', x0, y0, zoom=0.18, z=15)
    arr(ax, x0, y0, x1, y1, '#2255dd', rad=0.0, hw=2.6, tw=1.4, z=14)
# 기병 돌격 좌절 후 패주 (점선, 반대 방향)
arr(ax, 5.0, Y_FIELD + 0.2, 6.5, Y_VAN, '#2255dd', rad=0.1, dash=True, hw=2.2, tw=1.0, z=14)
arr(ax, 19.0, Y_FIELD + 0.2, 17.5, Y_VAN, '#2255dd', rad=-0.1, dash=True, hw=2.2, tw=1.0, z=14)

# 프랑스 선봉 돌격(남하) → 진창에 정체
arr(ax, 12.0, Y_VAN - 0.6, 12.0, Y_STAKE + 0.5, '#2255dd', rad=0.0, hw=4.5, tw=2.6, z=10)
marker_point(ax, 12.0, Y_FIELD, ms=32, color='#ff2200')
T(ax, '진창에 정체', 15.4, Y_FIELD, sz=30, c='#7a0000', bg='#fff0e8')

# 프랑스 패주(붕괴, 여러 방향 점선)
arr(ax, 11.0, Y_FIELD + 0.3, 8.0, Y_VAN + 0.6, '#2255dd', rad=0.15, dash=True, hw=2.6, tw=1.3, z=9)
arr(ax, 13.0, Y_FIELD + 0.3, 16.0, Y_VAN + 0.6, '#2255dd', rad=-0.15, dash=True, hw=2.6, tw=1.3, z=9)

draw_title(ax, ['아쟁쿠르 전투 전략도  ', 'Battle of Agincourt', '  (1415)'])

legend_items = [
    ('arr', '#ee2222', '장궁 사격'),
    ('arr', '#2255dd', '프랑스 돌격'),
    ('dash', '#2255dd', '프랑스 패주'),
    ('emoji', '🐎', '프랑스 기병'),
    ('emoji', '⚔️', '헨리 5세'),
    ('emoji', '🛡️', '프랑스 지휘부'),
    ('dot_r', '#ee3333', '잉글랜드 보병'),
    ('dot_b', '#2255dd', '프랑스 보병'),
    ('dot', '#5c3a1a', '말뚝 방어선'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items, title='범례 · 애형(隘形)/사지(死地)')

패군_rows = [
    ('전력+배치+보급', '1만4천, 귀족연합으로 통일 지휘 부재. 좁은 폭에 대군이 과밀 집중.'),
    ('지피(知彼)', '적의 궁핍만 보고 승리를 낙관, 장궁 살상력을 경시. 분속가모(忿速可侮).'),
    ('지기(知己)', '물량을 과신, 밀집시 대형이 무너진다는 것을 인식 못함.'),
    ('지지(知地)', '애형(양쪽 숲 사이 진창)을 적이 선점했는데도 정면으로 밀고 들어감.'),
    ('결과', '진창에 짓눌려 각개격파, 전사자 약 6천.'),
]
draw_analysis_box(ax, renderer, LX, '패군', '프랑스군 (달브레)', 패군_rows, '#1a3a7a')

승군_rows = [
    ('전력+배치+보급', '6천~8천(열세), 장궁병·중장병 분업. 헨리 5세 단일 지휘.'),
    ('지피(知彼)', '적이 물량으로 밀어붙여 진창에서 자멸하리라 예측.'),
    ('지기(知己)', '병참 붕괴라는 사지적(死地的) 상황을 받아들이고 장궁의 이점을 극대화.'),
    ('지지(知地)', '애형을 먼저 점거(선거지·先居之)해 말뚝으로 보강, 길목을 봉쇄.'),
    ('결과', '열세를 뒤집은 완승, 전사자 100여 명.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '헨리 5세', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agincourt_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
