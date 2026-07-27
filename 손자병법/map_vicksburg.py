#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""빅스버그 공성전(Siege of Vicksburg, 1863) 전략지형도 — Claude판

先奪其所愛 실증(서양): 링컨은 "빅스버그는 열쇠", 데이비스는 "남부를 붙드는
못대가리"라 불렀다. 그랜트는 강 정면(實)의 요새화를 피해 남쪽으로 도하한 뒤
배후(동)로 기동, 잭슨을 쳐 존스턴·펨버턴을 분리하고 챔피언 힐에서 각개격파했다.
정면강습(5.19·5.22)은 험형 방어선에 참패했으나, 포터 함대의 강상 통제로 보급을
완전 차단(圍地→死地)해 47일 만에 약 2만9천 대군을 통째로 항복시켰다 — 적이
가장 아끼던 미시시피강의 열쇠를 빼앗아 남부를 두 동강 냈다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from strategy_map_lib import *

np.random.seed(1863)

fig, ax, renderer = new_canvas()

extent = (0, 24, MAP_Y0, MAP_Y1)

# ── 지형: 서쪽=미시시피강 만곡 + 뢰스 절벽(도시), 동쪽=협곡 발달한 접근로 ──
lons = np.linspace(0, 1, 90)
lats = np.linspace(0, 1, 70)
LON, LAT = np.meshgrid(lons, lats)
elev = np.ones_like(LON) * 40.0
elev += 95 * np.exp(-(((LON - 0.20) ** 2) / 0.012))                                   # 강 동안의 높은 뢰스 절벽대(도시)
elev += 30 * np.exp(-(((LON - 0.48) ** 2) / 0.03 + ((LAT - 0.5) ** 2) / 0.5))         # 방어선 능선
elev -= 30 * np.exp(-(((LON - 0.07) ** 2) / 0.006))                                    # 강 저지
# 협곡(ravine) 지표: 동쪽 접근로에 종횡의 골
for rc in (0.30, 0.44, 0.58, 0.70):
    elev -= 14 * np.exp(-(((LON - rc) ** 2) / 0.0016))
terrain_colors = [
    (0.0, '#8aa0b8'),
    (0.22, '#b9b090'),
    (0.5, '#b0a878'),
    (0.75, '#8f9a5c'),
    (1.0, '#5f7040'),
]
draw_terrain(ax, elev, extent, terrain_colors)

# ── 미시시피강(서쪽, 세로, 만곡) ──
draw_river(ax, 2.3, MAP_Y0, MAP_Y1, amplitude=0.7, freq1=0.55, amp2=0.3, freq2=1.3,
           width=0.62, flow_up=False)
T(ax, hj('Mississippi', '미시시피') + '강', 1.1, MAP_Y1 - 1.2, sz=24, c='#0a3550', bg='#eaf3f8', ha='left')
T(ax, '뢰스 절벽 — 강상 함포로\n정면 공략 불가', 4.9, MAP_Y1 - 2.4, sz=22, c='#2a2010', bg='#efe7cf')

# 포터 함대(강상 통제, 4.16 야간 포대 통과)
for fy in (MAP_Y0 + 1.4, MAP_Y0 + 3.0, MAP_Y0 + 4.6):
    troops(ax, [2.3], [fy], '#ee3333', ms=140, alpha=0.9)
T(ax, '포터 함대 — 강상 통제\n(4.16 포대 통과)', 2.5, MAP_Y0 + 0.4, sz=20, c='#7a0000', bg='#fbeaea', ha='left')

# ── 도시(빅스버그) ──
pe_em(ax, '🛡️', 4.4, 13.7, zoom=0.20, z=17)
T(ax, '빅스버그 요새도시', 4.5, 12.4, sz=24, c='#0a1a6b', bg='#e8ecfb')
T(ax, hj('險形', '험형') + ' · ' + hj('圍地→死地', '위지→사지'), 4.6, 11.3, sz=21, c='#5a1010', bg='#f6ecec')

