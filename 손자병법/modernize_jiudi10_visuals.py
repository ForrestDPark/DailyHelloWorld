#!/usr/bin/env python3
"""九地篇 10구절의 최신 전역 시각 안내 세트를 재현 가능하게 생성한다."""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Ellipse


ROOT = Path(__file__).resolve().parent
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
FONT = font_manager.FontProperties(fname=FONT_PATH)
plt.rcParams["font.family"] = FONT.get_name()
plt.rcParams["axes.unicode_minus"] = False

BLUE = "#1f5aa6"
BLUE_LIGHT = "#dceafa"
RED = "#b63a3a"
RED_LIGHT = "#f7dddd"
GREEN = "#457b5a"
INK = "#25313b"
MUTED = "#667681"
PAPER = "#f6f1e7"
GRID = "#d8cdbb"


def canvas(title, subtitle):
    fig, ax = plt.subplots(figsize=(16, 10), dpi=150)
    fig.patch.set_facecolor(PAPER)
    ax.set_facecolor(PAPER)
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ax.text(0.6, 9.45, title, fontsize=25, fontweight="bold", color=INK, va="top")
    ax.text(0.62, 8.98, subtitle, fontsize=11.5, color=MUTED, va="top")
    ax.plot([0.6, 15.4], [8.72, 8.72], color=GRID, lw=1.4)
    return fig, ax


def card(ax, x, y, w, h, color, name, role, note):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc="white", ec=color, lw=2))
    ax.add_patch(Circle((x + 0.68, y + h / 2), 0.48, fc=color, ec="white", lw=2))
    initials = "".join(part[0] for part in name.replace("·", " ").split()[:2])
    ax.text(x + 0.68, y + h / 2, initials, ha="center", va="center",
            fontsize=15, color="white", fontweight="bold")
    ax.text(x + 1.32, y + h - 0.32, name, fontsize=15, color=color,
            fontweight="bold", va="top")
    ax.text(x + 1.32, y + h - 0.75, role, fontsize=10.5, color=INK, va="top")
    ax.text(x + 1.32, y + 0.32, note, fontsize=9.2, color=MUTED, va="bottom", wrap=True)


def commanders(spec):
    fig, ax = canvas(spec["title"] + " — 주요 인물 안내판",
                     "삽화형 인물 표식이며 실제 초상 복원이 아니다 · 파랑=승군, 빨강=패군")
    ax.add_patch(FancyBboxPatch((0.6, 0.55), 7.15, 7.7, boxstyle="round,pad=.04",
                                fc=RED_LIGHT, ec=RED, lw=1.4))
    ax.add_patch(FancyBboxPatch((8.25, 0.55), 7.15, 7.7, boxstyle="round,pad=.04",
                                fc=BLUE_LIGHT, ec=BLUE, lw=1.4))
    ax.text(0.95, 7.9, "패군", color=RED, fontsize=18, fontweight="bold")
    ax.text(8.6, 7.9, "승군", color=BLUE, fontsize=18, fontweight="bold")
    for i, item in enumerate(spec["losers"]):
        card(ax, 0.95, 5.8 - i * 2.15, 6.45, 1.65, RED, *item)
    for i, item in enumerate(spec["winners"]):
        card(ax, 8.6, 5.8 - i * 2.15, 6.45, 1.65, BLUE, *item)
    fig.savefig(ROOT / spec["commanders"], bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def box(ax, x, y, w, h, color, title, body):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=.025,rounding_size=.1",
                                fc="white", ec=color, lw=1.8))
    ax.text(x + 0.18, y + h - 0.22, title, color=color, fontsize=12,
            fontweight="bold", va="top")
    ax.text(x + 0.18, y + h - 0.68, body, color=INK, fontsize=9.2, va="top", wrap=True)


