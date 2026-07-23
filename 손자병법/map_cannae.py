#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""칸나에 전투(Battle of Cannae, BCE 216) 전략지형도

圍地(위지)·死地(사지) 실증 사례: 로마군(파울루스·바로)은 아우피두스강이
한쪽 측면을 막는 평원에 깊은 밀집대형으로 전개했다(隘·迂 — 들어간 곳은
좁고 나올 곳은 멀리 도는 圍地). 한니발은 중앙(갈리아·이베리아)을 완만한
초승달 모양으로 전진시킨 뒤 서서히 후퇴시켜 로마군을 안으로 끌어들이고,
양 측면의 아프리카 중보병이 안쪽으로 선회해 측면을 압박하는 동안,
하스드루발의 중기병이 로마 기병을 격파한 뒤 배후로 돌아 로마군을
완전히 에워쌌다. 병력 절대 열세(약 5만 대 8만6천)였던 카르타고군이
포위라는 지형적 함정으로 매 접점에서 수적 우위를 뒤집었다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(216)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 남쪽(하단)=아우피두스강, 나머지는 평탄한 개활지 ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 55.0
elev -= 10 * np.exp(-((LAT - 0.06) ** 2) / 0.01) * (1 + 0.08 * np.sin(LON * 6.0))   # 강변 저지
elev += 6 * np.sin(LON * 3.0) * np.exp(-((LAT - 0.5) ** 2) / 0.3)                    # 완만한 개활지 굴곡
terrain_colors = [
    (0.0, '#8a9a5c'),
    (0.35, '#a8b378'),
    (0.65, '#bcc48c'),
    (1.0, '#cfd39e'),
]
draw_terrain(ax, elev, extent, terrain_colors)

# 아우피두스강(Aufidus) — 남쪽 측면을 따라 동서로 흐름, 로마군 우익 퇴로 차단
ry = np.linspace(0, 24, 300)
rx_c = MAP_Y0 + 1.1 + 0.25 * np.sin(ry * 0.5) + 0.1 * np.sin(ry * 1.3)
rx_l, rx_r = rx_c - 0.35, rx_c + 0.35
from matplotlib.patches import Polygon as _Poly
ax.add_patch(_Poly(list(zip(ry, rx_l)) + list(zip(ry[::-1], rx_r[::-1])),
    fc='#4a9ac8', ec='#2a7aaa', lw=2, zorder=5, alpha=0.92))
ax.annotate('', xy=(18, rx_c[240]), xytext=(6, rx_c[80]),
    arrowprops=dict(arrowstyle='->', color='#2a7aaa', lw=2, mutation_scale=14), zorder=6)
T(ax, hj('Aufidus', '아우피두스강'), 3.2, MAP_Y0 + 2.0, sz=22, c='#0a3a5c', bg='#eef7fb', ha='left')

T(ax, hj('圍地', '위지') + '·' + hj('死地', '사지') + '·' + hj('隘形', '애형'),
  0.2, MAP_Y1 - 0.6, sz=25, c='#2a2010', bg='#ece4c0', ha='left')

# 바람(볼투르누스, 남동풍) — 흙먼지를 로마군 쪽으로
wind_x = np.linspace(19, 14, 5)
wind_y = np.linspace(MAP_Y0 + 6.5, MAP_Y0 + 5.3, 5)
for i in range(len(wind_x) - 1):
    ax.annotate('', xy=(wind_x[i+1], wind_y[i+1]), xytext=(wind_x[i], wind_y[i]),
        arrowprops=dict(arrowstyle='->', color='#999999', lw=2.2, alpha=0.8,
                         linestyle=(0, (3, 2))), zorder=9)
T(ax, '볼투르누스(남동풍) — 흙먼지가 로마군 시야를 가림', 16.0, MAP_Y0 + 7.2, sz=20, c='#4a4a4a', bg='#f0f0ea')

# ── y/x 배치 ──
Y_ROME = MAP_Y0 + 4.6
Y_CARTH = MAP_Y0 + 7.3

X_ROME = 11.5
X_CARTH_C = 11.5

# ── 로마군 중앙 보병(비정상적으로 깊은 밀집대형) ──
n_rome = 220
rome_x = X_ROME + np.random.uniform(-2.8, 2.8, n_rome)
rome_y = Y_ROME + np.random.uniform(-1.3, 1.3, n_rome)
troops(ax, rome_x, rome_y, '#2255dd', ms=95, alpha=0.78)
pe_em(ax, '⚔️', X_ROME, Y_ROME - 1.9, zoom=0.20, z=17)
T(ax, '로마 중앙보병(파울루스·바로)', X_ROME, Y_ROME - 2.7, sz=24, c='#0a1a6b', bg='#e8ecfb')

