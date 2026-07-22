#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국가 세력도 (보조 이미지) — 브라이텐펠트 전투(1631) 당시 신성로마제국 주변 세력 구도.
전략지형도(map_breitenfeld.py)와는 별개로, "이 전투 당시 주변에 어떤 나라들이 있었고
서로 어떤 외교관계였는가"만 간단히 보여주는 개략적 세력도(도식)다.
README 2번 섹션 "★ 국가 세력도" 스펙: 실사료 지도를 못 구했을 때의 우선순위 2(직접 제작) 경로.
지리적으로 정확한 지도가 아니라 원/사각형 도형 + 화살표로만 구성한 단순 개략도.
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from strategy_map_lib import fnt  # 기존 라이브러리의 한글/한자 폰트 자동감지 재사용

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'breitenfeld_powermap.png')

BG = '#f5f0e8'
BOX_EDGE = '#3a2f1e'
CATH_C = '#8a1f1f'   # 황제·가톨릭동맹 계열 (진한 적갈)
PROT_C = '#1f3f8a'   # 신교(스웨덴·작센) 계열 (진한 청)
NEUTRAL_C = '#6a6a5a'
SUPPORT_C = '#2f7a3a'

fig, ax = plt.subplots(figsize=(13, 9.5), dpi=160)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 13)
ax.set_ylim(0, 9.5)
ax.axis('off')

# ── 제목 배너 ──────────────────────────────────────────
ax.add_patch(FancyBboxPatch((0, 8.7), 13, 0.8, boxstyle='square,pad=0',
                             fc='#0d0800', ec='none', zorder=24))
ax.text(6.5, 9.1, '브라이텐펠트 전투 국가 세력도  (1631, 30년전쟁)',
        fontproperties=fnt(26, True), color='#ffd700', ha='center', va='center', zorder=25)


def box(x, y, w, h, title, sub, face, text_c='white'):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                 boxstyle='round,pad=0.08,rounding_size=0.12',
                                 fc=face, ec=BOX_EDGE, lw=1.8, zorder=10))
    ax.text(x, y + 0.16, title, fontproperties=fnt(17, True, text=title),
            color=text_c, ha='center', va='center', zorder=11)
    ax.text(x, y - 0.26, sub, fontproperties=fnt(11, False, text=sub),
            color=text_c, ha='center', va='center', zorder=11,
            path_effects=[pe.withStroke(linewidth=0, foreground=face)])


def arrow(x1, y1, x2, y2, color, style='-', lw=2.6, curve=0.0, dbl=False, z=6):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle='-|>' if not dbl else '<|-|>',
                         mutation_scale=18, color=color, linewidth=lw,
                         linestyle=style, connectionstyle=f'arc3,rad={curve}', zorder=z)
    ax.add_patch(a)


def label(x, y, s, sz=11, c='#111'):
    ax.text(x, y, s, fontproperties=fnt(sz, True, text=s), color=c, ha='center', va='center',
            zorder=15, path_effects=[pe.withStroke(linewidth=3.5, foreground=BG)])


# ── 세력 박스 배치 (지리적 개략 위치: 위=북, 아래=남) ──────────
FR   = (2.0, 7.0)   # 프랑스 (배후 재정지원국)
SW   = (7.0, 7.7)   # 스웨덴 (구스타프 아돌프)
BR   = (11.2, 6.6)  # 브란덴부르크 선제후국
SX   = (7.0, 5.0)   # 작센 선제후국 (요한 게오르크 1세)
EMP  = (7.0, 1.9)   # 황제(합스부르크)·가톨릭동맹 (틸리)

box(*FR, 2.6, 1.1, '프랑스', '재정 지원국', SUPPORT_C)
box(*SW, 2.9, 1.1, '스웨덴', '구스타프 아돌프', PROT_C)
box(*BR, 2.9, 1.1, '브란덴부르크', '선제후국', NEUTRAL_C)
box(*SX, 2.9, 1.1, '작센 선제후국', '요한 게오르크 1세', PROT_C)
box(*EMP, 4.2, 1.3, '신성로마제국 황제·가톨릭동맹', '페르디난트 2세 / 틸리 백작', CATH_C)

# ── 관계 화살표 ────────────────────────────────────────
arrow(FR[0] + 1.1, FR[1] - 0.2, SW[0] - 1.6, SW[1] + 0.1, SUPPORT_C, curve=-0.15)
label(4.15, 8.0, '지원(재정)\n바르발데 조약 1631.1', 10, SUPPORT_C)

arrow(SW[0], SW[1] - 0.6, SX[0], SX[1] + 0.6, PROT_C, dbl=True)
label(8.0, 6.35, '동맹\n1631.9.11', 10, PROT_C)

arrow(EMP[0] - 0.3, EMP[1] + 0.68, SX[0] - 0.3, SX[1] - 0.6, CATH_C, curve=0.1)
label(5.35, 3.4, '침공(적대)\n1631.9', 10, CATH_C)

arrow(EMP[0] + 1.5, EMP[1] + 0.6, SW[0] + 0.9, SW[1] - 1.3, CATH_C, dbl=True, lw=3.4, curve=-0.12)
label(9.9, 4.3, '교전\n1631.9.17\n브라이텐펠트', 10, CATH_C)

arrow(BR[0] - 0.4, BR[1] - 0.55, EMP[0] + 2.0, EMP[1] + 0.65, NEUTRAL_C, style=(0, (5, 4)), curve=0.12)
label(10.9, 4.3, '명목상 제국 소속\n실질 중립', 9.5, NEUTRAL_C)

# ── 범례 ────────────────────────────────────────────
LEG = [
    (PROT_C, '-', '동맹(신교 진영)'),
    (CATH_C, '-', '적대·교전(황제·가톨릭동맹)'),
    (SUPPORT_C, '-', '지원(재정)'),
    (NEUTRAL_C, (0, (5, 4)), '중립·명목상 소속'),
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
