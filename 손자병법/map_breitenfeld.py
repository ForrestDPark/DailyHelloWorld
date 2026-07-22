#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""브라이텐펠트 전투(Battle of Breitenfeld, 1631) 전략지형도

衢地(구지) 실증 사례: 작센 선제후국은 가톨릭동맹·스웨덴 양쪽 모두가 반드시
확보해야 할 접경지(諸侯之地三屬)였다. 틸리 백작이 이 접경지를 힘으로
굴복시키려 침공했지만(1631.9 초), 그 침공 자체가 오히려 요한 게오르크를
스웨덴과의 동맹으로 떠밀었다(9/11 동맹 요청 → 9/14 라이프치히 함락 →
9/17 결전). 먼저 접경지의 신의(동맹)를 얻은 구스타프 아돌프가 승기를 쥔다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(31)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 라이프치히 북서쪽 광활한 평원, 남쪽(제바우젠~브라이텐펠트 사이)
#    완만한 고지(황제군 포진지), 뢰버 시내가 동서로 가로지름 ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 105.0
elev += 45 * np.exp(-(((LON - 0.5) ** 2) / 0.14 + ((LAT - 0.13) ** 2) / 0.03))   # 남쪽 완만한 고지(황제군 포진)
elev -= 12 * np.exp(-(((LON - 0.5) ** 2) / 0.5 + ((LAT - 0.64) ** 2) / 0.01))    # 뢰버 시내 저지대
terrain_colors = [
    (0.0, '#b8c48a'),
    (0.3, '#c8cf98'),
    (0.6, '#d8d09a'),
    (0.82, '#c2b878'),
    (1.0, '#a89c5e'),
]
draw_terrain(ax, elev, extent, terrain_colors)

# 뢰버 시내(Loberbach) - 동서로 가로지르는 소하천, 습지성 저지
# 중심 y≈15.3, 진폭±0.5, 반폭 0.22 → 실제 점유 대역 약 14.58~16.02
np.random.seed(31)
ry = np.linspace(0, 24, 300)
rx_c = 15.3 + 0.35 * np.sin(ry * 0.9) + 0.15 * np.sin(ry * 2.1)
rx_u = rx_c + 0.22
rx_l = rx_c - 0.22
from matplotlib.patches import Polygon as _Poly
ax.add_patch(_Poly(list(zip(ry, rx_u)) + list(zip(ry[::-1], rx_l[::-1])),
    fc='#4a9ac8', ec='#2a7aaa', lw=2, zorder=5, alpha=0.9))
ax.annotate('', xy=(19.5, rx_c[243]), xytext=(4.5, rx_c[56]),
    arrowprops=dict(arrowstyle='->', color='#2a7aaa', lw=2, mutation_scale=14), zorder=6)
T(ax, hj('Loberbach', '뢰버 시내'), 21.0, 15.3, sz=26, c='#0a3a5c', bg='#eef7fb')

T(ax, '제바우젠(帝軍 우측 방면)', 4.6, MAP_Y0 + 1.0, sz=27, c='#3a2c10', bg='#e8dcbf')
T(ax, '브라이텐펠트', 14.5, MAP_Y0 + 1.0, sz=30, c='#3a2c10', bg='#e8dcbf')
T(ax, hj('衢地', '구지') + ' · 작센(라이프치히 8km)', 12.0, MAP_Y1 - 0.6, sz=32, c='#2a2010', bg='#e8dcc0')

# ── y 구역: 남(하단)=帝國·가톨릭동맹군(틸리, 고지 선점) / 북(상단)=스웨덴·작센 연합군 ──
# 뢰버 시내 대역(14.58~16.02)과 겹치지 않도록 각 라인·라벨에 충분한 여유를 둔다.
Y_TILLY = MAP_Y0 + 1.5         # 틸리 보병 중앙(테르시오 14개, 고지) = 9.7
Y_CAV = MAP_Y0 + 1.2           # 帝軍 좌우 기병 = 9.4
Y_ALLY_LINE = MAP_Y0 + 4.8     # 스웨덴·작센 연합군 최초 전개선(뢰버 도하 후) = 13.0
Y_ALLY_REAR = MAP_Y0 + 9.4     # 후속·예비대

# ── 帝國(가톨릭동맹)군: 틸리 보병 중앙 + 파펜하임(좌익) + 퓌르스텐베르크(우익) ──
n_tilly = 150
tilly_x = 12.0 + np.random.uniform(-3.6, 3.6, n_tilly)
tilly_y = Y_TILLY + np.random.uniform(-0.8, 0.8, n_tilly)
troops(ax, tilly_x, tilly_y, '#ee3333', ms=110, alpha=0.8)
T(ax, '틸리 보병 중앙(테르시오 14개)·틸리(총사령관)', 12.0, Y_TILLY - 1.2, sz=26, c='#7a0000', bg='#fbeaea')
pe_em(ax, '⚔️', 12.0, Y_TILLY + 1.0, zoom=0.20, z=17)

