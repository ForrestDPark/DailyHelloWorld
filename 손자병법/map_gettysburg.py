#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""게티즈버그 전투(Battle of Gettysburg, 1863) 전략지형도

爭地(쟁지) 실증 사례: 리틀 라운드 탑(Little Round Top) 고지 쟁탈.
북군이 남군보다 몇 분 먼저 고지를 점거한 뒤(先至者利), 그 이로움을 끝내
지키고(2일차) 오히려 셋째 날 피켓의 돌격까지 격퇴한다(3일차).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(19)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 서쪽 세미너리 능선(남군) / 동쪽 묘지능선(북군, 남단이 리틀 라운드 탑) ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 55.0
elev += 85 * np.exp(-(((LON - 0.17) ** 2) / 0.010 + ((LAT - 0.5) ** 2) / 0.55))   # 세미너리 능선(남군, 서)
elev += 120 * np.exp(-(((LON - 0.72) ** 2) / 0.008 + ((LAT - 0.52) ** 2) / 0.6))  # 묘지능선(북군, 동)
elev += 100 * np.exp(-(((LON - 0.78) ** 2) / 0.006 + ((LAT - 0.16) ** 2) / 0.018))  # 리틀 라운드 탑(남단)
elev += 60 * np.exp(-(((LON - 0.74) ** 2) / 0.006 + ((LAT - 0.08) ** 2) / 0.012))   # 빅 라운드 탑
elev += 75 * np.exp(-(((LON - 0.80) ** 2) / 0.008 + ((LAT - 0.90) ** 2) / 0.02))    # 컬프스 힐(북단)
elev -= 18 * np.exp(-(((LON - 0.45) ** 2) / 0.05 + ((LAT - 0.55) ** 2) / 0.2))      # 중앙 개활지(에미츠버그 로 일대)
terrain_colors = [
    (0.0, '#c8c0a0'),
    (0.3, '#b0b878'),
    (0.6, '#8fa15c'),
    (0.82, '#6a8a4a'),
    (1.0, '#4a6e3c'),
]
draw_terrain(ax, elev, extent, terrain_colors)

# 지형 라벨
T(ax, '세미너리 능선', 3.4, MAP_Y1 - 0.6, sz=32, c='#eef7e0', bg='#3a4e2c')
T(ax, '묘지능선', 19.2, MAP_Y1 - 3.4, sz=32, c='#eef7e0', bg='#3a4e2c')
T(ax, hj('爭地', '쟁지') + ' · 리틀 라운드 탑', 18.7, MAP_Y0 + 4.1, sz=32, c='#2a2010', bg='#e8dcc0')
marker_point(ax, 18.6, MAP_Y0 + 3.1, ms=30)
T(ax, '데블스 덴', 10.3, MAP_Y0 + 3.7, sz=28, c='#3a2c10', bg='#e8dcbf')

# ── y 구역 배분 (남=하단, 리틀 라운드 탑 쟁탈전 / 북=중상단, 피켓의 돌격) ──
Y_LRT = MAP_Y0 + 3.1          # 리틀 라운드 탑 정상부(북군 방어선)
Y_ASSAULT = MAP_Y0 + 1.3      # 남군 후드 사단 공격 개시선
Y_ANGLE = MAP_Y0 + 7.2        # 더 앵글 · 나무숲(피켓의 돌격 목표점)
Y_CONFED_JUMP = MAP_Y0 + 6.6  # 남군 피켓 돌격 출발선(세미너리 능선 중앙)

# ── 북군: 묘지능선을 따라 남북으로 길게 방어(먼저 점거, 先至) ──
n_ridge = 100
ridge_y = np.random.uniform(MAP_Y0 + 4.5, MAP_Y1 - 1.2, n_ridge)
ridge_x = 17.5 + np.random.uniform(-0.9, 0.9, n_ridge)
troops(ax, ridge_x, ridge_y, '#2255dd', ms=110, alpha=0.8)
T(ax, '북군 묘지능선 방어선', 19.6, MAP_Y0 + 9.5, sz=30, c='#0a1a6b', bg='#e8ecfb')

