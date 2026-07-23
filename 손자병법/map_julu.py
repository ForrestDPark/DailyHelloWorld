#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""거록대전(巨鹿之戰, BCE 207) 전략지형도

圍地(위지)·死地(사지) 실증 사례: 진(秦)의 장한(章邯)은 황하 강변에서
거록(巨鹿)까지 이어지는 단 하나의 좁은 용도(甬道, 고가 보급로)로
왕리(王離)의 포위군에 군량을 댔다 — 그 용도가 끊기면 왕리군은 성 안의
조(趙)군과 성 밖의 초(楚)군 사이에 낀 채 퇴로가 멀리 도는 곳에 갇히는
전형적 圍地였다. 항우(項羽)는 강을 건너자마자 배를 가라앉히고 솥을
깨뜨려(破釜沉舟) 전군을 스스로 死地로 몰아넣은 뒤, 아홉 차례 접전
끝에 용도를 끊고 왕리군을 궤멸시켰다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(207)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 남쪽(하단)=황하 도하 지점, 북쪽(상단)=거록성 인근 구릉 ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 60.0
elev += 40 * np.exp(-(((LON - 0.5) ** 2) / 0.06 + ((LAT - 0.88) ** 2) / 0.03))   # 거록성 인근 구릉
elev -= 18 * np.exp(-((LAT - 0.05) ** 2) / 0.008)                                # 황하 저지(남단)
terrain_colors = [
    (0.0, '#8a9160'),
    (0.3, '#9aa06e'),
    (0.6, '#7d8a52'),
    (1.0, '#586a38'),
]
draw_terrain(ax, elev, extent, terrain_colors)

# 황하(黃河) — 남쪽 끝을 동서로 흐름
ry = np.linspace(0, 24, 300)
rx_c = MAP_Y0 + 0.9 + 0.2 * np.sin(ry * 0.5)
rx_l, rx_r = rx_c - 0.4, rx_c + 0.4
from matplotlib.patches import Polygon as _Poly
ax.add_patch(_Poly(list(zip(ry, rx_l)) + list(zip(ry[::-1], rx_r[::-1])),
    fc='#c9a24a', ec='#9c7a2e', lw=2, zorder=5, alpha=0.9))
ax.annotate('', xy=(18, rx_c[240]), xytext=(6, rx_c[80]),
    arrowprops=dict(arrowstyle='->', color='#9c7a2e', lw=2, mutation_scale=14), zorder=6)
T(ax, hj('黃河', '황하'), 3.0, MAP_Y0 + 1.7, sz=22, c='#5a3f0a', bg='#f6ecd6', ha='left')

T(ax, hj('圍地', '위지') + '·' + hj('死地', '사지') + '·' + hj('隘形', '애형'),
  0.2, MAP_Y1 - 0.6, sz=25, c='#2a2010', bg='#ece4c0', ha='left')
T(ax, '거록성 인근 구릉', 21.0, MAP_Y1 - 0.6, sz=23, c='#1e2a12', bg='#dfe6cc')

# ── y 좌표 ──
Y_RIVER = MAP_Y0 + 1.7
Y_ZHANG = MAP_Y0 + 4.0    # 장한 본대(남측, 용도 수비)
Y_ROAD_MID = MAP_Y0 + 6.5  # 용도 중간(절단 지점)
Y_WANGLI = MAP_Y1 - 2.6    # 왕리 포위군(북측, 거록성 앞)
Y_JULU = MAP_Y1 - 1.4      # 거록성

X_CENTER = 12.0

# 거록성(작은 성곽 표식)
ax.add_patch(FancyBboxPatch(
    (X_CENTER - 0.5, Y_JULU - 0.35), 1.0, 0.7,
    boxstyle='square,pad=0.05', fc='#6b5636', ec='#3a2c14', lw=2, zorder=9))
