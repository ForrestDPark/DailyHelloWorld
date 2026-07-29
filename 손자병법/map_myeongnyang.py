#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""명량 해전(1597년 음력 9월 16일, 정유재란) 전략지형도

死焉不得·無所往則固·必死則生 실증 사례.
승군 이순신: 판옥선 13척으로 좁고 급조류가 흐르는 울돌목(隘形·死地)을 등지고
서서 "必死則生"으로 병사를 결속, 좁은 목이 왜군의 수적 우세를 무력화하도록 유도.
패군 일본 수군: 130여 척의 대함대가 좁은 수로에 몰려 서로 엉키고, 선봉 구루시마가
전사하자 결속이 무너져 밀려남(深入했으나 治로 잇지 못함).
근거: 이순신 『난중일기』, 『선조실록』, 정유재란 해전 연구.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(1597)

fig, ax, renderer = new_canvas()
extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 좌하단=진도(섬), 우상단=화원반도(해남 육지), 그 사이 좁은 수로=울돌목.
#          가운데가 조여드는 급류 협수로(隘形). 물길이 넓게 열리는 남동(하단)=외해 ──
lons = np.linspace(0, 1, 92)
lats = np.linspace(0, 1, 72)   # LAT 0=남(외해, 일본 진입), 1=북(내해, 조선 함대)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 16.0   # 물(저지=바다)
# 진도(좌하단 큰 섬)
elev += 46 * np.exp(-(((LON - 0.10) ** 2) / 0.020 + ((LAT - 0.32) ** 2) / 0.10))
# 화원반도·해남(우상단 육지)
elev += 46 * np.exp(-(((LON - 0.92) ** 2) / 0.022 + ((LAT - 0.72) ** 2) / 0.12))
# 수로를 가운데서 조이는 두 곶(울돌목 협착부)
elev += 20 * np.exp(-(((LON - 0.30) ** 2) / 0.006 + ((LAT - 0.52) ** 2) / 0.02))
elev += 20 * np.exp(-(((LON - 0.70) ** 2) / 0.006 + ((LAT - 0.50) ** 2) / 0.02))
terrain_colors = [
    (0.0, '#2f6ea6'),    # 깊은 물
    (0.30, '#3f8fc0'),   # 얕은 물
    (0.42, '#cdd39a'),   # 갯벌·물가
    (0.66, '#9aa863'),   # 해안 구릉
    (1.0, '#6d7d3c'),    # 육지 고지
]
draw_terrain(ax, elev, extent, terrain_colors)

X = 12.0

# 구절 라벨
T(ax, hj('無所往則固', '무소왕즉고') + '·' + hj('必死則生', '필사즉생'),
  0.3, MAP_Y1 - 0.55, sz=21, c='#0a2a3a', bg='#dcecf6', ha='left')

# 육지 라벨
T(ax, hj('珍島', '진도'), 3.4, MAP_Y0 + 2.4, sz=20, c='#173d17', bg='#e2efd0')
T(ax, hj('花源半島', '화원반도') + '(海南, 해남)', 20.0, MAP_Y1 - 2.6, sz=18,
  c='#173d17', bg='#e2efd0')

Y_KOR = MAP_Y1 - 2.9        # 조선 함대(북, 승군, 파랑)
Y_MID = (MAP_Y0 + MAP_Y1) / 2
Y_JAP = MAP_Y0 + 2.6        # 일본 함대(남, 패군, 빨강)

# ── 울돌목 급조류 ──
cy = np.linspace(MAP_Y0 + 1.0, MAP_Y1 - 1.2, 200)
cx = X + 1.6 * np.sin((cy - MAP_Y0) * 0.55)
ax.plot(cx, cy, color='#1f6fae', lw=2.0, alpha=0.5, zorder=4)
pe_em(ax, '🌊', X - 0.1, Y_MID + 0.3, zoom=0.12, z=19)
T(ax, hj('鳴梁', '명량') + '(울돌목) — 급조류 협수로', X + 0.7, Y_MID + 0.3,
  sz=18, c='#0a2a4a', bg='#dcecf6', ha='left')
# 조류 방향(전투 중 반전 — 주황 특수기동)
arr(ax, X - 2.2, Y_JAP + 1.6, X - 1.6, Y_MID - 0.2, '#ff6600', rad=0.15, hw=3.0, tw=1.6, z=10)
arr(ax, X + 2.4, Y_MID + 0.4, X + 1.8, Y_KOR - 1.4, '#ff6600', rad=0.15, hw=3.0, tw=1.6, z=10)
T(ax, '조류 반전 → 조선에 유리', X + 3.4, Y_MID - 1.1, sz=15, c='#7a3800',
  bg='#fff0e0', ha='left')

# ── 조선 함대(승군, 파랑) — 판옥선 13척, 일자진 횡대 ──
n_kor = 13
kor_x = np.linspace(X - 4.2, X + 4.2, n_kor)
kor_y = Y_KOR + np.random.uniform(-0.25, 0.25, n_kor)
troops(ax, kor_x, kor_y, '#2255dd', ms=150, alpha=0.92)
pe_em(ax, '⚔️', X - 5.0, Y_KOR + 0.1, zoom=0.16, z=19)
marker_point(ax, X, Y_KOR + 0.9, ms=20, color='#1f52c0')
T(ax, '이순신 기함 — 판옥선 13척 일자진', X, Y_KOR + 1.5, sz=18, c='#0a1a6b',
  bg='#e8ecfb')
