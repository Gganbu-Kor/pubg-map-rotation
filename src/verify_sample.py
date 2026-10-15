"""핵심 수치를 원본 데이터와 직접 대조하는 확인용 출력.

사용법: python3 src/verify_sample.py [매치 수] [seed]   (기본값: 5건, seed는 매번 무작위)
1부: 분석 대상 매치를 골라 API 원본을 다시 받아 저장된 값과 비교 (원본은 data/raw/verify/ 에 저장)
2부: 보고서 핵심 칸을 분석 코드 없이 수집 파일에서 다시 계산해 CSV 값과 비교
닉네임·계정 ID는 출력하지 않는다.
"""
import csv
import json
import random
import sys
from collections import Counter
from datetime import datetime, timedelta

from check_region import read_region
from collect import fetch_match
from test_api import ROOT, load_api_key

CUTOFF = "2026-10-14T02:00:00Z"
W5_START = "2026-10-07T02:00:00Z"
VERIFY_DIR = ROOT / "data" / "raw" / "verify"


def kst(created_at):
    return datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=9)


def band(created_at):
    h = kst(created_at).hour
    return "피크" if h >= 20 or h <= 1 else ("오후" if h >= 14 else "비피크")


def load_records():
    """분석 코드와 같은 규칙을 따로 구현: 일반 + 아시아 + 컷오프 이전, 사람 0명 제외"""
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
                and r["region"] == "as" and r["created_at"] < CUTOFF
                and r["humans"] > 0):
            r["human_survived_sec"] = surv[r["match_id"]]["human_survived_sec"]
            r["human_max_survived_sec"] = surv[r["match_id"]]["human_max_survived_sec"]
            out.append(r)
    return out


def check(label, saved, fresh):
    ok = "✓" if saved == fresh else "✗ 불일치"
    print(f"  | {label} | {saved} | {fresh} | {ok} |")
    return saved == fresh


def part1(records, n, seed, api_key):
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
              f"{'W5' if a['createdAt'] >= W5_START else 'W4'}, {band(a['createdAt'])}")
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
        for row in csv.DictReader(open(ROOT / "data" / "processed" / name, encoding="utf-8")):
            if all(row[k] == v for k, v in cond.items()):
                return row

    w5 = [r for r in records if r["created_at"] >= W5_START]
    print("| 칸 | 다시 계산한 과정 | 다시 계산 | CSV 값 | 일치 |")
    print("|---|---|---|---|---|")

    # Q1: W5 파라모 사람×시간 비중 (전체 모드) = 사람 생존 시간 합의 비중
    hm = lambda rs: sum(r["human_survived_sec"] / 60 for r in rs)
    paramo = [r for r in w5 if r["map"] == "Chimera_Main"]
    v = round(100 * hm(paramo) / hm(w5), 1)
    c = csv_row("weekly_map_share.csv", week="43.1 W5", map_en="Paramo")["human_time_share"]
    print(f"| Q1 W5 파라모 사람×시간 비중 | 파라모 {len(paramo)}건의 사람 생존 {hm(paramo):,.0f}분 ÷ "
          f"W5 전체 {len(w5)}건 {hm(w5):,.0f}분 | {v}% | {c}% | {'✓' if str(v) == c else '✗'} |")

    # Q1: W4 태이고 사람 비중 (전체 모드)
    w4 = [r for r in records if r["created_at"] < W5_START]
    taego4 = [r for r in w4 if r["map"] == "Tiger_Main"]
    h_t, h_all = sum(r["humans"] for r in taego4), sum(r["humans"] for r in w4)
    v = round(100 * h_t / h_all, 1)
    c = csv_row("weekly_map_share.csv", week="43.1 W4", map_en="Taego")["human_share"]
    print(f"| Q1 W4 태이고 사람 비중 | 태이고 사람 {h_t:,}명 ÷ W4 전체 사람 {h_all:,}명 | {v}% | {c}% | "
          f"{'✓' if str(v) == c else '✗'} |")

    # Q2: W5 스쿼드 비피크 태이고 봇 비율, 정원 대비 사람
    cell = [r for r in w5 if r["mode"].startswith("squad") and band(r["created_at"]) == "비피크"
            and r["map"] == "Tiger_Main"]
    bots, players, humans = (sum(r[k] for r in cell) for k in ("bots", "players", "humans"))
    row = csv_row("weekly_map_by_band.csv", group="squad", week="43.1 W5", band="비피크", map_en="Taego")
    v1, v2 = round(100 * bots / players, 1), round(100 * humans / len(cell) / 100, 1)
    print(f"| Q2 W5 스쿼드 비피크 태이고 봇 비율 | {len(cell)}건, 봇 {bots:,} ÷ 전체 {players:,} | {v1}% | "
          f"{row['bot_ratio']}% | {'✓' if str(v1) == row['bot_ratio'] else '✗'} |")
    print(f"| Q2 같은 칸 정원 대비 사람 | 사람 {humans:,} ÷ {len(cell)}건 ÷ 정원 100 | {v2}% | "
          f"{row['human_fill']}% | {'✓' if str(v2) == row['human_fill'] else '✗'} |")

    # 제안: W4 스쿼드 비피크 카라킨 정원 대비 사람 (정원 64)
    cell = [r for r in w4 if r["mode"].startswith("squad") and band(r["created_at"]) == "비피크"
            and r["map"] == "Summerland_Main"]
    humans = sum(r["humans"] for r in cell)
    row = csv_row("weekly_map_by_band.csv", group="squad", week="43.1 W4", band="비피크", map_en="Karakin")
    v = round(100 * humans / len(cell) / 64, 1)
    print(f"| 제안 W4 스쿼드 비피크 카라킨 정원 대비 사람 | 사람 {humans:,} ÷ {len(cell)}건 ÷ 정원 64 | {v}% | "
          f"{row['human_fill']}% | {'✓' if str(v) == row['human_fill'] else '✗'} |")


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else random.randrange(10000)
    records = load_records()
    print(f"분석 대상 매치: {len(records)}건 (일반 + 아시아 + 10/14 11:00 KST 이전, 사람 0명 제외)\n")
    part1(records, n, seed, load_api_key())
    part2(records)


if __name__ == "__main__":
    main()
