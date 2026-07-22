#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""토이토부르크 숲 전투(Battle of the Teutoburg Forest, CE 9) 전략지형도

重地(중지)·圮地(비지) 실증 사례: 바루스가 이끈 3개 군단(전투원 약 2만 +
비전투원 8천~1만)은 이미 게르마니아 깊숙이 들어와(重地) 등 뒤에 여러
게르만 정착지를 남겨둔 채, 칼크리제 언덕과 대습지(大沼澤) 사이 좁은 통로
(險形, 圮地) 로 유인됐다. 아르미니우스가 이끄는 게르만 부족연합(케루스키·
마르시·브루크테리·카티·카우키·시캄브리)은 이 험형을 먼저 선점하고
흙둔덕(Kalkriese Wall)까지 쌓아 로마군을 늪 쪽으로 몰아넣은 채, 11~13km로
길게 늘어진 종대를 3일에 걸쳐 여러 지점에서 동시다발적으로 타격했다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(9)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 북쪽(상단)=칼크리제 언덕(삼림 구릉), 남쪽(하단)=대습지(大沼澤) ──
#    로마 종대는 그 사이 좁은 통로(협형/비지)를 따라 동서로 길게 늘어섬 ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 60.0
elev += 52 * np.exp(-((LAT - 0.83) ** 2) / 0.028) * (1 + 0.14 * np.sin(LON * 6.0 + 0.5))   # 칼크리제 언덕(삼림)
elev -= 32 * np.exp(-((LAT - 0.12) ** 2) / 0.02) * (1 + 0.10 * np.sin(LON * 5.0 + 1.3))     # 대습지(大沼澤)
terrain_colors = [
    (0.0, '#54633a'),
    (0.28, '#75824a'),
    (0.52, '#8f9760'),
    (0.78, '#5c6a3e'),
    (1.0, '#384a26'),
]
draw_terrain(ax, elev, extent, terrain_colors)

T(ax, '칼크리제 언덕(삼림)', 0.15, MAP_Y1 - 4.2, sz=22, c='#20300f', bg='#e4ecd4', ha='left')
T(ax, '대습지(大沼澤) · 통행 불가', 12.0, MAP_Y0 + 0.85, sz=27, c='#20300f', bg='#e4ecd4')
T(ax, hj('重地', '중지') + '·' + hj('圮地', '비지') + '·' + hj('險形', '험형'),
  0.3, MAP_Y0 + 0.85, sz=25, c='#2a2010', bg='#ece4c0', ha='left')

# 게르만족이 쌓은 흙둔덕(Kalkriese Wall) — 언덕 기슭을 따라 길게 이어진 방벽
wall_x = np.linspace(1.0, 23.0, 200)
wall_y = MAP_Y1 - 3.1 + 0.12 * np.sin(wall_x * 1.3)
ax.plot(wall_x, wall_y, color='#4a3620', lw=7, alpha=0.75, zorder=4, solid_capstyle='round')
T(ax, '게르만족 축조 흙둔덕(방벽)', 12.0, MAP_Y1 - 3.75, sz=25, c='#3a2a10', bg='#efe6cc')

# ── y 구역 ──
Y_HILL = MAP_Y1 - 2.0        # 언덕 위 게르만 매복대
Y_COLUMN = MAP_Y0 + 4.2      # 로마군 종대(협형 통로)
Y_MARSH_LBL = MAP_Y0 + 0.9

# ── 로마군 종대: 11~13km로 늘어선 단일 대열, 부대별 구간 표시 ──
n_van = 55
van_x = 3.3 + np.random.uniform(-1.5, 1.5, n_van)
van_y = Y_COLUMN + np.random.uniform(-0.55, 0.55, n_van)
troops(ax, van_x, van_y, '#2255dd', ms=105, alpha=0.82)
T(ax, '선봉(제17군단 일부)', 3.3, Y_COLUMN - 1.35, sz=24, c='#0a1a6b', bg='#e8ecfb')

