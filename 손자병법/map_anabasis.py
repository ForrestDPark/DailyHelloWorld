#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""크세노폰의 만인대 원정(Anabasis, BCE 401~400) 전략지형도

九地 전체(輕地·重地·圮地·圍地·死地 등) 실증 사례: 쿠낙사 전투 후 지휘부가
암살당한 그리스 용병대는 페르시아 총독 티사페르네스의 추격을 받으며
페르시아 영토를 관통해 후퇴했다. 이 지도는 그 여정의 결정적 전환점 —
대(大)자브강(Great Zab) 도하 지점에서 카르두코이족 산악지대로 진입하는
구간 — 을 그린다. 강 유역(저지)에서는 페르시아 기병이 우위였지만,
산악 협로에 들어서는 순간 기병은 무력화되고 지형 자체가 그리스군의
방패가 됐다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(401)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 북쪽(상단)=카르두코이 산악지대, 남쪽(하단)=대자브강 저지 ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 55.0
elev += 55 * np.exp(-((LAT - 0.86) ** 2) / 0.03) * (1 + 0.18 * np.sin(LON * 7.0 + 0.4))   # 카르두코이 산악(북)
elev -= 20 * np.exp(-((LAT - 0.10) ** 2) / 0.012)                                          # 대자브강 저지(남)
terrain_colors = [
    (0.0, '#6a7a48'),
    (0.28, '#83925a'),
    (0.55, '#95a068'),
    (0.8, '#6f7d48'),
    (1.0, '#465a2e'),
]
draw_terrain(ax, elev, extent, terrain_colors)

T(ax, hj('圮地', '비지') + '·' + hj('圍地', '위지') + '·' + hj('險形', '험형'),
  0.2, MAP_Y1 - 0.6, sz=24, c='#2a2010', bg='#ece4c0', ha='left')
T(ax, '카르두코이 산악지대(오늘날 튀르키예 동남부)', 20.5, MAP_Y1 - 0.6, sz=20, c='#1e2a12', bg='#dfe6cc')

# 대자브강(Great Zab) — 남쪽 저지를 동서로 흐름
ry = np.linspace(0, 24, 300)
rx_c = MAP_Y0 + 1.9 + 0.25 * np.sin(ry * 0.45)
rx_l, rx_r = rx_c - 0.45, rx_c + 0.45
from matplotlib.patches import Polygon as _Poly
ax.add_patch(_Poly(list(zip(ry, rx_l)) + list(zip(ry[::-1], rx_r[::-1])),
    fc='#c9a24a', ec='#9c7a2e', lw=2, zorder=5, alpha=0.9))
T(ax, hj('大自布江', '대자브강'), 3.0, MAP_Y0 + 1.0, sz=22, c='#5a3f0a', bg='#f6ecd6', ha='left')

# ── y 좌표 ──
Y_RIVER = MAP_Y0 + 1.9
Y_PERSIAN = MAP_Y0 + 4.3     # 티사페르네스 추격군(남측 저지)
Y_CROSS = MAP_Y0 + 6.5       # 도하 지점(강변)
Y_REARGUARD = MAP_Y1 - 4.0   # 크세노폰 후위대(경사면)
Y_MAIN = MAP_Y1 - 2.2        # 그리스 본대(산악 진입)

X_CENTER = 12.0

# ── 티사페르네스 페르시아 추격군(남측 저지, 청색=패군) ──
n_pers = 150
pers_theta = np.random.uniform(0, 2 * np.pi, n_pers)
pers_r = np.random.uniform(1.0, 2.8, n_pers)
pers_x = X_CENTER + 3.0 + pers_r * np.cos(pers_theta)
pers_y = Y_PERSIAN + pers_r * 0.5 * np.sin(pers_theta)
troops(ax, pers_x, pers_y, '#2255dd', ms=85, alpha=0.75)
pe_em(ax, '⚔️', X_CENTER + 3.0, Y_PERSIAN - 2.0, zoom=0.20, z=17)
T(ax, '티사페르네스 추격군(기병 중심)', X_CENTER + 3.0, Y_PERSIAN - 2.8, sz=23, c='#0a1a6b', bg='#e8ecfb')

# ── 그리스 본대: 강을 건너 산악으로 진입 중 ──
n_main = 130
main_theta = np.random.uniform(0, 2 * np.pi, n_main)
main_r = np.random.uniform(0.8, 2.2, n_main)
main_x = X_CENTER - 2.0 + main_r * np.cos(main_theta)
main_y = Y_MAIN + main_r * 0.5 * np.sin(main_theta)
troops(ax, main_x, main_y, '#ee3333', ms=95, alpha=0.82)
pe_em(ax, '⚔️', X_CENTER - 2.0, Y_MAIN + 1.0, zoom=0.20, z=17)
T(ax, '그리스 본대(산악 진입, 경보병 재편)', X_CENTER - 4.3, Y_MAIN + 1.7, sz=20, c='#7a0000', bg='#fbeaea')