# 로마 우익 기병(파울루스, 강 쪽)
n_rc_r = 30
rcr_x = 17.3 + np.random.uniform(-0.8, 0.8, n_rc_r)
rcr_y = Y_ROME - 1.7 + np.random.uniform(-0.5, 0.5, n_rc_r)
troops(ax, rcr_x, rcr_y, '#3a6fd8', ms=100, alpha=0.75)
pe_em(ax, '🐎', 17.3, Y_ROME - 2.5, zoom=0.16, z=15)
T(ax, '로마 시민기병(파울루스)', 17.3, Y_ROME - 3.3, sz=21, c='#0a1a6b', bg='#e8ecfb')

# 로마 좌익 동맹기병(바로)
n_rc_l = 45
rcl_x = 5.5 + np.random.uniform(-1.0, 1.0, n_rc_l)
rcl_y = Y_ROME + 1.9 + np.random.uniform(-0.55, 0.55, n_rc_l)
troops(ax, rcl_x, rcl_y, '#3a6fd8', ms=100, alpha=0.75)
pe_em(ax, '🐎', 5.5, Y_ROME + 2.8, zoom=0.16, z=15)
T(ax, '동맹기병(바로)', 5.5, Y_ROME + 3.6, sz=22, c='#0a1a6b', bg='#e8ecfb')

# ── 카르타고 중앙(갈리아·이베리아, 초승달) ──
n_carth_c = 130
theta = np.random.uniform(0, np.pi, n_carth_c)
cc_x = X_CARTH_C + 4.2 * np.cos(theta) - 2.1
cc_y = Y_CARTH + 0.9 * np.sin(theta) + np.random.uniform(-0.3, 0.3, n_carth_c)
troops(ax, cc_x, cc_y, '#ee3333', ms=90, alpha=0.75)
pe_em(ax, '⚔️', X_CARTH_C, Y_CARTH + 1.3, zoom=0.20, z=17)
T(ax, '한니발(총지휘)·갈리아·이베리아 혼성군', X_CARTH_C, Y_CARTH + 2.1, sz=22, c='#7a0000', bg='#fbeaea')

# 아프리카 중보병(양 측면, 초승달 끝단)
n_af_l = 55
afl_x = 6.0 + np.random.uniform(-0.9, 0.9, n_af_l)
afl_y = Y_CARTH - 0.3 + np.random.uniform(-1.1, 1.1, n_af_l)
troops(ax, afl_x, afl_y, '#c22222', ms=100, alpha=0.85)
T(ax, '아프리카 중보병(좌)', 6.0, Y_CARTH - 2.0, sz=21, c='#7a0000', bg='#fbeaea')

n_af_r = 55
afr_x = 17.0 + np.random.uniform(-0.9, 0.9, n_af_r)
afr_y = Y_CARTH - 0.3 + np.random.uniform(-1.1, 1.1, n_af_r)
troops(ax, afr_x, afr_y, '#c22222', ms=100, alpha=0.85)
T(ax, '아프리카 중보병(우)', 17.0, Y_CARTH - 2.0, sz=21, c='#7a0000', bg='#fbeaea')

# 하스드루발 중기병(강 쪽, 남측)
n_hc = 35
hc_x = 19.5 + np.random.uniform(-0.8, 0.8, n_hc)
hc_y = Y_ROME - 1.9 + np.random.uniform(-0.5, 0.5, n_hc)
troops(ax, hc_x, hc_y, '#ee3333', ms=100, alpha=0.8)
pe_em(ax, '🐎', 19.5, Y_ROME - 2.7, zoom=0.16, z=15)
T(ax, '하스드루발(중기병)', 19.5, Y_ROME - 3.5, sz=20, c='#7a0000', bg='#fbeaea')

# 누미디아 경기병(북측)
n_nc = 35
nc_x = 3.2 + np.random.uniform(-0.8, 0.8, n_nc)
nc_y = Y_ROME + 2.0 + np.random.uniform(-0.5, 0.5, n_nc)
troops(ax, nc_x, nc_y, '#ee3333', ms=95, alpha=0.8)
pe_em(ax, '🐎', 3.2, Y_ROME + 2.9, zoom=0.16, z=15)
T(ax, '누미디아 경기병', 3.2, Y_ROME + 3.7, sz=20, c='#7a0000', bg='#fbeaea')

# ── 전개 순서 화살표 ──
# 1) 중앙 유인 후퇴 (카르타고 중앙이 로마 압박에 밀리는 척 후퇴)
arr(ax, X_CARTH_C, Y_CARTH - 0.2, X_CARTH_C, Y_ROME + 1.6, '#ee2222', rad=0.0, dash=True, hw=3.0, tw=1.6, z=10)
T(ax, '중앙 통제 후퇴(유인)', X_CARTH_C, Y_CARTH + 0.55, sz=19, c='#7a0000', bg='#fff0e8')

