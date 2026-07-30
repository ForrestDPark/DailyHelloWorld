#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""워틀링 스트리트 전투(61년, 브리타니아 부디카 반란) 전략지형도

死焉不得·無所往則固·不得已則鬪 실증 사례.
승군 파울리누스: 등 뒤에 숲, 좌우에 고지가 조여드는 좁은 협곡(隘形)을 먼저
차지해 퇴로를 스스로 끊고(無所往則固), 정면 개활지만 열어 매복 위험을 없앤 뒤
쐐기 대형으로 역돌격(不得已則鬪).
패군 부디카: 병력은 압도적이었으나 승리를 구경하러 온 가족의 수레를 후방에
둘러쳐(퇴로 자멸), 대오가 무너지자 그 수레벽에 막혀 도륙당함(死地인데 治가 없음).
근거: 타키투스 『연대기』 14.34~37, 카시우스 디오 『로마사』 62.8~12.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(61)

fig, ax, renderer = new_canvas()
extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 하단(남)=브리튼 대군이 몰려든 개활지, 위로 갈수록 좌우 고지가 조여드는
#          깔때기형 협곡(隘形), 최상단(북)=로마군 등 뒤의 숲(퇴로 차단) ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)   # LAT 0=남(하단, 브리튼), 1=북(상단, 숲/로마 배후)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 46.0
# 좌우 능선: 아래에서는 넓게(0.03/0.97), 위로 갈수록 안으로 모여(0.34/0.66) 협곡을 만든다
left_wall = 0.03 + 0.31 * LAT
right_wall = 0.97 - 0.31 * LAT
elev += 34 * np.exp(-((LON - left_wall) ** 2) / 0.006)
elev += 34 * np.exp(-((LON - right_wall) ** 2) / 0.006)
# 최상단 숲 언덕(로마군 배후)
elev += 15 * np.exp(-((LAT - 0.96) ** 2) / 0.010)
terrain_colors = [
    (0.0, '#a7b178'),    # 개활 초지(저지)
    (0.35, '#93a760'),
    (0.62, '#7e8f4b'),
    (0.82, '#6d7d3c'),
    (1.0, '#5c6b30'),    # 능선·숲 고지
]
draw_terrain(ax, elev, extent, terrain_colors)

X = 12.0

# 구절 라벨
T(ax, hj('無所往則固', '무소왕즉고') + '·' + hj('不得已則鬪', '부득이즉투'),
  0.3, MAP_Y1 - 0.55, sz=21, c='#2a2010', bg='#ece4c0', ha='left')

Y_FOREST = MAP_Y1 - 1.15    # 숲(로마 배후, 퇴로 차단)
Y_ROMAN = MAP_Y1 - 3.0      # 로마 군단(협곡 목, 승군, 파랑)
Y_PLAIN = (MAP_Y0 + MAP_Y1) / 2 - 0.3
Y_BRIT = MAP_Y0 + 3.3       # 브리튼 대군(패군, 빨강, 북상 공격)
Y_WAGON = MAP_Y0 + 1.0      # 브리튼 수레 방벽(가족·퇴로 자멸)

# ── 숲(북, 로마 배후) ──
for fx in np.linspace(3.0, 21.0, 11):
    pe_em(ax, '🌲', fx, Y_FOREST + np.random.uniform(-0.2, 0.2), zoom=0.14, z=16)
T(ax, hj('숲', 'wood') + ' — 로마군 배후 차단, 매복 불가',
  X, Y_FOREST - 0.6, sz=18, c='#173d17', bg='#dfeccb')

# ── 좌우 고지(협곡 벽) ──
T(ax, hj('고지', 'ridge'), 3.4, Y_ROMAN - 1.2, sz=17, c='#3a3410', bg='#e6e0bd')
T(ax, hj('고지', 'ridge'), 20.6, Y_ROMAN - 1.2, sz=17, c='#3a3410', bg='#e6e0bd')
T(ax, hj('隘形', '애형') + ' — 좁은 협곡 목', X, Y_ROMAN + 0.85, sz=18,
  c='#5a3d0a', bg='#f0e6c8')

# ── 로마군(승군, 파랑) — 협곡 목에 밀집 횡대 ──
n_rm = 46
rm_x = X + np.random.uniform(-3.0, 3.0, n_rm)
rm_y = Y_ROMAN + np.random.uniform(-0.45, 0.45, n_rm)
troops(ax, rm_x, rm_y, '#2255dd', ms=86, alpha=0.9)
pe_em(ax, '🛡️', X - 3.7, Y_ROMAN + 0.1, zoom=0.15, z=18)
pe_em(ax, '🐎', X + 4.0, Y_ROMAN + 0.2, zoom=0.13, z=18)
T(ax, '파울리누스(Paulinus) — 로마군 약 1만', X, Y_ROMAN - 0.95, sz=18,
  c='#0a1a6b', bg='#e8ecfb')

# ── 브리튼군(패군, 빨강) — 개활지에 대군, 북상 공격 ──
n_br = 150
br_x = X + np.random.uniform(-6.2, 6.2, n_br)
br_y = Y_BRIT + np.random.uniform(-1.6, 1.6, n_br)
troops(ax, br_x, br_y, '#ee3333', ms=52, alpha=0.8)
pe_em(ax, '⚔️', X - 6.6, Y_BRIT + 0.3, zoom=0.16, z=18)
T(ax, '부디카(Boudica) — 브리튼 연합 대군', X, Y_BRIT + 1.95, sz=18,
  c='#7a0000', bg='#fbeaea')

