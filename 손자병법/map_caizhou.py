#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""이소의 설야입채주(李愬雪夜入蔡州, 817년, 당 회서 토벌) 전략지형도

謹養而勿勞·倂氣積力·運兵計謀·爲不可測·投之無所往 실증 사례(승군 관점):
이소는 부임 후 일부러 약함을 가장해(謹養·倂氣) 오원제를 방심시키고, 항장
이우를 향도로 삼아 폭설의 밤에 문성책→장시촌(60리)→채주(70리) 130리를
아무도 예상 못 하게 강행(運兵計謀·爲不可測·深入)했다. 오원제의 주력
동중질은 회곡에 나가 있어 채주 본성은 노약병뿐이었다. 심입한 습격대는
퇴로 없는 결사(投之無所往·死且不北)로 새벽에 성벽을 넘어 오원제를 사로잡았다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(817)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 화북 평원, 겨울 대설. 대체로 평탄한 설원, 남서→북동으로 이어지는
#          완만한 기복과 여수(汝水) 저지 ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 50.0
elev += 6 * np.exp(-((LON - 0.75) ** 2) / 0.05)     # 북동쪽 약간 높은 대지
elev -= 10 * np.exp(-((LON - 0.55) ** 2) / 0.006)   # 여수(汝水) 저지
terrain_colors = [
    (0.0, '#9fb4c4'),    # 강 저지(설원 속)
    (0.3, '#dfe6ec'),    # 눈 덮인 평원
    (0.6, '#e9eef2'),
    (1.0, '#cdd6dc'),
]
draw_terrain(ax, elev, extent, terrain_colors)

T(ax, hj('爲不可測', '위불가측') + '·' + hj('深入', '심입') + ' — ' + hj('大雪', '대설') + '의 밤 130리 강행',
  0.2, MAP_Y1 - 0.55, sz=21, c='#20303c', bg='#eef3f6', ha='left')

# 주요 지점 좌표(캔버스)
X_WEN, Y_WEN = 3.2, MAP_Y0 + 1.6        # 문성책(이소 기지, 남서)
X_ZHANG, Y_ZHANG = 8.4, MAP_Y0 + 4.6    # 장시촌(중간 경유, 전초 요새)
X_CAI, Y_CAI = 15.0, MAP_Y0 + 7.4       # 채주성(목표, 오원제)
X_HUI, Y_HUI = 20.2, MAP_Y1 - 1.5       # 회곡(동중질 주력, 성 밖)
X_POND, Y_POND = 12.9, MAP_Y0 + 6.2     # 아압지

# ── 여수(汝水) — 채주 서쪽을 남북으로 흐름 ──
xr = X_CAI - 2.1 + 0.0 * np.linspace(0, 1, 300)
yv = np.linspace(MAP_Y0 + 0.5, MAP_Y1 - 0.5, 300)
xv_c = (X_CAI - 2.2) + 0.35 * np.sin(yv * 0.8) + 0.16 * np.sin(yv * 1.9)
ax.add_patch(__import__('matplotlib').patches.Polygon(
    list(zip(xv_c - 0.32, yv)) + list(zip((xv_c + 0.32)[::-1], yv[::-1])),
    fc='#6f9fc0', ec='#3f7398', lw=1.6, zorder=5, alpha=0.9))
T(ax, hj('汝水', '여수'), X_CAI - 2.6, MAP_Y0 + 9.4, sz=16, c='#20455f', bg='#e5eef4')

# ── 이소 습격대(승군, 공격, 적색) — 문성책→장시촌→채주 ──
# 행군 종대: 경로를 따라 scatter
def path_scatter(x1, y1, x2, y2, n, jitter=0.5, ms=70):
    t = np.linspace(0, 1, n)
    xs = x1 + t * (x2 - x1) + np.random.uniform(-jitter, jitter, n)
    ys = y1 + t * (y2 - y1) + np.random.uniform(-jitter, jitter, n)
    troops(ax, xs, ys, '#ee3333', ms=ms, alpha=0.82)

