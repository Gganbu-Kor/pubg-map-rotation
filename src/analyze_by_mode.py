"""analyze_weekly.py와 같은 지표를 솔로·듀오·스쿼드 모드별로 나눠 계산한다.

사용법: python3 src/analyze_by_mode.py
출력: data/processed/weekly_map_share_by_mode.csv (집계 수치만)
"""
import csv
from collections import Counter, defaultdict

from analyze_weekly import API_TO_EN, MAX_PLAYERS, SUFFIX, WEEKS, add_match, load_matches, median_min, new_stats
from test_api import ROOT

MODES = ["solo", "duo", "squad"]  # 1인칭(-fpp)과 3인칭은 합침
OUT = ROOT / "data" / "processed" / f"weekly_map_share_by_mode{SUFFIX}.csv"


def main():
    rotation = defaultdict(dict)
    starts = {}
    for row in csv.DictReader(open(ROOT / "data" / "processed" / "rotation_as_pc.csv", encoding="utf-8")):
        rotation[row["week"]][row["map_en"]] = (row["map_ko"], row["slot"])
        starts[row["week"]] = row["start_utc"]

    stats = defaultdict(lambda: {**new_stats(), "fpp": 0})
    raw_modes = Counter()
    for r in load_matches(verbose=True):
        week = [w for w in WEEKS if r["created_at"] >= starts[w]][-1]
        m = API_TO_EN.get(r["map"], r["map"])
        mode = r["mode"].replace("-fpp", "")
        raw_modes[r["mode"]] += 1
        if m not in rotation[week] or mode not in MODES:
            continue
        s = stats[(mode, week, m)]
        add_match(s, r)
        s["fpp"] += r["mode"].endswith("-fpp")

    print("원래 모드 분포:", dict(raw_modes.most_common()))
    rows = []
    for mode in MODES:
        for week in WEEKS:
            maps = rotation[week]
            tot_m = sum(stats[(mode, week, m)]["matches"] for m in maps)
            tot_h = sum(stats[(mode, week, m)]["humans"] for m in maps)
            tot_hm = sum(stats[(mode, week, m)]["human_min"] for m in maps)
            fpp = sum(stats[(mode, week, m)]["fpp"] for m in maps)
            print(f"\n## {mode} | {week} (매치 {tot_m:,}건, 그중 1인칭 {fpp}건)")
            print("| 맵 | 자리 | 매치 | 매치 비중 | 사람 비중 | 사람×시간 비중 | 경기 시간 중앙값(사람 기준, 분) | 봇 비율 "
                  "| 한 판 사람 | 정원 대비 사람 |")
            print("|---|---|---|---|---|---|---|---|---|---|")
            for m in sorted(maps, key=lambda m: -stats[(mode, week, m)]["matches"]):
                s = stats[(mode, week, m)]
                ko, slot = maps[m]
                cap = MAX_PLAYERS.get(m, 100)
                n = s["matches"]
                row = {
                    "mode": mode, "week": week, "map_en": m, "map_ko": ko, "slot": slot,
                    "matches": n, "fpp_matches": s["fpp"],
                    "match_share": round(100 * n / tot_m, 1) if tot_m else None,
                    "human_share": round(100 * s["humans"] / tot_h, 1) if tot_h else None,
                    "human_time_share": round(100 * s["human_min"] / tot_hm, 1) if tot_hm else None,
                    "median_match_min": median_min(s),
                    "bot_ratio": round(100 * s["bots"] / s["players"], 1) if s["players"] else None,
                    "humans_per_match": round(s["humans"] / n, 1) if n else None,
                    "max_players": cap,
                    "human_fill": round(100 * s["humans"] / n / cap, 1) if n else None,
                }
                rows.append(row)
                fmt = lambda v, pct=True: "-" if v is None else (f"{v}%" if pct else f"{v}")
                print(f"| {ko} | {slot} | {n:,} | {fmt(row['match_share'])} | {fmt(row['human_share'])} | "
                      f"{fmt(row['human_time_share'])} | {fmt(row['median_match_min'], False)} | "
                      f"{fmt(row['bot_ratio'])} | {fmt(row['humans_per_match'], False)} | "
                      f"{fmt(row['human_fill'])} |")

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n저장: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
