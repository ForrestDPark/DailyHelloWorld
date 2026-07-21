#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
전략지형도 공통 라이브러리 (구지편 첫구절: 정형전투 / 아쟁쿠르전투)

v2: 텍스트 폭 실측 기반 줄바꿈, 정보박스 세로 채움 자동 분배,
    하단 3박스 캔버스 중앙 정렬, 한자 옆 독음 표기 헬퍼(hj) 추가.
"""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.patheffects as pe
import matplotlib.offsetbox as ob
from matplotlib.patches import FancyBboxPatch, Polygon
from matplotlib.colors import LightSource
import matplotlib.colors as mcolors
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = '/System/Library/Fonts/AppleSDGothicNeo.ttc'
FALLBACK_FONT_PATH = '/System/Library/Fonts/STHeiti Medium.ttc'
EMOJI_PATH = '/System/Library/Fonts/Apple Color Emoji.ttc'

_main_ft = fm.get_font(FONT_PATH)


def _needs_fallback(s):
    for c in s:
        if ord(c) > 127 and _main_ft.get_char_index(ord(c)) == 0:
            return True
    return False


def fnt(size, bold=False, text=None):
    path = FALLBACK_FONT_PATH if (text and _needs_fallback(text)) else FONT_PATH
    fp = fm.FontProperties(fname=path, size=size)
    if bold:
        fp.set_weight('bold')
    return fp


def hj(hanja_text, reading):
    """한자 표기 + 옆에 한글 독음. 예: hj('隘地','애지') -> '隘地(애지)'"""
    return f'{hanja_text}({reading})'


_emoji_cache = {}


def make_emoji(e, px=160):
    if e in _emoji_cache:
        return _emoji_cache[e]
    font = ImageFont.truetype(EMOJI_PATH, px)
    img = Image.new('RGBA', (px + 20, px + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((10, 10), e, font=font, embedded_color=True)
    arr = np.asarray(img)
    _emoji_cache[e] = arr
    return arr


def pe_em(ax, e, x, y, zoom=0.22, z=20):
    ax.add_artist(ob.AnnotationBbox(
        ob.OffsetImage(make_emoji(e), zoom=zoom),
        (x, y), frameon=False, zorder=z))


def troops(ax, xs, ys, color, ms=256, alpha=0.82, z=8):
    ax.scatter(xs, ys, s=ms, c=color, alpha=alpha, zorder=z,
               edgecolors='white', linewidths=0.5)


def arr(ax, x1, y1, x2, y2, color, rad=0.15, hw=4.0, tw=2.3,
        alpha=0.90, z=11, dash=False):
    ls = (0, (8, 4)) if dash else 'solid'
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle=f'fancy,head_width={hw},head_length={hw*0.6},tail_width={tw}',
            color=color, alpha=alpha, mutation_scale=20,
            connectionstyle=f'arc3,rad={rad}',
            linestyle=ls), zorder=z)


def T(ax, s, x, y, sz=40, c='#111', ha='center', va='center',
      bold=True, bg='white', bw=6):
    ax.text(x, y, s, fontproperties=fnt(sz, bold, text=s),
            color=c, ha=ha, va=va, zorder=25,
            path_effects=[pe.withStroke(linewidth=bw, foreground=bg)])


def marker_point(ax, x, y, ms=26, color='#ffaa00', z=12):
    ax.plot(x, y, 'o', ms=ms, color='none', mec=color, mew=3.5, zorder=z)


# ── 캔버스 상수 ──────────────────────────────────────────────
FIGSIZE = (24, 20)
DPI = 155
XLIM = (0, 24)
YLIM = (0, 20)
MAP_Y0 = 8.2
MAP_Y1 = 19.2
INFO_Y0 = 0.3
INFO_Y1 = 7.9
BW = 7.0
BH = INFO_Y1 - INFO_Y0
GAP = 0.3
# 3개 박스 + 2개 간격을 캔버스(0~24) 정중앙에 배치
LX = (24 - (3 * BW + 2 * GAP)) / 2

TITLE_SZ = 56
LB_TTL = round(44 * 0.8)
LB_SZ = round(40 * 0.8)
LB_SUB = round(29 * 0.8)
LB_LEG = 32


def new_canvas():
    fig = plt.figure(figsize=FIGSIZE, dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(*XLIM)
    ax.set_ylim(*YLIM)
    ax.axis('off')
    fig.patch.set_facecolor('#f5f0e8')
    ax.set_facecolor('#f5f0e8')
    # renderer를 미리 확보해 텍스트 폭 실측에 사용
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    return fig, ax, renderer


def draw_title(ax, parts):
    """parts: 문자열(단일 폰트로 충분할 때) 또는 스크립트가 섞여 폴백이 필요한
    문자열들의 리스트(각각을 이어붙여 렌더링, 혼합 글리프 누락 방지)."""
    ax.add_patch(FancyBboxPatch((0, MAP_Y1), 24, 0.80,
        boxstyle='square,pad=0', fc='#0d0800', ec='none', zorder=24))
    if isinstance(parts, str):
        parts = [parts]

    def _w(p):
        return sum(0.55 if ord(c) < 256 else 1.0 for c in p)

    widths = [_w(p) for p in parts]
    total = sum(widths) or 1
    start = 12 - (total / 2)
    cursor = start
    for p, w in zip(parts, widths):
        cx = cursor + w / 2
        ax.text(cx, MAP_Y1 + 0.40, p,
                fontproperties=fnt(TITLE_SZ, True, text=p), color='#ffd700',
                ha='center', va='center', zorder=25)
        cursor += w


def draw_terrain(ax, elev, extent, terrain_colors):
    ls = LightSource(azdeg=315, altdeg=45)
    cmap_terrain = mcolors.LinearSegmentedColormap.from_list('t', terrain_colors)
    rgb = ls.shade(elev, cmap=cmap_terrain, vmin=elev.min(), vmax=elev.max(),
                   blend_mode='soft', vert_exag=8)
    ax.imshow(rgb, extent=extent, origin='lower', aspect='auto', zorder=1)
    lon = np.linspace(extent[0], extent[1], elev.shape[1])
    lat = np.linspace(extent[2], extent[3], elev.shape[0])
    LON, LAT = np.meshgrid(lon, lat)
    levels = np.linspace(elev.min(), elev.max(), 8)[1:-1]
    ax.contour(LON, LAT, elev, levels=levels, colors='#5a4a30',
               linewidths=0.4, alpha=0.35, zorder=2)


def draw_river(ax, base_x, y0, y1, amplitude, freq1, amp2, freq2, width,
               fc='#4a9ac8', ec='#2a7aaa', flow_up=True):
    ry = np.linspace(y0, y1, 300)
    rx_c = base_x + amplitude * np.sin(ry * freq1) + amp2 * np.sin(ry * freq2)
    rx_l = rx_c - width
    rx_r = rx_c + width
    ax.add_patch(Polygon(
        list(zip(rx_l, ry)) + list(zip(rx_r[::-1], ry[::-1])),
        fc=fc, ec=ec, lw=2, zorder=5, alpha=0.92))
    i1, i2 = (80, 260) if flow_up else (260, 80)
    ax.annotate('', xy=(rx_c[i2], ry[i2]), xytext=(rx_c[i1], ry[i1]),
        arrowprops=dict(arrowstyle='->', color=ec, lw=2, mutation_scale=14),
        zorder=6)


# ════════════════════════════════════════════════════════════
# 텍스트 폭 실측 + 자동 줄바꿈/세로 채움 분배
# ════════════════════════════════════════════════════════════

def _text_width_data(ax, renderer, s, fontprop):
    if not s:
        return 0.0
    t = ax.text(0, 0, s, fontproperties=fontprop, alpha=0)
    bbox = t.get_window_extent(renderer=renderer)
    t.remove()
    inv = ax.transData.inverted()
    x0, _ = inv.transform((bbox.x0, bbox.y0))
    x1, _ = inv.transform((bbox.x1, bbox.y1))
    return abs(x1 - x0)


def wrap_by_width(ax, renderer, text, fontprop, max_width_data):
    """실제 렌더 폭을 측정해 max_width_data를 넘지 않도록 줄바꿈."""
    lines = []
    current = ''
    for ch in text:
        trial = current + ch
        w = _text_width_data(ax, renderer, trial, fontprop)
        if w > max_width_data and current:
            lines.append(current)
            current = ch
        else:
            current = trial
    if current:
        lines.append(current)
    return lines or ['']


def draw_legend_box(ax, renderer, x0, items, title='범례'):
    y0 = INFO_Y0
    ax.add_patch(FancyBboxPatch((x0, y0), BW, BH,
        boxstyle='round,pad=0.08,rounding_size=0.15',
        fc='#fffdf7', ec='#6b5636', lw=2.2, zorder=20))

    # 제목이 박스 폭을 넘지 않도록 폰트 축소
    title_max_w = BW - 0.5
    ttl_size = LB_TTL
    while ttl_size > 16 and _text_width_data(ax, renderer, title, fnt(ttl_size, True, text=title)) > title_max_w:
        ttl_size -= 1
    T(ax, title, x0 + BW / 2, y0 + BH - 0.55, sz=ttl_size, c='#3a2c14', bg='#fffdf7', bw=0)

    col_w = BW / 2
    icon_w = 0.75
    top_margin = 1.35
    bottom_margin = 0.35
    available = BH - top_margin - bottom_margin
    n_rows = (len(items) + 1) // 2
    max_w = col_w - icon_w - 0.15

    leg_size = None
    row_lines = None
    for size in range(LB_LEG, 13, -1):
        fp = fnt(size, False)
        lines_per_item = [len(wrap_by_width(ax, renderer, label, fp, max_w)) for _, _, label in items]
        rl = []
        for r in range(n_rows):
            a = lines_per_item[2 * r]
            b = lines_per_item[2 * r + 1] if 2 * r + 1 < len(items) else 0
            rl.append(max(a, b))
        line_h = 0.32 * size / 23
        row_heights = [max(0.55, l * line_h + 0.28) for l in rl]
        if sum(row_heights) <= available or size <= 14:
            leg_size = size
            row_lines = rl
            break
    fp = fnt(leg_size, False)
    line_h = 0.32 * leg_size / 23

    y = y0 + BH - top_margin
    for i, (kind, val, label) in enumerate(items):
        col = i % 2
        row = i // 2
        cx = x0 + 0.45 + col * col_w
        row_top = y - sum((max(0.55, l * line_h + 0.28)) for l in row_lines[:row])
        cy = row_top
        if kind == 'arr':
            ax.annotate('', xy=(cx + 0.55, cy), xytext=(cx, cy),
                arrowprops=dict(arrowstyle='-|>', color=val, lw=3.2), zorder=21)
        elif kind == 'dash':
            ax.annotate('', xy=(cx + 0.55, cy), xytext=(cx, cy),
                arrowprops=dict(arrowstyle='-|>', color=val, lw=3.2,
                                 linestyle=(0, (5, 3))), zorder=21)
        elif kind == 'emoji':
            pe_em(ax, val, cx + 0.25, cy, zoom=0.12, z=21)
        elif kind in ('dot_r', 'dot_b'):
            ax.scatter([cx + 0.25], [cy], s=110, c=val, edgecolors='white',
                       linewidths=0.5, zorder=21)
        elif kind == 'dot':
            ax.plot(cx + 0.25, cy, 'o', ms=13, color='none', mec=val, mew=2.5, zorder=21)

        lines = wrap_by_width(ax, renderer, label, fp, max_w)
        ly = cy if len(lines) == 1 else cy + line_h * (len(lines) - 1) / 2
        for line in lines:
            ax.text(cx + icon_w, ly, line, fontproperties=fnt(leg_size, False, text=line),
                    color='#222', ha='left', va='center', zorder=21)
            ly -= line_h


def draw_analysis_box(ax, renderer, x0, side_label, general_name, rows, header_color):
    y0 = INFO_Y0
    ax.add_patch(FancyBboxPatch((x0, y0), BW, BH,
        boxstyle='round,pad=0.08,rounding_size=0.15',
        fc='#fffdf7', ec=header_color, lw=2.6, zorder=20))
    ax.add_patch(FancyBboxPatch((x0, y0 + BH - 0.85), BW, 0.85,
        boxstyle='square,pad=0', fc=header_color, ec='none', zorder=21))
    T(ax, f'{side_label}  {general_name}', x0 + BW / 2, y0 + BH - 0.44,
      sz=LB_TTL, c='white', bg=header_color, bw=0)

    left_pad = 0.4
    right_pad = 0.4
    max_w = BW - left_pad - right_pad
    n = len(rows)
    label_h = 0.48
    top_margin = 1.45
    bottom_margin = 0.30
    available = BH - top_margin - bottom_margin
    gap_ratio = 1.3

    # 폰트 크기를 LB_SUB부터 점차 줄여가며, 줄간격이 가독 최소치(1.3배 폰트크기)
    # 아래로 내려가지 않는 선에서 내용이 박스 안에 다 들어가는 크기를 찾는다.
    chosen = None
    for size in range(LB_SUB, 13, -1):
        content_fp = fnt(size, False)
        wrapped_rows = [(label, wrap_by_width(ax, renderer, content, content_fp, max_w))
                         for label, content in rows]
        total_lines = sum(len(lines) for _, lines in wrapped_rows)
        denom = total_lines + (n - 1) * gap_ratio
        line_h = (available - n * label_h) / denom if denom > 0 else 0
        min_readable = 1.3 * size / 72
        if line_h >= min_readable:
            chosen = (size, wrapped_rows, line_h)
            break
        chosen = (size, wrapped_rows, max(line_h, min_readable * 0.92))
    size, wrapped_rows, line_h = chosen
    row_gap_extra = gap_ratio * line_h

    cursor = y0 + BH - top_margin
    for label, lines in wrapped_rows:
        T(ax, label, x0 + left_pad, cursor, sz=LB_SZ, c=header_color, ha='left',
          bg='#fffdf7', bw=3)
        cursor -= label_h
        for line in lines:
            ax.text(x0 + left_pad, cursor, line, fontproperties=fnt(size, False, text=line),
                    color='#222', ha='left', va='center', zorder=25,
                    path_effects=[pe.withStroke(linewidth=3, foreground='#fffdf7')])
            cursor -= line_h
        cursor -= row_gap_extra
