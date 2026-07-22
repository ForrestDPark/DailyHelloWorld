#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국가 세력도 (보조 이미지) — 필(邲) 전투(BCE 597) 당시 춘추시대 열국 구도.
전략지형도(map_bi.py)와는 별개로, "이 전투 당시 주변에 어떤 나라들이 있었고
서로 어떤 관계였는가"만 간단히 보여주는 개략적 세력도(도식)다. 지리적으로 정확한
지도가 아니라 원/사각형 도형 + 화살표로만 구성한 단순 개략도 (README 2번 섹션 참조).
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from strategy_map_lib import fnt, hj

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bi_powermap.png')

BG = '#f5f0e8'
BOX_EDGE = '#3a2f1e'
JIN_C = '#1f3f8a'    # 晉 계열 (진한 청)
CHU_C = '#8a1f1f'    # 楚 계열 (진한 적)
ZHENG_C = '#9a7a1f'  # 鄭 (구지, 황토색)
QI_C = '#4a4a4a'     # 齊 (관망 세력, 회색)

fig, ax = plt.subplots(figsize=(13, 9.5), dpi=160)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 13)
ax.set_ylim(0, 9.5)
ax.axis('off')

ax.add_patch(FancyBboxPatch((0, 8.7), 13, 0.8, boxstyle='square,pad=0',
                             fc='#0d0800', ec='none', zorder=24))
ax.text(6.5, 9.1, '필(邲) 전투 국가 세력도  (BCE 597, 춘추시대)',
        fontproperties=fnt(26, True), color='#ffd700', ha='center', va='center', zorder=25)


def box(x, y, w, h, title, sub, face, text_c='white'):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                 boxstyle='round,pad=0.08,rounding_size=0.12',
                                 fc=face, ec=BOX_EDGE, lw=1.8, zorder=10))
    ax.text(x, y + 0.16, title, fontproperties=fnt(18, True, text=title),
            color=text_c, ha='center', va='center', zorder=11)
    ax.text(x, y - 0.28, sub, fontproperties=fnt(11, False, text=sub),
            color=text_c, ha='center', va='center', zorder=11)


def arrow(x1, y1, x2, y2, color, style='-', lw=2.6, curve=0.0, dbl=False, z=6):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle='-|>' if not dbl else '<|-|>',
                         mutation_scale=18, color=color, linewidth=lw,
                         linestyle=style, connectionstyle=f'arc3,rad={curve}', zorder=z)
    ax.add_patch(a)


def label(x, y, s, sz=11, c='#111'):
    ax.text(x, y, s, fontproperties=fnt(sz, True, text=s), color=c, ha='center', va='center',
            zorder=15, path_effects=[pe.withStroke(linewidth=3.5, foreground=BG)])


# ── 세력 박스 배치 (지리적 개략 위치: 위=북, 아래=남) ──────────
JIN  = (6.6, 7.7)   # 晉 (북, 패자 경쟁국)
QI   = (11.0, 7.2)  # 齊 (동, 독자 세력·관망)
ZH   = (6.6, 4.6)   # 鄭 (중앙, 구지 — 진·초 사이에 낀 접경국)
CHU  = (6.6, 1.7)   # 楚 (남, 초장왕)

box(*JIN, 3.0, 1.15, hj('晉','진'), '진경공 / 순림보', JIN_C)
box(*QI, 2.6, 1.15, hj('齊','제'), '독자 세력', QI_C)
box(*ZH, 3.0, 1.15, hj('鄭','정'), '구지(衢地) — 접경국', ZHENG_C)
box(*CHU, 3.0, 1.15, hj('楚','초'), '초장왕 / 손숙오', CHU_C)

# ── 관계 화살표 ────────────────────────────────────────
arrow(JIN[0] - 1.75, JIN[1] - 0.45, CHU[0] - 1.75, CHU[1] + 0.45, '#7a1f1f', dbl=True, lw=3.4, curve=-0.2, z=5)
label(3.35, 4.6, '패권 다툼\n(진초쟁패)', 10.5, '#7a1f1f')

arrow(CHU[0] + 0.3, CHU[1] + 0.6, ZH[0] + 0.3, ZH[1] - 0.6, CHU_C, curve=-0.08)
label(8.15, 3.05, '복속(항복)\nBCE 597', 10, CHU_C)

arrow(ZH[0] - 0.3, ZH[1] - 0.6, JIN[0] - 0.3, JIN[1] + 0.6, JIN_C, style=(0, (5, 4)), curve=-0.08)
label(5.15, 6.0, '이반\n(구원 실패)', 10, JIN_C)

arrow(QI[0] - 0.7, QI[1] - 0.55, JIN[0] + 1.35, JIN[1] + 0.2, QI_C, style=(0, (2, 3)), curve=0.1, lw=2.0)
label(9.6, 8.35, '패권 관망\n(독자 세력)', 9.5, QI_C)

# ── 범례 ────────────────────────────────────────────
LEG = [
    (CHU_C, '-', '적대·패권 다툼 / 복속'),
    (JIN_C, '-', '기존 우호(연결선)'),
    (JIN_C, (0, (5, 4)), '이반·구원 실패'),
    (QI_C, (0, (2, 3)), '중립·독자 세력(관망)'),
]
lx0, ly0 = 0.5, 0.35
for i, (c, ls, txt) in enumerate(LEG):
    ly = ly0 + (len(LEG) - 1 - i) * 0.32
    ax.plot([lx0, lx0 + 0.55], [ly, ly], color=c, lw=2.6, linestyle=ls, zorder=20)
    ax.text(lx0 + 0.75, ly, txt, fontproperties=fnt(10.5, False, text=txt), color='#222',
            ha='left', va='center', zorder=20)

plt.tight_layout(pad=0.3)
plt.savefig(OUT, facecolor=BG)
print('saved:', OUT)