def structure(spec):
    fig, ax = canvas(spec["title"] + " — 장군 조직도와 작전 편제",
                     "실선=지휘 관계 · 점선=참모 제안·독립 임무 · 병력은 사료상 확인 범위")
    columns = [(0.75, RED, RED_LIGHT, "패군", spec["loser_org"]),
               (8.15, BLUE, BLUE_LIGHT, "승군", spec["winner_org"])]
    for x, color, bg, label, nodes in columns:
        ax.add_patch(FancyBboxPatch((x, 0.55), 7.05, 7.7, boxstyle="round,pad=.04",
                                    fc=bg, ec=color, lw=1.3))
        ax.text(x + 0.25, 7.92, label, color=color, fontsize=17, fontweight="bold")
        for i, (title, body) in enumerate(nodes):
            y = 6.72 - i * 1.65
            box(ax, x + 0.35, y, 6.35, 1.18, color, title, body)
            if i:
                ax.add_patch(FancyArrowPatch((x + 3.52, y + 1.58), (x + 3.52, y + 1.2),
                                             arrowstyle="-|>", mutation_scale=12, color=color, lw=1.5))
    fig.savefig(ROOT / spec["structure"], bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def sequence(spec):
    fig, ax = canvas(spec["title"] + " — 단계별 전역 흐름도",
                     "같은 색과 화살표가 네 단계에서 이어지도록 정리한 작전 진행도")
    positions = [(0.8, 4.65), (8.25, 4.65), (0.8, 0.8), (8.25, 0.8)]
    for i, ((head, body, result), (x, y)) in enumerate(zip(spec["steps"], positions), 1):
        color = BLUE if result == "win" else RED if result == "loss" else GREEN
        ax.add_patch(FancyBboxPatch((x, y), 6.95, 3.05, boxstyle="round,pad=.04,rounding_size=.12",
                                    fc="white", ec=color, lw=2))
        ax.add_patch(Circle((x + 0.55, y + 2.48), 0.32, fc=color, ec="none"))
        ax.text(x + 0.55, y + 2.48, str(i), color="white", fontsize=13,
                fontweight="bold", ha="center", va="center")
        ax.text(x + 1.02, y + 2.72, head, color=color, fontsize=14,
                fontweight="bold", va="top")
        ax.text(x + 0.42, y + 2.12, body, color=INK, fontsize=10.1, va="top", wrap=True)
    ax.add_patch(FancyArrowPatch((7.76, 6.18), (8.17, 6.18), arrowstyle="-|>",
                                 mutation_scale=16, color=MUTED, lw=1.6))
    ax.add_patch(FancyArrowPatch((11.7, 4.52), (11.7, 3.92), arrowstyle="-|>",
                                 mutation_scale=16, color=MUTED, lw=1.6))
    ax.add_patch(FancyArrowPatch((8.18, 2.32), (7.77, 2.32), arrowstyle="-|>",
                                 mutation_scale=16, color=MUTED, lw=1.6))
    fig.savefig(ROOT / spec["sequence"], bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def country_map_sedan(spec):
    shp = "/opt/anaconda3/lib/python3.11/site-packages/pyogrio/tests/fixtures/naturalearth_lowres/naturalearth_lowres.shp"
    world = gpd.read_file(shp)
    europe = world.cx[-6:16, 42:55]
    fig, ax = plt.subplots(figsize=(16, 10), dpi=150)
    fig.patch.set_facecolor(PAPER)
    ax.set_facecolor("#e9f1f2")
    europe.plot(ax=ax, color="#eee7d8", edgecolor="#786f63", linewidth=.7)
    for name, color in [("France", RED_LIGHT), ("Germany", BLUE_LIGHT), ("Belgium", "#f3e8b2"),
                        ("Netherlands", "#eee0b0"), ("Luxembourg", "#eee0b0")]:
        europe[europe["name"] == name].plot(ax=ax, color=color, edgecolor="#6e665d", linewidth=.9)
    points = {"스당(Sedan)": (4.94, 49.70), "아르덴(Ardennes)": (5.4, 49.9),
              "브뤼셀(Brussels)": (4.35, 50.85), "아브빌(Abbeville)": (1.83, 50.11)}
    for label, (x, y) in points.items():
        ax.scatter(x, y, s=75, color=BLUE if "스당" in label or "아브빌" in label else INK, zorder=5)
        ax.text(x + .18, y + .12, label, fontsize=10, fontproperties=FONT, color=INK)
    ax.annotate("", xy=(4.94, 49.70), xytext=(7.8, 50.4),
                arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=3))
    ax.annotate("", xy=(1.83, 50.11), xytext=(4.94, 49.70),
                arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=3))
    ax.set_xlim(-5, 13)
    ax.set_ylim(43, 54.5)
    ax.set_title("스당 돌파 — 1940년 서유럽 교전국과 주공 방향", fontsize=23,
                 fontweight="bold", fontproperties=FONT, color=INK, pad=18)
    ax.text(-4.7, 43.25, "파랑 화살표: 독일 A집단군의 아르덴 통과→스당 도하→해협 진출\n국경선은 위치 참조용이며 실제 군사 점령선은 날짜에 따라 변했다.",
            fontsize=10.5, fontproperties=FONT, color=MUTED)
    ax.axis("off")
    fig.savefig(ROOT / spec["country"], bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def country_map_yinping(spec):
    shp = "/opt/anaconda3/lib/python3.11/site-packages/pyogrio/tests/fixtures/naturalearth_lowres/naturalearth_lowres.shp"
    world = gpd.read_file(shp)
    china = world[world["name"] == "China"]
    fig, ax = plt.subplots(figsize=(16, 10), dpi=150)
    fig.patch.set_facecolor(PAPER)
    ax.set_facecolor("#e9f1f2")
    china.plot(ax=ax, color="#eee7d8", edgecolor="#6e665d", linewidth=1)
    zones = [((109, 34.5), 16, 8, BLUE_LIGHT, "위(魏)"), ((104.5, 30), 10, 6, RED_LIGHT, "촉한(蜀漢)"),
             ((117, 29), 12, 7, "#e4ecd2", "오(吳)")]
    for (xy, w, h, color, label) in zones:
        ax.add_patch(Ellipse(xy, w, h, fc=color, ec="none", alpha=.78))
        ax.text(*xy, label, ha="center", va="center", fontsize=15, fontweight="bold",
                fontproperties=FONT, color=INK)
    pts = {"음평(陰平)": (104.4, 33.2), "강유(江油)": (104.7, 31.8),
           "면죽(綿竹)": (104.2, 31.3), "성도(成都)": (104.07, 30.67), "검각(劍閣)": (105.5, 32.3)}
    for label, (x, y) in pts.items():
        ax.scatter(x, y, s=65, color=BLUE if label.startswith(("음평", "강유")) else RED, zorder=5)
        ax.text(x + .25, y + .12, label, fontsize=10, fontproperties=FONT, color=INK)
    ax.annotate("", xy=(104.7, 31.8), xytext=(104.4, 33.2),
                arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=3))
    ax.annotate("", xy=(104.07, 30.67), xytext=(104.7, 31.8),
                arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=3))
    ax.set_xlim(92, 124)
    ax.set_ylim(20, 43)
    ax.set_title("등애의 음평 기습 — 263년 삼국 세력과 우회축", fontsize=23,
                 fontweight="bold", fontproperties=FONT, color=INK, pad=18)
    ax.text(92.8, 20.7, "세력권은 사료상 근거지를 중심으로 단순화한 개략 영향권이다.\n현대 중국 외곽선은 위치 참조용이며 삼국의 정확한 국경선이 아니다.",
            fontsize=10.5, fontproperties=FONT, color=MUTED)
    ax.axis("off")
    fig.savefig(ROOT / spec["country"], bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


SEDAN = {
    "title": "스당 돌파(1940)",
    "commanders": "sedan1940_commanders.png",
    "structure": "sedan1940_command_structure.png",
    "country": "sedan1940_country_map.png",
    "sequence": "sedan1940_codex_sequence_map.png",
    "losers": [
        ("모리스 가믈랭", "프랑스군 총사령관", "주력군을 벨기에로 전진시켜 아르덴의 경보를 늦게 반영"),
        ("샤를 욍치제", "프랑스 제2군 사령관", "스당 방면 방어를 맡았으나 예비대 투입과 반격이 지연"),
    ],
    "winners": [
        ("에리히 폰 만슈타인", "낫질 작전 구상", "연합군을 북쪽으로 끌어낸 뒤 아르덴을 주공으로 삼는 구상"),
        ("하인츠 구데리안", "제19기갑군단 지휘", "스당 도하 뒤 정지 명령에 묶이지 않고 서쪽으로 돌파"),
    ],
    "loser_org": [
        ("연합군 최고지휘 — 가믈랭", "D계획에 따라 주력군을 벨기에 방면으로 전개"),
        ("프랑스 제2군 — 욍치제", "스당·아르덴 방면 방어와 예비대 운용"),
        ("제55보병사단", "예비역 중심으로 뫼즈강 정면의 방어진지 담당"),
    ],
    "winner_org": [
        ("A집단군 — 룬트슈테트", "아르덴 주공과 뫼즈강 돌파 축 지휘"),
        ("클라이스트 기갑집단", "기갑군단을 좁은 도로망에 집중"),
        ("제19기갑군단 — 구데리안", "스당 도하·교두보 확대·해협 방면 진격"),
    ],
    "steps": [
        ("연합군을 북쪽으로 끌어냄", "독일 B집단군이 네덜란드·벨기에를 위협하자 연합군 주력이 D계획에 따라 북진했다.", "neutral"),
        ("아르덴에 주공 집중", "만슈타인의 구상대로 기갑부대가 방어가 약한 아르덴 도로망을 통과해 스당에 집결했다.", "win"),
        ("항공폭격 뒤 뫼즈강 도하", "집중 폭격이 프랑스 방어부대의 지휘·통신을 흔든 사이 공병과 보병이 교두보를 만들었다.", "loss"),
        ("정지하지 않고 해협으로", "구데리안은 국지 반격보다 작전적 속도를 택해 아브빌까지 진출, 북쪽 연합군을 갈라놓았다.", "win"),
    ],
}

YINPING = {
    "title": "등애의 음평 기습(263)",
    "commanders": "yinping_commanders.png",
    "structure": "yinping_command_structure.png",
    "country": "yinping_country_map.png",
    "sequence": "yinping_codex_sequence_map.png",
    "losers": [
        ("유선(劉禪)", "촉한 황제", "성도 방어와 국가 최종 결정을 맡았으나 전선 경보가 수도 방어로 이어지지 못함"),
        ("제갈첨(諸葛瞻)", "위장군·면죽 방어", "등애군을 면죽에서 막았으나 기습군의 속도와 전투 경험에 밀림"),
    ],
    "winners": [
        ("등애(鄧艾)", "위나라 정서장군", "검각 정면을 피하고 음평의 험로를 넘어 촉한의 배후를 찌름"),
        ("종회(鍾會)", "위나라 진서장군", "검각에서 강유의 주력을 붙들어 등애의 우회가 들키지 않게 함"),
    ],
    "loser_org": [
        ("황제 — 유선", "성도 조정의 최종 결정과 항복"),
        ("검각 방어 — 강유", "촉한 주력으로 종회의 대군을 정면 저지"),
        ("면죽 방어 — 제갈첨", "급히 모은 수도권 병력으로 등애의 우회군 차단"),
    ],
    "winner_org": [
        ("위 조정 — 사마소", "촉 정벌 승인과 전체 전략 통제"),
        ("정면군 — 종회", "검각에서 강유 주력을 붙잡는 正"),
        ("우회군 — 등애", "음평 험로를 통과해 강유·면죽·성도를 찌르는 奇"),
    ],
    "steps": [
        ("종회가 검각을 붙듦", "강유가 촉한 주력으로 검각을 지키자 위군의 정면 진격은 멈췄다.", "neutral"),
        ("등애가 음평 험로 선택", "등애는 방비가 없다고 판단한 산악 우회로에 경량 병력을 투입해 길 없는 길을 넘었다.", "win"),
        ("강유·면죽 연속 돌파", "강유에서 항복을 받아 보급을 보충하고, 제갈첨이 지킨 면죽을 격파해 성도 앞까지 진출했다.", "loss"),
        ("유선의 항복", "검각의 촉 주력은 건재했지만 수도가 직접 위협받자 유선이 항복해 촉한이 무너졌다.", "win"),
    ],
}


def main():
    for spec in (SEDAN, YINPING):
        commanders(spec)
        structure(spec)
        sequence(spec)
    country_map_sedan(SEDAN)
    country_map_yinping(YINPING)
    print("generated:", *(str(p.name) for p in ROOT.glob("*10*.png")))
    print("generated Jiudi 10 visual set")


if __name__ == "__main__":
    main()