n_bag = 90
bag_x = 8.6 + np.random.uniform(-2.4, 2.4, n_bag)
bag_y = Y_COLUMN + np.random.uniform(-0.6, 0.6, n_bag)
troops(ax, bag_x, bag_y, '#5a7fe0', ms=90, alpha=0.6)
T(ax, '병참 마차·비전투원(8천~1만)', 8.6, Y_COLUMN - 1.35, sz=24, c='#0a1a6b', bg='#e8ecfb')

n_mid = 70
mid_x = 13.8 + np.random.uniform(-1.9, 1.9, n_mid)
mid_y = Y_COLUMN + np.random.uniform(-0.55, 0.55, n_mid)
troops(ax, mid_x, mid_y, '#2255dd', ms=110, alpha=0.82)
T(ax, '제18군단', 13.8, Y_COLUMN - 1.35, sz=25, c='#0a1a6b', bg='#e8ecfb')

n_rear = 75
rear_x = 18.6 + np.random.uniform(-2.1, 2.1, n_rear)
rear_y = Y_COLUMN + np.random.uniform(-0.55, 0.55, n_rear)
troops(ax, rear_x, rear_y, '#2255dd', ms=110, alpha=0.85)
pe_em(ax, '⚔️', 18.6, Y_COLUMN + 1.1, zoom=0.20, z=17)
T(ax, '제19군단·바루스(총사령관)', 18.6, Y_COLUMN - 1.35, sz=24, c='#0a1a6b', bg='#e8ecfb')

n_cav = 30
cav_x = 22.3 + np.random.uniform(-0.7, 0.7, n_cav)
cav_y = Y_COLUMN + np.random.uniform(-0.5, 0.5, n_cav)
troops(ax, cav_x, cav_y, '#3a6fd8', ms=100, alpha=0.7)
pe_em(ax, '🐎', 22.3, Y_COLUMN + 0.95, zoom=0.16, z=15)
T(ax, '기병(누마니우스 발라)', 22.3, Y_COLUMN - 1.35, sz=22, c='#0a1a6b', bg='#e8ecfb')

# ── 게르만 부족연합: 언덕 위 여러 지점에 분산 매복(3일간 다발적 타격) ──
amb_points = [(4.0, '케루스키(先鋒)'), (9.3, '브루크테리·마르시'), (14.2, '카티'), (19.4, '시캄브리·카우키')]
for ax_, label in amb_points:
    n = 34
    gx = ax_ + np.random.uniform(-1.1, 1.1, n)
    gy = Y_HILL + np.random.uniform(-0.6, 0.6, n)
    troops(ax, gx, gy, '#ee3333', ms=95, alpha=0.8)
    T(ax, label, ax_, Y_HILL + 1.35, sz=22, c='#7a0000', bg='#fbeaea')

pe_em(ax, '⚔️', 4.0, Y_HILL - 0.9, zoom=0.20, z=17)
T(ax, '아르미니우스(총지휘)', 4.0, Y_HILL - 1.7, sz=25, c='#7a0000', bg='#fbeaea')

# 다발적 매복 공격(언덕 → 종대, 4개 지점에서 각각 타격)
arr(ax, 4.0, Y_HILL - 1.2, 3.4, Y_COLUMN + 1.0, '#ee2222', rad=0.08, hw=3.6, tw=1.9, z=12)
arr(ax, 9.3, Y_HILL - 1.2, 8.8, Y_COLUMN + 1.0, '#ee2222', rad=0.05, hw=4.0, tw=2.2, z=12)
arr(ax, 14.2, Y_HILL - 1.2, 13.9, Y_COLUMN + 1.0, '#ee2222', rad=-0.05, hw=3.6, tw=1.9, z=12)
arr(ax, 19.4, Y_HILL - 1.2, 18.9, Y_COLUMN + 1.0, '#ee2222', rad=-0.08, hw=3.6, tw=1.9, z=12)

