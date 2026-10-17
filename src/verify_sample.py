"""핵심 수치를 원본 데이터와 직접 대조하는 확인용 출력.

사용법: python3 src/verify_sample.py [매치 수] [seed]            (본 분석: 43.1 W4·W5)
        PERIOD=w1 python3 src/verify_sample.py [매치 수] [seed]  (재현 확인: 43.2 W1)
1부: 분석 대상 매치를 골라 API 원본을 다시 받아 저장된 값과 비교 (원본은 data/raw/verify/ 에 저장)
2부: 보고서 핵심 칸을 분석 코드 없이 수집 파일에서 다시 계산해 CSV 값과 비교
분석 코드의 규칙(기간·제외 조건·주차 구분)을 일부러 여기서 따로 구현한다. 닉네임·계정 ID는 출력하지 않는다.
"""
import csv
import json
import os
import random
import sys
from collections import Counter
from datetime import datetime, timedelta

from check_region import read_region
from collect import fetch_match
from test_api import ROOT, load_api_key

W5_START, W1_START, W1_END = "2026-10-07T02:00:00Z", "2026-10-14T02:00:00Z", "2026-10-21T02:00:00Z"
PERIOD = os.environ.get("PERIOD", "main")
BOUNDS = {"main": ("", W1_START), "w1": (W1_START, W1_END)}[PERIOD]
SUFFIX = {"main": "", "w1": "_w1"}[PERIOD]
KO = {"Tiger_Main": "태이고", "Chimera_Main": "파라모", "Summerland_Main": "카라킨", "Neon_Main": "론도"}
# 2부에서 다시 계산할 칸: (종류, 주차, 시간대, API 맵 이름, 영문 맵 이름, 정원)
CHECKS = {
    "main": [("사람×시간 비중", "43.1 W5", "", "Chimera_Main", "Paramo", 64),
             ("사람 비중", "43.1 W4", "", "Tiger_Main", "Taego", 100),
             ("스쿼드 봇·정원 대비 사람", "43.1 W5", "비피크", "Tiger_Main", "Taego", 100),
             ("스쿼드 봇·정원 대비 사람", "43.1 W4", "비피크", "Summerland_Main", "Karakin", 64)],
    "w1": [("사람×시간 비중", "43.2 W1", "", "Neon_Main", "Rondo", 100),
           ("사람 비중", "43.2 W1", "", "Tiger_Main", "Taego", 100),
           ("스쿼드 봇·정원 대비 사람", "43.2 W1", "비피크", "Tiger_Main", "Taego", 100),
           ("스쿼드 봇·정원 대비 사람", "43.2 W1", "피크", "Neon_Main", "Rondo", 100)],
}[PERIOD]
VERIFY_DIR = ROOT / "data" / "raw" / "verify"


def kst(created_at):
    return datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=9)


def band(created_at):
    h = kst(created_at).hour
    return "피크" if h >= 20 or h <= 1 else ("오후" if h >= 14 else "비피크")


def week_of(created_at):
    return "43.2 W1" if created_at >= W1_START else ("43.1 W5" if created_at >= W5_START else "43.1 W4")


def load_records():
    """분석 코드와 같은 규칙을 따로 구현: 일반 + 아시아 + 기간 안, 사람 0명 제외"""
    recs = {}
    for line in open(ROOT / "data" / "raw" / "collect_steam.jsonl", encoding="utf-8"):
        r = json.loads(line)
        recs[r["match_id"]] = r
    surv = {}
    for line in open(ROOT / "data" / "raw" / "survival_steam.jsonl", encoding="utf-8"):
        s = json.loads(line)
        if "error" not in s and "human_max_survived_sec" in s:
            surv[s["match_id"]] = s
    out = []
    for r in recs.values():
        if ("error" not in r and r["match_type"] == "official" and not r["custom"]
                and r["region"] == "as" and BOUNDS[0] <= r["created_at"] < BOUNDS[1] and r["humans"] > 0):
            if "human_max_survived_sec" not in r:  # 10/16 이전 수집분은 별도 파일에 있음
                r["human_survived_sec"] = surv[r["match_id"]]["human_survived_sec"]
                r["human_max_survived_sec"] = surv[r["match_id"]]["human_max_survived_sec"]
            out.append(r)
    return out


def check(label, saved, fresh):
    ok = "✓" if saved == fresh else "✗ 불일치"
    print(f"  | {label} | {saved} | {fresh} | {ok} |")
    return saved == fresh


