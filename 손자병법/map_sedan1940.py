#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""스당 돌파(Fall Gelb·만슈타인 계획, 1940.5) 전략지형도

兵之情主速·由不虞之道·攻其所不戒也 실증 사례: 연합군이 "전차가 통과할 수
없다"고 믿었던 아르덴 삼림을 독일 기갑군단이 사흘 만에 주파했다. 뫼즈강
스당 구간을 지키던 프랑스 55보병사단(예비역·경장비)은 정예가 아니었고,
급강하폭격과 신속한 도하 앞에 붕괴했다 — 이후 기갑부대는 해안까지 곧장
질주(낫질 작전)해 벨기에의 연합군 주력을 통째로 갈라놓았다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(1940)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 북쪽=아르덴 삼림(구릉), 중앙=뫼즈강(스당), 남쪽=개활 평원(해안 방면) ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 48.0
elev += 46 * np.exp(-((LAT - 0.78) ** 2) / 0.045) * (1 + 0.2 * np.sin(LON * 8.0 + 0.3))  # 아르덴 삼림(북)
elev -= 14 * np.exp(-((LAT - 0.30) ** 2) / 0.012)                                         # 뫼즈강 저지
terrain_colors = [
    (0.0, '#7a8a52'),
    (0.32, '#8a9860'),
    (0.58, '#9ba470'),
    (0.82, '#7d8a52'),
    (1.0, '#566234'),
]
draw_terrain(ax, elev, extent, terrain_colors)

T(ax, hj('由不虞之道', '유불우지도') + '·' + hj('速', '속'),
  0.2, MAP_Y1 - 0.6, sz=24, c='#2a2010', bg='#ece4c0', ha='left')
T(ax, hj('阿爾丁', '아르덴') + ' 삼림 — "전차 통과 불가" 오판', 18.0, MAP_Y1 - 0.6, sz=20, c='#1e2a12', bg='#dfe6cc')

# 뫼즈강(동서로 흐름)
ry = np.linspace(0, 24, 300)
rx_c = MAP_Y0 + 3.9 + 0.25 * np.sin(ry * 0.35)
rx_l, rx_r = rx_c - 0.45, rx_c + 0.45
from matplotlib.patches import Polygon as _Poly
ax.add_patch(_Poly(list(zip(ry, rx_l)) + list(zip(ry[::-1], rx_r[::-1])),
    fc='#c9a24a', ec='#9c7a2e', lw=2, zorder=5, alpha=0.9))
T(ax, hj('默茲河', '뫼즈강') + '(스당 구간)', 3.0, MAP_Y0 + 3.0, sz=21, c='#5a3f0a', bg='#f6ecd6', ha='left')

Y_ARDENNES = MAP_Y1 - 3.2      # 독일 기갑군단, 삼림 종대 이동
Y_MEUSE = MAP_Y0 + 3.9          # 뫼즈강·스당 도하 지점
Y_BREAKOUT = MAP_Y0 + 1.2       # 돌파 후 해안 질주 방향

X_CENTER = 12.0

# ── 독일 기갑군단(아르덴 삼림 종대, 적색=승군) ──
n_pz = 130
col_x = X_CENTER + np.random.uniform(-1.2, 1.2, n_pz)
col_y = Y_ARDENNES + np.random.uniform(-2.6, 2.6, n_pz)
troops(ax, col_x, col_y, '#ee3333', ms=80, alpha=0.8)
pe_em(ax, '⚔️', X_CENTER, Y_ARDENNES + 2.1, zoom=0.20, z=17)
T(ax, '구데리안 제19기갑군단 — 삼림 종대(정체된 대열)', X_CENTER, Y_ARDENNES + 2.9, sz=19, c='#7a0000', bg='#fbeaea')

# ── 프랑스 55보병사단(스당 방어, 청색=패군, 예비역·경장비) ──
n_fr = 55
fr_x = X_CENTER + np.random.uniform(-2.6, 2.6, n_fr)
fr_y = Y_MEUSE + np.random.uniform(-0.7, 0.7, n_fr)
troops(ax, fr_x, fr_y, '#2255dd', ms=75, alpha=0.75)
pe_em(ax, '⚔️', X_CENTER - 4.0, Y_MEUSE - 1.6, zoom=0.16, z=17)
T(ax, '프랑스 55예비사단(경장비) — 스당 방어', X_CENTER - 4.0, Y_MEUSE - 2.4, sz=18, c='#0a1a6b', bg='#e8ecfb')

