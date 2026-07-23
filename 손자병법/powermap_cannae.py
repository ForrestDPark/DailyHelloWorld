#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국가 세력도 (보조 이미지) — 칸나에 전투(BCE 216) 당시 로마·카르타고와
주변 동맹 구도. 전략지형도(map_cannae.py)와는 별개로, "이 전투 당시
주변에 어떤 세력들이 있었고 서로 어떤 관계였는가"만 간단히 보여주는
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

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cannae_powermap.png')

BG = '#f5f0e8'
BOX_EDGE = '#3a2f1e'
ROME_C = '#1f3f8a'    # 로마 계열(진한 청)
CARTH_C = '#8a1f1f'   # 카르타고 계열(진한 적)
ALLY_C = '#6a6a5a'    # 각지 동맹·속국(회색)

fig, ax = plt.subplots(figsize=(13, 9.5), dpi=160)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 13)
ax.set_ylim(0, 9.5)
ax.axis('off')

ax.add_patch(FancyBboxPatch((0, 8.7), 13, 0.8, boxstyle='square,pad=0',
                             fc='#0d0800', ec='none', zorder=24))
ax.text(6.5, 9.1, '칸나에 전투 국가 세력도  (BCE 216, 제2차 포에니 전쟁)',
        fontproperties=fnt(22, True), color='#ffd700', ha='center', va='center', zorder=25)


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


# ── 세력 박스 배치(지리적 개략: 위=이탈리아 반도, 아래=지중해 서·남) ──
ROME = (3.0, 7.6)      # 로마 공화정(이탈리아 중부)
ALLIES = (10.7, 7.6)   # 이탈리아 동맹시(라틴·삼니움 등, 동요)
CARTH = (7.0, 5.0)     # 카르타고(한니발, 이탈리아 원정 중)
IBERIA = (2.8, 2.0)    # 카르타고령 이베리아(병력·자원 공급원)
NUMIDIA = (10.7, 2.0)  # 누미디아(기병 동맹)

box(*ROME, 3.1, 1.3, hj('Roma', '로마'), '집정관 파울루스·바로', ROME_C)
box(*ALLIES, 3.3, 1.2, '이탈리아 동맹시', '라틴·삼니움 등, 충성 동요', ALLY_C)
box(*CARTH, 3.1, 1.3, hj('Carthago', '카르타고'), '한니발(이탈리아 원정군)', CARTH_C)
box(*IBERIA, 3.1, 1.3, '카르타고령 이베리아', '병력·자원 공급 기지', CARTH_C)
box(*NUMIDIA, 3.1, 1.3, '누미디아', '경기병 동맹(마시니사 등)', ALLY_C)

# ── 관계 화살표 ──
arrow(ROME[0] + 1.6, ROME[1] - 0.1, ALLIES[0] - 1.7, ALLIES[1] - 0.05, ROME_C, lw=3.0, curve=-0.05)
label(6.8, 7.75, '동맹시 협약\n(병력 징발)', 10, ROME_C)

arrow(CARTH[0] - 0.2, CARTH[1] + 0.75, ROME[0] + 0.1, ROME[1] - 0.75, CARTH_C, dbl=True, lw=3.6, curve=0.1)
label(5.0, 6.35, '칸나에 결전\n(BCE 216.8.2)', 10.5, CARTH_C)

arrow(IBERIA[0] + 0.2, IBERIA[1] + 0.7, CARTH[0] - 0.9, CARTH[1] - 1.0, CARTH_C, style=(0, (2, 3)), curve=0.1, lw=2.2)
label(4.0, 3.5, '병력·보급 공급', 9.5, CARTH_C)

arrow(NUMIDIA[0] - 0.2, NUMIDIA[1] + 0.7, CARTH[0] + 0.9, CARTH[1] - 1.0, CARTH_C, style=(0, (2, 3)), curve=-0.1, lw=2.2)
label(9.6, 3.5, '경기병 파병', 9.5, CARTH_C)

arrow(ALLIES[0] - 0.6, ALLIES[1] - 0.7, CARTH[0] + 1.5, CARTH[1] + 0.6, ALLY_C, style=(0, (1, 2)), curve=-0.15, lw=1.8)
label(9.5, 6.3, '전후 이탈(카푸아 등\n일부 동맹시)', 9, ALLY_C)

# ── 범례 ──
LEG = [
    (ROME_C, '-', '로마 공화정·동맹시'),
    (CARTH_C, '-', '카르타고군 교전·보급선'),
    (CARTH_C, (0, (2, 3)), '카르타고 지원(이베리아·누미디아)'),
    (ALLY_C, (0, (1, 2)), '동맹 이탈(전후)'),
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