# ── 크세노폰 후위대: 도하 지점 방어, 추격 저지 ──
n_rg = 70
rg_x = X_CENTER + 0.5 + np.random.uniform(-1.7, 1.7, n_rg)
rg_y = Y_CROSS + np.random.uniform(-0.7, 0.7, n_rg)
troops(ax, rg_x, rg_y, '#ee3333', ms=100, alpha=0.85)
pe_em(ax, '⚔️', X_CENTER + 0.5, Y_CROSS + 1.5, zoom=0.20, z=17)
T(ax, '크세노폰 후위대(도하 엄호)', X_CENTER + 0.5, Y_CROSS + 2.3, sz=24, c='#7a0000', bg='#fbeaea')

# ── 화살표: 페르시아 기병 추격 → 강변에서 저지 ──
arr(ax, X_CENTER + 3.0, Y_PERSIAN + 1.5, X_CENTER + 1.0, Y_CROSS - 0.7, '#2255dd', rad=0.1, hw=4.0, tw=2.1, z=12)
pe_em(ax, '🚫', X_CENTER + 1.2, Y_CROSS - 1.2, zoom=0.16, z=18)
T(ax, '기병 추격 — 강·산악에 저지됨', X_CENTER + 4.6, Y_CROSS - 1.4, sz=19, c='#0a1a6b', bg='#e8ecfb')

# 그리스군 도하 후 산악 진입(주력 이동)
arr(ax, X_CENTER + 0.3, Y_CROSS + 0.6, X_CENTER - 1.5, Y_MAIN - 0.8, '#cc2222', rad=-0.1, hw=3.6, tw=1.9, z=12)
T(ax, '도하 후 산악 진입', X_CENTER - 3.6, Y_CROSS + 1.2, sz=19, c='#7a0000', bg='#fff0e8')

# 후위대 최종 합류(점선)
arr(ax, X_CENTER + 0.5, Y_CROSS + 1.4, X_CENTER - 1.0, Y_MAIN - 0.3, '#ee3333', rad=0.05, dash=True, hw=2.6, tw=1.3, z=9)
T(ax, '후위대 합류 → 산악 안전지대', X_CENTER - 5.0, Y_MAIN - 1.4, sz=18, c='#7a0000', bg='#fff0e8')

# 페르시아군 추격 포기(점선, 남쪽으로 회군)
arr(ax, X_CENTER + 3.0, Y_PERSIAN - 0.5, X_CENTER + 5.5, MAP_Y0 + 0.6, '#888888', rad=-0.1, dash=True, hw=2.2, tw=1.1, z=9)
T(ax, '추격 실패 → 회군', X_CENTER + 6.5, MAP_Y0 + 1.4, sz=18, c='#4a4a4a', bg='#f0f0ea')

draw_title(ax, ['크세노폰 만인대 원정 전략도 ', 'Anabasis', ' (BCE 401~400)'])

legend_items = [
    ('arr', '#2255dd', '페르시아 기병 추격'),
    ('arr', '#cc2222', '그리스군 도하·산악 진입'),
    ('dash', '#ee3333', '후위대 합류'),
    ('dash', '#888888', '페르시아 추격 실패·회군'),
    ('emoji', '⚔️', '지휘관'),
    ('emoji', '🚫', '지형에 의한 저지'),
    ('dot_r', '#ee3333', '그리스 용병대'),
    ('dot_b', '#2255dd', '페르시아 추격군'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items, title=hj('圮地', '비지') + '·' + hj('圍地', '위지'))

패군_rows = [
    ('道(지기)', '거짓 휴전으로 그리스 지휘부 암살 — 신뢰 아닌 기만으로 시작.'),
    ('天(지피)', '그리스군의 산악 우회 가능성을 예측 못함.'),
    ('地(지형)', '카르두코이 산악은 기병이 완전히 무력화되는 遠形.'),
    ('將', '智(지형 예측 실패)·信(휴전 파기) 모두 부족.'),
    ('法(전력배치)', '기병 중심 편제, 병력 수 사료상 불명.'),
    ('결과', '그리스군을 끝내 놓침 — 走(주): 승산 없는 무리한 추격 지속.'),
]
draw_analysis_box(ax, renderer, LX, '패군', '티사페르네스', 패군_rows, '#1a3a7a')

승군_rows = [
    ('道(지기)', '지휘부 몰살 후 병사 투표로 재건, 자발적 결속.'),
    ('天(지피)', '페르시아군이 기병 중심임을 읽고 평지 결전을 회피.'),
    ('地(지형)', '산악·강 등 다양한 지형에 맞춰 능동적으로 대응 전환.'),
    ('將', '智(지형별 전술 전환)·勇(즉각적 지휘 인수)이 뚜렷.'),
    ('法(전력배치)', '중장보병 1만여 → 행군 중 경보병 신설로 기동성 보강.'),
    ('결과', '약 8,000명(3/4) 생환 — 識衆寡之用者勝: 유연한 병력 운용.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '크세노폰', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'anabasis_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
