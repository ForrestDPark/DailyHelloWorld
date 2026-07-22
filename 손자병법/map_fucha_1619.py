#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""부차(富車)전투 · 심하(深河)전투(1619, 사르후 전투 일환) 전략지형도

重地(중지)·圮地(비지) 실증 사례: 명 동로군(유정)과 조선원정군(강홍립·
김경서·김응하)은 이미 만주 산림지대 깊숙이 들어와(重地) 등 뒤로 여러
성채를 지나온 채, 아부달리·부차 일대의 험준한 산림 협곡(險形, 圮地)을
지나야 했다. 후방 보급 지연으로 조선군이 유정의 본대와 분리된 채 뒤처진
사이, 누르하치는 "任爾幾路來, 我只一路去"(네가 몇 갈래로 오든 나는 한
길로 간다) 원칙으로 병력을 집중시켜 아부달리에서 유정을 먼저 격파하고,
그 여세로 부차의 조선군을 덮쳤다 — 마침 역풍이 조선군 조총·화포의
연기를 되돌려 시야를 가리는 순간, 후금 기병이 돌파했다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(1619)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 만주 산림·구릉 지대, 북동(우상단)=후금 본거지 방면 산악,
#    남서(좌하단)=명·조선 원정군 진입로. 심하(深河)가 남북으로 관통 ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 70.0
elev += 48 * np.exp(-(((LON - 0.85) ** 2) / 0.05 + ((LAT - 0.78) ** 2) / 0.05))   # 동북 산악(후금 방면)
elev += 30 * np.exp(-(((LON - 0.68) ** 2) / 0.02 + ((LAT - 0.55) ** 2) / 0.02))   # 아부달리 협곡 인근 구릉
elev -= 14 * np.exp(-(((LON - 0.2) ** 2) / 0.05 + ((LAT - 0.2) ** 2) / 0.05))     # 서남 저지(진입로)
terrain_colors = [
    (0.0, '#7a8a52'),
    (0.3, '#8f9a5e'),
    (0.55, '#6f7f48'),
    (0.8, '#4f6034'),
    (1.0, '#334322'),
]
draw_terrain(ax, elev, extent, terrain_colors)

# 심하(深河) - 화면을 남북으로 가로지르는 강, 조선군 진영 서쪽을 지남
np.random.seed(1619)
ry = np.linspace(MAP_Y0, MAP_Y1, 300)
rx_c = 4.3 + 0.35 * np.sin(ry * 0.85) + 0.15 * np.sin(ry * 2.0)
rx_l, rx_r = rx_c - 0.26, rx_c + 0.26
from matplotlib.patches import Polygon as _Poly
ax.add_patch(_Poly(list(zip(rx_l, ry)) + list(zip(rx_r[::-1], ry[::-1])),
    fc='#4a9ac8', ec='#2a7aaa', lw=2, zorder=5, alpha=0.92))
ax.annotate('', xy=(rx_c[240], ry[240]), xytext=(rx_c[60], ry[60]),
    arrowprops=dict(arrowstyle='->', color='#2a7aaa', lw=2, mutation_scale=14), zorder=6)
T(ax, hj('深河', '심하'), 2.2, MAP_Y0 + 8.5, sz=26, c='#0a3a5c', bg='#eef7fb')

T(ax, hj('重地', '중지') + '·' + hj('圮地', '비지') + '·' + hj('險形', '험형'),
  0.15, MAP_Y0 + 0.5, sz=25, c='#2a2010', bg='#ece4c0', ha='left')
T(ax, '만주 산림·구릉(후금 본거지 방면)', 19.0, MAP_Y1 - 0.6, sz=25, c='#1e2a12', bg='#dfe6cc')

# ── y/x 배치 ──
Y_MING = MAP_Y0 + 6.6         # 유정 본대(아부달리 방면, 산림 깊숙)
Y_JOSEON = MAP_Y0 + 3.0       # 조선군(부차, 심하 인근, 후방 분리)
Y_JIN = MAP_Y1 - 2.2          # 후금 본대 최초 위치(동북 산악)

X_MING = 16.5
X_JOSEON = 8.0
X_JIN0 = 21.5