# 급강하폭격 표시
pe_em(ax, '🔥', X_CENTER, Y_MEUSE + 0.3, zoom=0.15, z=18)
T(ax, '슈투카 급강하폭격 — 방어선 공황', X_CENTER + 4.2, Y_MEUSE + 1.2, sz=17, c='#7a0000', bg='#fff0e8')

# ── 화살표 ──
arr(ax, X_CENTER, Y_ARDENNES - 2.8, X_CENTER, Y_MEUSE + 1.0, '#cc2222', rad=0.0, hw=4.2, tw=2.2, z=13)
T(ax, '사흘 만에 삼림 주파·도하 강행', X_CENTER + 5.6, Y_ARDENNES - 1.5, sz=18, c='#7a0000', bg='#fff0e8')

# 도하 후 서쪽(해안)으로 질주 — 낫질 작전
arr(ax, X_CENTER - 1.0, Y_MEUSE - 1.2, 2.0, Y_BREAKOUT, '#ee2222', rad=-0.1, hw=4.0, tw=2.0, z=12)
T(ax, '낫질 작전(Sichelschnitt) — 해안까지 질주', 5.0, Y_BREAKOUT - 1.0, sz=18, c='#7a0000', bg='#fff0e8', ha='left')

# 프랑스군 붕괴·패주
arr(ax, X_CENTER - 2.0, Y_MEUSE - 0.3, X_CENTER - 4.5, MAP_Y0 + 0.8, '#2255dd', rad=0.1, dash=True, hw=2.4, tw=1.2, z=9)
T(ax, '55사단 붕괴·패주', X_CENTER - 6.5, MAP_Y0 + 1.3, sz=16, c='#0a1a6b', bg='#e8ecfb', ha='left')

# 연합군 주력(북쪽 벨기에)이 고립되는 상황을 화살표로 암시
arr(ax, X_CENTER + 2.0, Y_ARDENNES + 2.0, X_CENTER + 7.5, Y_ARDENNES - 3.5, '#888888', rad=0.15, dash=True, hw=2.0, tw=1.0, z=8)
T(ax, '연합군 주력(벨기에) 배후 차단', 20.0, Y_ARDENNES - 1.0, sz=16, c='#4a4a4a', bg='#f0f0ea')

draw_title(ax, ['스당 돌파 전략도 ', 'Fall Gelb — Sedan', ' (1940)'])

legend_items = [
    ('arr', '#cc2222', '독일군 주파·도하·돌파'),
    ('dash', '#2255dd', '프랑스군 붕괴·패주'),
    ('dash', '#888888', '연합군 배후 차단'),
    ('emoji', '⚔️', '지휘관'),
    ('emoji', '🔥', '급강하폭격'),
    ('dot_r', '#ee3333', '독일군'),
    ('dot_b', '#2255dd', '프랑스군'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items, title=hj('速', '속') + '·' + hj('不虞', '불우'))

패군_rows = [
    ('道(지기)', '가믈랭의 "전차는 아르덴을 못 지난다"는 확신을 전군이 그대로 답습 — 검증 없는 결속.'),
    ('天(지피)', '아르덴 삼림에 대한 독일군의 실제 기동력을 완전히 오판.'),
    ('地(지형)', '뫼즈강 스당 구간을 경장비 예비사단만으로 방어 — 험지를 過信.'),
    ('將', '智(정찰·재평가) 부족 — 경보를 받고도 대응을 늦춤.'),
    ('法(전력배치)', '55예비사단(경장비) 약 2만, 전차 300여, 포 174문.'),
    ('결과', '방어선 붕괴·포로 다수 — 走(무리한 고정방어로 붕괴).'),
]
draw_analysis_box(ax, renderer, LX, '패군', '위치제(프랑스 2군)', 패군_rows, '#1a3a7a')

승군_rows = [
    ('道(지기)', '만슈타인의 계획을 히틀러가 채택, 구데리안이 현장 재량으로 밀어붙임.'),
    ('天(지피)', '연합군이 아르덴을 무방비로 둘 것을 정확히 읽음.'),
    ('地(지형)', '"통과 불가"로 여겨진 삼림을 오히려 기습로로 역이용.'),
    ('將', '智(작전 구상)·勇(현장 강행 돌파)이 뚜렷.'),
    ('法(전력배치)', '제19기갑군단 등 기갑사단 다수, 총 병력 다수 논쟁적.'),
    ('결과', '스당 돌파·해안 질주 — 知可以戰與不可以戰者勝·以虞待不虞者勝.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '구데리안·만슈타인', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sedan1940_claude_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