n_papp = 60
papp_x = 4.2 + np.random.uniform(-1.4, 1.4, n_papp)
papp_y = Y_CAV + np.random.uniform(-0.7, 0.7, n_papp)
troops(ax, papp_x, papp_y, '#ee3333', ms=110, alpha=0.75)
pe_em(ax, '🐎', 4.2, Y_CAV + 0.9, zoom=0.20, z=15)
T(ax, '파펜하임 기병(帝軍 좌익)', 4.2, Y_CAV - 1.1, sz=26, c='#7a0000', bg='#fbeaea')

n_furst = 60
furst_x = 20.5 + np.random.uniform(-1.4, 1.4, n_furst)
furst_y = Y_CAV + np.random.uniform(-0.7, 0.7, n_furst)
troops(ax, furst_x, furst_y, '#ee3333', ms=110, alpha=0.75)
pe_em(ax, '🐎', 20.5, Y_CAV + 0.9, zoom=0.20, z=15)
T(ax, '퓌르스텐베르크 기병(帝軍 우익)', 20.5, Y_CAV - 1.1, sz=26, c='#7a0000', bg='#fbeaea')

# 파펜하임 조기 돌격(명령 없이 수 차례 돌격) → 스웨덴 우익에 격퇴됨(점선 후퇴)
arr(ax, 5.0, Y_CAV + 1.0, 6.3, Y_ALLY_LINE - 0.7, '#ee2222', rad=0.1, hw=3.6, tw=1.8, z=12)
arr(ax, 6.6, Y_ALLY_LINE - 0.4, 5.2, Y_CAV + 1.4, '#ee2222', rad=0.15, dash=True, hw=2.6, tw=1.2, z=9)

# 퓌르스텐베르크 → 작센군 궤멸(성공)
arr(ax, 20.0, Y_CAV + 1.0, 19.6, Y_ALLY_LINE - 0.7, '#ee2222', rad=-0.1, hw=4.0, tw=2.0, z=12)

# ── 스웨덴·작센 연합군: 우익(구스타프+바네르) / 중앙 / 좌익(호른) / 작센(최좌익) ──
n_swed_r = 55
swr_x = 6.0 + np.random.uniform(-1.6, 1.6, n_swed_r)
swr_y = Y_ALLY_LINE + np.random.uniform(-0.8, 0.8, n_swed_r)
troops(ax, swr_x, swr_y, '#2255dd', ms=140, alpha=0.88)
pe_em(ax, '⚔️', 6.0, Y_ALLY_LINE + 1.1, zoom=0.20, z=17)
T(ax, '구스타프 아돌프·바네르(우익)', 6.0, Y_ALLY_LINE - 1.3, sz=26, c='#0a1a6b', bg='#e8ecfb')

n_swed_c = 110
swc_x = 12.3 + np.random.uniform(-2.6, 2.6, n_swed_c)
swc_y = Y_ALLY_LINE + np.random.uniform(-0.8, 0.8, n_swed_c)
troops(ax, swc_x, swc_y, '#2255dd', ms=120, alpha=0.82)
T(ax, '스웨덴 중앙(보병 7여단·기병 3연대)', 12.3, Y_ALLY_LINE - 1.5, sz=25, c='#0a1a6b', bg='#e8ecfb')

n_horn = 50
horn_x = 16.6 + np.random.uniform(-1.3, 1.3, n_horn)
horn_y = Y_ALLY_LINE + np.random.uniform(-0.8, 0.8, n_horn)
troops(ax, horn_x, horn_y, '#2255dd', ms=130, alpha=0.85)
T(ax, '호른(좌익, 90도 전환·재정비)', 19.4, Y_ALLY_LINE, sz=25, c='#0a1a6b', bg='#e8ecfb')
marker_point(ax, 17.6, Y_ALLY_LINE, ms=26, color='#ffaa00')

n_sax = 65
sax_x = 20.9 + np.random.uniform(-1.4, 1.4, n_sax)
sax_y = Y_ALLY_LINE + np.random.uniform(-0.8, 0.8, n_sax)
troops(ax, sax_x, sax_y, '#3a6fd8', ms=110, alpha=0.55)
T(ax, '작센군(요한 게오르크)', 20.9, Y_ALLY_LINE - 1.3, sz=25, c='#0a1a6b', bg='#e8ecfb')

