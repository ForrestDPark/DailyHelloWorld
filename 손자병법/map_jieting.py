#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""가정 전투(街亭之戰, CE 228) 전략지형도

爭地(쟁지)·掛形(괘형) 실증 사례: 촉한 선봉장 마속은 제갈량의 지시(산 아래
도로·성읍을 거점으로 삼으라)를 어기고 물이 없는 산 정상에 진을 쳤다.
위나라 장수 장합은 산기슭의 물길을 끊어 마속군을 고립시킨 뒤 총공격해
궤멸시켰다 — 부장 왕평만이 별동대 1천 명으로 대오를 유지해 전멸을 면했다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(228)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 중앙에 고립된 산(마속의 진지), 주변은 가정(街亭) 평지·도로 ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 48.0
elev += 60 * np.exp(-(((LON - 0.48) ** 2) / 0.045 + ((LAT - 0.55) ** 2) / 0.05))  # 중앙 고립 산
terrain_colors = [
    (0.0, '#7d8a52'),
    (0.35, '#8f9a60'),
    (0.62, '#a8ac72'),
    (0.85, '#8a9058'),
    (1.0, '#5c6a3a'),
]
draw_terrain(ax, elev, extent, terrain_colors)

T(ax, hj('爭地', '쟁지') + '·' + hj('掛形', '괘형'),
  0.2, MAP_Y1 - 0.6, sz=25, c='#2a2010', bg='#ece4c0', ha='left')
T(ax, hj('街亭', '가정') + ' 도로·성읍 일대', 19.5, MAP_Y1 - 0.6, sz=22, c='#1e2a12', bg='#dfe6cc')

X_CENTER = 12.0
Y_HILLTOP = MAP_Y0 + 8.3      # 산 정상(마속 본진)
Y_MIDSLOPE = MAP_Y0 + 6.0     # 산 중턱(위군 포위선)
Y_STREAM = MAP_Y0 + 3.6       # 산기슭 물길(차단 지점)
Y_ROAD = MAP_Y0 + 1.8         # 가정 도로(왕평 별동대)

# 산기슭 물길(가늘게, 산을 반쯤 두르는 곡선)
sy = np.linspace(2.0, 22.0, 240)
sx = Y_STREAM + 0.35 * np.sin((sy - 2.0) * 0.35)
from matplotlib.patches import Polygon as _Poly
ax.add_patch(_Poly(list(zip(sy, sx - 0.22)) + list(zip(sy[::-1], sx[::-1] + 0.22)),
    fc='#c9a24a', ec='#9c7a2e', lw=1.6, zorder=5, alpha=0.9))
T(ax, '수원(水源)', 3.0, Y_STREAM + 1.0, sz=21, c='#5a3f0a', bg='#f6ecd6', ha='left')

# 가정 도로(하단, 동서로 관통)
ax.plot(np.linspace(0.5, 23.5, 100), np.full(100, Y_ROAD),
    color='#8a6a2a', lw=8, alpha=0.55, zorder=4, solid_capstyle='round')
T(ax, hj('街亭', '가정') + ' 관도(원래 방어 거점)', X_CENTER, Y_ROAD - 1.0, sz=21, c='#5a3f0a', bg='#f6ecd6')

# ── 마속군(산 정상, 청색=패군) ──
n_ms = 110
ms_theta = np.random.uniform(0, 2 * np.pi, n_ms)
ms_r = np.random.uniform(0.5, 1.8, n_ms)
ms_x = X_CENTER + ms_r * np.cos(ms_theta)
ms_y = Y_HILLTOP + ms_r * 0.6 * np.sin(ms_theta)
troops(ax, ms_x, ms_y, '#2255dd', ms=100, alpha=0.82)
pe_em(ax, '⚔️', X_CENTER, Y_HILLTOP + 1.5, zoom=0.20, z=17)
T(ax, '마속(馬謖) 본진 — 수원 없는 산 정상', X_CENTER, Y_HILLTOP + 2.3, sz=22, c='#0a1a6b', bg='#e8ecfb')

# ── 장합군(산 중턱을 둘러싸며 포위, 적색=승군) ──
enc_points = [(X_CENTER - 5.5, Y_MIDSLOPE - 0.5), (X_CENTER + 5.5, Y_MIDSLOPE - 0.5),
              (X_CENTER - 3.5, Y_STREAM - 0.3), (X_CENTER + 3.5, Y_STREAM - 0.3)]
for ex, ey in enc_points:
    n = 35
    gx = ex + np.random.uniform(-1.3, 1.3, n)
    gy = ey + np.random.uniform(-0.6, 0.6, n)
    troops(ax, gx, gy, '#ee3333', ms=90, alpha=0.8)

pe_em(ax, '⚔️', X_CENTER + 5.5, Y_MIDSLOPE - 2.0, zoom=0.20, z=17)
T(ax, '장합(張郃) 위군 — 산을 포위, 물길 차단', X_CENTER + 5.5, Y_MIDSLOPE - 2.8, sz=22, c='#7a0000', bg='#fbeaea')