pe_em(ax, '🔥', 8.8, Y_COLUMN + 0.1, zoom=0.15, z=18)
marker_point(ax, 8.8, Y_COLUMN, ms=28, color='#ff2200')
T(ax, '병참열 궤멸 지점', 6.0, Y_COLUMN + 0.05, sz=23, c='#7a0000', bg='#fff0e8')

# 누마니우스 발라의 기병 이탈 시도(로마군 진행방향 그대로 강행 이탈) → 결국 따라잡혀 전멸(점선 반대방향)
arr(ax, 22.3, Y_COLUMN + 1.0, 23.5, Y_COLUMN + 2.6, '#3a6fd8', rad=0.1, hw=2.4, tw=1.2, z=10)
arr(ax, 23.3, Y_COLUMN + 2.9, 22.0, Y_COLUMN + 1.6, '#2255dd', rad=0.1, dash=True, hw=2.4, tw=1.2, z=9)
T(ax, '기병 이탈 시도 → 추격·전멸', 22.0, Y_COLUMN + 3.3, sz=21, c='#0a1a6b', bg='#e8ecfb')

# 로마군 전체 붕괴(3일째, 최종 궤멸) — 종대 전체가 방향을 잃고 흩어짐(점선)
arr(ax, 13.8, Y_COLUMN - 1.0, 12.0, MAP_Y0 + 0.5, '#2255dd', rad=0.1, dash=True, hw=2.6, tw=1.3, z=9)
T(ax, '3일간 지속된 다발적 매복 끝 전멸', 12.0, MAP_Y0 + 2.0, sz=24, c='#20300f', bg='#e4ecd4')

draw_title(ax, ['토이토부르크 숲 전투 전략도 ', 'Teutoburg', ' (CE 9)'])

legend_items = [
    ('arr', '#ee2222', '게르만 매복공격(4곳)'),
    ('dash', '#2255dd', '로마군 붕괴·패주'),
    ('arr', '#3a6fd8', '기병 이탈'),
    ('emoji', '⚔️', '지휘관'),
    ('emoji', '🐎', '로마 기병'),
    ('emoji', '🔥', '궤멸 지점'),
    ('dot_r', '#ee3333', '게르만 부족연합'),
    ('dot_b', '#2255dd', '로마 군단'),
    ('dot', '#ffaa00', '요충지'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items, title=hj('重地', '중지') + '·' + hj('圮地', '비지'))

패군_rows = [
    ('지기(知己)', '2만 전투원+비전투원 1만 종대, 세게스테스 경고 무시(廉潔可辱).'),
    ('지피(知彼)', '친로마파 아르미니우스를 끝까지 신뢰(愛民可煩).'),
    ('지지(知地)', '칼크리제 험형(險形)에 스스로 유인됨(圮地).'),
    ('장(將)', '嚴은 있으나 智·信 결핍, 경고 묵살.'),
    ('전력배치(法)', '3개 군단, 병참열과 뒤섞인 늘어진 단일종대.'),
    ('결과', '3일간 매복 끝 전멸 — 亂(란): 장수 약하고 군기 문란.'),
]
draw_analysis_box(ax, renderer, LX, '패군', '바루스', 패군_rows, '#1a3a7a')

승군_rows = [
    ('지기(知己)', '여러 부족을 독립이라는 대의로 결집.'),
    ('지피(知彼)', '바루스의 방심과 이동 타이밍을 정확히 읽음.'),
    ('지지(知地)', '험형(險形) 선점, 흙둔덕으로 늪 쪽 압박(我先居之).'),
    ('장(將)', '智·信 뚜렷, 3일간 냉정히 매복 통제(嚴).'),
    ('전력배치(法)', '약 15,000, 4개 지점 분산매복 각개타격.'),
    ('결과', '로마 3개 군단 전멸 — 上下同欲者勝.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '아르미니우스', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'teutoburg_forest_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
