"""핵심 숫자의 95% 범위(부트스트랩)를 계산한다.

사용법: python3 src/bootstrap_ci.py
방법: 각 칸의 매치를 같은 개수만큼 중복 허용으로 다시 뽑아 숫자를 다시 계산하는 일을 2,000번 반복하고,
      그 결과의 하위 2.5% ~ 상위 2.5% 사이를 95% 범위로 본다. (seed 고정 → 다시 돌려도 같은 결과)
출력: data/processed/bootstrap_ci.csv (집계 수치만)
"""
import csv
import random
from collections import defaultdict

from analyze_by_band import HOUR_TO_BAND
from analyze_by_hour import kst_hour
from analyze_weekly import API_TO_EN, MAX_PLAYERS, PREF_43_2, SUFFIX, WEEKS, load_matches
from test_api import ROOT

B = 2000
RNG = random.Random(42)
OUT = ROOT / "data" / "processed" / f"bootstrap_ci{SUFFIX}.csv"


def ci(values):
    s = sorted(values)
    return s[int(0.025 * len(s))], s[int(0.975 * len(s)) - 1]


def resample(rs):
    return [rs[RNG.randrange(len(rs))] for _ in rs]


def bot_ratio(rs):
    return 100 * sum(r["bots"] for r in rs) / sum(r["players"] for r in rs)


def human_fill(rs, cap):
    return 100 * sum(r["humans"] for r in rs) / len(rs) / cap


def q1_gaps(rs, maps):
    """그 주 5개 맵의 환산 선호도와 사람 비중·사람×시간 비중의 평균 차이(%p)"""
    pref_sum = sum(PREF_43_2[m] for m in maps)
    h = defaultdict(float)
    t = defaultdict(float)
    for r in rs:
        h[r["map_en"]] += r["humans"]
        t[r["map_en"]] += r["human_survived_sec"]
    th, tt = sum(h.values()), sum(t.values())
    gap_h = sum(abs(100 * h[m] / th - 100 * PREF_43_2[m] / pref_sum) for m in maps) / len(maps)
    gap_t = sum(abs(100 * t[m] / tt - 100 * PREF_43_2[m] / pref_sum) for m in maps) / len(maps)
    return gap_h, gap_t