# ── 왕평 별동대(도로 근처, 청색이나 대오 유지) ──
n_wp = 22
wp_x = X_CENTER - 8.0 + np.random.uniform(-1.0, 1.0, n_wp)
wp_y = Y_ROAD + np.random.uniform(-0.5, 0.5, n_wp)
troops(ax, wp_x, wp_y, '#2255dd', ms=110, alpha=0.95)
pe_em(ax, '🥁', X_CENTER - 8.0, Y_ROAD + 1.3, zoom=0.16, z=17)
T(ax, '왕평(王平) 별동대(1,000, 대오 유지)', X_CENTER - 8.0, Y_ROAD - 1.0, sz=20, c='#0a1a6b', bg='#e8ecfb')

# ── 화살표 ──
# 위군 포위 압축(4방향)
for ex, ey in enc_points:
    arr(ax, ex, ey, X_CENTER + (ex - X_CENTER) * 0.25, Y_MIDSLOPE, '#ee2222', rad=0.05, hw=3.0, tw=1.6, z=11)

pe_em(ax, '🚫', X_CENTER, Y_STREAM + 0.5, zoom=0.16, z=18)
marker_point(ax, X_CENTER, Y_STREAM, ms=26, color='#ff2200')
T(ax, '물길 차단 지점', X_CENTER + 3.2, Y_STREAM - 0.9, sz=19, c='#7a0000', bg='#fff0e8')

# 마속군 붕괴(점선, 사방으로 흩어짐)
arr(ax, X_CENTER - 0.5, Y_HILLTOP - 1.2, X_CENTER - 3.5, Y_MIDSLOPE + 0.6, '#2255dd', rad=0.1, dash=True, hw=2.4, tw=1.2, z=9)
arr(ax, X_CENTER + 0.5, Y_HILLTOP - 1.2, X_CENTER + 3.5, Y_MIDSLOPE + 0.6, '#2255dd', rad=-0.1, dash=True, hw=2.4, tw=1.2, z=9)
T(ax, '수원 차단 → 대오 붕괴·궤멸', X_CENTER, Y_HILLTOP + 0.0, sz=19, c='#0a1a6b', bg='#e8ecfb')

# 왕평 별동대는 북을 치며 대오 유지(장합이 매복을 우려해 접근 안 함) — 위군과의 거리 표시
arr(ax, X_CENTER - 5.8, Y_MIDSLOPE - 1.0, X_CENTER - 7.6, Y_ROAD + 1.0, '#888888', rad=-0.1, dash=True, hw=2.0, tw=1.0, z=9)
T(ax, '장합, 매복 우려로 접근 안 함', X_CENTER - 8.5, Y_MIDSLOPE - 2.0, sz=17, c='#4a4a4a', bg='#f0f0ea')

draw_title(ax, ['가정 전투 전략도 ', hj('街亭之戰', '가정지전'), ' (CE 228)'])

legend_items = [
    ('arr', '#ee2222', '위군 포위·압축'),
    ('dash', '#2255dd', '마속군 붕괴'),
    ('dash', '#888888', '왕평 별동대 회피'),
    ('emoji', '⚔️', '지휘관'),
    ('emoji', '🥁', '왕평(대오 유지)'),
    ('emoji', '🚫', '물길 차단'),
    ('dot_r', '#ee3333', '위(魏)군'),
    ('dot_b', '#2255dd', '촉한군'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items, title=hj('爭地', '쟁지') + '·' + hj('掛形', '괘형'))

패군_rows = [
    ('道(지기)', '제갈량 절도 위반, 왕평 간언 묵살 — 지휘부 내 결속 파탄.'),
    ('天(지피)', '장합의 전력·전술 수준을 오판.'),
    ('地(지형)', '물 없는 산 정상 掛形 — 스스로 퇴로 없는 자리를 선택.'),
    ('將', '智(보급 무시)·嚴(간언 묵살) 모두 부족.'),
    ('法(전력배치)', '본진 산 위, 왕평 별동대만 별도(1,000).'),
    ('결과', '전군 궤멸 — 陷(함): 지휘관이 밀어붙였으나 병사가 무너짐.'),
]
draw_analysis_box(ax, renderer, LX, '패군', '마속', 패군_rows, '#1a3a7a')

승군_rows = [
    ('道(지기)', '신속·정확한 결단이 그대로 실행됨(세부 결속 기록은 불명).'),
    ('天(지피)', '마속의 산 정상 포진이라는 결정적 실수를 정확히 포착.'),
    ('地(지형)', '물길이라는 급소를 정확히 짚어 험지를 함정으로 역이용.'),
    ('將', '智(급소 통찰)·勇(신속한 실행력)이 뚜렷.'),
    ('法(전력배치)', '산 포위 편제, 병력 수 사료상 불명.'),
    ('결과', '마속군 궤멸, 제1차 북벌 좌절 — 知可以戰與不可以戰者勝.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '장합', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jieting_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
