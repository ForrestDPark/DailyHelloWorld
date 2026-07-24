#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국가 세력도 (보조 이미지) — 아우스터리츠 전투(1805) 당시 제3차 대프랑스동맹과
나폴레옹 제국·동맹국 구도. 전략지형도(map_austerlitz.py)와는 별개로,
"이 전투 당시 주변에 어떤 세력들이 있었고 서로 어떤 관계였는가"만 간단히
보여주는 개략적 세력도.
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from strategy_map_lib import fnt, hj

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'austerlitz_powermap.png')

BG = '#f5f0e8'
BOX_EDGE = '#3a2f1e'
FR_C = '#1f3f8a'    # 프랑스 제국(청)
AU_C = '#8a1f1f'    # 오스트리아 제국(적)
RU_C = '#1f6a3f'    # 러시아 제국(녹)
GER_C = '#6a4a1f'   # 독일 제후국(프랑스 동맹, 갈색)
UK_C = '#6a6a5a'    # 영국(제3차 동맹 배후, 회색)

fig, ax = plt.subplots(figsize=(13, 9.5), dpi=160)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 13)
ax.set_ylim(0, 9.5)
ax.axis('off')

ax.add_patch(FancyBboxPatch((0, 8.7), 13, 0.8, boxstyle='square,pad=0',
                             fc='#0d0800', ec='none', zorder=24))
ax.text(6.5, 9.1, '아우스터리츠 전투 국가 세력도  (1805, 제3차 대프랑스동맹 전쟁)',
        fontproperties=fnt(21, True), color='#ffd700', ha='center', va='center', zorder=25)


def box(x, y, w, h, title, sub, face, text_c='white'):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                 boxstyle='round,pad=0.08,rounding_size=0.12',
                                 fc=face, ec=BOX_EDGE, lw=1.8, zorder=10))
    ax.text(x, y + 0.18, title, fontproperties=fnt(16, True, text=title),
            color=text_c, ha='center', va='center', zorder=11)
    ax.text(x, y - 0.30, sub, fontproperties=fnt(10, False, text=sub),
            color=text_c, ha='center', va='center', zorder=11)


def arrow(x1, y1, x2, y2, color, style='-', lw=2.6, curve=0.0, dbl=False, z=6):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle='-|>' if not dbl else '<|-|>',
                         mutation_scale=18, color=color, linewidth=lw,
                         linestyle=style, connectionstyle=f'arc3,rad={curve}', zorder=z)
    ax.add_patch(a)


def label(x, y, s, sz=10.5, c='#111'):
    ax.text(x, y, s, fontproperties=fnt(sz, True, text=s), color=c, ha='center', va='center',
            zorder=15, path_effects=[pe.withStroke(linewidth=3.5, foreground=BG)])


# ── 세력 박스 배치 ──────────
FRANCE = (6.5, 7.6)     # 나폴레옹 1세(프랑스 제1제국)
AUSTRIA = (2.6, 5.0)    # 프란츠 1세(오스트리아 제국)
RUSSIA = (10.4, 5.0)    # 알렉산드르 1세(러시아 제국)
GERMANY = (6.5, 2.2)    # 바이에른 등 라인동맹 전신 제후국(프랑스 동맹)
UK = (10.4, 7.9)        # 영국(제3차 동맹 주도, 배후 지원)

box(*FRANCE, 3.6, 1.3, '나폴레옹 1세', '프랑스 제1제국, 그랑다르메 총사령관', FR_C)
box(*AUSTRIA, 3.4, 1.3, '프란츠 1세', '오스트리아 제국(신성로마제국 겸)', AU_C)
box(*RUSSIA, 3.4, 1.3, '알렉산드르 1세', '러시아 제국, 친정', RU_C)
box(*GERMANY, 3.6, 1.3, '바이에른 등 독일 제후국', '프랑스와 동맹, 후방 지원', GER_C)
box(*UK, 3.0, 1.1, '영국', '제3차 대프랑스동맹 주도·자금 지원', UK_C)

# ── 관계 화살표 ──
arrow(AUSTRIA[0] + 0.3, AUSTRIA[1] + 0.6, RUSSIA[0] - 0.3, RUSSIA[1] + 0.6, RU_C, dbl=True, lw=3.0, curve=-0.15)
label(6.5, 5.9, '제3차 대프랑스동맹(오·러 연합)', 10.5, RU_C)

arrow(UK[0] - 0.2, UK[1] - 0.5, RUSSIA[0] + 0.2, RUSSIA[1] + 0.7, UK_C, style=(0, (2, 3)), lw=2.0, curve=0.1)
label(10.9, 6.6, '자금·외교 지원', 9, UK_C)

arrow(FRANCE[0], FRANCE[1] - 0.7, GERMANY[0], GERMANY[1] + 0.7, FR_C, lw=2.6, curve=0.0)
label(6.5, 4.55, '동맹·병참 지원', 10, FR_C)

arrow(AUSTRIA[0] + 1.7, AUSTRIA[1] - 0.1, FRANCE[0] - 1.8, FRANCE[1] - 0.3, AU_C, dbl=True, lw=3.4, curve=0.1)
label(4.2, 6.5, '결전(아우스터리츠)', 10.5, AU_C)

arrow(RUSSIA[0] - 1.7, RUSSIA[1] - 0.1, FRANCE[0] + 1.8, FRANCE[1] - 0.3, RU_C, dbl=True, lw=3.4, curve=-0.1)
label(8.8, 6.5, '결전(아우스터리츠)', 10.5, RU_C)

# ── 범례 ──
LEG = [
    (RU_C, '-', '제3차 동맹(오·러) 연합·결전'),
    (FR_C, '-', '프랑스·동맹국 관계'),
    (UK_C, (0, (2, 3)), '영국의 배후 지원'),
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