def main():
    starts = {}
    rotation = defaultdict(list)
    for row in csv.DictReader(open(ROOT / "data" / "processed" / "rotation_as_pc.csv", encoding="utf-8")):
        starts[row["week"]] = row["start_utc"]
        rotation[row["week"]].append(row["map_en"])
    rs_all = load_matches()
    for r in rs_all:
        r["week"] = [w for w in WEEKS if r["created_at"] >= starts[w]][-1]
        r["map_en"] = API_TO_EN[r["map"]]
        r["band"] = HOUR_TO_BAND[kst_hour(r["created_at"])]
        r["squad"] = r["mode"].startswith("squad")
    rows = []

    def add(metric, week, map_en, band, n, est, lo, hi):
        rows.append({"metric": metric, "week": week, "map_en": map_en, "band": band, "n": n,
                     "estimate": round(est, 1), "ci_low": round(lo, 1), "ci_high": round(hi, 1)})

    # ① Q1: 환산 선호도와의 평균 차이 (전체 모드)
    print("① Q1 환산 선호도와의 평균 차이 (%p, 95% 범위)")
    for w in WEEKS:
        rs = [r for r in rs_all if r["week"] == w]
        est = q1_gaps(rs, rotation[w])
        boot = [q1_gaps(resample(rs), rotation[w]) for _ in range(B)]
        for i, name in enumerate(["q1_gap_human_share", "q1_gap_human_time_share"]):
            lo, hi = ci([b[i] for b in boot])
            add(name, w, "", "", len(rs), est[i], lo, hi)
            print(f"  {w} {'사람 비중' if i == 0 else '사람×시간 비중'}: {est[i]:.1f} ({lo:.1f} ~ {hi:.1f})")

    # ② 스쿼드: 맵 × 시간대 봇 비율, 비피크 − 피크 차이
    print("\n② 스쿼드 봇 비율: 비피크 − 피크 차이 (%p, 95% 범위) → 범위가 0보다 크면 '비피크에 확실히 높음'")
    for w in WEEKS:
        for m in rotation[w]:
            cell = {b: [r for r in rs_all if r["week"] == w and r["squad"] and r["map_en"] == m and r["band"] == b]
                    for b in ("피크", "오후", "비피크")}
            for b, rs in cell.items():
                if not rs:  # 매치가 없는 칸은 계산하지 않음 (W1처럼 기간이 짧을 때)
                    continue
                cap = MAX_PLAYERS.get(m, 100)
                boot_b = [bot_ratio(resample(rs)) for _ in range(B)]
                boot_f = [human_fill(resample(rs), cap) for _ in range(B)]
                add("squad_bot_ratio", w, m, b, len(rs), bot_ratio(rs), *ci(boot_b))
                add("squad_human_fill", w, m, b, len(rs), human_fill(rs, cap), *ci(boot_f))
            pk, op = cell["피크"], cell["비피크"]
            if not pk or not op:
                print(f"  {w} {m:8s}: 피크 {len(pk)}건 / 비피크 {len(op)}건 → 매치가 없어 계산 생략")
                continue
            diffs = [bot_ratio(resample(op)) - bot_ratio(resample(pk)) for _ in range(B)]
            lo, hi = ci(diffs)
            est = bot_ratio(op) - bot_ratio(pk)
            add("squad_bot_offpeak_minus_peak", w, m, "", len(op), est, lo, hi)
            if min(len(pk), len(op)) < 10:
                verdict = "표본 너무 적음(10건 미만): 판단 보류"
            elif lo > 0:
                verdict = "확실히 높음"
            elif hi < 0:
                verdict = "확실히 낮음"
            else:
                verdict = "0을 포함: 우연일 수 있음"
            print(f"  {w} {m:8s}: {est:+5.1f} ({lo:+5.1f} ~ {hi:+5.1f}), 비피크 {len(op)}건  ← {verdict}")

    # ③ 발견 1 헤드라인: 스쿼드 22시 vs 09시 봇 비율 (기간 전체 합계)
    print("\n③ 스쿼드 봇 비율 22시 vs 09시 (기간 전체 합계, 95% 범위)")
    for h in (22, 9):
        rs = [r for r in rs_all if r["squad"] and kst_hour(r["created_at"]) == h]
        if not rs:
            print(f"  {h:02d}시: 매치 없음")
            continue
        lo, hi = ci([bot_ratio(resample(rs)) for _ in range(B)])
        add("squad_bot_ratio_hour", "", "", f"{h:02d}시", len(rs), bot_ratio(rs), lo, hi)
        print(f"  {h:02d}시: {bot_ratio(rs):.1f}% ({lo:.1f} ~ {hi:.1f}), {len(rs)}건")

    # ④ 발견 3: 맵별 정원 대비 사람 비율 (전체 모드)
    print("\n④ 정원 대비 사람 비율 (전체 모드, 95% 범위)")
    for w in WEEKS:
        for m in rotation[w]:
            rs = [r for r in rs_all if r["week"] == w and r["map_en"] == m]
            cap = MAX_PLAYERS.get(m, 100)
            lo, hi = ci([human_fill(resample(rs), cap) for _ in range(B)])
            add("human_fill_all_modes", w, m, "", len(rs), human_fill(rs, cap), lo, hi)
            print(f"  {w} {m:8s}: {human_fill(rs, cap):.1f}% ({lo:.1f} ~ {hi:.1f}), {len(rs)}건")

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    print(f"\n저장: {OUT.relative_to(ROOT)} ({len(rows)}행)")


if __name__ == "__main__":
    main()