# 2) 하스드루발 기병 → 로마 우익기병 격파
arr(ax, 19.5, Y_ROME - 1.4, 17.6, Y_ROME - 1.7, '#ee2222', rad=-0.1, hw=3.8, tw=2.0, z=12)

# 3) 하스드루발 기병 우회 → 로마 좌익 동맹기병 배후 공격
arr(ax, 16.5, Y_ROME - 0.6, 5.8, Y_ROME + 1.3, '#ee2222', rad=0.35, hw=3.6, tw=1.9, z=12)
T(ax, '하스드루발 우회 기동(배후 타격)', 11.0, Y_ROME - 3.6, sz=20, c='#7a0000', bg='#fff0e8')

# 4) 아프리카 보병 양 측면 → 로마 중앙 측면으로 선회
arr(ax, 6.0, Y_CARTH - 1.2, 9.0, Y_ROME + 0.5, '#ee2222', rad=-0.15, hw=3.4, tw=1.8, z=12)
arr(ax, 17.0, Y_CARTH - 1.2, 14.0, Y_ROME + 0.5, '#ee2222', rad=0.15, hw=3.4, tw=1.8, z=12)

# 5) 로마군 압축·궤멸 지점
pe_em(ax, '🔥', X_ROME, Y_ROME, zoom=0.16, z=18)
marker_point(ax, X_ROME, Y_ROME, ms=30, color='#ff2200')
T(ax, '완전포위·대학살 지점', X_ROME, Y_ROME + 0.9, sz=21, c='#7a0000', bg='#fff0e8')

# 6) 로마군 붕괴(압축된 채 흩어짐)
arr(ax, X_ROME - 1.5, Y_ROME - 0.8, X_ROME - 3.0, MAP_Y0 + 3.0, '#2255dd', rad=0.1, dash=True, hw=2.4, tw=1.2, z=9)
arr(ax, X_ROME + 1.5, Y_ROME - 0.8, X_ROME + 3.0, MAP_Y0 + 3.0, '#2255dd', rad=-0.1, dash=True, hw=2.4, tw=1.2, z=9)

draw_title(ax, ['칸나에 전투 전략도 ', 'Cannae', ' (BCE 216)'])

legend_items = [
    ('arr', '#ee2222', '카르타고 공격(포위)'),
    ('dash', '#ee2222', '중앙 후퇴(유인)'),
    ('dash', '#2255dd', '로마군 붕괴'),
    ('dash', '#999999', '남동풍(먼지)'),
    ('emoji', '⚔️', '지휘관'),
    ('emoji', '🐎', '기병'),
    ('emoji', '🔥', '궤멸 지점'),
    ('dot_r', '#ee3333', '카르타고군'),
    ('dot_b', '#2255dd', '로마군'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items, title=hj('圍地', '위지') + '·' + hj('死地', '사지'))

패군_rows = [
    ('道(지기)', '지휘권 매일 교대(파울루스·바로), 병력우위 믿고 깊은 밀집대형.'),
    ('天(지피)', '남동풍 흙먼지+정치적 압박 속 바로가 결전 강행.'),
    ('地(지형)', '아우피두스강이 측면을 막아 좁아지는 함정(圍地·隘形).'),
    ('將', '바로는 勇 과다·智 부족(忿速可侮), 파울루스 경고 묵살.'),
    ('法(전력배치)', '보병 약 7만+기병 약 6,400, 이례적으로 깊은 대형.'),
    ('결과', '이중포위 속 전멸 — 北(배): 적정 오판, 정예 선봉 부재.'),
]
draw_analysis_box(ax, renderer, LX, '패군', '파울루스·바로', 패군_rows, '#1a3a7a')

승군_rows = [
    ('道(지기)', '다민족 혼성군을 개인 신뢰로 결속, 중앙 통제후퇴 유지.'),
    ('天(지피)', '로마 정치적 압박(바로의 조급함)을 외부 기회로 활용.'),
    ('地(지형)', '강이 퇴로를 막는 평원을 직접 전장으로 선택(隘形 선점).'),
    ('將', '智·嚴 뚜렷, 다민족 지휘관에 정확한 타이밍 부여.'),
    ('法(전력배치)', '약 5만(보병 4만+기병 1만), 초승달 진형+양익 포위.'),
    ('결과', '로마군 5~7만 전사 — 以虞待不虞者勝: 정교한 계책으로 무방비 적 타격.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '한니발', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cannae_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
