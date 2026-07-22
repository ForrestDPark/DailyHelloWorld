#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국가 세력도 (보조 이미지) — 부차·심하전투(1619) 당시 명·후금·조선·예허 세력 구도.
전략지형도(map_fucha_1619.py)와는 별개로, "이 전투 당시 주변에 어떤 나라들이
있었고 서로 어떤 관계였는가"만 간단히 보여주는 개략적 세력도(도식)다.
지리적으로 정확한 지도가 아니라 원/사각형 도형 + 화살표로만 구성한 단순
개략도(README 2번 섹션 참조).
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from strategy_map_lib import fnt, hj

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fucha_1619_powermap.png')

BG = '#f5f0e8'
BOX_EDGE = '#3a2f1e'
MING_C = '#1f3f8a'   # 明 계열(진한 청)
JIN_C = '#8a1f1f'    # 後金 계열(진한 적)
JOSEON_C = '#1f5a2f' # 朝鮮(진한 녹)
YEHE_C = '#6a6a5a'   # 예허(회색, 명 편에 가담한 여진 일파)

fig, ax = plt.subplots(figsize=(13, 9.5), dpi=160)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 13)
ax.set_ylim(0, 9.5)
ax.axis('off')

ax.add_patch(FancyBboxPatch((0, 8.7), 13, 0.8, boxstyle='square,pad=0',
                             fc='#0d0800', ec='none', zorder=24))
ax.text(6.5, 9.1, '부차·심하전투 국가 세력도  (1619, 사르후 전투)',
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


# ── 세력 박스 배치(지리적 개략: 위=북/만주, 아래=남/한반도) ──────────
MING  = (2.8, 7.6)   # 명(북경, 서방)
YEHE  = (10.7, 7.6)  # 예허 여진(명과 결탁, 후금과 대립)
JIN   = (7.2, 5.0)   # 후금(누르하치, 허투알라 — 중앙 만주)
JOSEON = (2.8, 2.0)  # 조선(남, 원정군 파병)

box(*MING, 3.1, 1.3, hj('明', '명'), '만력제 / 총사령 양호', MING_C)
box(*YEHE, 2.8, 1.2, '예허(葉赫) 여진', '해서여진, 명 편 참전', YEHE_C)
box(*JIN, 3.1, 1.3, hj('後金', '후금'), '누르하치(8기)', JIN_C)
box(*JOSEON, 3.1, 1.3, hj('朝鮮', '조선'), '광해군 / 강홍립·김경서', JOSEON_C)

# ── 관계 화살표 ────────────────────────────────────────
arrow(MING[0] + 1.6, MING[1] - 0.1, JIN[0] - 1.6, JIN[1] + 1.1, MING_C, dbl=False, lw=3.2, curve=-0.1)
label(5.2, 7.2, '4로 분산 정벌\n(양호 총지휘)', 10, MING_C)

arrow(YEHE[0] - 0.3, YEHE[1] - 0.65, JIN[0] + 1.2, JIN[1] + 1.15, YEHE_C, style=(0, (2, 3)), curve=0.1, lw=2.0)
label(9.7, 6.2, '명 편 가담\n(15,000 지원)', 9.5, YEHE_C)

arrow(MING[0] - 0.2, MING[1] - 0.7, JOSEON[0] - 0.2, JOSEON[1] + 0.7, MING_C, curve=0.0, lw=2.8)
label(1.15, 4.8, '참전 요청\n(재조지은 명분)', 9.5, MING_C)

arrow(JOSEON[0] + 1.6, JOSEON[1] + 0.5, JIN[0] - 1.7, JIN[1] - 0.9, MING_C, curve=0.12, lw=2.8)
label(4.3, 3.0, '조선원정군 파병\n(1만~1.3만)', 9.5, MING_C)

arrow(JIN[0] - 0.9, JIN[1] - 1.0, MING[0] + 0.4, MING[1] - 1.3, JIN_C, dbl=True, lw=3.6, curve=0.15)
label(3.6, 5.55, '교전(각개격파)\n아부달리·부차', 10, JIN_C)

arrow(JIN[0] - 0.2, JIN[1] - 1.15, JOSEON[0] + 1.0, JOSEON[1] + 1.0, JIN_C, lw=3.6, curve=-0.15)
label(6.0, 3.55, '역풍·돌파\n(부차, 좌영궤멸)', 10, JIN_C)

# ── 범례 ────────────────────────────────────────────
LEG = [
    (MING_C, '-', '명·조선 연합(정벌·참전)'),
    (JIN_C, '-', '후금의 교전·타격'),
    (YEHE_C, (0, (2, 3)), '예허(명 편 가담)'),
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
