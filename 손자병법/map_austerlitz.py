#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""아우스터리츠 전투(Battle of Austerlitz, 1805.12.2) 전략지형도

前後不相及·衆寡不相恃 실증 사례: 나폴레옹은 일부러 약해 보이는 모습을 연출해
연합군(러시아·오스트리아)이 남익으로 무리하게 병력을 이동시키도록 유인했다.
그 결과 중앙의 프라첸 고지(Pratzen Heights)가 비었고, 술트 군단이 새벽 안개를
틈타 이곳을 급습해 연합군을 남북 두 동강으로 절단했다 — 절단된 남익은
사트샨(Satschan) 연못 방면으로 몰려 궤멸했다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(1805)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 서쪽=골드바흐 시내·저지, 중앙=프라첸 고지(남북 능선), 남쪽=사트샨·메니츠 연못 ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 50.0
elev += 55 * np.exp(-((LON - 0.58) ** 2) / 0.010)                                    # 프라첸 고지(남북 능선)
elev -= 18 * np.exp(-((LON - 0.32) ** 2) / 0.010)                                    # 골드바흐 시내 저지
elev -= 26 * np.exp(-(((LON - 0.30) ** 2) / 0.03 + ((LAT - 0.08) ** 2) / 0.02))      # 사트샨·메니츠 연못(남쪽)
terrain_colors = [
    (0.0, '#7a94a0'),
    (0.30, '#8f9a68'),
    (0.55, '#a8ac72'),
    (0.80, '#8a9058'),
    (1.0, '#6a7048'),
]
draw_terrain(ax, elev, extent, terrain_colors)

T(ax, hj('中央突破', '중앙돌파') + '·' + hj('分斷', '분단'),
  0.2, MAP_Y1 - 0.6, sz=25, c='#2a2010', bg='#ece4c0', ha='left')
T(ax, hj('普拉岑高地', '프라첸 고지') + ' (Pratzen Heights)', 17.5, MAP_Y1 - 0.6, sz=21, c='#1e2a12', bg='#dfe6cc')

# 골드바흐 시내(서쪽, 남북으로 흐름)
gy = np.linspace(2.0, 22.0, 260)
gx = 7.5 + 0.35 * np.sin((gy - 2.0) * 0.3)
from matplotlib.patches import Polygon as _Poly
ax.add_patch(_Poly(list(zip(gy, gx - 0.28)) + list(zip(gy[::-1], gx[::-1] + 0.28)),
    fc='#c9a24a', ec='#9c7a2e', lw=1.6, zorder=5, alpha=0.85))
T(ax, hj('戈爾德巴赫', '골드바흐') + ' 시내', 2.0, MAP_Y0 + 6.5, sz=19, c='#5a3f0a', bg='#f6ecd6', ha='left')

# 사트샨·메니츠 연못(남쪽 저지, 얼어붙은 습지)
pond = _Poly([(1.5, MAP_Y0 + 0.3), (10.5, MAP_Y0 + 0.3), (9.0, MAP_Y0 + 2.6), (2.5, MAP_Y0 + 2.6)],
             fc='#a9c8dc', ec='#6a97ae', lw=1.8, zorder=4, alpha=0.85)
ax.add_patch(pond)
T(ax, hj('薩恰恩沼澤', '사트샨·메니츠 연못(결빙)'), 6.0, MAP_Y0 + 1.3, sz=18, c='#0a2a3a', bg='#eaf3f7')

X_CENTER = 14.0
Y_PRATZEN_MID = MAP_Y0 + 6.5    # 프라첸 고지 중앙(원래 연합군 4종대)
Y_NORTH = MAP_Y1 - 3.0          # 북익(바그라티온 vs 란·뮈라)
Y_SOUTH = MAP_Y0 + 2.2          # 남익(다부 vs 연합군 1~3종대)

# ── 연합군 남익(1~3종대, 청색=패군) — 골드바흐 남쪽으로 이동 중 ──
n_s = 120
s_theta = np.random.uniform(0, 2 * np.pi, n_s)
s_r = np.random.uniform(0.6, 2.4, n_s)
s_x = 8.0 + s_r * np.cos(s_theta)
s_y = Y_SOUTH + s_r * 0.5 * np.sin(s_theta)
troops(ax, s_x, s_y, '#2255dd', ms=85, alpha=0.78)
pe_em(ax, '⚔️', 10.5, Y_SOUTH + 1.8, zoom=0.18, z=17)
T(ax, '연합군 1~3종대(도흐투로프·랑주롱·프르질레프스키)', 10.5, Y_SOUTH + 2.6, sz=16, c='#0a1a6b', bg='#e8ecfb')