# 리틀 라운드 탑 수비대(빈센트 여단, 20메인 포함) - 남단에 밀집
n_lrt = 55
lrt_x = 18.3 + np.random.uniform(-0.7, 0.9, n_lrt)
lrt_y = Y_LRT + np.random.uniform(-1.1, 0.9, n_lrt)
troops(ax, lrt_x, lrt_y, '#2255dd', ms=150, alpha=0.88)

# 20메인 연대(체임벌린) - 좌익 최남단, 방어선이 꺾여 있는 지점('V'자 굴절)
n_me = 22
me_x = 17.3 + np.random.uniform(-0.35, 0.35, n_me)
me_y = Y_LRT - 1.4 + np.random.uniform(-0.4, 0.4, n_me)
troops(ax, me_x, me_y, '#2255dd', ms=170, alpha=0.92)
T(ax, '20메인 연대(체임벌린)', 17.3, Y_LRT - 2.6, sz=28, c='#0a1a6b', bg='#e8ecfb')
pe_em(ax, '⚔️', 17.3, Y_LRT - 1.4, zoom=0.20, z=17)

# 체임벌린 총검 돌격(우로 돌며 휩쓰는 역습, 탄약 고갈 직후)
arr(ax, 17.0, Y_LRT - 1.8, 15.3, MAP_Y0 + 0.9, '#2255dd', rad=-0.30, hw=4.0, tw=2.0, z=16)

# ── 남군: 세미너리 능선 본대 + 후드 사단의 리틀 라운드 탑 공격 ──
n_sem = 90
sem_y = np.random.uniform(MAP_Y0 + 0.6, MAP_Y1 - 1.0, n_sem)
sem_x = 4.3 + np.random.uniform(-1.0, 1.0, n_sem)
troops(ax, sem_x, sem_y, '#ee3333', ms=100, alpha=0.75)
T(ax, '남군 세미너리 능선 본대', 4.4, MAP_Y0 + 0.6, sz=28, c='#7a0000', bg='#fbeaea')

# 후드 사단 / 15·47 앨라배마 연대 - 데블스 덴을 지나 리틀 라운드 탑 남서측을 공격
n_hood = 60
hood_x = 12.0 + np.random.uniform(-1.8, 2.0, n_hood)
hood_y = Y_ASSAULT + np.random.uniform(-0.9, 0.9, n_hood)
troops(ax, hood_x, hood_y, '#ee3333', ms=130, alpha=0.82)
T(ax, '후드 사단(15·47 앨라배마)', 11.6, Y_ASSAULT - 1.1, sz=28, c='#7a0000', bg='#fbeaea')

# 남군의 리틀 라운드 탑 공격 진격(격퇴됨)
arr(ax, 12.6, Y_ASSAULT + 0.6, 17.0, Y_LRT - 1.5, '#ee2222', rad=-0.1, hw=4.2, tw=2.2, z=10)
# 격퇴되어 패주(점선, 반대 방향)
arr(ax, 15.8, MAP_Y0 + 1.0, 12.0, MAP_Y0 + 0.4, '#ee2222', rad=0.1, dash=True, hw=2.6, tw=1.2, z=9)

# ── 피켓의 돌격(3일차): 세미너리 능선 중앙에서 개활지를 가로질러 더 앵글로 ──
n_pick = 140
pick_spread = np.random.uniform(-1, 1, n_pick)
pick_x = 6.0 + pick_spread * 4.2
pick_y = Y_CONFED_JUMP + np.random.uniform(-0.5, 0.5, n_pick)
troops(ax, pick_x, pick_y, '#ee3333', ms=100, alpha=0.78)
T(ax, '피켓·페티그루·트림블 사단', 6.6, Y_CONFED_JUMP + 1.0, sz=28, c='#7a0000', bg='#fbeaea')

arr(ax, 8.5, Y_CONFED_JUMP, 16.0, Y_ANGLE, '#ee2222', rad=0.02, hw=4.6, tw=2.6, z=10)
marker_point(ax, 16.3, Y_ANGLE, ms=30, color='#ff2200')
T(ax, "'더 앵글'·나무숲(최고조점)", 16.6, Y_ANGLE - 1.1, sz=28, c='#7a0000', bg='#fff0e8')

