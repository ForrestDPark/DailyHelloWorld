#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""관도대전(官渡之戰, 200년) 전략지형도 — Claude판

先奪其所愛 실증(동양): 원소의 우세는 머릿수만이 아니라 지구전을 감당할 군량
우위에서 나왔고, 그 우위 전체를 담보한 것이 후방 보급기지 오소(烏巢)였다.
정면에서는 열세인 조조가 정공으로 원소를 꺾을 수 없었으나, 투항한 허유의
첩보로 오소의 위치·허술을 특정해 친솔 야습으로 군량을 전소시키자, 잘 조직된
대군이 싸우기도 전에 스스로 무너졌다(장합·고람 투항) — 적이 가장 아끼던 것을
빼앗아 대군을 휘둘리게 만든 「先奪其所愛, 則聽矣」의 교과서.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *
from matplotlib.patches import Polygon as _Poly

np.random.seed(200)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 황하 남안의 개활 평원(支形/通形), 완만한 기복 ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 48.0
elev += 8 * np.sin(LON * 6.0) * np.cos(LAT * 4.0)          # 완만한 기복
elev -= 20 * np.exp(-((LAT - 0.93) ** 2) / 0.010)          # 북쪽 황하 저지
terrain_colors = [
    (0.0, '#c8b98a'),
    (0.35, '#bcb072'),
    (0.62, '#a6a862'),
    (0.82, '#8f9a52'),
    (1.0, '#6f7d3e'),
]
draw_terrain(ax, elev, extent, terrain_colors)

# ── 황하(북쪽, 동서로 흐름) ──
gx = np.linspace(0, 24, 300)
gy_c = (MAP_Y1 - 0.7) + 0.18 * np.sin(gx * 0.5)
gy_l, gy_u = gy_c - 0.42, gy_c + 0.42
ax.add_patch(_Poly(list(zip(gx, gy_l)) + list(zip(gx[::-1], gy_u[::-1])),
    fc='#c9a24a', ec='#9c7a2e', lw=2, zorder=5, alpha=0.92))
T(ax, hj('黃河', '황하'), 1.4, MAP_Y1 - 0.7, sz=24, c='#5a3f0a', bg='#f6ecd6', ha='left')
T(ax, hj('白馬·延津', '백마·연진') + ' 나루\n서전(안량·문추 전사)',
  5.3, MAP_Y1 - 1.55, sz=19, c='#5a3f0a', bg='#f6ecd6')

Y_RIVER = MAP_Y1 - 0.7
Y_YUAN = MAP_Y1 - 3.2       # 원소 대영(강 남안)
Y_CAO = MAP_Y0 + 3.4        # 조조 관도 방어선
Y_XU = MAP_Y0 + 0.7         # 허(許昌) 방향

# ── 원소 대군(파랑, 강 남안에 대영) ──
n_yuan = 150
yx = 9.5 + np.random.uniform(-4.2, 4.2, n_yuan)
yy = Y_YUAN + np.random.uniform(-1.5, 1.5, n_yuan)
troops(ax, yx, yy, '#2255dd', ms=95, alpha=0.8)
pe_em(ax, '⚔️', 9.5, Y_YUAN + 2.0, zoom=0.20, z=17)
T(ax, '원소(袁紹) 대군 — 약 10만(논쟁적), 대영', 9.5, Y_YUAN + 2.7, sz=21, c='#0a1a6b', bg='#e8ecfb')

# ── 오소(북동, 원소 후방의 군량고) ──
WX, WY = 19.6, Y_YUAN + 1.0
marker_point(ax, WX, WY, ms=30, color='#ffaa00')
pe_em(ax, '🔥', WX, WY, zoom=0.15, z=18)
T(ax, hj('烏巢', '오소') + ' — 원소 군량고', WX, WY + 1.15, sz=21, c='#7a0000', bg='#fff0e8')
T(ax, '대영서 북동 40리 · 순우경 1만여', WX, WY - 1.15, sz=18, c='#2a2010', bg='#fff2d8')

# ── 조조 관도 방어선(빨강, 축성 농성) ──
n_cao = 90
cx_ = 9.5 + np.random.uniform(-4.0, 4.0, n_cao)
cy_ = Y_CAO + np.random.uniform(-0.9, 0.9, n_cao)
troops(ax, cx_, cy_, '#ee3333', ms=95, alpha=0.85)
# 축성(망루·참호) 표시
for wx in np.linspace(5.8, 13.2, 6):
    ax.plot([wx, wx], [Y_CAO + 1.0, Y_CAO + 1.5], color='#7a3a10', lw=3, zorder=7)
ax.plot([5.5, 13.5], [Y_CAO + 1.0, Y_CAO + 1.0], color='#7a3a10', lw=2, ls=(0, (4, 3)), zorder=7)
pe_em(ax, '⚔️', 9.5, Y_CAO - 1.4, zoom=0.20, z=17)
T(ax, '조조(曹操) — ' + hj('官渡', '관도') + ' 축성 방어선(망루·참호)', 9.5, Y_CAO - 2.1, sz=21, c='#7a0000', bg='#fbeaea')
T(ax, hj('支形', '지형') + ' — 서로 나가기를 꺼린 반년 교착', 3.0, Y_CAO + 2.6, sz=19, c='#2a2010', bg='#ece4c0', ha='left')