# ── 프랑스 다부 군단(남쪽, 적색=승군) — 남익 저지 ──
n_dv = 40
dv_x = 6.0 + np.random.uniform(-1.2, 1.2, n_dv)
dv_y = Y_SOUTH - 1.0 + np.random.uniform(-0.6, 0.6, n_dv)
troops(ax, dv_x, dv_y, '#ee3333', ms=90, alpha=0.85)
pe_em(ax, '⚔️', 6.0, Y_SOUTH - 2.3, zoom=0.16, z=17)
T(ax, '다부(3군단) — 강행군 도착, 남익 저지', 4.0, Y_SOUTH + 1.6, sz=17, c='#7a0000', bg='#fbeaea', ha='left')

# ── 프라첸 고지: 원래 연합군 4종대 있었으나 남하로 약화(옅은 표시) ──
n_p = 55
p_theta = np.random.uniform(0, 2 * np.pi, n_p)
p_r = np.random.uniform(0.4, 1.8, n_p)
p_x = X_CENTER + p_r * np.cos(p_theta) * 0.6
p_y = Y_PRATZEN_MID + p_r * np.sin(p_theta)
troops(ax, p_x, p_y, '#6a86cc', ms=60, alpha=0.35)
T(ax, '4종대 잔류(약화, 콜로바트·근위대)', X_CENTER - 1.5, Y_PRATZEN_MID + 0.5, sz=16, c='#334477', bg='#eef1fb')

# ── 프랑스 술트 군단(중앙 돌파 주력, 적색) ──
n_so = 110
so_x = X_CENTER - 3.5 + np.random.uniform(-1.3, 1.3, n_so)
so_y = MAP_Y0 + 3.5 + np.random.uniform(-1.0, 1.0, n_so)
troops(ax, so_x, so_y, '#ee3333', ms=95, alpha=0.85)
pe_em(ax, '⚔️', X_CENTER - 3.5, MAP_Y0 + 5.3, zoom=0.20, z=17)
T(ax, '술트(4군단) — 안개 속 돌파 주력', X_CENTER - 3.5, MAP_Y0 + 6.1, sz=21, c='#7a0000', bg='#fbeaea')

# ── 연합군 북익(바그라티온, 청색) ──
n_bg = 70
bg_x = X_CENTER + 2.5 + np.random.uniform(-1.5, 1.5, n_bg)
bg_y = Y_NORTH + np.random.uniform(-0.8, 0.8, n_bg)
troops(ax, bg_x, bg_y, '#2255dd', ms=90, alpha=0.8)
pe_em(ax, '⚔️', X_CENTER + 2.5, Y_NORTH + 1.2, zoom=0.18, z=17)
T(ax, '바그라티온(북익)', X_CENTER + 1.0, Y_NORTH - 2.4, sz=19, c='#0a1a6b', bg='#e8ecfb')

# ── 프랑스 란·뮈라(북익 견제, 적색) ──
n_lm = 60
lm_x = X_CENTER + 6.5 + np.random.uniform(-1.3, 1.3, n_lm)
lm_y = Y_NORTH - 0.5 + np.random.uniform(-0.9, 0.9, n_lm)
troops(ax, lm_x, lm_y, '#ee3333', ms=85, alpha=0.8)
pe_em(ax, '🐎', X_CENTER + 6.5, Y_NORTH + 1.2, zoom=0.18, z=17)
T(ax, '란·뮈라(좌익, 기병예비)', X_CENTER + 6.5, Y_NORTH - 2.1, sz=18, c='#7a0000', bg='#fbeaea')

# ── 화살표 ──
# 연합군 남하(중앙 약화)
arr(ax, X_CENTER, Y_PRATZEN_MID - 1.5, 9.5, Y_SOUTH + 1.5, '#2255dd', rad=-0.15, dash=True, hw=3.0, tw=1.6, z=9)
T(ax, '연합군, 중앙 비우고 남익 증원 이동', X_CENTER - 1.0, Y_PRATZEN_MID - 3.2, sz=17, c='#0a1a6b', bg='#e8ecfb')