def part1(records, n, seed, api_key):
    n = min(n, len(records))
    print(f"# 1부. 매치 단위 검증 ({n}건, seed={seed} → 같은 seed로 다시 돌리면 같은 매치가 뽑힘)\n")
    VERIFY_DIR.mkdir(parents=True, exist_ok=True)
    all_ok = True
    for i, r in enumerate(random.Random(seed).sample(records, n), 1):
        mid = r["match_id"]
        match = fetch_match(mid, api_key)
        path = VERIFY_DIR / f"{mid}.json"
        path.write_text(json.dumps(match, ensure_ascii=False, indent=2), encoding="utf-8")

        a = match["data"]["attributes"]
        ids = [p["attributes"]["stats"]["playerId"]
               for p in match["included"] if p["type"] == "participant"]
        prefixes = Counter(pid.split(".")[0] for pid in ids)
        human_times = [p["attributes"]["stats"]["timeSurvived"] for p in match["included"]
                       if p["type"] == "participant"
                       and p["attributes"]["stats"]["playerId"].startswith("account.")]
        url = next(x["attributes"]["URL"] for x in match["included"] if x["type"] == "asset")
        region = read_region(url)[0]

        print(f"## 매치 {i}/{n}: {mid}")
        print(f"  시작 시각: {a['createdAt']} (UTC) = {kst(a['createdAt']):%m/%d %H:%M} (KST) → "
              f"{week_of(a['createdAt'])}, {band(a['createdAt'])}")
        print("  | 항목 | 저장된 값 | 원본에서 다시 계산 | 일치 |")
        print("  |---|---|---|---|")
        results = [
            check("맵", r["map"], a["mapName"]),
            check("모드", r["mode"], a["gameMode"]),
            check("시작 시각", r["created_at"], a["createdAt"]),
            check("matchType", r["match_type"], a["matchType"]),
            check("커스텀 여부", r["custom"], a["isCustomMatch"]),
            check("경기 시간(초)", r["duration"], a["duration"]),
            check("지역(텔레메트리)", r["region"], region),
            check("전체 인원", r["players"], len(ids)),
            check("사람(account.)", r["humans"], prefixes.get("account", 0)),
            check("봇(ai.)", r["bots"], prefixes.get("ai", 0)),
            check("사람 생존 시간 합(초)", r["human_survived_sec"], sum(human_times)),
            check("사람 최대 생존(초) = 경기 시간", r["human_max_survived_sec"], max(human_times)),
        ]
        others = {k: v for k, v in prefixes.items() if k not in ("account", "ai")}
        print(f"  playerId 앞부분 종류: {dict(prefixes)}" + (f"  ← 사람·봇 외 {others}" if others else ""))
        print(f"  원본 파일: {path.relative_to(ROOT)}  (파일에서 \"playerId\": \"ai. 를 검색하면 봇 수를 직접 셀 수 있음)\n")
        all_ok &= all(results)
    print(f"1부 결과: {'모두 일치' if all_ok else '불일치 있음 → 위 표 확인'}\n")


def part2(records):
    print("# 2부. 집계 검증 (분석 코드 없이 수집 파일에서 다시 계산 → CSV 값과 비교)\n")

    def csv_row(name, **cond):
        for row in csv.DictReader(open(ROOT / "data" / "processed" / f"{name}{SUFFIX}.csv", encoding="utf-8")):
            if all(row[k] == v for k, v in cond.items()):
                return row

    def show(label, how, v, c):
        print(f"| {label} | {how} | {v}% | {c}% | {'✓' if str(v) == c else '✗'} |")

    print("| 칸 | 다시 계산한 과정 | 다시 계산 | CSV 값 | 일치 |")
    print("|---|---|---|---|---|")
    for kind, week, bnd, api_map, en_map, cap in CHECKS:
        wk = [r for r in records if week_of(r["created_at"]) == week]
        name = f"{week} {KO[api_map]}"
        if kind == "사람×시간 비중":
            hm = lambda rs: sum(r["human_survived_sec"] / 60 for r in rs)
            m = [r for r in wk if r["map"] == api_map]
            v = round(100 * hm(m) / hm(wk), 1)
            c = csv_row("weekly_map_share", week=week, map_en=en_map)["human_time_share"]
            show(f"Q1 {name} 사람×시간 비중", f"{len(m)}건의 사람 생존 {hm(m):,.0f}분 ÷ 주 전체 {len(wk)}건 {hm(wk):,.0f}분", v, c)
        elif kind == "사람 비중":
            m = [r for r in wk if r["map"] == api_map]
            h_m, h_all = sum(r["humans"] for r in m), sum(r["humans"] for r in wk)
            c = csv_row("weekly_map_share", week=week, map_en=en_map)["human_share"]
            show(f"Q1 {name} 사람 비중", f"사람 {h_m:,}명 ÷ 주 전체 사람 {h_all:,}명", round(100 * h_m / h_all, 1), c)
        else:
            cell = [r for r in wk if r["mode"].startswith("squad") and band(r["created_at"]) == bnd
                    and r["map"] == api_map]
            if not cell:
                print(f"| Q2 {name} 스쿼드 {bnd} | 매치 0건 → 검증 생략 | - | - | - |")
                continue
            bots, players, humans = (sum(r[k] for r in cell) for k in ("bots", "players", "humans"))
            row = csv_row("weekly_map_by_band", group="squad", week=week, band=bnd, map_en=en_map)
            show(f"Q2 {name} 스쿼드 {bnd} 봇 비율", f"{len(cell)}건, 봇 {bots:,} ÷ 전체 {players:,}",
                 round(100 * bots / players, 1), row["bot_ratio"])
            show(f"Q2 같은 칸 정원 대비 사람", f"사람 {humans:,} ÷ {len(cell)}건 ÷ 정원 {cap}",
                 round(100 * humans / len(cell) / cap, 1), row["human_fill"])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else random.randrange(10000)
    records = load_records()
    print(f"[{PERIOD}] 분석 대상 매치: {len(records)}건 (일반 + 아시아 + 기간 {BOUNDS[0] or '처음'} ~ {BOUNDS[1]} UTC, 사람 0명 제외)\n")
    part1(records, n, seed, load_api_key())
    part2(records)


if __name__ == "__main__":
    main()
