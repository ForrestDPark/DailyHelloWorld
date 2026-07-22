#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""장평대전 상당(上黨) 쟁탈(長平之戰, BCE 260) 전략지형도

爭地(쟁지) 실증 사례: 상당(上黨)은 한·조·진 모두가 탐낸 요충지였다.
조괄이 백기의 위장 후퇴에 낚여 진지를 벗어나 추격하는 순간, 남북 협곡에
매복해 있던 진군 별동대(2만5천) + 정예기병(5천)이 배후로 돌아 들어가
퇴로를 끊고 완전 포위망을 완성한 장면을 묘사한다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(26)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 남북(장축)으로 뻗은 협곡 계곡, 동서 양쪽에 산(매복지) ──
lons = np.linspace(0, 1, 80)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 190.0
elev -= 150 * np.exp(-(((LON - 0.5) ** 2) / 0.045))                                # 중앙 계곡(단수 유역)
elev += 70 * np.exp(-(((LON - 0.08) ** 2) / 0.010 + ((LAT - 0.5) ** 2) / 0.5))      # 서쪽 산(骷髏山·마안학 매복지)
elev += 70 * np.exp(-(((LON - 0.92) ** 2) / 0.010 + ((LAT - 0.5) ** 2) / 0.5))      # 동쪽 산(홍가구·형촌 매복지)
terrain_colors = [
    (0.0, '#8a9a5b'),
    (0.30, '#a8ac6e'),
    (0.55, '#c9c090'),
    (0.78, '#8f9a6a'),
    (1.0, '#5f6f42'),
]
draw_terrain(ax, elev, extent, terrain_colors)

# 단수(丹水) - 계곡 중심을 남북으로 흐름
draw_river(ax, base_x=12.0, y0=MAP_Y0, y1=MAP_Y1, amplitude=0.45, freq1=1.0,
           amp2=0.2, freq2=2.4, width=0.30, flow_up=True)

T(ax, '서산(매복지)', 3.0, MAP_Y1 - 0.6, sz=30, c='#eef7e0', bg='#3a4e2c')
T(ax, '동산(매복지)', 21.0, MAP_Y1 - 0.6, sz=30, c='#eef7e0', bg='#3a4e2c')
T(ax, hj('爭地', '쟁지') + ' · ' + hj('上黨', '상당'), 12.0, MAP_Y1 - 0.6, sz=34, c='#2a2010', bg='#e8dcc0')

# ── y 구역 배분 (북=상단, 조나라 후방·한단 방면 / 남=하단, 진나라 방면) ──
# 4개 구역을 위→아래로 2.6~2.8 간격으로 넉넉히 분리해 라벨이 겹치지 않게 한다.
Y_ZHAO_WALL = MAP_Y0 + 9.4    # 조나라 원래 진지(벽루) — 후방에 남겨진 잔류 부대
Y_CUTOFF = MAP_Y0 + 6.8       # 진 기병이 퇴로를 끊는 지점(조괄 본대 vs 후방 진지 사이)
Y_ZHAO_MAIN = MAP_Y0 + 4.2    # 조괄 본대(백기 유인에 낚여 전진한 위치, 현재 포위됨)
Y_QIN_DECOY = MAP_Y0 + 1.4    # 진나라 위장후퇴 부대(최종적으로 조군을 막아선 위치)

# ── 조나라 후방 잔류 진지(벽루) — 본대와 단절된 소수 잔류 병력 ──
n_wall = 30
wall_x = 12.0 + np.random.uniform(-1.6, 1.6, n_wall)
wall_y = Y_ZHAO_WALL + np.random.uniform(-0.5, 0.5, n_wall)
troops(ax, wall_x, wall_y, '#2255dd', ms=110, alpha=0.6)
T(ax, '조군 잔류 진지(壁壘)', 17.3, Y_ZHAO_WALL, sz=27, c='#0a1a6b', bg='#e8ecfb')
T(ax, hj('丹水', '단수'), 15.2, Y_ZHAO_WALL - 1.5, sz=28, c='#0a3a5c', bg='#eef7fb')

# ── 조괄 본대 — 유인에 낚여 전진, 현재 사방이 포위된 상태 ──
n_main = 130
main_x = 12.0 + np.random.uniform(-2.5, 2.5, n_main)
main_y = Y_ZHAO_MAIN + np.random.uniform(-1.2, 1.2, n_main)
troops(ax, main_x, main_y, '#2255dd', ms=140, alpha=0.85)
T(ax, '조괄 본대(45만, 포위됨)', 6.7, Y_ZHAO_MAIN, sz=30, c='#0a1a6b', bg='#e8ecfb')
pe_em(ax, '🛡️', 12.0, Y_ZHAO_MAIN + 0.2, zoom=0.20, z=17)

# 조괄의 최후 돌파 시도(점선, 남쪽 진 방면으로 필사적으로 뚫으려 함 — 실패)
arr(ax, 11.3, Y_ZHAO_MAIN - 1.3, 10.2, Y_QIN_DECOY + 1.1, '#2255dd', rad=0.1, dash=True, hw=3.2, tw=1.6, z=12)

# ── 진나라 위장후퇴 부대 — 처음엔 밀리는 척 후퇴하다 남단에서 버티고 막아섬 ──
n_decoy = 70
decoy_x = 12.0 + np.random.uniform(-2.1, 2.1, n_decoy)
decoy_y = Y_QIN_DECOY + np.random.uniform(-0.8, 0.8, n_decoy)
troops(ax, decoy_x, decoy_y, '#ee3333', ms=120, alpha=0.82)
T(ax, '진 위장후퇴 부대(왕흘)', 17.6, Y_QIN_DECOY, sz=27, c='#7a0000', bg='#fbeaea')

