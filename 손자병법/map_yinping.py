#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""등애의 음평 기습(263년, 촉한멸망전) 전략지형도

兵之情主速·由不虞之道·攻其所不戒也 실증 사례: 종회의 위나라 주력이 검각에서
강유의 방어에 막혀 정체되자, 등애는 소수 정예를 이끌고 사람이 다니지 않는
음평 소로 700여 리를 뚫었다(무인지경, 절벽에서 담요로 몸을 감싸 굴러
내려감). 방비 없는 강유성·부성을 거쳐 면죽에서 제갈첨을 격파하고 곧장
성도로 들이닥쳐 촉한을 멸망시켰다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(263)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 북쪽=검각 험로(종회 주력 저지선), 남쪽=음평 소로·사천 분지(무인지경) ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 50.0
elev += 50 * np.exp(-((LAT - 0.86) ** 2) / 0.03) * (1 + 0.25 * np.sin(LON * 7.5 + 0.5))  # 검각 험산(북)
elev += 30 * np.exp(-(((LON - 0.35) ** 2) / 0.02 + ((LAT - 0.55) ** 2) / 0.05))            # 음평 소로 험지(중앙)
elev -= 18 * np.exp(-((LAT - 0.12) ** 2) / 0.014)                                          # 사천 분지 저지(남)
terrain_colors = [
    (0.0, '#6a7a48'),
    (0.28, '#83925a'),
    (0.55, '#96a066'),
    (0.80, '#6f7d48'),
    (1.0, '#465a2e'),
]
draw_terrain(ax, elev, extent, terrain_colors)

T(ax, hj('由不虞之道', '유불우지도') + '·' + hj('無人之境', '무인지경'),
  0.2, MAP_Y1 - 0.6, sz=23, c='#2a2010', bg='#ece4c0', ha='left')
T(ax, hj('劍閣', '검각') + ' — 강유 방어(위군 정체)', 19.0, MAP_Y1 - 0.6, sz=21, c='#1e2a12', bg='#dfe6cc')

Y_JIANGE = MAP_Y1 - 2.6        # 검각(북쪽, 종회 주력 vs 강유)
Y_YINPING = MAP_Y0 + 6.8        # 음평 소로(등애 우회, 험지)
Y_JIANGYOU = MAP_Y0 + 4.2       # 강유성·부성(무방비)
Y_MIANZHU = MAP_Y0 + 1.8        # 면죽(제갈첨 최후 방어)

X_CENTER = 12.0

# ── 종회 주력(검각, 청색 아님 — 같은 위군이지만 정체된 본대, 회색조로 구분) ──
n_zh = 100
zh_x = X_CENTER - 2.0 + np.random.uniform(-2.6, 2.6, n_zh)
zh_y = Y_JIANGE + np.random.uniform(-0.9, 0.9, n_zh)
troops(ax, zh_x, zh_y, '#8899aa', ms=75, alpha=0.7)
pe_em(ax, '⚔️', X_CENTER - 2.0, Y_JIANGE + 1.6, zoom=0.18, z=17)
T(ax, '종회(鍾會) 위군 주력 — 검각에서 정체', X_CENTER - 2.0, Y_JIANGE + 2.4, sz=19, c='#3a3a3a', bg='#eef0f2')

# 강유(촉한) 방어군
n_jw = 45
jw_x = X_CENTER + 3.0 + np.random.uniform(-1.2, 1.2, n_jw)
jw_y = Y_JIANGE - 0.5 + np.random.uniform(-0.6, 0.6, n_jw)
troops(ax, jw_x, jw_y, '#2255dd', ms=85, alpha=0.85)
pe_em(ax, '🛡️', X_CENTER + 3.0, Y_JIANGE - 1.6, zoom=0.16, z=17)
T(ax, '강유(姜維) — 검각 험로 고수', X_CENTER + 3.0, Y_JIANGE - 2.4, sz=18, c='#0a1a6b', bg='#e8ecfb')

# ── 등애 정예(음평 소로 우회, 적색=승군) ──
n_deng = 70
path_t = np.linspace(0, 1, n_deng)
dg_x = X_CENTER - 6.0 + path_t * 4.5 + np.random.uniform(-0.5, 0.5, n_deng)
dg_y = Y_JIANGE - 1.5 - path_t * (Y_JIANGE - 1.5 - Y_YINPING) + np.random.uniform(-0.5, 0.5, n_deng)
troops(ax, dg_x, dg_y, '#ee3333', ms=80, alpha=0.85)
pe_em(ax, '⚔️', X_CENTER - 6.0, Y_JIANGE - 1.0, zoom=0.18, z=17)
T(ax, '등애(鄧艾) 정예 — 음평 소로 700여 리 강행', X_CENTER - 7.5, Y_YINPING + 1.6, sz=19, c='#7a0000', bg='#fbeaea', ha='left')
pe_em(ax, '🪢', X_CENTER - 3.0, Y_YINPING, zoom=0.14, z=18)
T(ax, '절벽에서 담요로 몸을 감싸 굴러 내려감', X_CENTER - 3.0, Y_YINPING - 1.1, sz=16, c='#7a0000', bg='#fff0e8')