# 개활지 노출(장궁 대신 포격) 표시
np.random.seed(5)
for i in range(10):
    x0 = np.random.uniform(9.0, 15.0)
    y0 = np.random.uniform(Y_CONFED_JUMP - 0.6, Y_CONFED_JUMP + 0.6)
    arr(ax, x0, y0, x0 + np.random.uniform(-0.3, 0.3), Y_ANGLE - 0.5, '#cc1111',
        rad=0.0, hw=1.0, tw=0.3, alpha=0.4, z=9)

# 피켓의 돌격 격퇴 후 패주(앵글 지점에서 시작, 위아래로 나뉘어 진로와
# 겹치지 않게 갈라짐)
arr(ax, 16.3, Y_ANGLE + 0.4, 9.5, Y_CONFED_JUMP + 1.6, '#ee3333', rad=0.20, dash=True, hw=2.6, tw=1.2, z=9)
arr(ax, 16.3, Y_ANGLE - 0.4, 9.5, Y_CONFED_JUMP - 1.6, '#ee3333', rad=-0.20, dash=True, hw=2.6, tw=1.2, z=9)

# 북군 지휘부(미드, 묘지능선 중앙 후방 · 앵글과 충분히 이격)
pe_em(ax, '🛡️', 19.8, Y_ANGLE + 2.6, zoom=0.20, z=17)
T(ax, '미드(포토맥군 사령부)', 20.6, Y_ANGLE + 1.7, sz=26, c='#0a1a6b', bg='#e8ecfb')

draw_title(ax, ['게티즈버그 전투 전략도  ', 'Gettysburg', '  (1863)'])

legend_items = [
    ('arr', '#ee2222', '남군 돌격'),
    ('dash', '#ee2222', '남군 패주'),
    ('arr', '#2255dd', '총검 역습'),
    ('emoji', '⚔️', '체임벌린'),
    ('emoji', '🛡️', '미드(사령부)'),
    ('dot_r', '#ee3333', '남군 보병'),
    ('dot_b', '#2255dd', '북군 보병'),
    ('dot', '#ffaa00', '요충지(고지)'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items, title=hj('爭地', '쟁지') + ' · 리틀 라운드 탑/더 앵글')

패군_rows = [
    ('전력+배치+보급', '북버지니아군 약 7만5천. 스튜어트 기병 이탈로 사흘간 적정 보고 단절, 원정이라 병참선이 늘어짐.'),
    ('지피(知彼)', '기병 부재로 북군 배치·규모를 정확히 모른 채 공격 결정 — 결정적 오판.'),
    ('지기(知己)', '챈슬러즈빌 연승을 과신, 정면돌파 능력을 과대평가(피켓의 돌격, 必死可殺).'),
    ('지지(知地)', '리틀 라운드 탑 등 쟁지를 북군이 먼저 점거했음에도 정면 강습을 고집.'),
    ('결과', "피켓의 돌격 실패로 약 1만2천 명 사상, 이후 공세 능력 상실."),
]
draw_analysis_box(ax, renderer, LX, '패군', '로버트 E. 리', 패군_rows, '#7a2020')

승군_rows = [
    ('전력+배치+보급', '포토맥군 약 9만3천. 본토 방어전이라 보급선이 짧고 안정적(散地의 이점).'),
    ('지피(知彼)', '남군의 측면 우회 의도를 사전 간파, 워런이 즉각 방어병력 투입.'),
    ('지기(知己)', '탄약 고갈 상황에서도 총검 돌격 능력을 정확히 판단, 역공 결단.'),
    ('지지(知地)', "고지라는 쟁지의 가치를 정확히 인식, '먼저 이르러 지킨다'를 실행."),
    ('결과', '리틀 라운드 탑 사수로 측면 우회 저지, 게티즈버그 승리의 결정적 축.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '체임벌린 / 미드', 승군_rows, '#1a3a7a')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gettysburg_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
