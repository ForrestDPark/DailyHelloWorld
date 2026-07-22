#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""필(邲) 전투(邲之戰, BCE 597) 전략지형도

衢地(구지) 실증 사례: 정(鄭)은 진·초·제 등 열강이 모두 접한(諸侯之地三屬)
전형적 구지였다. 초장왕이 진의 구원군보다 먼저 정을 굴복시키고(先至),
뒤늦게 도착한 진군(중군좌 先縠의 독단적 도하로 내부 분열까지 겹침)을
황하 남안에서 격파한다. 진군은 앞에는 초의 총공세, 뒤에는 황하를 두어
퇴로가 막힌 채 참패하고, 배 안에 손가락이 가득할 만큼 처참하게 패주한다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(59)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 황하 남안의 평탄한 저습지 평원, 서쪽에 완만한 敖山(오산) 구릉 ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 78.0
elev += 55 * np.exp(-(((LON - 0.15) ** 2) / 0.012 + ((LAT - 0.62) ** 2) / 0.06))   # 敖山(서쪽 구릉, 상군 방비 지점)
elev -= 18 * np.exp(-(((LON - 0.5) ** 2) / 0.4 + ((LAT - 0.92) ** 2) / 0.01))       # 황하 연안 저지대(북단)
terrain_colors = [
    (0.0, '#c8bd8e'),
    (0.28, '#d6cc9e'),
    (0.55, '#c3b47a'),
    (0.8, '#a89858'),
    (1.0, '#8a7a42'),
]
draw_terrain(ax, elev, extent, terrain_colors)

# 황하(黃河) - 지도 북단을 동서로 흐름(진군의 퇴로이자 배후 장애물)
np.random.seed(59)
ry = np.linspace(0, 24, 300)
rx_c = MAP_Y1 - 1.0 + 0.30 * np.sin(ry * 0.8) + 0.14 * np.sin(ry * 2.0)
rx_u = rx_c + 0.42
rx_l = rx_c - 0.42
from matplotlib.patches import Polygon as _Poly
ax.add_patch(_Poly(list(zip(ry, rx_u)) + list(zip(ry[::-1], rx_l[::-1])),
    fc='#4a9ac8', ec='#2a7aaa', lw=2, zorder=5, alpha=0.92))
ax.annotate('', xy=(19.5, rx_c[243]), xytext=(4.5, rx_c[56]),
    arrowprops=dict(arrowstyle='->', color='#2a7aaa', lw=2, mutation_scale=14), zorder=6)
T(ax, hj('黃河', '황하') + ' (北岸, 진군 본래 주둔지)', 18.6, MAP_Y1 - 1.0, sz=27, c='#0a3a5c', bg='#eef7fb')

T(ax, hj('敖山', '오산'), 3.4, MAP_Y0 + 6.1, sz=28, c='#3a2c10', bg='#e8dcbf')
T(ax, hj('衢地', '구지') + ' · ' + hj('鄭', '정') + '(先至而得天下衆)', 12.0, MAP_Y0 + 5.0, sz=29, c='#2a2010', bg='#e8dcc0')

# ── y 구역: 남(하단)=楚軍 총공세 개시선 / 북(상단)=晉軍 배치선(배후 황하) ──
# 황하 대역은 대략 17.3~19.1(rx_c 중심 18.2 ± 진폭0.44 ± 반폭0.42) — 이 대역과
# 겹치지 않도록 진군 라인·라벨은 16.8 이하로, 초군 라벨 스택은 지도 하단(8.2)
# 위로 충분한 여백을 두고 배치한다.
Y_CHU_LINE = MAP_Y0 + 3.6      # 초군 전개선 = 11.8
Y_JIN_LINE = MAP_Y0 + 6.8      # 진군 전개선(배후 황하까지 여유 확보) = 15.0
Y_RIVER_PANIC = MAP_Y1 - 1.7   # 혼란 도하 지점(황하 남안) = 17.5

# ── 楚軍: 중군(沈尹)·좌군(子重)·우군(子反), 楚莊王·孫叔敖 총지휘 ──
n_chu_c = 130
chu_c_x = 12.0 + np.random.uniform(-2.6, 2.6, n_chu_c)
chu_c_y = Y_CHU_LINE + np.random.uniform(-0.9, 0.9, n_chu_c)
troops(ax, chu_c_x, chu_c_y, '#ee3333', ms=120, alpha=0.82)
T(ax, '초 중군(沈尹)', 12.0, Y_CHU_LINE - 1.5, sz=28, c='#7a0000', bg='#fbeaea')
pe_em(ax, '⚔️', 12.0, Y_CHU_LINE - 2.2, zoom=0.20, z=17)
T(ax, '楚莊王·孫叔敖(친정·총지휘)', 12.0, Y_CHU_LINE - 2.9, sz=25, c='#7a0000', bg='#fbeaea')

