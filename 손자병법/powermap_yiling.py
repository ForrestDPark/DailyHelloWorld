#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국가 세력도 (보조 이미지) — 이릉대전(222년) 당시 삼국(위·촉·오) 정립 구도와
관우 사후 촉-오 관계 파탄. 전략지형도(map_yiling.py)와는 별개로, "이 전투
당시 주변에 어떤 세력들이 있었고 서로 어떤 관계였는가"만 간단히 보여주는
개략적 세력도.
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from strategy_map_lib import fnt, hj

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'yiling_powermap.png')

BG = '#f5f0e8'
BOX_EDGE = '#3a2f1e'
SHU_C = '#1f6a3f'   # 촉한(녹색)
WU_C = '#8a1f1f'    # 오(적색)
WEI_C = '#1f3f8a'   # 위(청색)

fig, ax = plt.subplots(figsize=(13, 9.5), dpi=160)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 13)
ax.set_ylim(0, 9.5)
ax.axis('off')

ax.add_patch(FancyBboxPatch((0, 8.7), 13, 0.8, boxstyle='square,pad=0',
                             fc='#0d0800', ec='none', zorder=24))
ax.text(6.5, 9.1, '이릉대전 국가 세력도  (222년, 삼국 정립기·관우 사후 촉-오 파탄)',
        fontproperties=fnt(21, True), color='#ffd700', ha='center', va='center', zorder=25)


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


# ── 세력 박스 배치 ──────────
LIUBEI = (3.0, 7.6)     # 유비(촉한, 원정군 지휘)
LUXUN = (10.0, 7.6)     # 육손(오, 방어군 지휘)
SUNQUAN = (10.0, 5.0)   # 손권(오 국주)
WEI_COURT = (10.0, 2.2) # 위(魏) 조정, 오의 배후를 견제하는 제3자
ZHUGE = (3.0, 5.0)      # 제갈량(성도 유수, 원정 불참)

box(*LIUBEI, 3.6, 1.3, hj('劉備', '유비'), '촉한 황제, 관우 복수 친정', SHU_C)
box(*LUXUN, 3.6, 1.3, hj('陸遜', '육손'), '오 대도독, 지구전 방어', WU_C)
box(*SUNQUAN, 3.4, 1.3, hj('孫權', '손권'), '오 국주, 육손에 전권 위임', WU_C)
box(*WEI_COURT, 3.4, 1.3, '위(魏) 조정', '조비, 오의 형식적 신속(臣屬) 수용', WEI_C)
box(*ZHUGE, 3.4, 1.3, hj('諸葛亮', '제갈량'), '성도 유수, 원정 미동행', SHU_C)

# ── 관계 화살표 ──
arrow(LIUBEI[0], LIUBEI[1] - 0.7, ZHUGE[0], ZHUGE[1] + 0.7, SHU_C, lw=2.6, curve=0.0)
label(3.0, 6.55, '원정 결단(간언 배제)', 10, SHU_C)

arrow(SUNQUAN[0], SUNQUAN[1] + 0.7, LUXUN[0], LUXUN[1] - 0.7, WU_C, lw=3.0, curve=0.0)
label(10.0, 6.55, '전권 위임', 10.5, WU_C)

arrow(SUNQUAN[0] - 0.2, SUNQUAN[1] - 0.7, WEI_COURT[0] - 0.2, WEI_COURT[1] + 0.7, WEI_C, dbl=True, lw=2.6, style=(0, (2, 3)), curve=0.1)
label(9.5, 3.6, '형식적 신속(배후 안정)', 10, WEI_C)

arrow(LIUBEI[0] + 1.8, LIUBEI[1] - 0.1, LUXUN[0] - 1.8, LUXUN[1] - 0.1, WU_C, dbl=True, lw=3.4, curve=0.05)
label(6.5, 8.2, '이릉대전(222)', 12, WU_C)

# ── 범례 ──
LEG = [
    (SHU_C, '-', '촉한 내부 지휘'),
    (WU_C, '-', '오 지휘·결전'),
    (WEI_C, (0, (2, 3)), '위-오 외교(배후 안정)'),
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