# ── 명 동로군(유정) — 아부달리 협곡으로 깊숙이 진입, 조선군과 분리 ──
n_ming = 130
ming_x = X_MING + np.random.uniform(-2.6, 2.6, n_ming)
ming_y = Y_MING + np.random.uniform(-0.85, 0.85, n_ming)
troops(ax, ming_x, ming_y, '#2255dd', ms=110, alpha=0.8)
pe_em(ax, '⚔️', X_MING, Y_MING + 1.35, zoom=0.20, z=17)
T(ax, '명 동로군(유정, 아부달리)', X_MING, Y_MING - 1.6, sz=25, c='#0a1a6b', bg='#e8ecfb')

# ── 조선원정군 — 부차(富車), 후방 보급 지연으로 본대와 분리된 채 뒤처짐 ──
n_kr_main = 90
kr_x = X_JOSEON + np.random.uniform(-2.1, 2.1, n_kr_main)
kr_y = Y_JOSEON + np.random.uniform(-0.75, 0.75, n_kr_main)
troops(ax, kr_x, kr_y, '#2255dd', ms=115, alpha=0.85)
T(ax, '조선군 본대(강홍립·김경서)', X_JOSEON + 1.6, Y_JOSEON - 2.15, sz=21, c='#0a1a6b', bg='#e8ecfb')

n_kr_left = 45
kl_x = X_JOSEON - 3.3 + np.random.uniform(-1.1, 1.1, n_kr_left)
kl_y = Y_JOSEON + 0.3 + np.random.uniform(-0.6, 0.6, n_kr_left)
troops(ax, kl_x, kl_y, '#5a7fe0', ms=115, alpha=0.9)
pe_em(ax, '🛡️', X_JOSEON - 3.3, Y_JOSEON + 1.5, zoom=0.20, z=17)
T(ax, '좌영(김응하)·조총수 방어선', X_JOSEON - 3.3, Y_JOSEON + 2.4, sz=22, c='#0a1a6b', bg='#e8ecfb')

# 역풍(逆風) — 후금 방면(동북)에서 조선군 조총 진영(서남)으로 불어 화약연기를 되돌림
wind_x = np.linspace(X_JOSEON + 3.2, X_JOSEON - 2.2, 5)
wind_y = np.linspace(Y_JOSEON + 2.6, Y_JOSEON + 0.6, 5)
for i in range(len(wind_x) - 1):
    ax.annotate('', xy=(wind_x[i+1], wind_y[i+1]), xytext=(wind_x[i], wind_y[i]),
        arrowprops=dict(arrowstyle='->', color='#999999', lw=2.4, alpha=0.85,
                         linestyle=(0, (3, 2))), zorder=9)
T(ax, '역풍(逆風) — 화약연기가 조선군 시야를 가림', X_JOSEON + 1.0, Y_JOSEON + 3.1, sz=23, c='#4a4a4a', bg='#f0f0ea')

# ── 후금 8기(누르하치) — 아부달리에서 유정 격파 후, 여세로 부차의 조선군 타격 ──
n_jin = 140
jin_x = X_JIN0 + np.random.uniform(-1.9, 1.9, n_jin)
jin_y = Y_JIN + np.random.uniform(-0.9, 0.9, n_jin)
troops(ax, jin_x, jin_y, '#ee3333', ms=115, alpha=0.85)
pe_em(ax, '🐎', X_JIN0, Y_JIN + 1.4, zoom=0.20, z=17)
T(ax, '후금 8기(누르하치, 총지휘)', X_JIN0, Y_JIN - 1.6, sz=24, c='#7a0000', bg='#fbeaea')
T(ax, '"몇 갈래로 오든 나는 한 길로 간다"', X_JIN0 - 0.3, Y_JIN - 2.35, sz=19, c='#7a0000', bg='#fbeaea')

# 1차: 후금 기병 → 유정 본대(아부달리) 격파
arr(ax, X_JIN0 - 1.5, Y_JIN - 0.8, X_MING + 1.8, Y_MING + 0.9, '#ee2222', rad=-0.1, hw=4.2, tw=2.2, z=12)
pe_em(ax, '🔥', X_MING, Y_MING, zoom=0.16, z=18)
marker_point(ax, X_MING, Y_MING, ms=28, color='#ff2200')

