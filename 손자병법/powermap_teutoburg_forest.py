#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국가 세력도 (보조 이미지) — 토이토부르크 숲 전투(CE 9) 당시 로마 제국과
게르마니아 부족들의 세력 구도. README 2번 섹션 "★ 국가 세력도" 스펙:
실사료 지도의 안정적인 직접 이미지 URL을 확보하지 못해(우선순위 2 경로)
원/사각형 도형 + 화살표만으로 구성한 개략도로 대체한다.
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from strategy_map_lib import fnt

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'teutoburg_forest_powermap.png')

BG = '#f5f0e8'
BOX_EDGE = '#3a2f1e'
ROME_C = '#8a1f1f'
GERM_C = '#1f5a2f'
NEUTRAL_C = '#6a6a5a'

fig, ax = plt.subplots(figsize=(13, 9.5), dpi=160)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 13)
ax.set_ylim(0, 9.5)
ax.axis('off')

ax.add_patch(FancyBboxPatch((0, 8.7), 13, 0.8, boxstyle='square,pad=0',
                             fc='#0d0800', ec='none', zorder=24))
ax.text(6.5, 9.1, '토이토부르크 숲 전투 국가 세력도  (CE 9)',
        fontproperties=fnt(24, True), color='#ffd700', ha='center', va='center', zorder=25)


def box(x, y, w, h, title, sub, face, text_c='white'):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                 boxstyle='round,pad=0.08,rounding_size=0.12',
                                 fc=face, ec=BOX_EDGE, lw=1.8, zorder=10))
    ax.text(x, y + 0.16, title, fontproperties=fnt(16, True, text=title),
            color=text_c, ha='center', va='center', zorder=11)
    ax.text(x, y - 0.26, sub, fontproperties=fnt(10.5, False, text=sub),
            color=text_c, ha='center', va='center', zorder=11)


def arrow(x1, y1, x2, y2, color, style='-', lw=2.6, curve=0.0, dbl=False, z=6):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle='-|>' if not dbl else '<|-|>',
                         mutation_scale=18, color=color, linewidth=lw,
                         linestyle=style, connectionstyle=f'arc3,rad={curve}', zorder=z)
    ax.add_patch(a)


def label(x, y, s, sz=10, c='#111'):
    ax.text(x, y, s, fontproperties=fnt(sz, True, text=s), color=c, ha='center', va='center',
            zorder=15, path_effects=[pe.withStroke(linewidth=3.5, foreground=BG)])


# ── 세력 배치(지리적 개략: 좌=서, 우=동 / 위=북, 아래=남) ──────────
ROME  = (2.1, 5.6)   # 로마 제국(라인강 서안, 갈리아 방면)
GERMLO = (2.1, 3.0)  # 로마 속주화 시도 대상: 라인강 동안 게르마니아(옛 속주)
CHER  = (6.5, 7.5)   # 케루스키족(아르미니우스)
CHAU  = (10.0, 7.5)  # 카우키족
MARS  = (5.0, 5.1)   # 마르시족
BRUC  = (7.2, 5.1)   # 브루크테리족
CHAT  = (9.4, 5.1)   # 카티족
SICA  = (11.6, 5.1)  # 시캄브리족

box(*ROME, 3.0, 1.4, '로마 제국', '아우구스투스 황제·바루스(총독)', ROME_C)
box(*GERMLO, 2.9, 1.1, '게르마니아 속주(옛)', '라인강 동안, 사실상 상실', NEUTRAL_C)
box(*CHER, 2.6, 1.0, '케루스키족', '아르미니우스', GERM_C)
box(*CHAU, 2.0, 0.9, '카우키족', '', GERM_C)
box(*MARS, 1.9, 0.9, '마르시족', '', GERM_C)
box(*BRUC, 2.1, 0.9, '브루크테리족', '', GERM_C)
box(*CHAT, 1.9, 0.9, '카티족', '', GERM_C)
box(*SICA, 2.1, 0.9, '시캄브리족', '', GERM_C)

# ── 관계 화살표 ──────────────────────────────────────────
arrow(ROME[0], ROME[1] - 0.75, GERMLO[0], GERMLO[1] + 0.6, ROME_C, curve=0.0, lw=3.0)
label(3.6, 4.3, '정복·속주화 시도\n(BCE 12~CE 9)', 9.5, ROME_C)

arrow(ROME[0] + 1.5, ROME[1] + 0.4, CHER[0] - 1.5, CHER[1] - 0.2, ROME_C, style=(0, (5, 4)), curve=-0.1)
label(4.9, 6.9, '보조부대 복무·\n로마 시민권(위장 충성)', 9, ROME_C)

arrow(CHER[0] - 0.9, CHER[1] - 0.6, MARS[0] + 0.4, MARS[1] + 0.55, GERM_C, dbl=True, curve=-0.1)
arrow(CHER[0] - 0.3, CHER[1] - 0.55, BRUC[0] - 0.1, BRUC[1] + 0.5, GERM_C, dbl=True, curve=0.05)
arrow(CHER[0] + 0.5, CHER[1] - 0.5, CHAT[0] - 0.3, CHAT[1] + 0.55, GERM_C, dbl=True, curve=0.1)
arrow(CHER[0] + 1.0, CHER[1] - 0.3, CHAU[0] - 0.4, CHAU[1] - 0.1, GERM_C, dbl=True, curve=-0.15)
arrow(CHAT[0] + 0.9, CHAT[1] + 0.1, SICA[0] - 1.0, SICA[1] + 0.05, GERM_C, dbl=True, curve=0.1)
label(6.5, 6.3, '부족연합\n(아르미니우스 결집)', 10, GERM_C)

arrow(GERMLO[0] + 1.3, GERMLO[1] + 0.4, MARS[0] - 0.9, MARS[1] - 0.9, GERM_C, lw=3.4, curve=0.15)
label(4.0, 2.9, '매복·타격\n(칼크리제, CE 9)', 9.5, GERM_C)

# ── 범례 (우하단 여백) ──────────────────────────────────
LEG = [
    (ROME_C, '-', '로마 지배·시도'),
    (GERM_C, '-', '게르만 부족연합·타격'),
    (ROME_C, (0, (5, 4)), '보조병 복무(위장 충성)'),
    (NEUTRAL_C, '-', '옛 속주(사실상 상실)'),
]
lx0, ly0 = 9.4, 3.0
for i, (c, ls, txt) in enumerate(LEG):
    ly = ly0 - i * 0.36
    ax.plot([lx0, lx0 + 0.55], [ly, ly], color=c, lw=2.6, linestyle=ls, zorder=20)
    ax.text(lx0 + 0.75, ly, txt, fontproperties=fnt(10, False, text=txt), color='#222',
            ha='left', va='center', zorder=20)

plt.tight_layout(pad=0.3)
plt.savefig(OUT, facecolor=BG)
print('saved:', OUT)