path_scatter(X_WEN + 0.4, Y_WEN + 0.3, X_ZHANG - 0.4, Y_ZHANG - 0.3, 34, 0.45, 62)
path_scatter(X_ZHANG + 0.3, Y_ZHANG + 0.3, X_CAI - 1.0, Y_CAI - 0.8, 40, 0.5, 66)

# 문성책
marker_point(ax, X_WEN, Y_WEN, ms=24, color='#cc2222')
pe_em(ax, '⚔️', X_WEN - 0.2, Y_WEN + 1.0, zoom=0.16, z=18)
T(ax, '이소(李愬) — ' + hj('文城柵', '문성책') + ' 출발', X_WEN + 0.3, Y_WEN - 1.0,
  sz=18, c='#7a0000', bg='#fbeaea', ha='left')

# 장시촌
marker_point(ax, X_ZHANG, Y_ZHANG, ms=20, color='#cc2222')
T(ax, hj('張柴村', '장시촌') + ' — 60리, 수졸 전멸·교량 차단', X_ZHANG + 0.4, Y_ZHANG - 1.0,
  sz=16, c='#7a2000', bg='#fbeee0', ha='left')

# 아압지
pe_em(ax, '🦆', X_POND, Y_POND, zoom=0.12, z=18)
T(ax, hj('鵝鴨池', '아압지') + ' — 새를 놀래 군 소리 은폐', X_POND - 0.2, Y_POND - 0.85,
  sz=15, c='#20455f', bg='#e5eef4', ha='left')

# ── 채주성(패군, 방어, 청색) — 오원제, 노약병 수비 ──
# 성벽 사각형
from matplotlib.patches import FancyBboxPatch as _FBP
ax.add_patch(_FBP((X_CAI - 1.15, Y_CAI - 1.0), 2.3, 2.0,
    boxstyle='square,pad=0', fc='#c9d6e6', ec='#1f52c0', lw=3.5, zorder=7, alpha=0.85))
n_gar = 26
troops(ax, X_CAI + np.random.uniform(-0.85, 0.85, n_gar),
       Y_CAI + np.random.uniform(-0.7, 0.7, n_gar), '#2f6fd8', ms=48, alpha=0.8)
pe_em(ax, '🛡️', X_CAI + 1.35, Y_CAI + 0.9, zoom=0.14, z=18)
T(ax, '오원제(吳元濟) — ' + hj('蔡州城', '채주성') + ', 노약병 수비', X_CAI, Y_CAI + 1.7,
  sz=18, c='#0a1a6b', bg='#e8ecfb')

# ── 회곡의 동중질 주력(성 밖, 회색조로 "부재" 강조) ──
n_hui = 55
troops(ax, X_HUI + np.random.uniform(-1.8, 1.8, n_hui),
       Y_HUI + np.random.uniform(-1.0, 1.0, n_hui), '#8fa0b5', ms=60, alpha=0.7)
pe_em(ax, '🐎', X_HUI - 2.2, Y_HUI + 0.2, zoom=0.14, z=17)
T(ax, '동중질(董重質) 주력 1만', X_HUI - 0.3, Y_HUI + 1.35, sz=17, c='#3a4a5a', bg='#eef1f4')
T(ax, hj('洄曲', '회곡') + '에 나가 성 방어 공백', X_HUI - 0.3, Y_HUI - 1.55, sz=15, c='#3a4a5a', bg='#eef1f4')

