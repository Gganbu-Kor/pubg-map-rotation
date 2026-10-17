"""보고서용 차트 3개를 PNG로 만든다.

사용법: .venv/bin/python src/make_charts.py   (먼저 analyze_*.py 실행, matplotlib 필요)
출력: outputs/charts/q1_preference_vs_actual.png, q2_squad_band_heatmap.png, hourly_squad.png
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "charts"
WEEKS = ["43.1 W4", "43.1 W5"]
BANDS = ["피크", "오후", "비피크"]
SLOT_KO = {"fixed": "고정", "favored": "선호", "etc": "기타"}

# 색: 차트 지침의 기본 팔레트 (검증된 1·2번 색 + 기준선용 회색)
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE = "#2a78d6", "#eb6834"
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

# 한글 글꼴 (Mac 기본 글꼴)
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
if Path(FONT).exists():
    font_manager.fontManager.addfont(FONT)
    plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT).get_name()
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": INK2,
    "axes.grid": False, "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.titlecolor": INK, "axes.unicode_minus": False,
})


def read(name):
    return list(csv.DictReader(open(PROC / name, encoding="utf-8")))


def style_axis(ax, grid_axis="x"):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis=grid_axis, color=GRID, linewidth=1, linestyle="-")
    ax.set_axisbelow(True)


def q1_chart():
    """주차별: 5개 맵의 환산 선호도(회색 기준점) vs 사람 비중(파랑 원) vs 사람×시간 비중(주황 마름모)"""
    rows = read("weekly_map_share.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharex=True)
    for ax, week in zip(axes, WEEKS):
        w = [r for r in rows if r["week"] == week]
        pref_sum = sum(float(r["pref_43_2"]) for r in w)
        w.sort(key=lambda r: float(r["pref_43_2"]))  # 아래에서 위로: 선호도 낮은 맵 → 높은 맵
        for y, r in enumerate(w):
            pref = 100 * float(r["pref_43_2"]) / pref_sum
            hs, ht = float(r["human_share"]), float(r["human_time_share"])
            lo, hi = min(pref, hs, ht), max(pref, hs, ht)
            ax.plot([lo, hi], [y, y], color=AXIS, linewidth=2, solid_capstyle="round", zorder=1)
            ax.scatter(pref, y, s=90, marker="o", facecolor=SURFACE, edgecolor=MUTED, linewidth=2, zorder=3,
                       label="공식 선호도 (5개 맵 기준 환산)" if y == 0 else None)
            ax.scatter(hs, y, s=70, marker="o", color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=4,
                       label="사람 비중 (≈ 이용 횟수)" if y == 0 else None)
            ax.scatter(ht, y, s=80, marker="D", color=ORANGE, edgecolor=SURFACE, linewidth=2, zorder=4,
                       label="사람×시간 비중 (≈ 이용 시간)" if y == 0 else None)
            ax.text(hi + 2.6, y, f"{pref:.1f} / {hs:.1f} / {ht:.1f}", va="center", fontsize=8, color=MUTED)
        ax.set_yticks(range(len(w)))
        ax.set_yticklabels([f"{r['map_ko']} ({SLOT_KO[r['slot']]})" for r in w])
        n = sum(int(r["matches"]) for r in w)
        ax.set_title(f"{week}  (매치 {n:,}건)", loc="left")
        ax.set_xlim(0, 60)
        ax.set_xlabel("그 주 로테이션 5개 맵 안에서의 비중 (%)")
        style_axis(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False, fontsize=9, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("직전 공식 선호도(43.2)와 실제 사람 플레이 비중은 크게 다르지 않았다", x=0.01, ha="left",
                 fontsize=14, fontweight="bold", color=INK)
    fig.text(0.01, 0.885, "스팀 아시아 일반 매치, 전체 모드 · 공식 선호도는 측정 기간(8/3~9/28)이 달라 참고 기준 · "
             "오른쪽 숫자 = 공식 / 사람 / 사람×시간", fontsize=9, color=INK2)
    fig.tight_layout(rect=(0, 0.06, 1, 0.87))
    path = OUT / "q1_preference_vs_actual.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def q2_chart():
    """스쿼드: 주차 × 맵 × 시간대 봇 비율 히트맵 (칸 안에 봇 비율과 매치 수)"""
    rows = [r for r in read("weekly_map_by_band.csv") if r["group"] == "squad"]
    cmap = LinearSegmentedColormap.from_list("seq_blue", SEQ_BLUE)
    vmax = 45
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    for ax, week in zip(axes, WEEKS):
        w = [r for r in rows if r["week"] == week]
        maps = []
        for r in w:
            if (r["map_ko"], r["slot"]) not in maps:
                maps.append((r["map_ko"], r["slot"]))
        grid = [[next(float(r["bot_ratio"]) for r in w if r["map_ko"] == m and r["band"] == b) for b in BANDS]
                for m, _ in maps]
        counts = [[next(int(r["matches"]) for r in w if r["map_ko"] == m and r["band"] == b) for b in BANDS]
                  for m, _ in maps]
        im = ax.imshow(grid, cmap=cmap, vmin=0, vmax=vmax, aspect="auto")
        for i in range(len(maps)):
            for j in range(len(BANDS)):
                v, n = grid[i][j], counts[i][j]
                color = "white" if v > vmax * 0.55 else INK  # 진한 칸은 흰 글씨
                ax.text(j, i - 0.12, f"{v:.1f}%", ha="center", va="center", fontsize=11, fontweight="bold", color=color)
                small = " · 표본 적음" if n < 30 else ""
                ax.text(j, i + 0.22, f"{n}건{small}", ha="center", va="center", fontsize=7.5, color=color)
        ax.set_xticks(range(len(BANDS)))
        ax.set_xticklabels(["피크\n20~01시", "오후\n14~19시", "비피크\n02~13시"])
        ax.set_yticks(range(len(maps)))
        ax.set_yticklabels([f"{m} ({SLOT_KO[s]})" for m, s in maps])
        ax.tick_params(length=0)
        for side in ax.spines.values():
            side.set_visible(False)
        ax.set_xticks([x - 0.5 for x in range(1, len(BANDS))], minor=True)
        ax.set_yticks([y - 0.5 for y in range(1, len(maps))], minor=True)
        ax.grid(which="minor", color=SURFACE, linewidth=2)  # 칸 사이 2px 여백
        ax.set_title(week, loc="left")
    cbar = fig.colorbar(im, ax=axes, fraction=0.025, pad=0.02)
    cbar.set_label("봇 비율 (%)", color=INK2)
    cbar.outline.set_visible(False)
    fig.suptitle("비피크 시간대에는 모든 맵에서 봇 비율이 올라간다", x=0.01, ha="left",
                 fontsize=14, fontweight="bold", color=INK)
    fig.text(0.01, 0.9, "스쿼드만 (1인칭 포함) · 한국 시간 기준 · 칸 아래 숫자 = 매치 수, 30건 미만은 경향 수준으로만 해석",
             fontsize=9, color=INK2)
    fig.subplots_adjust(top=0.8, wspace=0.45, right=0.88)
    path = OUT / "q2_squad_band_heatmap.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def hourly_chart():
    """보조: 한국 시간 1시간 단위 스쿼드 매치 수(위)와 스쿼드 봇 비율(아래). 단위가 달라 축을 나눔"""
    rows = read("hourly_kst.csv")
    hours = [int(r["hour_kst"]) for r in rows]
    matches = [int(r["matches_squad"]) for r in rows]
    bots = [float(r["bot_ratio_squad"]) for r in rows]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [1, 1.2]})
    for ax in (ax1, ax2):  # 이야기의 중심인 비피크만 회색 배경
        ax.axvspan(1.5, 13.5, color="#f0efec", zorder=0)
    for lo, hi, name in [(-0.5, 1.5, "피크"), (1.5, 13.5, "비피크"), (13.5, 19.5, "오후"), (19.5, 23.5, "피크")]:
        ax1.text((lo + hi) / 2, max(matches) * 1.1, name, ha="center", fontsize=9, color=INK2)
    ax1.bar(hours, matches, width=0.6, color=BLUE, zorder=2)
    ax1.set_ylabel("스쿼드 매치 수")
    ax1.set_ylim(0, max(matches) * 1.2)
    style_axis(ax1, "y")
    ax2.plot(hours, bots, color=BLUE, linewidth=2, solid_joinstyle="round", zorder=3)
    ax2.scatter(hours, bots, s=36, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=4)
    for h in (bots.index(max(bots)), bots.index(min(bots))):
        ax2.annotate(f"{hours[h]:02d}시 {bots[h]:.1f}%", (hours[h], bots[h]), xytext=(0, 10 if h == bots.index(max(bots)) else -16),
                     textcoords="offset points", ha="center", fontsize=9, color=INK)
    ax2.set_ylabel("스쿼드 봇 비율 (%)")
    ax2.set_ylim(0, max(bots) * 1.25)
    ax2.set_xticks(hours)
    ax2.set_xticklabels([f"{h:02d}" for h in hours])
    ax2.set_xlabel("매치 시작 시각 (한국 시간)")
    style_axis(ax2, "y")
    fig.suptitle("사람이 적은 시간일수록 봇이 많다 (스쿼드)", x=0.01, ha="left", fontsize=14,
                 fontweight="bold", color=INK)
    fig.text(0.01, 0.915, "스팀 아시아 일반 매치, 43.1 W4·W5 합계 · 회색 배경 = 비피크(02~13시) · 피크 20~01시, 오후 14~19시",
             fontsize=9, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    path = OUT / "hourly_squad.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for f in (q1_chart, q2_chart, hourly_chart):
        print("저장:", f().relative_to(ROOT))


if __name__ == "__main__":
    main()
