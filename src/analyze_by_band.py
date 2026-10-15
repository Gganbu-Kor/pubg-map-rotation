"""주차 × 시간대(피크·오후·비피크, 한국 시간) × 맵으로 매치 비중, 봇 비율, 정원 대비 사람을 본다.

사용법: python3 src/analyze_by_band.py
출력: data/processed/weekly_map_by_band.csv (집계 수치만, 전체 모드 + 스쿼드만)
"""
import csv
from collections import defaultdict

from analyze_by_hour import kst_hour
from analyze_weekly import API_TO_EN, MAX_PLAYERS, WEEKS, add_match, load_matches, median_min, new_stats
from test_api import ROOT

# 시간대 구간 (한국 시간, 시작 시 포함)
BANDS = {"피크": [20, 21, 22, 23, 0, 1], "오후": list(range(14, 20)), "비피크": list(range(2, 14))}
HOUR_TO_BAND = {h: b for b, hours in BANDS.items() for h in hours}
OUT = ROOT / "data" / "processed" / "weekly_map_by_band.csv"


def main():
    rotation = defaultdict(dict)
    starts = {}
    for row in csv.DictReader(open(ROOT / "data" / "processed" / "rotation_as_pc.csv", encoding="utf-8")):
        rotation[row["week"]][row["map_en"]] = (row["map_ko"], row["slot"])
        starts[row["week"]] = row["start_utc"]

    stats = defaultdict(new_stats)
    for r in load_matches(verbose=True):
        week = [w for w in WEEKS if r["created_at"] >= starts[w]][-1]
        band = HOUR_TO_BAND[kst_hour(r["created_at"])]
        m = API_TO_EN.get(r["map"], r["map"])
        if m not in rotation[week]:
            continue
        groups = ["all"] + (["squad"] if r["mode"].startswith("squad") else [])
        for g in groups:
            add_match(stats[(g, week, band, m)], r)

    rows = []
    for g in ["all", "squad"]:
        for week in WEEKS:
            maps = rotation[week]
            totals = {b: sum(stats[(g, week, b, m)]["matches"] for m in maps) for b in BANDS}
            totals_hm = {b: sum(stats[(g, week, b, m)]["human_min"] for m in maps) for b in BANDS}
            title = "전체 모드" if g == "all" else "스쿼드만"
            print(f"\n## {title} | {week} (피크 {totals['피크']}건, 오후 {totals['오후']}건, 비피크 {totals['비피크']}건)")
            print("| 맵 | 자리 | " + " | ".join(f"{b} 매치 비중(건) | {b} 봇 | {b} 정원 대비 사람" for b in BANDS) + " |")
            print("|---|---|" + "---|" * (3 * len(BANDS)))
            for m in sorted(maps, key=lambda m: -sum(stats[(g, week, b, m)]["matches"] for b in BANDS)):
                ko, slot = maps[m]
                cap = MAX_PLAYERS.get(m, 100)
                cells = []
                for b in BANDS:
                    s = stats[(g, week, b, m)]
                    n = s["matches"]
                    row = {
                        "group": g, "week": week, "band": b, "map_en": m, "map_ko": ko, "slot": slot,
                        "matches": n,
                        "match_share": round(100 * n / totals[b], 1) if totals[b] else None,
                        "human_time_share": (round(100 * s["human_min"] / totals_hm[b], 1)
                                             if totals_hm[b] else None),
                        "median_match_min": median_min(s),
                        "bot_ratio": round(100 * s["bots"] / s["players"], 1) if s["players"] else None,
                        "human_fill": round(100 * s["humans"] / n / cap, 1) if n else None,
                    }
                    rows.append(row)
                    f = lambda v: "-" if v is None else f"{v}%"
                    cells += [f"{f(row['match_share'])} ({n})", f(row["bot_ratio"]), f(row["human_fill"])]
                print(f"| {ko} | {slot} | " + " | ".join(cells) + " |")

    with open(OUT, "w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n저장: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