# 술트 → 프라첸 고지 돌파
arr(ax, X_CENTER - 2.5, MAP_Y0 + 5.0, X_CENTER, Y_PRATZEN_MID - 0.5, '#cc2222', rad=0.1, hw=4.2, tw=2.2, z=13)
pe_em(ax, '🚫', X_CENTER, Y_PRATZEN_MID + 0.3, zoom=0.16, z=18)
T(ax, '안개 걷히는 순간 고지 급습·점령', X_CENTER - 1.5, Y_PRATZEN_MID + 2.4, sz=18, c='#7a0000', bg='#fff0e8')

# 고지 점령 후 남북 분단(붉은 화살표 두 갈래)
arr(ax, X_CENTER, Y_PRATZEN_MID, X_CENTER + 2.0, Y_NORTH - 1.0, '#ee2222', rad=0.15, hw=3.2, tw=1.7, z=11)
arr(ax, X_CENTER, Y_PRATZEN_MID, 9.5, Y_SOUTH + 0.5, '#ee2222', rad=-0.15, hw=3.2, tw=1.7, z=11)
T(ax, '연합군 남·북 절단', X_CENTER + 4.3, Y_PRATZEN_MID - 1.6, sz=18, c='#7a0000', bg='#fff0e8')

# 남익 패주 → 사트샨 연못
arr(ax, 8.0, Y_SOUTH - 0.3, 5.5, MAP_Y0 + 1.6, '#2255dd', rad=0.1, dash=True, hw=2.6, tw=1.3, z=9)
T(ax, '연합군 남익, 결빙된 연못으로 궤주', 7.0, MAP_Y0 + 0.6, sz=16, c='#0a1a6b', bg='#e8ecfb')

draw_title(ax, ['아우스터리츠 전투 전략도 ', 'Austerlitz', ' (1805)'])

legend_items = [
    ('arr', '#cc2222', '프랑스군 돌파·분단'),
    ('dash', '#2255dd', '연합군 남하·패주'),
    ('emoji', '⚔️', '지휘관'),
    ('emoji', '🐎', '기병'),
    ('emoji', '🚫', '고지 급습 지점'),
    ('dot_r', '#ee3333', '프랑스군'),
    ('dot_b', '#2255dd', '연합군(러시아·오스트리아)'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items, title=hj('中央突破', '중앙돌파'))

패군_rows = [
    ('道(지기)', '쿠투조프의 신중론을 알렉산드르 1세가 묵살, 바이로터안 강행 — 지휘부 내부부터 균열.'),
    ('天(지피)', '나폴레옹의 약체 연출(기만)에 그대로 걸려듦.'),
    ('地(지형)', '프라첸 고지를 방치하고 남익으로 무리하게 병력을 이동, 중앙이 얇아짐.'),
    ('將', '智(정교한 계획)는 있었으나 임기응변 부족 — 忿速可侮형 경직성.'),
    ('法(전력배치)', '5개 종대, 총 약 7만3천~8만9천.'),
    ('결과', '남북 절단·궤멸 — 崩(부장급 불복·독단, 쿠투조프 판단 묵살).'),
]
draw_analysis_box(ax, renderer, LX, '패군', '바이로터/알렉산드르 1세', 패군_rows, '#1a3a7a')

승군_rows = [
    ('道(지기)', '전야 병사들의 자발적 횃불 행진 — 결속 최고조.'),
    ('天(지피)', '연합군의 조급함을 정확히 읽고 기만으로 유인.'),
    ('地(지형)', '프라첸 고지의 감제 가치를 정확히 읽고 안개 타이밍에 급습.'),
    ('將', '智·勇·嚴이 고루 뛰어남, 특히 타이밍 계산의 智가 핵심.'),
    ('法(전력배치)', '다부·술트·베르나도트·란 등 병력 약 6만5천~7만5천.'),
    ('결과', '연합군 완파 — 知可以戰與不可以戰者勝·將能而君不御者勝.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '나폴레옹', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'austerlitz_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
