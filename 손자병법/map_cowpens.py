#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""카우펜스 전투(1781년 1월 17일, 미국 독립전쟁) 전략지형도

謹養而勿勞·爲不可測·投之無所往 실증 사례(승군 관점): 대니얼 모건은 등 뒤로
약 5~6마일 떨어진 범람한 브로드강을 두어 민병대가 무한정 달아나지 못하게
하고(投之無所往), 라이플맨→민병대→대륙군의 3중 종심 방어와 계획된 후퇴로
적을 오판시켰다(爲不可測). 반면 배내스터 탈턴은 새벽 강행군으로 지친 병력을
휴식·정찰 없이 즉시 투입(謹養而勿勞 위반)했다가 이중포위로 궤멸했다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(1781)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 남쪽(하단)=영국군 진입로, 완만한 오르막 → 낮은 능선 두 개(중앙·상단),
#          북쪽(상단)=범람한 브로드강(퇴로 차단, 배수진) ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)   # LAT 0 = 남(하단), 1 = 북(상단)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 50.0
elev += 22 * np.exp(-((LAT - 0.60) ** 2) / 0.010)   # 제3선(대륙군)이 선 낮은 능선
elev += 12 * np.exp(-((LAT - 0.30) ** 2) / 0.008)   # 제1선 앞 낮은 crest
elev -= 8 * np.exp(-((LAT - 0.45) ** 2) / 0.004)    # 두 능선 사이 저지(swale)
elev -= 26 * np.exp(-((LAT - 0.93) ** 2) / 0.012)   # 브로드강 저지대(상단)
terrain_colors = [
    (0.0, '#4a8ec2'),    # 강 저지
    (0.22, '#9fb27a'),   # 초지 저지
    (0.5, '#b8bd82'),     # 개활 방목지
    (0.78, '#9aa863'),
    (1.0, '#77863f'),     # 능선
]
draw_terrain(ax, elev, extent, terrain_colors)

X_CENTER = 12.0

# 지형 라벨
T(ax, hj('投之無所往', '투지무소왕') + '·' + hj('死且不北', '사차불배'),
  0.2, MAP_Y1 - 0.55, sz=22, c='#2a2010', bg='#ece4c0', ha='left')

Y_RIVER = MAP_Y1 - 1.05      # 브로드강(북, 상단, 배수진)
Y_RESERVE = MAP_Y1 - 2.7     # 워싱턴 기병 예비대
Y_LINE3 = MAP_Y1 - 4.3       # 제3선 하워드 대륙군(능선)
Y_LINE2 = MAP_Y1 - 6.2       # 제2선 피컨스 민병대
Y_LINE1 = MAP_Y1 - 7.9       # 제1선 라이플맨(저격)
Y_BRITISH = MAP_Y0 + 1.2     # 탈턴 영국군(남에서 북상 공격)

# ── 브로드강(상단, 배수진) — 사인 곡선 ──
ry = np.linspace(2.0, 22.0, 300)
rx_c = ry * 0 + 0  # placeholder; use draw_river horizontal? lib draw_river is vertical.
# 수평 강을 직접 그린다
from matplotlib.patches import Polygon as _Poly
xr = np.linspace(1.0, 23.0, 300)
yr_c = Y_RIVER + 0.35 * np.sin(xr * 0.9) + 0.18 * np.sin(xr * 2.1)
yr_t = yr_c + 0.42
yr_b = yr_c - 0.42
ax.add_patch(_Poly(list(zip(xr, yr_t)) + list(zip(xr[::-1], yr_b[::-1])),
                   fc='#4a9ac8', ec='#2a7aaa', lw=2, zorder=5, alpha=0.92))
T(ax, hj('브로드강', 'Broad R.') + ' — 범람, 퇴로 차단(약 5~6마일 뒤)',
  X_CENTER, Y_RIVER + 0.75, sz=19, c='#0a2a4a', bg='#dcecf6')