T(ax, hj('必死則生', '필사즉생') + ' — 사지에서 결사', X, Y_KOR - 0.85, sz=17,
  c='#0a1a6b', bg='#e8ecfb')

# ── 일본 함대(패군, 빨강) — 130여 척이 좁은 목에 밀집 ──
n_jap = 60
jap_x = X + np.random.uniform(-5.4, 5.4, n_jap)
jap_y = Y_JAP + np.random.uniform(-1.5, 1.5, n_jap)
troops(ax, jap_x, jap_y, '#ee3333', ms=44, alpha=0.78)
pe_em(ax, '⚔️', X - 5.8, Y_JAP - 0.2, zoom=0.14, z=18)
T(ax, '일본 수군 — 130여 척(도도 다카토라)', X, Y_JAP + 2.1, sz=18, c='#7a0000',
  bg='#fbeaea')
marker_point(ax, X + 3.2, Y_JAP + 0.6, ms=16, color='#cc0000')
pe_em(ax, '🔥', X + 3.2, Y_JAP + 0.6, zoom=0.10, z=19)
T(ax, '구루시마 전사', X + 4.6, Y_JAP + 0.9, sz=15, c='#7a0000', bg='#fff0e8', ha='left')

# ── 화살표 ──
# 일본 북상 진입(빨강 실선)
arr(ax, X - 2.6, Y_JAP + 2.4, X - 2.6, Y_KOR - 1.6, '#ee2222', rad=0.0, hw=4.0, tw=2.2, z=12)
# 조선 화포 집중 사격·역공(파랑 실선)
arr(ax, X - 1.0, Y_KOR - 1.2, X - 1.0, Y_MID + 0.2, '#2255dd', rad=0.0, hw=4.0, tw=2.2, z=13)
arr(ax, X + 2.0, Y_KOR - 1.2, X + 2.0, Y_MID, '#2255dd', rad=0.0, hw=3.6, tw=1.9, z=13)
T(ax, '판옥선 화포 집중 → 선봉 격침', X + 3.4, Y_KOR - 1.7, sz=15, c='#0a1a6b',
  bg='#e8ecfb', ha='left')
# 일본 궤퇴(빨강 점선)
arr(ax, X - 4.0, Y_JAP + 0.5, X - 6.2, MAP_Y0 + 0.6, '#ee2222', rad=0.1, hw=3.0, tw=1.5, z=11, dash=True)
T(ax, '좁은 목에 엉켜 퇴각', X - 5.4, MAP_Y0 + 0.9, sz=15, c='#7a0000',
  bg='#fff0e8', ha='left')

draw_title(ax, ['명량 해전 전략도  ', hj('鳴梁海戰', '명량해전'), '  (1597)'])

legend_items = [
    ('arr', '#ee2222', '일본 진입'),
    ('dash', '#ee2222', '일본 궤퇴'),
    ('arr', '#2255dd', '조선 화포 역공'),
    ('arr', '#ff6600', '조류 반전'),
    ('emoji', '🌊', '급조류 협수로'),
    ('emoji', '🔥', '격침·전사'),
    ('dot_r', '#ee3333', '일본 수군'),
    ('dot_b', '#2255dd', '조선 수군'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items,
                title=hj('隘形', '애형') + '·' + hj('死地', '사지'))

패군_rows = [
    ('道(지기)', '칠천량 대승 뒤의 과신. 소규모 조선 잔여 함대를 얕보고 급조류 협수로로 밀집 진입.'),
    ('天(지피)', '울돌목 조류의 시각·방향과 좁은 목이 대함대에 불리함을 오판. 낮은 확률의 역전을 무시.'),
    ('地(지형)', '좁은 수로에서 130여 척이 서로 엉켜 수적 우세가 오히려 족쇄가 됨(深入했으나 治 없음).'),
    ('將', '勇·과신 앞서고 지형 판단 부족. 선봉 구루시마 전사로 지휘 결속 붕괴.'),
    ('法(전력배치)', '130여 척 대함대이나 좁은 목에서 동시 투입 불가, 선두만 소모.'),
    ('결과', '31척 이상 격침·궤퇴. 深入則拘를 治로 잇지 못한 파국.'),
]
draw_analysis_box(ax, renderer, LX, '패군', '도도·구루시마', 패군_rows, '#7a2020')

승군_rows = [
    ('道(지기)', '"必死則生"으로 겁먹은 수군을 결속. 13척뿐인 사지에서 도주 대신 결사로 사기 전환.'),
    ('天(지피)', '울돌목 조류의 반전 시점을 읽고, 좁은 목이 적의 대군을 무력화하도록 시기를 택함.'),
    ('地(지형)', '급조류 협수로(隘形·死地)를 등지고 선점 — 퇴로 없음이 곧 결속(無所往則固).'),
    ('將', '智(조류·지형 활용)·信(선두 사수)·嚴(대오 유지)이 압도. 사지를 생지로 뒤집음.'),
    ('法(전력배치)', '판옥선 13척, 우수한 화포·견고한 선체로 좁은 목에서 화력 집중 운용.'),
    ('결과', '조선 손실 0척으로 대승. 投之亡地然後存·陷之死地然後生.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '이순신', 승군_rows, '#1a3a7a')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'myeongnyang_claude_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