# ── 강유성·부성(무방비, 등애 통과) ──
T(ax, '강유(江油)·부(涪) — 무방비 통과', X_CENTER, Y_JIANGYOU + 0.7, sz=18, c='#5a3f0a', bg='#f6ecd6')
pe_em(ax, '🚫', X_CENTER, Y_JIANGYOU, zoom=0.14, z=18)

# ── 제갈첨(諸葛瞻) 최후 방어(면죽, 청색=패군) ──
n_zg = 50
zg_x = X_CENTER + np.random.uniform(-1.8, 1.8, n_zg)
zg_y = Y_MIANZHU + np.random.uniform(-0.6, 0.6, n_zg)
troops(ax, zg_x, zg_y, '#2255dd', ms=85, alpha=0.85)
pe_em(ax, '⚔️', X_CENTER, Y_MIANZHU + 1.4, zoom=0.18, z=17)
T(ax, '제갈첨(諸葛瞻) — 면죽 최후 방어, 전사', X_CENTER, Y_MIANZHU - 1.0, sz=19, c='#0a1a6b', bg='#e8ecfb')

# ── 화살표 ──
arr(ax, X_CENTER - 6.0, Y_JIANGE - 1.8, X_CENTER - 3.5, Y_YINPING + 0.5, '#cc2222', rad=0.1, hw=3.6, tw=1.9, z=12)
arr(ax, X_CENTER - 3.0, Y_YINPING - 0.3, X_CENTER - 0.5, Y_JIANGYOU + 0.3, '#cc2222', rad=-0.05, hw=3.6, tw=1.9, z=12)
arr(ax, X_CENTER, Y_JIANGYOU - 0.5, X_CENTER, Y_MIANZHU + 1.0, '#ee2222', rad=0.0, hw=4.0, tw=2.1, z=13)
T(ax, '무인지경 우회 → 면죽 직공', X_CENTER + 5.0, Y_JIANGYOU - 0.5, sz=18, c='#7a0000', bg='#fff0e8')

# 면죽 함락 후 성도로
arr(ax, X_CENTER + 0.3, Y_MIANZHU - 0.8, X_CENTER + 4.5, MAP_Y0 + 0.5, '#ee2222', rad=-0.1, hw=3.2, tw=1.7, z=11)
T(ax, '성도(成都) 직공 → 유선 항복', X_CENTER + 6.0, MAP_Y0 + 0.8, sz=17, c='#7a0000', bg='#fff0e8', ha='left')

draw_title(ax, ['등애의 음평 기습 전략도 ', '鄧艾偸渡陰平', ' (263)'])

legend_items = [
    ('arr', '#cc2222', '등애군 우회 기동'),
    ('arr', '#ee2222', '면죽 직공·성도 진격'),
    ('emoji', '⚔️', '지휘관'),
    ('emoji', '🪢', '절벽 강하'),
    ('emoji', '🚫', '무방비 통과'),
    ('dot_r', '#ee3333', '등애군(위)'),
    ('dot_b', '#2255dd', '촉한군'),
    ('dot', '#8899aa', '종회 주력(위, 검각 정체)'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items, title=hj('速', '속') + '·' + hj('不虞', '불우'))

패군_rows = [
    ('道(지기)', '유선의 조정이 항전·천도·투항으로 분열, 초주의 투항론이 득세 — 결속 붕괴.'),
    ('天(지피)', '검각만 막으면 안전하다 여겨 음평 방면 정찰·수비를 사실상 방치.'),
    ('地(지형)', '음평 소로를 "사람이 다닐 수 없는 길"로 과신 — 험지가 오히려 무방비 통로가 됨.'),
    ('將', '제갈첨은 智(선제 방어선 구축)가 늦어 면죽에서야 요격, 勇은 있었으나 시기를 놓침.'),
    ('法(전력배치)', '제갈첨 면죽 방어군 수만(사료상 편차), 강유성·부성은 사실상 무방비.'),
    ('결과', '면죽 궤멸·성도 항복 — 北(적정을 헤아리지 못하고 대비 없이 무너짐).'),
]
draw_analysis_box(ax, renderer, LX, '패군', '제갈첨·유선', 패군_rows, '#1a3a7a')

승군_rows = [
    ('道(지기)', '고령에도 정예를 자원해 이끈 등애의 결단에 병사들이 죽음을 무릅쓰고 따름.'),
    ('天(지피)', '위군 주력이 검각에 묶인 시점, 촉한이 음평을 비워둔 빈틈을 정확히 포착.'),
    ('地(지형)', '무인지경 험로를 오히려 기습로로 역이용, 담요로 절벽을 굴러 내려가는 강행군.'),
    ('將', '智(우회 노선 구상)·勇(직접 선두에서 강하)이 압도적.'),
    ('法(전력배치)', '정예 수천(사료상 편차), 경장비로 신속 기동.'),
    ('결과', '촉한 멸망 — 兵之情主速·由不虞之道·攻其所不戒也의 정석적 실현.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '등애', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'yinping_claude_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
