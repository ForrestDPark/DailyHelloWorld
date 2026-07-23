#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국가 세력도 (보조 이미지) — 거록대전(BCE 207) 당시 진(秦)·초(楚)와
반진(反秦) 제후 연합 구도. 전략지형도(map_julu.py)와는 별개로, "이 전투
당시 주변에 어떤 세력들이 있었고 서로 어떤 관계였는가"만 간단히 보여주는
개략적 세력도(도식)다. 원/사각형 도형 + 화살표로만 구성한 단순 개략도
(README 2번 섹션 참조).
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from strategy_map_lib import fnt, hj

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'julu_powermap.png')

BG = '#f5f0e8'
BOX_EDGE = '#3a2f1e'
QIN_C = '#1f3f8a'    # 秦 계열(진한 청)
CHU_C = '#8a1f1f'    # 楚 계열(진한 적)
ALLY_C = '#6a6a5a'   # 제후 연합(회색)

fig, ax = plt.subplots(figsize=(13, 9.5), dpi=160)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 13)
ax.set_ylim(0, 9.5)
ax.axis('off')

ax.add_patch(FancyBboxPatch((0, 8.7), 13, 0.8, boxstyle='square,pad=0',
                             fc='#0d0800', ec='none', zorder=24))
ax.text(6.5, 9.1, '거록대전 국가 세력도  (BCE 207, 진말 반란기)',
        fontproperties=fnt(24, True), color='#ffd700', ha='center', va='center', zorder=25)


def box(x, y, w, h, title, sub, face, text_c='white'):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                 boxstyle='round,pad=0.08,rounding_size=0.12',
                                 fc=face, ec=BOX_EDGE, lw=1.8, zorder=10))
    ax.text(x, y + 0.18, title, fontproperties=fnt(17, True, text=title),
            color=text_c, ha='center', va='center', zorder=11)
    ax.text(x, y - 0.28, sub, fontproperties=fnt(10.5, False, text=sub),
            color=text_c, ha='center', va='center', zorder=11)


def arrow(x1, y1, x2, y2, color, style='-', lw=2.6, curve=0.0, dbl=False, z=6):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle='-|>' if not dbl else '<|-|>',
                         mutation_scale=18, color=color, linewidth=lw,
                         linestyle=style, connectionstyle=f'arc3,rad={curve}', zorder=z)
    ax.add_patch(a)


def label(x, y, s, sz=10.5, c='#111'):
    ax.text(x, y, s, fontproperties=fnt(sz, True, text=s), color=c, ha='center', va='center',
            zorder=15, path_effects=[pe.withStroke(linewidth=3.5, foreground=BG)])


# ── 세력 박스 배치(지리적 개략: 위=북, 아래=남) ──────────
QIN = (7.2, 7.6)      # 진(秦, 함양 조정 — 조고가 실권)
ZHAO = (2.8, 5.0)     # 조(趙, 거록성 농성)
CHU = (10.7, 5.0)     # 초(楚, 항우)
ALLIES = (2.8, 2.0)   # 관망하던 제후 연합(연·제·위 등)

box(*QIN, 3.1, 1.3, hj('秦', '진'), '조정 실권 조고 / 장한·왕리', QIN_C)
box(*ZHAO, 3.1, 1.3, hj('趙', '조'), '거록성 농성', ALLY_C)
box(*CHU, 3.1, 1.3, hj('楚', '초'), '항우(송의 참수 후 지휘권 탈취)', CHU_C)
box(*ALLIES, 3.5, 1.3, '제후 연합(관망)', '연·제·위 등, 초반 불참전', ALLY_C)

# ── 관계 화살표 ──
arrow(QIN[0] - 1.6, QIN[1] - 0.5, ZHAO[0] + 0.3, ZHAO[1] + 0.75, QIN_C, lw=3.2, curve=-0.1)
label(4.3, 6.9, '왕리군 포위\n(장한 후방 지원)', 10, QIN_C)

arrow(CHU[0] - 1.6, CHU[1] + 0.1, ZHAO[0] + 1.5, ZHAO[1] + 0.1, CHU_C, dbl=False, lw=3.4, curve=0.05)
label(6.75, 4.6, '구원(도하·용도 절단)', 10, CHU_C)

arrow(CHU[0] - 0.3, CHU[1] - 0.75, QIN[0] - 0.5, QIN[1] - 1.4, CHU_C, dbl=True, lw=3.6, curve=0.1)
label(8.3, 6.3, '거록 결전\n(BCE 207)', 10.5, CHU_C)

arrow(ALLIES[0] + 0.2, ALLIES[1] + 0.7, CHU[0] - 2.2, CHU[1] - 1.3, ALLY_C, style=(0, (2, 3)), curve=0.15, lw=2.0)
label(5.0, 3.0, '초반 관망\n(作壁上觀)', 9.5, ALLY_C)

arrow(ALLIES[0] + 1.0, ALLIES[1] + 1.3, CHU[0] - 2.0, CHU[1] - 0.3, CHU_C, style=(0, (1, 2)), curve=0.25, lw=1.8)
label(7.3, 2.2, '승전 후 항우 휘하 합류', 9, CHU_C)

# ── 범례 ──
LEG = [
    (QIN_C, '-', '진(秦) 포위·지원'),
    (CHU_C, '-', '초(楚) 구원·교전'),
    (ALLY_C, (0, (2, 3)), '제후 연합(초반 관망)'),
    (CHU_C, (0, (1, 2)), '승전 후 항우 휘하 합류'),
]
lx0, ly0 = 0.5, 0.9
for i, (c, ls, txt) in enumerate(LEG):
    ly = ly0 - i * 0.34
    ax.plot([lx0, lx0 + 0.55], [ly, ly], color=c, lw=2.6, linestyle=ls, zorder=20)
    ax.text(lx0 + 0.75, ly, txt, fontproperties=fnt(10.5, False, text=txt), color='#222',
            ha='left', va='center', zorder=20)

plt.tight_layout(pad=0.3)
plt.savefig(OUT, facecolor=BG)
print('saved:', OUT)
