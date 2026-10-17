"""매치 시작 시각(한국 시간) 1시간 단위로 매치 수와 봇 비율을 모드별로 본다.

사용법: python3 src/analyze_by_hour.py
출력: data/processed/hourly_kst.csv (집계 수치만)
"""
import csv
from collections import defaultdict
from datetime import datetime, timedelta

from analyze_weekly import SUFFIX, load_matches
from test_api import ROOT

MODES = ["solo", "duo", "squad"]
OUT = ROOT / "data" / "processed" / f"hourly_kst{SUFFIX}.csv"


def kst_hour(created_at):
    """'2026-10-02T13:05:00Z' (UTC) → 한국 시간의 시(0~23)"""
    t = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=9)
    return t.hour


def main():
    stats = defaultdict(lambda: {"matches": 0, "humans": 0, "bots": 0, "players": 0})
    for r in load_matches(verbose=True):
        h = kst_hour(r["created_at"])
        mode = r["mode"].replace("-fpp", "")
        for key in ((h, "all"), (h, mode)):
            s = stats[key]
            s["matches"] += 1
            s["humans"] += r["humans"]
            s["bots"] += r["bots"]
            s["players"] += r["players"]

    def bot(h, mode):
        s = stats[(h, mode)]
        return round(100 * s["bots"] / s["players"], 1) if s["players"] else None

    total = sum(stats[(h, "all")]["matches"] for h in range(24))
    rows = []
    print("| 시(KST) | 매치 | 비중 | 스쿼드/듀오/솔로 매치 | 봇 비율 전체 | 스쿼드 | 듀오 | 솔로 |")
    print("|---|---|---|---|---|---|---|---|")
    for h in range(24):
        a = stats[(h, "all")]
        row = {"hour_kst": h, "matches": a["matches"],
               "share": round(100 * a["matches"] / total, 1),
               **{f"matches_{m}": stats[(h, m)]["matches"] for m in MODES},
               "bot_ratio_all": bot(h, "all"),
               **{f"bot_ratio_{m}": bot(h, m) for m in MODES}}
        rows.append(row)
        f = lambda v: "-" if v is None else f"{v}%"
        print(f"| {h:02d} | {a['matches']} | {row['share']}% | "
              f"{row['matches_squad']}/{row['matches_duo']}/{row['matches_solo']} | "
              f"{f(row['bot_ratio_all'])} | {f(row['bot_ratio_squad'])} | "
              f"{f(row['bot_ratio_duo'])} | {f(row['bot_ratio_solo'])} |")
    print(f"합계 {total}건")

    with open(OUT, "w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"저장: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
