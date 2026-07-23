#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국가 세력도 (보조 이미지) — 크세노폰 만인대 원정(BCE 401~400) 당시
아케메네스 페르시아 내부 왕위 다툼과 그리스 용병대의 위치 구도.
전략지형도(map_anabasis.py)와는 별개로, "이 원정 당시 주변에 어떤
세력들이 있었고 서로 어떤 관계였는가"만 간단히 보여주는 개략적 세력도.
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from strategy_map_lib import fnt, hj

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'anabasis_powermap.png')

BG = '#f5f0e8'
BOX_EDGE = '#3a2f1e'
PERSIA_C = '#1f3f8a'   # 아케메네스 왕실(진한 청)
CYRUS_C = '#6a4a1f'    # 소(小)키루스 반란군(갈색)
GREEK_C = '#8a1f1f'    # 그리스 용병대(진한 적)
TRIBE_C = '#6a6a5a'    # 현지 부족(회색)

fig, ax = plt.subplots(figsize=(13, 9.5), dpi=160)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 13)
ax.set_ylim(0, 9.5)
ax.axis('off')

ax.add_patch(FancyBboxPatch((0, 8.7), 13, 0.8, boxstyle='square,pad=0',
                             fc='#0d0800', ec='none', zorder=24))
ax.text(6.5, 9.1, '크세노폰 만인대 원정 국가 세력도  (BCE 401~400, 아케메네스 왕위 다툼기)',
        fontproperties=fnt(20, True), color='#ffd700', ha='center', va='center', zorder=25)


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
KING = (7.2, 7.6)       # 아르타크세르크세스 2세(대왕, 수사)
CYRUS = (2.6, 7.6)      # 소(小)키루스(반란, 사르디스)
TISSA = (10.9, 5.0)     # 티사페르네스(총독, 추격군)
GREEKS = (2.6, 5.0)     # 그리스 만인대(크세노폰)
TRIBES = (2.6, 2.2)     # 카르두코이·아르메니아 등 현지 부족

box(*KING, 3.4, 1.3, hj('阿契美尼德', '아케메네스') + ' 왕실', '아르타크세르크세스 2세(대왕)', PERSIA_C)
box(*CYRUS, 3.4, 1.3, '소(小)키루스', '반란, 쿠낙사에서 전사', CYRUS_C)
box(*TISSA, 3.4, 1.3, '티사페르네스', '총독, 그리스군 추격 지휘', PERSIA_C)
box(*GREEKS, 3.4, 1.3, '그리스 만인대', '크세노폰 지휘, 고립 후퇴', GREEK_C)
box(*TRIBES, 3.6, 1.3, '카르두코이 등 현지 부족', '적대적 산악민, 통행 방해', TRIBE_C)

# ── 관계 화살표 ──
arrow(CYRUS[0] + 0.2, CYRUS[1] - 0.1, KING[0] - 1.7, KING[1] - 0.1, CYRUS_C, dbl=True, lw=3.4, curve=0.1)
label(4.9, 8.2, '쿠낙사 전투\n(왕위 다툼)', 10, CYRUS_C)

arrow(CYRUS[0], CYRUS[1] - 0.7, GREEKS[0], GREEKS[1] + 0.7, CYRUS_C, lw=2.6, curve=0.0)
label(2.6, 6.55, '용병 고용\n(키루스 전사 후 고립)', 9.5, CYRUS_C)

arrow(KING[0] + 0.3, KING[1] - 0.7, TISSA[0] - 0.6, TISSA[1] + 1.4, PERSIA_C, lw=3.0, curve=-0.1)
label(9.6, 6.7, '추격·섬멸 명령', 10, PERSIA_C)

arrow(TISSA[0] - 1.8, TISSA[1] - 0.2, GREEKS[0] + 1.8, GREEKS[1] - 0.1, PERSIA_C, dbl=True, lw=3.4, curve=0.05)
label(6.75, 4.55, '거짓 휴전 → 추격전', 10.5, PERSIA_C)

arrow(TRIBES[0] + 0.3, TRIBES[1] + 0.7, GREEKS[0] + 0.1, GREEKS[1] - 0.7, TRIBE_C, style=(0, (2, 3)), curve=0.1, lw=2.0)
label(2.9, 3.6, '산악 통과 저지\n(부분 교전)', 9.5, TRIBE_C)

# ── 범례 ──
LEG = [
    (CYRUS_C, '-', '반란·용병 고용'),
    (PERSIA_C, '-', '왕실 명령·추격전'),
    (TRIBE_C, (0, (2, 3)), '현지 부족의 저지'),
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