T(ax, hj('巨鹿城', '거록성') + '(조군 수비)', X_CENTER, Y_JULU + 0.75, sz=22, c='#3a2c14', bg='#efe6cc')

# 용도(甬道) — 황하에서 거록성까지 이어지는 고가 보급로
road_x = np.full(200, X_CENTER)
road_y = np.linspace(Y_RIVER + 0.6, Y_WANGLI - 0.6, 200)
ax.plot(road_x, road_y, color='#8a6a2a', lw=9, alpha=0.7, zorder=4, solid_capstyle='round')
T(ax, hj('甬道', '용도') + '(고가 보급로)', X_CENTER + 3.2, Y_ROAD_MID + 1.4, sz=23, c='#5a3f0a', bg='#f6ecd6')

# ── 왕리 포위군(북측, 거록성 앞, 청색=패군) ──
n_wl = 130
wl_theta = np.random.uniform(0, 2 * np.pi, n_wl)
wl_r = np.random.uniform(0.9, 2.3, n_wl)
wl_x = X_CENTER + wl_r * np.cos(wl_theta)
wl_y = Y_WANGLI + wl_r * 0.55 * np.sin(wl_theta)
troops(ax, wl_x, wl_y, '#2255dd', ms=95, alpha=0.78)
pe_em(ax, '⚔️', X_CENTER, Y_WANGLI - 2.4, zoom=0.20, z=17)
T(ax, '왕리(王離) 포위군', X_CENTER, Y_WANGLI - 3.2, sz=25, c='#0a1a6b', bg='#e8ecfb')

# ── 장한 본대(남측, 용도 수비, 청색) ──
n_zh = 90
zh_x = 6.0 + np.random.uniform(-2.2, 2.2, n_zh)
zh_y = Y_ZHANG + np.random.uniform(-0.9, 0.9, n_zh)
troops(ax, zh_x, zh_y, '#3a6fd8', ms=100, alpha=0.8)
pe_em(ax, '⚔️', 6.0, Y_ZHANG + 1.6, zoom=0.20, z=17)
T(ax, '장한(章邯) 본대(용도 수비)', 6.0, Y_ZHANG - 1.7, sz=24, c='#0a1a6b', bg='#e8ecfb')

# ── 초(楚)군 항우 — 도하 지점(남측)에서 북상 ──
n_xy = 140
xy_x = 17.5 + np.random.uniform(-2.3, 2.3, n_xy)
xy_y = Y_RIVER + 1.5 + np.random.uniform(-0.8, 0.8, n_xy)
troops(ax, xy_x, xy_y, '#ee3333', ms=110, alpha=0.85)
pe_em(ax, '⚔️', 17.5, Y_RIVER + 3.0, zoom=0.20, z=17)
T(ax, '항우(項羽) 초군(도하 직후)', 17.5, Y_RIVER + 3.8, sz=24, c='#7a0000', bg='#fbeaea')
T(ax, '破釜沉舟(파부침주) — 배·솥을 버리고 사흘치 식량만 휴대', 21.0, Y_RIVER + 0.4, sz=17, c='#7a0000', bg='#fff0e8')

# ── 전개 화살표 ──
# 1) 초군 → 용도 중간 지점 강습(9차 접전, 절단)
arr(ax, 16.0, Y_RIVER + 2.2, X_CENTER + 1.5, Y_ROAD_MID, '#ee2222', rad=-0.15, hw=4.0, tw=2.1, z=12)
pe_em(ax, '🔥', X_CENTER, Y_ROAD_MID, zoom=0.16, z=18)
marker_point(ax, X_CENTER, Y_ROAD_MID, ms=28, color='#ff2200')
T(ax, '용도 절단 지점(9차 접전)', X_CENTER + 3.6, Y_ROAD_MID - 0.9, sz=20, c='#7a0000', bg='#fff0e8')