# ── 남부(펨버턴) 수비대: 도시를 감싼 반원형 9마일 토루(파랑, 방자) ──
cx, cy = 5.2, 13.6
thetas = np.linspace(np.deg2rad(-46), np.deg2rad(46), 120)
R = 5.6 + 0.2 * np.sin(thetas * 5)
arc_x = cx + R * np.cos(thetas)
arc_y = cy + R * np.sin(thetas)
jitter = np.random.uniform(-0.26, 0.26, len(arc_x))
troops(ax, arc_x + jitter, arc_y + jitter, '#2255dd', ms=95, alpha=0.82)
T(ax, '펨버턴 수비대\n반원형 9마일 토루(4개 사단)', 7.0, cy - 0.2, sz=20, c='#0a1a6b', bg='#e8ecfb')

# 주요 보루 3거점(요충지 마커 + 라벨)
def redoubt(theta_deg, name, note, dy=-1.0):
    th = np.deg2rad(theta_deg)
    x = cx + 5.9 * np.cos(th)
    y = cy + 5.9 * np.sin(th)
    marker_point(ax, x, y, ms=28, color='#ffaa00')
    T(ax, name + '\n' + note, x, y + dy, sz=19, c='#2a2010', bg='#fff2d8')
    return x, y

rx_n, ry_n = redoubt(46, '스톡케이드 리댄(북)', '5.19 셔먼 강습 격퇴', dy=-0.95)
rx_c, ry_c = redoubt(2, '제3루이지애나 리댄(중앙)', '6.25 갱도 폭파', dy=1.0)
rx_s, ry_s = redoubt(-46, '레일로드 리다우트(남)', '5.22 매클러낸드 강습 격퇴', dy=1.0)

# ── 연방(그랜트) 포위군: 반원 바깥(동쪽)에 3개 축선(빨강, 공자) ──
def union_block(bx, by, n=42, sp=1.5):
    gx = bx + np.random.uniform(-sp, sp, n)
    gy = by + np.random.uniform(-1.2, 1.2, n)
    troops(ax, gx, gy, '#ee3333', ms=90, alpha=0.8)

union_block(14.5, 16.9)   # 북(셔먼 XV군단)
union_block(16.2, 13.6)   # 중앙(맥퍼슨 XVII군단)
union_block(14.5, 10.3)   # 남(매클러낸드→오드 XIII군단)
pe_em(ax, '⚔️', 17.6, 13.6, zoom=0.20, z=17)
T(ax, '그랜트 테네시군 — 포위 7.7만', 18.2, 13.6, sz=21, c='#7a0000', bg='#fbeaea', ha='left')
T(ax, '셔먼 XV', 14.5, 18.2, sz=20, c='#7a0000', bg='#fbeaea')
T(ax, '맥퍼슨 XVII', 18.6, 15.6, sz=20, c='#7a0000', bg='#fbeaea')
T(ax, '매클러낸드→오드 XIII', 14.5, 8.7, sz=20, c='#7a0000', bg='#fbeaea')

# ── 그랜트 배후 기동(남쪽 브루인즈버그 도하 → 동으로 우회) ──
arr(ax, 13.5, MAP_Y0 + 0.5, 15.5, 11.7, '#ee2222', rad=-0.35, hw=4.2, tw=2.4, z=10)
T(ax, '남쪽 도하 후 배후(동)로 기동\n' + hj('避實擊虛', '피실격허'),
  19.0, MAP_Y0 + 1.1, sz=19, c='#7a0000', bg='#fff0e8', ha='left')

# ── 정면 강습(실선) → 격퇴 패주(점선) ──
arr(ax, 13.3, 16.8, rx_n + 0.5, ry_n, '#ee2222', rad=0.1, hw=4.0, tw=2.2, z=10)     # 5.19 북
arr(ax, rx_n + 0.7, ry_n - 0.4, 13.4, 16.2, '#ee2222', rad=0.15, dash=True, hw=2.4, tw=1.2, z=9)
arr(ax, 13.3, 10.3, rx_s + 0.5, ry_s, '#ee2222', rad=-0.1, hw=4.0, tw=2.2, z=10)     # 5.22 남
arr(ax, rx_s + 0.7, ry_s + 0.4, 13.4, 10.9, '#ee2222', rad=-0.15, dash=True, hw=2.4, tw=1.2, z=9)
# 중앙 갱도 폭파(화공/특수)
pe_em(ax, '🔥', rx_c + 0.15, ry_c, zoom=0.14, z=18)
arr(ax, 15.6, 13.6, rx_c + 0.6, ry_c, '#ff6600', rad=0.0, hw=3.6, tw=1.9, z=11)