# ── 브리튼 수레 방벽(가족·퇴로 자멸) — 하단 호형 ──
wx = np.linspace(3.0, 21.0, 22)
wy = Y_WAGON - 0.5 * np.sin((wx - 3.0) / 18.0 * np.pi)
ax.scatter(wx, wy, s=240, marker='s', c='#8a5a2a', edgecolors='#3a2410',
           linewidths=1.2, zorder=9)
T(ax, '브리튼 수레 방벽 — 가족 관전, 퇴로 자멸', X, Y_WAGON - 1.05, sz=17,
  c='#4a2a08', bg='#f0e2cf')

# ── 화살표 ──
# 브리튼 북상 공격(빨강 실선)
arr(ax, X, Y_BRIT + 2.4, X, Y_ROMAN - 1.7, '#ee2222', rad=0.0, hw=4.4, tw=2.6, z=12)
# 로마 쐐기 역돌격(파랑 실선, 좁게 시작해 벌어짐)
arr(ax, X - 1.4, Y_ROMAN - 0.7, X - 3.2, Y_PLAIN, '#2255dd', rad=-0.25, hw=3.6, tw=1.9, z=13)
arr(ax, X + 1.4, Y_ROMAN - 0.7, X + 3.2, Y_PLAIN, '#2255dd', rad=0.25, hw=3.6, tw=1.9, z=13)
arr(ax, X, Y_ROMAN - 0.8, X, Y_PLAIN - 0.4, '#2255dd', rad=0.0, hw=4.0, tw=2.2, z=13)
T(ax, '쐐기 대형 역돌격(cuneus)', X + 3.7, Y_PLAIN + 0.5, sz=16, c='#0a1a6b',
  bg='#e8ecfb', ha='left')
# 브리튼 궤주가 수레벽에 막힘(빨강 점선, 짧게)
arr(ax, X - 4.2, Y_BRIT - 1.4, X - 5.0, Y_WAGON + 0.5, '#ee2222', rad=0.1, hw=2.8, tw=1.4, z=11, dash=True)
arr(ax, X + 4.2, Y_BRIT - 1.4, X + 5.0, Y_WAGON + 0.5, '#ee2222', rad=-0.1, hw=2.8, tw=1.4, z=11, dash=True)
T(ax, '퇴로 막혀 도륙', X, Y_BRIT - 2.2, sz=15, c='#7a0000', bg='#fff0e8')

draw_title(ax, ['워틀링 전투 전략도  ', 'Watling Street', '  (AD 61)'])

legend_items = [
    ('arr', '#ee2222', '브리튼 공격'),
    ('dash', '#ee2222', '브리튼 궤주'),
    ('arr', '#2255dd', '로마 쐐기 역돌격'),
    ('emoji', '🌲', '숲(배후 차단)'),
    ('emoji', '🐎', '기병'),
    ('emoji', '🛡️', '군단 지휘'),
    ('dot_r', '#ee3333', '브리튼군'),
    ('dot_b', '#2255dd', '로마군'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items,
                title=hj('隘形', '애형') + '·' + hj('死地', '사지'))

패군_rows = [
    ('道(지기)', '이케니·트리노반테스 등 부족 연합. 학정에 대한 분노로 결집했으나 규율·편제가 느슨했고 대승을 자신해 가족까지 데려옴.'),
    ('天(지피)', '수적 우세만 믿고 로마군이 고른 협곡·숲 지형의 함정을 읽지 못함. 낮은 확률의 패배를 무시.'),
    ('地(지형)', '개활지에서 정면 밀집 돌격. 스스로 두른 수레벽이 퇴로를 끊어 死地를 자초.'),
    ('將', '勇·忿速(분노·저돌)만 앞서고 智·嚴 부족 — 忿速可侮 유형.'),
    ('法(전력배치)', '수만~수십만 대군이나 정면 한 방향 돌격뿐, 예비·우회 없음.'),
    ('결과', '약 8만 전사 vs 로마 400. 治 없는 死地의 파국(北).'),
]
draw_analysis_box(ax, renderer, LX, '패군', '부디카', 패군_rows, '#7a2020')

승군_rows = [
    ('道(지기)', '군단병의 오랜 훈련과 규율. 퇴로 없는 자리에서도 대오를 유지해 결사의 사기로 전환.'),
    ('天(지피)', '정면 개활지에 매복 없음을 먼저 확인하고, 지친·과신한 적이 밀집 돌격할 것을 예견.'),
    ('地(지형)', '등 뒤 숲, 좌우 고지가 조인 좁은 협곡(隘形)을 선점 — 측면·후방이 차단돼 무소왕즉고.'),
    ('將', '智(지형 선택)·嚴(정지→쐐기의 통제)이 압도. 사지에 서되 결사로 이끎.'),
    ('法(전력배치)', '제14군단+제20군단 분견대+보조병 약 1만. 필럼 일제투척→쐐기 돌격의 정밀 운용.'),
    ('결과', '10배 이상 열세로 대승. 陷之死地然後生의 정석.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '파울리누스', 승군_rows, '#1a3a7a')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'watling_claude_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