# ── 영국군(패군, 공격, 적색) — 남쪽에서 북상 ──
n_br = 95
br_x = X_CENTER + np.random.uniform(-3.2, 3.2, n_br)
br_y = Y_BRITISH + np.random.uniform(-0.9, 0.9, n_br)
troops(ax, br_x, br_y, '#ee3333', ms=78, alpha=0.85)
pe_em(ax, '⚔️', X_CENTER - 3.6, Y_BRITISH + 0.2, zoom=0.17, z=17)
T(ax, '탈턴(Tarleton) — 새벽 12마일 강행군 직후 즉시 공격',
  X_CENTER, Y_BRITISH - 1.15, sz=19, c='#7a0000', bg='#fbeaea')
pe_em(ax, '🐎', X_CENTER + 4.2, Y_BRITISH + 0.5, zoom=0.13, z=18)
pe_em(ax, '💣', X_CENTER - 1.2, Y_BRITISH + 0.9, zoom=0.11, z=18)

# ── 미국군 제1선: 라이플맨(승군, 청색, 저격 후 후퇴) ──
n_l1 = 26
l1_x = X_CENTER + np.random.uniform(-3.6, 3.6, n_l1)
l1_y = Y_LINE1 + np.random.uniform(-0.35, 0.35, n_l1)
troops(ax, l1_x, l1_y, '#3f7de0', ms=60, alpha=0.8)
T(ax, '제1선 라이플맨 — 장교 조준 2발 후 후퇴', X_CENTER, Y_LINE1 - 0.9,
  sz=17, c='#0a1a6b', bg='#e8ecfb')

# ── 제2선: 피컨스 민병대 ──
n_l2 = 34
l2_x = X_CENTER + np.random.uniform(-3.8, 3.8, n_l2)
l2_y = Y_LINE2 + np.random.uniform(-0.4, 0.4, n_l2)
troops(ax, l2_x, l2_y, '#2f6fd8', ms=70, alpha=0.85)
pe_em(ax, '🛡️', X_CENTER - 4.4, Y_LINE2, zoom=0.13, z=18)
T(ax, '제2선 피컨스 민병대 — 일제사격 2회 후 좌측 우회', X_CENTER, Y_LINE2 - 0.9,
  sz=17, c='#0a1a6b', bg='#e8ecfb')

# ── 제3선: 하워드 대륙군 정규 보병(능선) ──
n_l3 = 40
l3_x = X_CENTER + np.random.uniform(-3.4, 3.4, n_l3)
l3_y = Y_LINE3 + np.random.uniform(-0.45, 0.45, n_l3)
troops(ax, l3_x, l3_y, '#1f52c0', ms=88, alpha=0.9)
pe_em(ax, '🛡️', X_CENTER + 4.2, Y_LINE3 + 0.2, zoom=0.15, z=18)
T(ax, '제3선 하워드 대륙군 — 최후 저지선(능선)', X_CENTER, Y_LINE3 + 1.15,
  sz=18, c='#0a1a6b', bg='#e8ecfb')

# ── 예비: 워싱턴 기병 ──
pe_em(ax, '🐎', X_CENTER - 5.2, Y_RESERVE, zoom=0.16, z=18)
T(ax, '워싱턴 기병 예비대 — 능선 뒤 은폐', X_CENTER - 1.2, Y_RESERVE, sz=17,
  c='#0a1a6b', bg='#e8ecfb', ha='left')
marker_point(ax, X_CENTER - 5.2, Y_RESERVE, ms=22, color='#1f52c0')

# ── 화살표 ──
# 영국군 북상 공격
arr(ax, X_CENTER, Y_BRITISH + 1.0, X_CENTER, Y_LINE1 - 0.6, '#ee2222', rad=0.0, hw=4.2, tw=2.3, z=12)
# 계획된 후퇴(같은 방향처럼 보이나 통제된 후퇴) — 하워드 대륙군 잠깐 뒤로
arr(ax, X_CENTER + 2.6, Y_LINE3 - 0.3, X_CENTER + 2.6, Y_LINE3 + 0.9, '#ff6600', rad=0.0, hw=3.0, tw=1.6, z=12, dash=True)
T(ax, '오해된 후퇴 → 근거리 일제사격+총검 반격', X_CENTER + 3.0, Y_LINE2 + 0.7,
  sz=15, c='#7a3800', bg='#fff0e0', ha='left')