# 유정군 붕괴(점선, 반대방향 궤멸)
arr(ax, X_MING - 1.0, Y_MING - 1.0, X_MING - 3.2, MAP_Y0 + 1.2, '#2255dd', rad=0.1, dash=True, hw=2.6, tw=1.3, z=9)

# 2차: 후금 기병, 여세로 부차의 조선군 좌영 돌파(화약연기로 시야 가려진 순간)
arr(ax, X_MING - 1.0, Y_MING - 0.3, X_JOSEON - 2.4, Y_JOSEON + 1.6, '#ee2222', rad=-0.12, hw=4.0, tw=2.1, z=12)
pe_em(ax, '🔥', X_JOSEON - 3.3, Y_JOSEON + 0.2, zoom=0.16, z=18)
marker_point(ax, X_JOSEON - 3.3, Y_JOSEON, ms=28, color='#ff2200')
T(ax, '좌영 궤멸·김응하 전사', X_JOSEON - 3.3, Y_JOSEON - 1.55, sz=21, c='#7a0000', bg='#fff0e8')

# 조선군 본대 붕괴(점선) → 강홍립·김경서 이하 항복
arr(ax, X_JOSEON, Y_JOSEON - 1.0, X_JOSEON + 1.3, MAP_Y0 + 0.6, '#2255dd', rad=-0.08, dash=True, hw=2.6, tw=1.3, z=9)
T(ax, '강홍립·김경서 이하 항복', X_JOSEON + 3.0, MAP_Y0 + 0.5, sz=20, c='#0a1a6b', bg='#e8ecfb')

draw_title(ax, ['부차·심하전투 전략도 ', 'Battle of Fucha', ' (1619)'])

legend_items = [
    ('arr', '#ee2222', '후금 기병 각개격파'),
    ('dash', '#2255dd', '명·조선군 붕괴·항복'),
    ('dash', '#999999', '역풍(화약연기 역류)'),
    ('emoji', '⚔️', '지휘관'),
    ('emoji', '🛡️', '좌영(김응하)'),
    ('emoji', '🐎', '후금 기병'),
    ('emoji', '🔥', '궤멸 지점'),
    ('dot_r', '#ee3333', '후금 8기'),
    ('dot_b', '#2255dd', '명·조선 연합군'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items, title=hj('重地', '중지') + '·' + hj('圮地', '비지'))

패군_rows = [
    ('지기(知己)', '조총수 다수 편제, 강행군·군량 두절로 지친 채 전투(愛民可煩).'),
    ('지피(知彼)', '역풍이라는 기상변수와 후금 기병력을 과소평가.'),
    ('지지(知地)', '만주 산림 험형(險形)—본대·조선군 분리된 채 협곡 진입.'),
    ('장(將)', '김응하는 勇 뚜렷하나 유정·강홍립은 근접전 대비 부족(智 결핍).'),
    ('전력배치(法)', '명군 약 3만+조선군 1만~1.3만, 보급 지연으로 분리.'),
    ('결과', '좌영 전멸·유정 전사·강홍립 항복 — 北(배): 정예 선봉 없이 화력만 의존.'),
]
draw_analysis_box(ax, renderer, LX, '패군', '유정·강홍립·김응하', 패군_rows, '#1a3a7a')

승군_rows = [
    ('지기(知己)', '전군 6만 열세 인식, "임이기로래 아지일로거"로 집중 결단.'),
    ('지피(知彼)', '명군 4로 분산과 조선군의 분리·지연을 정확히 읽음.'),
    ('지지(知地)', '만주 산림 험형을 홈그라운드로 삼아 각개격파.'),
    ('장(將)', '智·嚴 뚜렷, 8기 전체를 하나의 명령체계로 집중 통솔.'),
    ('전력배치(法)', '8기 약 6만, 아부달리·부차 순차 집중 타격.'),
    ('결과', '명·조선 연합군 궤멸 — 識衆寡之用者勝: 국지적 수적우위를 만들어냄.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '누르하치', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fucha_1619_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