# ── 허(許昌), 조조 근거지(남) ──
pe_em(ax, '🛡️', 9.5, Y_XU, zoom=0.18, z=17)
T(ax, hj('許昌', '허창') + ' — 조조 근거지(후방)', 11.0, Y_XU, sz=19, c='#7a0000', bg='#fbeaea', ha='left')

# ── 화살표 ──
# 원소 진격(남하, 파랑)
arr(ax, 7.5, Y_YUAN - 1.7, 7.5, Y_CAO + 1.9, '#2255dd', rad=0.0, hw=3.6, tw=1.9, z=10)
arr(ax, 12.0, Y_YUAN - 1.7, 12.0, Y_CAO + 1.9, '#2255dd', rad=0.0, hw=3.6, tw=1.9, z=10)
T(ax, '원소 대군 남하 압박', 14.6, (Y_YUAN + Y_CAO) / 2, sz=19, c='#0a1a6b', bg='#e8ecfb', ha='left')

# 조조 오소 야습(친솔 정예 5천, 적 후방 우회 → 화공)
arr(ax, 13.2, Y_CAO + 1.2, WX - 0.6, WY - 0.4, '#ff6600', rad=-0.32, hw=4.4, tw=2.4, z=13)
T(ax, '조조 친솔 야습(5천) — 적 후방 우회, ' + hj('先奪其所愛', '선탈기소애'),
  16.2, Y_CAO + 0.2, sz=18, c='#7a0000', bg='#fff0e8')

# 허유 투항(첩보 제공)
arr(ax, 15.5, Y_YUAN - 0.3, 12.8, Y_CAO + 1.6, '#8a5a00', rad=0.2, dash=True, hw=2.4, tw=1.2, z=9)
T(ax, '허유 투항 — 오소 밀고', 17.4, Y_YUAN - 0.6, sz=18, c='#6a4a00', bg='#f3ecd8', ha='left')

# 오소 방화 후 원소군 붕괴·패주(북으로, 황하 건너)
arr(ax, 6.5, Y_YUAN + 0.5, 4.0, Y_RIVER - 0.6, '#2255dd', rad=0.15, dash=True, hw=2.6, tw=1.3, z=9)
arr(ax, 13.0, Y_YUAN + 0.5, 15.0, Y_RIVER - 0.6, '#2255dd', rad=-0.15, dash=True, hw=2.6, tw=1.3, z=9)
T(ax, '군량 전소 → 전군 붕괴·황하 이북 패주', 9.5, Y_YUAN - 3.0, sz=18, c='#0a1a6b', bg='#e8ecfb')

# 장합·고람 투항(방향 전환)
T(ax, '장합·고람 진영 불사르고 투항(崩)', 4.2, Y_CAO - 0.3, sz=18, c='#5a1a1a', bg='#f6ecec', ha='left')

draw_title(ax, ['관도대전 전략도  ', hj('官渡之戰', '관도지전'), '  (200)'])

legend_items = [
    ('arr', '#ff6600', '조조 야습(화공)'),
    ('arr', '#2255dd', '원소 남하'),
    ('dash', '#2255dd', '원소 붕괴·패주'),
    ('dash', '#8a5a00', '허유 투항·밀고'),
    ('emoji', '⚔️', '지휘관'),
    ('emoji', '🔥', '오소 방화'),
    ('dot_r', '#ee3333', '조조군'),
    ('dot_b', '#2255dd', '원소군'),
    ('dot', '#ffaa00', '요충지(오소)'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items,
                title=hj('先奪其所愛', '선탈기소애') + ' · 오소의 군량')

패군_rows = [
    ('道(지기)', '병력 우위를 과신, 저수의 신중론을 물리치고 전풍을 투옥 — 참모 파벌 상쟁으로 상하 결속 붕괴(君의 지휘 장애).'),
    ('天(지피)', '조조를 얕봄(경적). 허유의 이탈이라는 통제 불가 변수를 스스로 자초.'),
    ('地(지형)', '황하 건너 원정(重地)으로 병참선이 길어짐, 支形 교착에서 양도(오소)가 취약.'),
    ('將(장수)', '오만·우유부단 — 오소 급습에 소수만 증원, 곽도 말 좇아 본영 역공(우선순위 오판).'),
    ('法(전력배치)', '약 10만(논쟁적), 안량·문추 조기 상실. 군량을 오소에 집적(순우경 1만여).'),
    ('결과', '군량 전소→장합·고람 투항→전군 붕괴 — 崩(大吏怒而不服). 화북 상실.'),
]
draw_analysis_box(ax, renderer, LX, '패군', '원소', 패군_rows, '#1a3a7a')

승군_rows = [
    ('道(지기)', '순욱·가후 등 소수 참모와 긴밀한 결속(上下同欲), 후방 순욱의 서신이 지구전을 지지.'),
    ('天(지피)', '허유의 첩보(오소 위치·허술)를 즉시 신뢰·활용, 적의 소진 확률을 읽음.'),
    ('地(지형)', '관도에 축성 농성으로 정면(正)을 고착, 적 후방의 虛(오소)를 우회 타격.'),
    ('將(장수)', '智·勇 — 열세·군량 고갈 속 후퇴를 접고 친솔 야습(先奪其所愛)을 결단.'),
    ('法(전력배치)', '소수(1만 미만~수만, 논쟁적), 오소 습격대 정예 약 5천 친솔.'),
    ('결과', '오소 방화로 대군을 스스로 무너뜨림 — 以虞待不虞者勝·將能而君不御者勝.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '조조', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'guandu_claude_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