# ── 화살표 ──
arr(ax, X_WEN + 0.6, Y_WEN + 0.5, X_ZHANG - 0.5, Y_ZHANG - 0.4, '#ee2222', rad=0.08, hw=3.6, tw=1.9, z=12)
arr(ax, X_ZHANG + 0.5, Y_ZHANG + 0.5, X_CAI - 1.4, Y_CAI - 1.1, '#ee2222', rad=-0.08, hw=4.0, tw=2.1, z=12)
T(ax, '문성책→장시촌(60리)→채주(70리)', 6.0, MAP_Y0 + 6.4, sz=16, c='#7a0000', bg='#fff0e8', ha='left')
# 성벽 등반·입성
arr(ax, X_CAI - 1.3, Y_CAI - 1.0, X_CAI - 0.5, Y_CAI - 0.3, '#ff6600', rad=0.0, hw=3.0, tw=1.6, z=13)
T(ax, '사고(새벽) 성벽 등반 → 오원제 생포', X_CAI + 0.3, Y_CAI - 1.6, sz=15, c='#7a3800', bg='#fff2e2', ha='left')
# 동중질 주력은 성으로 오지 못함(차단)
arr(ax, X_HUI - 1.5, Y_HUI - 1.2, X_CAI + 2.2, Y_CAI + 0.6, '#8fa0b5', rad=0.2, hw=2.6, tw=1.3, z=11, dash=True)
T(ax, '주력 역습 차단(교량 절단)', X_HUI - 3.4, Y_HUI - 2.0, sz=14, c='#3a4a5a', bg='#eef1f4', ha='left')

draw_title(ax, ['이소의 설야입채주 전략도  ', '李愬雪夜入蔡州', '  (817)'])

legend_items = [
    ('arr', '#ee2222', '습격대 진격'),
    ('arr', '#ff6600', '성벽 등반'),
    ('dash', '#8fa0b5', '주력 역습(차단)'),
    ('emoji', '⚔️', '지휘관'),
    ('emoji', '🦆', '아압지'),
    ('emoji', '🐎', '기병'),
    ('dot_r', '#ee3333', '습격대(당)'),
    ('dot_b', '#2f6fd8', '오원제군'),
    ('dot', '#8fa0b5', '주력(성밖)'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items,
                title=hj('雪夜', '설야') + '·' + hj('不可測', '불가측'))

패군_rows = [
    ('道(지기)', '아버지 오소양의 죽음을 숨기고 자립한 오원제는 민심·군심의 결속이 약했고, 항장이 잇달아 이탈.'),
    ('天(지피)', '이소의 위장약세를 액면대로 믿어 방심, 폭설의 밤을 "설마 이런 날에"라며 정상화 편향으로 오판.'),
    ('地(지형)', '채주 본성은 여수·평원의 요지였으나, 주력을 회곡·북선에 빼내 정작 성 자체가 무방비.'),
    ('將', '智(위험 신호 재평가)·嚴(야간 경계)이 모두 부족 — 보고를 세 번이나 불신한 過信.'),
    ('法(전력배치)', '정예는 회곡의 동중질에게 집중, 성내는 노약병뿐. 동계 순찰·봉수가 사실상 마비.'),
    ('결과', '아성 함락·생포·처형. 北(적정을 헤아리지 못하고 무너짐), 회서 반란 종결.'),
]
draw_analysis_box(ax, renderer, LX, '패군', '오원제', 패군_rows, '#1a3a7a')

승군_rows = [
    ('道(지기)', '항장 이우를 빈객으로 대우하고 병자를 돌봐 결속을 쌓음. 조정(배도)이 감군을 혁파해 지휘를 일원화.'),
    ('天(지피)', '이광안의 북선 압박으로 오원제 정예가 회곡에 쏠린 틈과 대설의 밤을 정확히 포착(將能而君不御).'),
    ('地(지형)', '평원 130리를 폭설로 은폐, 아압지 새로 소음을 지우며 성 밑까지 무탐지 접근.'),
    ('將', '智(위장약세·향도 포섭·야습 설계)·勇(친정 강행)이 압도. 諸將 실색에도 결단 관철.'),
    ('法(전력배치)', '선봉·중군·후군 각 3천(총 9천). 별동대로 회곡·교량 차단, 경장 급습.'),
    ('결과', '오원제 생포. 以虞待不虞者勝·將能而君不御者勝의 정석.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '이소', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'caizhou_claude_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