# 작센군 궤주(초전 붕괴, 전장 이탈) — 점선, 반대(북동) 방향(뢰버 시내를 가로질러 이탈)
arr(ax, 21.3, Y_ALLY_LINE + 0.7, 23.2, MAP_Y1 - 1.2, '#2255dd', rad=0.1, dash=True, hw=2.6, tw=1.2, z=9)

# 틸리 중앙보병, 작센 붕괴한 틈으로 동진(우회 기동) → 호른의 새 방어선과 충돌
arr(ax, 14.5, Y_TILLY + 1.4, 18.3, Y_ALLY_LINE - 0.9, '#ff6600', rad=-0.15, hw=3.4, tw=1.7, z=13)

# 스웨덴 중앙+우익, 예비대를 돌려 틸리 보병을 포위(협공)
arr(ax, 7.0, Y_ALLY_LINE - 0.6, 10.0, Y_TILLY + 1.2, '#ff6600', rad=0.1, hw=3.2, tw=1.6, z=13)
arr(ax, 17.5, Y_ALLY_LINE - 0.9, 14.5, Y_TILLY + 1.4, '#ff6600', rad=-0.05, hw=3.2, tw=1.6, z=13)

pe_em(ax, '🔥', 12.0, Y_TILLY + 0.2, zoom=0.16, z=18)
marker_point(ax, 12.0, Y_TILLY, ms=30, color='#ff2200')
T(ax, '帝軍 보병 포위·붕괴', 8.6, Y_TILLY + 0.1, sz=27, c='#7a0000', bg='#fff0e8')

# 틸리군 최종 패주(남쪽으로)
arr(ax, 11.0, Y_TILLY - 0.7, 8.0, MAP_Y0 + 0.3, '#ee3333', rad=0.1, dash=True, hw=2.8, tw=1.3, z=9)

draw_title(ax, ['브라이텐펠트 전투 전략도  ', 'Breitenfeld', '  (1631)'])

legend_items = [
    ('arr', '#ee2222', '帝軍 기병 돌격'),
    ('dash', '#ee2222', '격퇴·패주'),
    ('arr', '#ff6600', '포위 기동'),
    ('dash', '#2255dd', '작센군 궤주'),
    ('emoji', '🐎', '기병(帝軍 양익)'),
    ('emoji', '⚔️', '지휘관'),
    ('emoji', '🔥', '보병 붕괴 지점'),
    ('dot_r', '#ee3333', '가톨릭동맹 보병'),
    ('dot_b', '#2255dd', '스웨덴 보병'),
    ('dot', '#ffaa00', '호른 방향전환점'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items, title=hj('衢地', '구지') + ' · 작센')

패군_rows = [
    ('전력+배치+보급', '가톨릭동맹군 약 3만1천~3만5천. 마그데부르크 파괴로 자체 병참기지 상실, 작센 현지 징발에 의존.'),
    ('지피(知彼)', '작센-스웨덴 동맹 체결(9/11)과 그 급박한 타이밍을 못 읽음 — 忿速可侮(마그데부르크 이후 조급한 결전 강행).'),
    ('지기(知己)', '테르시오 무패 신화를 과신, 스웨덴 신형 경량포·삼단사격의 화력 우위를 과소평가(廉潔可辱: 구식 교리 고수).'),
    ('지지(知地)', "브라이텐펠트 평원은 通形(我可往彼可來) — 마그데부르크 파괴로 이미 糧道를 스스로 끊은 채 통형 원칙을 어김."),
    ('결과', '보병 중앙 포위·붕괴, 약 7,600명 사상·6,000명 포로, 틸리 중상 — 구지 선점 실패의 대가.'),
]
draw_analysis_box(ax, renderer, LX, '패군', '틸리 백작', 패군_rows, '#7a2020')

승군_rows = [
    ('전력+배치+보급', '스웨덴·작센 연합 약 4만150. 佛(프랑스) 바르발데 조약 보조금으로 정규 보급 체계 유지.'),
    ('지피(知彼)', '틸리의 병참 붕괴와 침공의 역설(작센을 동맹으로 떠민 것)을 정확히 읽고 급박한 타이밍을 활용.'),
    ('지기(知己)', '화력 우위(3~5배 발사속도)를 정확히 계산, 좌익 붕괴 직후 즉각 예비대 재배치로 결단.'),
    ('지지(知地)', '通形 원칙대로 뢰버 시내 배후 고지·바람 방향을 선점, 좌익의 虛를 90도 전환으로 實로 바꿈(奇正 병용).'),
    ('결과', '帝軍 보병 포위 섬멸, 스웨덴의 독일 개입 본격화 — 접경지(구지)를 먼저 얻어 천하의 향배를 결정.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '구스타프 아돌프', 승군_rows, '#1a3a7a')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'breitenfeld_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
