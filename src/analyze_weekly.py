"""주차별로 열린 5개 맵의 매치 비중, 사람 비중, 한 판 사람 수를 계산한다.

사용법: python3 src/analyze_weekly.py
입력: data/raw/collect_steam.jsonl, data/processed/rotation_as_pc.csv
출력: data/processed/weekly_map_share.csv (집계 수치만)
"""
import csv
import json
from collections import defaultdict
from statistics import median

from test_api import ROOT

CUTOFF = "2026-10-14T02:00:00Z"  # 43.2 로테이션 교체(11:00 KST) 이전만 분석
WEEKS = ["43.1 W4", "43.1 W5"]
API_TO_EN = {
    "Baltic_Main": "Erangel", "Tiger_Main": "Taego", "Desert_Main": "Miramar",
    "Savage_Main": "Sanhok", "DihorOtok_Main": "Vikendi", "Chimera_Main": "Paramo",
    "Summerland_Main": "Karakin", "Neon_Main": "Rondo", "Kiki_Main": "Deston",
}
# 참고 기준: 43.2 AS 맵 선호도 (측정 기간 8/3 ~ 9/28, 분석 기간과 겹치지 않음)
PREF_43_2 = {"Taego": 34.7, "Erangel": 20.1, "Sanhok": 10.2, "Miramar": 9.9, "Vikendi": 6.7,
             "Rondo": 5.1, "Paramo": 4.6, "Karakin": 4.4, "Deston": 4.3}
# 맵별 최대 인원 (카라킨·파라모는 64명, 나머지는 100명 — 사용자 확인)
MAX_PLAYERS = {"Karakin": 64, "Paramo": 64}
OUT = ROOT / "data" / "processed" / "weekly_map_share.csv"


def is_excluded(r):
    """사람 0명 매치는 사람 기준 분석에 의미가 없어 제외 (사용자 결정).
    duration이 긴 매치는 사람이 끝낸 뒤 봇만 남아 열려 있던 것이라 제외하지 않는다."""
    return r["humans"] == 0


def load_matches(verbose=False):
    """같은 매치가 여러 줄이면 마지막 줄을 쓰고, 분석 대상만 남긴다. 사람 생존 시간(합·최대)을 붙인다."""
    recs = {}
    for line in open(ROOT / "data" / "raw" / "collect_steam.jsonl", encoding="utf-8"):
        r = json.loads(line)
        recs[r["match_id"]] = r
    survival = {}
    for line in open(ROOT / "data" / "raw" / "survival_steam.jsonl", encoding="utf-8"):
        s = json.loads(line)
        if "error" not in s and "human_max_survived_sec" in s:
            survival[s["match_id"]] = s

    base = [r for r in recs.values()
            if "error" not in r and r["match_type"] == "official" and not r["custom"]
            and r["region"] == "as" and r["created_at"] < CUTOFF]
    missing = [r for r in base if r["match_id"] not in survival]
    if missing:
        raise SystemExit(f"생존 시간이 없는 매치 {len(missing)}건 → python3 src/add_survival.py 를 먼저 실행")
    for r in base:
        r["human_survived_sec"] = survival[r["match_id"]]["human_survived_sec"]
        r["human_max_survived_sec"] = survival[r["match_id"]]["human_max_survived_sec"]
    kept = [r for r in base if not is_excluded(r)]
    if verbose:
        print(f"분석 대상 {len(base):,}건 중 사람 0명 매치 {len(base) - len(kept):,}건 제외 → {len(kept):,}건")
    return kept


def new_stats():
    return {"matches": 0, "humans": 0, "bots": 0, "players": 0, "match_secs": [], "human_min": 0.0}


def add_match(s, r):
    """매치 1건의 숫자를 집계에 더한다. human_min = 사람들이 실제로 생존한 시간(분)의 합"""
    s["matches"] += 1
    s["humans"] += r["humans"]
    s["bots"] += r["bots"]
    s["players"] += r["players"]
    s["match_secs"].append(r["human_max_survived_sec"])
    s["human_min"] += r["human_survived_sec"] / 60


def median_min(s):
    """사람 기준 경기 시간(그 판에서 가장 오래 산 사람의 생존 시간)의 중앙값(분)"""
    return round(median(s["match_secs"]) / 60, 1) if s["match_secs"] else None


def main():
    rotation = defaultdict(dict)  # 주차 -> {맵: (한글 이름, 슬롯)}
    starts = {}
    for row in csv.DictReader(open(ROOT / "data" / "processed" / "rotation_as_pc.csv", encoding="utf-8")):
        rotation[row["week"]][row["map_en"]] = (row["map_ko"], row["slot"])
        starts[row["week"]] = row["start_utc"]

    stats = defaultdict(new_stats)
    outside = 0
    for r in load_matches(verbose=True):
        week = [w for w in WEEKS if r["created_at"] >= starts[w]][-1]
        m = API_TO_EN.get(r["map"], r["map"])
        if m not in rotation[week]:
            outside += 1
            continue
        add_match(stats[(week, m)], r)

    rows = []
    for week in WEEKS:
        maps = rotation[week]
        tot_m = sum(stats[(week, m)]["matches"] for m in maps)
        tot_h = sum(stats[(week, m)]["humans"] for m in maps)
        tot_hm = sum(stats[(week, m)]["human_min"] for m in maps)
        print(f"\n## {week} (매치 {tot_m:,}건, 사람 {tot_h:,}명)")
        print("| 맵 | 자리 | 43.2 선호도(참고) | 매치 | 매치 비중 | 사람 비중 | 사람×시간 비중 | 경기 시간 중앙값(사람 기준, 분) "
              "| 봇 비율 | 한 판 사람 | 한 판 전체 | 정원 | 정원 대비 사람 |")
        print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for m in sorted(maps, key=lambda m: -stats[(week, m)]["matches"]):
            s = stats[(week, m)]
            ko, slot = maps[m]
            row = {
                "week": week, "map_en": m, "map_ko": ko, "slot": slot, "pref_43_2": PREF_43_2[m],
                "matches": s["matches"], "match_share": round(100 * s["matches"] / tot_m, 1),
                "humans": s["humans"], "human_share": round(100 * s["humans"] / tot_h, 1),
                # 사람×시간 비중: 그 맵에서 사람들이 보낸 시간(사람 수 × 경기 시간)의 비중
                "human_time_share": round(100 * s["human_min"] / tot_hm, 1),
                "median_match_min": median_min(s),
                "bot_ratio": round(100 * s["bots"] / s["players"], 1),
                "humans_per_match": round(s["humans"] / s["matches"], 1),
                "players_per_match": round(s["players"] / s["matches"], 1),
                "max_players": MAX_PLAYERS.get(m, 100),
            }
            # 정원 대비 사람 비율: 한 판 사람 수 ÷ 그 맵의 최대 인원 (크기가 다른 맵끼리 비교용)
            row["human_fill"] = round(100 * s["humans"] / s["matches"] / row["max_players"], 1)
            rows.append(row)
            print(f"| {ko} | {slot} | {row['pref_43_2']}% | {row['matches']:,} | {row['match_share']}% | "
                  f"{row['human_share']}% | {row['human_time_share']}% | {row['median_match_min']} | "
                  f"{row['bot_ratio']}% | {row['humans_per_match']} | "
                  f"{row['players_per_match']} | {row['max_players']} | {row['human_fill']}% |")

    print(f"\n로테이션 밖의 맵: {outside}건")
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"저장: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