# 47일 포위·굴착 표시(연방 참호 병렬선)
for k, rr in enumerate((6.7, 7.2)):
    tx = cx + rr * np.cos(thetas)
    ty = cy + rr * np.sin(thetas)
    ax.plot(tx, ty, color='#7a1010', lw=1.4, ls=(0, (4, 3)), alpha=0.5, zorder=7)
T(ax, '47일 포위·참호·굴착 — 보급 완전 차단', 9.5, MAP_Y1 - 0.55, sz=20, c='#7a0000', bg='#fff0e8')

draw_title(ax, ['빅스버그 공성전 전략도  ', 'Vicksburg', '  (1863)'])

legend_items = [
    ('arr', '#ee2222', '연방 강습/기동'),
    ('dash', '#ee2222', '강습 격퇴·패주'),
    ('arr', '#ff6600', '갱도 폭파'),
    ('emoji', '⚔️', '그랜트'),
    ('emoji', '🛡️', '빅스버그(펨버턴)'),
    ('dot_r', '#ee3333', '연방군(포위)'),
    ('dot_b', '#2255dd', '남부군(수비)'),
    ('dot', '#ffaa00', '요충지(보루)'),
]
draw_legend_box(ax, renderer, LX + BW + GAP, legend_items,
                title=hj('先奪其所愛', '선탈기소애') + ' · 미시시피의 열쇠')

패군_rows = [
    ('道(지기)', '북부 태생의 불신 속에 데이비스 "사수" 명령에 과잉 순응 — 존스턴의 "버리고 합류하라"와 충돌해 수뇌부 결속 붕괴.'),
    ('天(지피)', '존스턴 구원군의 규모·의지를 오판, "곧 온다"는 통제 불가 변수에 도박.'),
    ('地(지형)', '험형 요새의 이점을 안았으나 강·적군에 삼면이 막혀 圍地→死地로 전락.'),
    ('將(장수)', '必生可虜 — 진지·자산 집착. 모호성 회피로 챔피언 힐서 병력 어정쩡 분할.'),
    ('法(전력배치)', '약 3만, 스티븐슨·포니·스미스·보웬 4개 사단. 47일 포위로 군량 고갈(노새·쥐 고기).'),
    ('결과', '약 2만9천 전군 항복 — 北(요적 실패). 미시시피강 개방·남부 분단.'),
]
draw_analysis_box(ax, renderer, LX, '패군', '펨버턴', 패군_rows, '#1a3a7a')

승군_rows = [
    ('道(지기)', '링컨·핼렉의 재량 위임(君不御), 군단장과 신뢰 결속 — 셔먼조차 반대한 도하를 관철.'),
    ('天(지피)', '요새화된 정면(實)을 피해 남·동(虛)으로 우회, 잭슨을 쳐 존스턴·펨버턴을 分.'),
    ('地(지형)', '험형 정면강습(5.19·5.22) 참패를 즉시 인정, 포위·굴착으로 전환.'),
    ('將(장수)', '智(도하·병참 설계)·勇(계산된 모험) — 실패를 빠르게 접고 승률 누적.'),
    ('法(전력배치)', '테네시군 3.5만→7.7만, 포터 함대 강상통제로 무제한 재보급.'),
    ('결과', '빅스버그 함락 — 將能而君不御者勝·以虞待不虞者勝.'),
]
draw_analysis_box(ax, renderer, LX + 2 * (BW + GAP), '승군', '그랜트', 승군_rows, '#7a2020')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vicksburg_claude_map.png')
fig.savefig(out, dpi=DPI, facecolor='#f5f0e8')
print('saved', out)