# 조괄이 유인당해 남하 추격한 경로(회색 점선 화살표로 과거 이동 표시)
arr(ax, 12.0, Y_ZHAO_WALL - 0.7, 12.0, Y_ZHAO_MAIN + 1.4, '#888888', rad=0.0, hw=2.0, tw=1.0, dash=True, z=7, alpha=0.5)

# ── 진나라 매복 별동대(2만5천) — 서/동 양쪽 산에서 협공하며 조여듦 ──
n_amb_w = 55
amb_w_x = 4.0 + np.random.uniform(-1.3, 1.3, n_amb_w)
amb_w_y = MAP_Y0 + 5.5 + np.random.uniform(-3.0, 3.0, n_amb_w)
troops(ax, amb_w_x, amb_w_y, '#ee3333', ms=110, alpha=0.8)
T(ax, '진 매복대(서익)', 4.0, MAP_Y0 + 0.9, sz=28, c='#7a0000', bg='#fbeaea')

n_amb_e = 55
amb_e_x = 20.0 + np.random.uniform(-1.3, 1.3, n_amb_e)
amb_e_y = MAP_Y0 + 5.5 + np.random.uniform(-3.0, 3.0, n_amb_e)
troops(ax, amb_e_x, amb_e_y, '#ee3333', ms=110, alpha=0.8)
T(ax, '진 매복대(동익)', 20.0, MAP_Y0 + 0.9, sz=28, c='#7a0000', bg='#fbeaea')

# 매복대가 협곡을 나와 조군 배후로 조여드는 포위 기동(주황색 = 특수기동)
arr(ax, 5.3, MAP_Y0 + 8.0, 10.3, Y_CUTOFF, '#ff8800', rad=-0.15, hw=3.0, tw=1.5, z=13)
arr(ax, 18.7, MAP_Y0 + 8.0, 13.7, Y_CUTOFF, '#ff8800', rad=0.15, hw=3.0, tw=1.5, z=13)
arr(ax, 5.3, MAP_Y0 + 3.2, 9.3, Y_ZHAO_MAIN, '#ff8800', rad=0.1, hw=3.0, tw=1.5, z=13)
arr(ax, 18.7, MAP_Y0 + 3.2, 14.7, Y_ZHAO_MAIN, '#ff8800', rad=-0.1, hw=3.0, tw=1.5, z=13)

# ── 진 정예기병(5천) — 조괄 본대와 후방 잔류 진지 사이 통로를 끊음(퇴로 차단) ──
cav_x = [8.6, 10.4, 12.0, 13.6, 15.4]
cav_y = [Y_CUTOFF - 0.25, Y_CUTOFF + 0.25, Y_CUTOFF - 0.2, Y_CUTOFF + 0.25, Y_CUTOFF - 0.25]
for cx, cy in zip(cav_x, cav_y):
    pe_em(ax, '🐎', cx, cy, zoom=0.20, z=15)
marker_point(ax, 12.0, Y_CUTOFF, ms=32, color='#ff2200')
T(ax, '포위 완성·퇴로 차단(46일)', 18.4, Y_CUTOFF, sz=27, c='#7a0000', bg='#fff0e8')

# 백기 지휘 표식(전체를 조망하는 위치, 동쪽 산 기슭)
pe_em(ax, '⚔️', 19.0, MAP_Y0 + 3.3, zoom=0.20, z=17)

draw_title(ax, ['장평대전 상당쟁탈 전략도  ', '長平之戰', '  (BCE 260)'])

legend_items = [
    ('arr', '#ee2222', '위장 후퇴선'),
    ('arr', '#ff8800', '매복대 포위'),
    ('dash', '#2255dd', '조군 돌파시도'),
    ('dash', '#888888', '조괄 추격로'),
    ('emoji', '🐎', '기병 차단'),
    ('emoji', '⚔️', '백기(총지휘)'),
    ('dot_r', '#ee3333', '진나라 보병'),
    ('dot_b', '#2255dd', '조나라 보병'),
    ('dot', '#ffaa00', '포위 완성점'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items, title=hj('爭地', '쟁지') + ' · ' + hj('上黨', '상당'))

패군_rows = [
    ('전력+배치+보급', '조군 약 45만. 염파의 지구전 편제를 조괄이 공세로 재편, 보급선을 전방으로 무리하게 전진.'),
    ('지피(知彼)', '백기로의 은밀한 지휘관 교체를 모른 채 왕흘 상대로만 판단 — 결정적 오판.'),
    ('지기(知己)', '병서 이론에만 능해 실전 지휘를 과신(必死可殺). 46일 포위 끝에 돌파하다 전사.'),
    ('지지(知地)', "상당의 지리적 가치만 보고 진격, 협곡·매복지형을 읽지 못함."),
    ('결과', "조군 전멸(40만 생매장 포함). 쟁지는 얻었으나 지형 운용에서 완패."),
]
draw_analysis_box(ax, renderer, LX, '패군', '조괄', 패군_rows, '#1a3a7a')

승군_rows = [
    ('전력+배치+보급', '진군 약 60만 동원, 정예를 매복·차단 부대로 재편. 진왕이 총력으로 보급·차단을 지원.'),
    ('지피(知彼)', '조괄의 공명심과 이론 중심 성향을 간파, 거짓 패주로 유인.'),
    ('지기(知己)', '매복·차단 능력을 정확히 계산, 포위망 완성 전까지 정면 결전을 피함.'),
    ('지지(知地)', '협곡 지형을 사전 답사해 조군 퇴로에 매복 배치 — 쟁지 선점 후 방어까지 완수.'),
    ('결과', '조군을 완전 포위 섬멸, 전국시대 세력균형을 진나라로 결정적으로 기울임.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '백기', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'changping_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