# 2) 초군 주력 → 왕리 포위군 배후·측면 강습
arr(ax, 17.0, Y_ROAD_MID + 0.8, X_CENTER + 2.0, Y_WANGLI - 0.5, '#ee2222', rad=-0.1, hw=4.2, tw=2.2, z=12)

# 3) 거록성 조군 → 왕리군에 반격(협공, 실선 짧게)
arr(ax, X_CENTER - 0.2, Y_JULU - 0.6, X_CENTER - 1.2, Y_WANGLI + 0.8, '#cc6600', rad=0.1, hw=2.8, tw=1.4, z=11)
T(ax, '조군 성 밖 반격(협공)', X_CENTER - 3.4, Y_JULU - 1.0, sz=19, c='#7a3a00', bg='#fff0e8')

# 4) 왕리군 붕괴·포로(청색 점선)
arr(ax, X_CENTER, Y_WANGLI - 1.5, X_CENTER + 1.0, MAP_Y1 - 0.6, '#2255dd', rad=0.1, dash=True, hw=2.6, tw=1.3, z=9)
T(ax, '왕리 포로·포위군 궤멸', 4.0, Y_WANGLI + 0.3, sz=20, c='#0a1a6b', bg='#e8ecfb')

# 5) 장한 본대 고립 → 이후 항복(회색 점선, 남서 방향)
arr(ax, 6.0, Y_ZHANG - 1.2, 3.0, MAP_Y0 + 0.5, '#888888', rad=-0.1, dash=True, hw=2.2, tw=1.1, z=9)
T(ax, '장한 고립 → 이후 항복', 3.0, MAP_Y0 + 1.4, sz=19, c='#4a4a4a', bg='#f0f0ea')

draw_title(ax, ['거록대전 전략도 ', hj('巨鹿之戰', '거록지전'), ' (BCE 207)'])

legend_items = [
    ('arr', '#ee2222', '초군 공격(용도 절단)'),
    ('arr', '#cc6600', '조군 협공'),
    ('dash', '#2255dd', '왕리군 붕괴'),
    ('dash', '#888888', '장한 고립·항복'),
    ('emoji', '⚔️', '지휘관'),
    ('emoji', '🔥', '절단 지점'),
    ('dot_r', '#ee3333', '초(楚)군'),
    ('dot_b', '#2255dd', '진(秦)군'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items, title=hj('圍地', '위지') + '·' + hj('死地', '사지'))

패군_rows = [
    ('道(지기)', '전후방 이원 지휘(장한·왕리)+조고의 조정 간섭, 결속 취약.'),
    ('天(지피)', '항우의 결사적 도하·공세라는 외부 변수에 무방비.'),
    ('地(지형)', '단일 용도(甬道)가 유일한 보급·연결로 — 절단 즉시 圍地.'),
    ('將', '왕리는 智·勇 갖췄으나 장한과의 협조 실패로 고립.'),
    ('法(전력배치)', '전후방 분리 편제, 용도 수비 병력 부족.'),
    ('결과', '왕리 포로·장한 항복 — 崩(붕): 후방과 단절된 채 홀로 응전.'),
]
draw_analysis_box(ax, renderer, LX, '패군', '왕리·장한', 패군_rows, '#1a3a7a')

승군_rows = [
    ('道(지기)', '송의 참수로 지휘 통일, 파부침주로 전군 결사 각오 강제.'),
    ('天(지피)', '진군 내부 불화(장한-왕리 협조 부족)라는 틈을 포착.'),
    ('地(지형)', '스스로 사지를 택해 도하, 적의 隘形(용도) 급소를 절단.'),
    ('將', '智·嚴 뚜렷, 9차 교전을 결단력으로 밀어붙임.'),
    ('法(전력배치)', '사흘치 식량만 남긴 결사 편제, 단일 지휘.'),
    ('결과', '진 주력군 궤멸 — 知可以戰與不可以戰者勝: 결전 타이밍을 정확히 판단.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '항우', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'julu_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