n_chu_l = 65
chu_l_x = 4.3 + np.random.uniform(-1.6, 1.6, n_chu_l)
chu_l_y = Y_CHU_LINE + np.random.uniform(-0.9, 0.9, n_chu_l)
troops(ax, chu_l_x, chu_l_y, '#ee3333', ms=110, alpha=0.8)
T(ax, '초 좌군(子重)', 4.3, Y_CHU_LINE - 1.5, sz=27, c='#7a0000', bg='#fbeaea')

n_chu_r = 65
chu_r_x = 19.7 + np.random.uniform(-1.6, 1.6, n_chu_r)
chu_r_y = Y_CHU_LINE + np.random.uniform(-0.9, 0.9, n_chu_r)
troops(ax, chu_r_x, chu_r_y, '#ee3333', ms=110, alpha=0.8)
T(ax, '초 우군(子反)', 19.7, Y_CHU_LINE - 1.5, sz=27, c='#7a0000', bg='#fbeaea')

# 초군 총공세(3로 동시 진격, 伍參의 진언으로 결전 결심)
arr(ax, 12.0, Y_CHU_LINE + 1.2, 12.0, Y_JIN_LINE - 1.0, '#ee2222', rad=0.0, hw=4.4, tw=2.4, z=11)
arr(ax, 4.6, Y_CHU_LINE + 1.2, 6.6, Y_JIN_LINE - 1.0, '#ee2222', rad=0.1, hw=3.4, tw=1.8, z=11)
arr(ax, 19.4, Y_CHU_LINE + 1.2, 17.6, Y_JIN_LINE - 1.0, '#ee2222', rad=-0.1, hw=3.4, tw=1.8, z=11)

# ── 晉軍: 중군(荀林父/先縠)·상군(士會, 敖山 방비로 상대적으로 온전)·하군(趙朔/欒書) ──
n_jin_c = 110
jin_c_x = 12.0 + np.random.uniform(-2.2, 2.2, n_jin_c)
jin_c_y = Y_JIN_LINE + np.random.uniform(-0.7, 0.7, n_jin_c)
troops(ax, jin_c_x, jin_c_y, '#2255dd', ms=120, alpha=0.82)
T(ax, '진 중군(荀林父/先縠)', 12.0, Y_JIN_LINE + 1.3, sz=26, c='#0a1a6b', bg='#e8ecfb')
pe_em(ax, '🛡️', 12.0, Y_JIN_LINE + 1.9, zoom=0.20, z=17)

n_jin_x = 55
jin_x_x = 4.2 + np.random.uniform(-1.6, 1.6, n_jin_x)
jin_x_y = Y_JIN_LINE - 0.4 + np.random.uniform(-0.7, 0.7, n_jin_x)
troops(ax, jin_x_x, jin_x_y, '#3a6fd8', ms=110, alpha=0.65)
T(ax, '진 상군(士會, 敖山 방비)', 4.2, Y_JIN_LINE + 1.3, sz=25, c='#0a1a6b', bg='#e8ecfb')
# 상군은 사전에 방비를 해두어 상대적으로 질서 있게 철수(궤주가 아닌 정연한 후퇴) — 敖山 방면으로
arr(ax, 3.8, Y_JIN_LINE - 0.8, 3.3, MAP_Y0 + 7.0, '#3a6fd8', rad=0.0, hw=2.4, tw=1.2, z=10)

n_jin_h = 70
jin_h_x = 19.6 + np.random.uniform(-1.8, 1.8, n_jin_h)
jin_h_y = Y_JIN_LINE + np.random.uniform(-0.7, 0.7, n_jin_h)
troops(ax, jin_h_x, jin_h_y, '#2255dd', ms=115, alpha=0.8)
T(ax, '진 하군(趙朔/欒書)', 19.6, Y_JIN_LINE + 1.3, sz=26, c='#0a1a6b', bg='#e8ecfb')

