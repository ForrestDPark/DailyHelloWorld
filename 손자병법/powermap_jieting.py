#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국가 세력도 (보조 이미지) — 가정 전투(CE 228) 당시 촉한(蜀漢)·위(魏)·오(吳)
삼국 구도와 제갈량의 제1차 북벌 지휘 체계. 전략지형도(map_jieting.py)와는
별개로, "이 전투 당시 주변에 어떤 세력들이 있었고 서로 어떤 관계였는가"만
간단히 보여주는 개략적 세력도.
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from strategy_map_lib import fnt, hj

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jieting_powermap.png')

BG = '#f5f0e8'
BOX_EDGE = '#3a2f1e'
SHU_C = '#1f6a3f'   # 촉한(녹색)
WEI_C = '#1f3f8a'   # 위(청색)
WU_C = '#8a1f1f'    # 오(적색, 참고용)

fig, ax = plt.subplots(figsize=(13, 9.5), dpi=160)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 13)
ax.set_ylim(0, 9.5)
ax.axis('off')

ax.add_patch(FancyBboxPatch((0, 8.7), 13, 0.8, boxstyle='square,pad=0',
                             fc='#0d0800', ec='none', zorder=24))
ax.text(6.5, 9.1, '가정 전투 국가 세력도  (CE 228, 삼국 정립기·제1차 북벌)',
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


# ── 세력 박스 배치 ──────────
ZHUGE = (3.0, 7.6)    # 제갈량(총사령관, 후방 본대)
MASU = (3.0, 5.0)     # 마속(선봉, 가정 방어)
ZHANGHE = (10.0, 5.0) # 장합(위 원군)
WEI_COURT = (10.0, 7.6)  # 위 조정(조예)
WU = (10.0, 2.2)      # 오(吳, 참고 — 이번 전투에 직접 개입 없음)

box(*ZHUGE, 3.4, 1.3, hj('諸葛亮', '제갈량'), '촉한 총사령관, 제1차 북벌', SHU_C)
box(*MASU, 3.4, 1.3, hj('馬謖', '마속'), '선봉장, 가정 방어 임무', SHU_C)
box(*ZHANGHE, 3.4, 1.3, hj('張郃', '장합'), '위 원군, 가정 급파', WEI_C)
box(*WEI_COURT, 3.4, 1.3, '위(魏) 조정', '조예(魏 明帝)', WEI_C)
box(*WU, 3.4, 1.3, '오(吳)', '이번 전투에 직접 개입 없음', WU_C)

# ── 관계 화살표 ──
arrow(ZHUGE[0], ZHUGE[1] - 0.7, MASU[0], MASU[1] + 0.7, SHU_C, lw=3.0, curve=0.0)
label(3.0, 6.55, '가정 방어 지시\n(산 아래 성읍 거점)', 9.5, SHU_C)

arrow(WEI_COURT[0], WEI_COURT[1] - 0.7, ZHANGHE[0], ZHANGHE[1] + 0.7, WEI_C, lw=3.0, curve=0.0)
label(10.0, 6.55, '가정 구원 명령', 10, WEI_C)

arrow(MASU[0] + 1.8, MASU[1] - 0.1, ZHANGHE[0] - 1.8, ZHANGHE[1] - 0.1, WEI_C, dbl=True, lw=3.4, curve=0.05)
label(6.5, 4.55, '가정 전투(CE 228)', 11, WEI_C)

arrow(ZHUGE[0] + 0.3, ZHUGE[1] + 0.6, WEI_COURT[0] - 0.3, WEI_COURT[1] + 0.6, '#6a5a3a', style=(0, (2, 3)), curve=-0.15, lw=1.8)
label(6.5, 8.5, '제1차 북벌(전체 전선)', 9.5, '#6a5a3a')

# ── 범례 ──
LEG = [
    (SHU_C, '-', '촉한 지휘·명령'),
    (WEI_C, '-', '위 지휘·전투'),
    ('#6a5a3a', (0, (2, 3)), '북벌 전체 구도'),
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