# 이중포위: 워싱턴 기병 우회(좌), 피컨스 민병대 재편(우)
arr(ax, X_CENTER - 5.0, Y_RESERVE - 0.4, X_CENTER - 2.0, Y_LINE1 + 0.2, '#1f52c0', rad=0.35, hw=3.4, tw=1.8, z=13)
arr(ax, X_CENTER + 5.0, Y_LINE2 - 0.3, X_CENTER + 2.2, Y_LINE1 - 0.1, '#1f52c0', rad=-0.35, hw=3.4, tw=1.8, z=13)
T(ax, '이중포위(칸나에식)', X_CENTER + 5.6, Y_LINE1 + 0.4, sz=16, c='#0a1a6b', bg='#e8ecfb')
# 탈턴 패주
arr(ax, X_CENTER - 2.0, Y_BRITISH - 0.2, X_CENTER - 5.5, MAP_Y0 + 0.5, '#ee2222', rad=0.1, hw=3.0, tw=1.5, z=11, dash=True)
T(ax, '탈턴 잔여 기병 탈출', X_CENTER - 5.8, MAP_Y0 + 0.8, sz=15, c='#7a0000', bg='#fff0e8', ha='left')

draw_title(ax, ['카우펜스 전투 전략도  ', 'Battle of Cowpens', '  (1781)'])

legend_items = [
    ('arr', '#ee2222', '영국군 공격'),
    ('dash', '#ff6600', '계획된 후퇴'),
    ('arr', '#1f52c0', '미국군 포위'),
    ('dash', '#ee2222', '영국군 패주'),
    ('emoji', '🐎', '기병'),
    ('emoji', '💣', '포병'),
    ('emoji', '🛡️', '보병 지휘'),
    ('dot_r', '#ee3333', '영국군'),
    ('dot_b', '#1f52c0', '미국군'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items,
                title=hj('養', '양') + '·' + hj('不可測', '불가측'))

패군_rows = [
    ('道(지기)', '정규군·왕당파 군단·고지대 연대·기병의 혼성 편제로 결속이 약했고, 탈턴의 저돌적 명성에 기댄 과신이 판단을 지배.'),
    ('天(지피)', '민병대를 얕보고 3중 종심 배치와 은폐 기병을 정찰 없이 지나쳐, 모건이 판 함정을 읽지 못함.'),
    ('地(지형)', '개활 방목지를 정면 돌격에만 유리하다 보고, 능선·저지(swale)를 이용한 종심 방어의 함정을 간과.'),
    ('將', '勇은 넘쳤으나 智(정찰·판단)·嚴(대오 통제)이 부족 — 忿速可侮에 가까운 성급함.'),
    ('法(전력배치)', '약 1,100명. 새벽 강행군으로 식량 소진·수면 4시간 미만, 라인 편성·예비대 배치 전 성급히 돌격.'),
    ('결과', '86% 사상·궤멸. 北(적정을 헤아리지 못하고 무너짐) — 謹養而勿勞를 정면으로 어김.'),
]
draw_analysis_box(ax, renderer, LX, '패군', '탈턴', 패군_rows, '#7a2020')

승군_rows = [
    ('道(지기)', '모닥불을 돌며 병사를 규합, 민병대의 이탈 심리를 "두 발만 쏘면 자유"로 역이용해 결속으로 전환.'),
    ('天(지피)', '탈턴의 저돌성과 민병대 경시를 정확히 읽고, 강행군에 지친 적이 즉시 돌격할 것을 예견.'),
    ('地(지형)', '등 뒤 5~6마일에 범람한 브로드강을 두어 무한 도주를 차단(投之無所往), 능선·저지로 종심 구성.'),
    ('將', '智(무기 특성·심리 설계)·嚴(통제된 후퇴)이 압도 — 병사를 사지에 두되 결사로 이끎.'),
    ('法(전력배치)', '라이플맨→민병대→대륙군 3중선 + 워싱턴 기병 예비. 무기별 역할 분담이 정밀.'),
    ('결과', '이중포위로 대승. 以虞待不虞者勝(준비한 자가 준비 없는 자를 이김).'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '모건', 승군_rows, '#1a3a7a')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cowpens_claude_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