# 선곡(先縠)의 개전 전 독단적 도하(회색 점선, 명령 없이 단독으로 강행) — 황하(북안)에서
# 남안(전장)으로 건너온 경로. 화살표 시작점은 강 대역(약 17.3~19.1) 안에서 출발.
arr(ax, 13.5, MAP_Y1 - 0.9, 12.8, Y_JIN_LINE + 0.5, '#888888', rad=0.15, hw=2.2, tw=1.0, dash=True, z=7, alpha=0.55)
T(ax, '先縠 독단 도하(개전 전)', 16.4, MAP_Y1 - 2.7, sz=25, c='#3a3a3a', bg='#eeeeee')

# 진 중군·하군 궤주 — 전방(초군) 반대 방향인 북쪽 황하를 향해 혼란 도주(점선)
arr(ax, 11.6, Y_JIN_LINE + 1.4, 11.0, Y_RIVER_PANIC - 0.3, '#2255dd', rad=0.08, dash=True, hw=3.0, tw=1.5, z=9)
arr(ax, 19.2, Y_JIN_LINE + 1.4, 18.0, Y_RIVER_PANIC - 0.3, '#2255dd', rad=-0.08, dash=True, hw=3.0, tw=1.5, z=9)

pe_em(ax, '🔥', 12.3, Y_RIVER_PANIC, zoom=0.16, z=18)
marker_point(ax, 12.3, Y_RIVER_PANIC, ms=30, color='#ff2200')
T(ax, "혼란 도하 · 舟中之指可掬", 8.0, Y_RIVER_PANIC + 0.1, sz=27, c='#7a0000', bg='#fff0e8')

draw_title(ax, ['필(邲) 전투 전략도  ', '邲之戰', '  (BCE 597)'])

legend_items = [
    ('arr', '#ee2222', '초군 3로 총공세'),
    ('dash', '#2255dd', '진 중·하군 궤주(도하)'),
    ('arr', '#3a6fd8', '진 상군(士會) 질서 철수'),
    ('dash', '#888888', '先縠 독단 도하(개전전)'),
    ('emoji', '⚔️', '楚莊王(친정)'),
    ('emoji', '🛡️', '荀林父(중군장)'),
    ('emoji', '🔥', '혼란 도하 지점'),
    ('dot_r', '#ee3333', '초나라 보병'),
    ('dot_b', '#2255dd', '진나라 보병'),
    ('dot', '#ffaa00', '패주·참화 지점'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items, title=hj('衢地', '구지') + ' · ' + hj('鄭', '정'))

패군_rows = [
    ('전력+배치+보급', '진군 약 5만(전통 추정치, 정사 확정 아님). 신임 중군장 荀林父가 삼군 통솔 미숙, 先縠 항명으로 지휘 붕괴.'),
    ('지피(知彼)', '정의 항복은 파악했으나 楚의 결전 의지(伍參의 진언)를 예측 못함 — 忿速可侮(先縠의 독단 도하가 전형).'),
    ('지기(知己)', '荀林父 자신의 통솔력 부족과 삼군 불화를 방치 — 결단하지 못한 채 방비도 없이 무너짐(愛民可煩에 가까운 우유부단).'),
    ('지지(知地)', "邲은 通形이나 배후에 황하를 두어 퇴로가 막힘 — 虛實의 虛가 완전히 노출, 奇正의 奇조차 쓰지 못하고 붕괴."),
    ('결과', '중군·하군 궤멸, 황하 도하 중 참사(舟中之指可掬) — 구지(鄭) 선점 실패로 초의 패업을 열어줌.'),
]
draw_analysis_box(ax, renderer, LX, '패군', '荀林父', 패군_rows, '#1a3a7a')

승군_rows = [
    ('전력+배치+보급', '초군 병력 규모는 사료상 불명(통설 약 30만은 과장 가능성). 孫叔敖가 왕명을 받아 삼군을 실전 지휘.'),
    ('지피(知彼)', '伍參이 荀林父의 미숙·先縠의 조급·삼군 불화를 정확히 짚어 결전을 진언 — 지피의 모범.'),
    ('지기(知己)', '楚莊王이 친정의 상징성과 군 사기를 정확히 계산해 결전을 결단(廉潔可辱의 위험을 정확한 판단으로 상쇄).'),
    ('지지(知地)', '邲의 通形에서 유리한 위치를 선점(先居高陽), 진군이 강을 등지게 만들어 虛實의 허를 극대화(奇正 병용의 총공세).'),
    ('결과', '진군 완파, 楚莊王 패업 확정 — "先至而得天下衆" 그대로 정(鄭)이라는 구지를 먼저 얻어 중원의 향배를 결정.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '楚莊王', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bi_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
