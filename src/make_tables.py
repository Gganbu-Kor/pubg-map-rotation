"""분석 결과 CSV로 보고서용 최종 표(Q1, Q2)를 만든다.

사용법: python3 src/make_tables.py   (먼저 analyze_weekly.py, analyze_by_band.py 실행)
출력: outputs/report/final_tables.md (집계 수치만)
"""
import csv

from analyze_weekly import WEEKS
from test_api import ROOT

PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "report" / "final_tables.md"
SLOT_KO = {"fixed": "고정", "favored": "선호", "etc": "기타"}
BANDS = ["피크", "오후", "비피크"]


def ranks(rows, key):
    """그 주 5개 맵 안에서 key 값이 큰 순서대로 1~5위"""
    order = sorted(rows, key=lambda r: -float(r[key]))
    return {r["map_en"]: i + 1 for i, r in enumerate(order)}


def q1_section(lines):
    rows = list(csv.DictReader(open(PROC / "weekly_map_share.csv", encoding="utf-8")))
    lines += ["## Q1. 주차별 공식 선호도(참고) vs 사람 기준 비중",
              "> 기준: **전체 모드, 전체 시간대**, 사람 0명 매치 제외. 순위는 그 주 로테이션 5개 맵 안에서의 순위.",
              "> 공식 선호도는 측정 기간(8/3 ~ 9/28)이 달라 정답이 아닌 참고 기준.", ""]
    for week in WEEKS:
        w = [r for r in rows if r["week"] == week]
        rp, rh, rt = ranks(w, "pref_43_2"), ranks(w, "human_share"), ranks(w, "human_time_share")
        n = sum(int(r["matches"]) for r in w)
        # 공식 선호도는 9개 맵 합이 100% → 그 주 열린 5개 맵끼리 다시 100%로 나눠야 내 비중과 같은 기준
        pref_sum = sum(float(r["pref_43_2"]) for r in w)
        lines += [f"### {week} (매치 {n:,}건)", "",
                  "| 맵 | 자리 | 43.2 선호도 (순위) | 선호도를 5개 맵 기준으로 환산 | 사람 비중 (순위) "
                  "| 사람×시간 비중 (순위) | 매치 비중 (참고) |",
                  "|---|---|---|---|---|---|---|"]
        for r in sorted(w, key=lambda r: rp[r["map_en"]]):
            m = r["map_en"]
            mark = lambda rk: f"{rk}위" + ("" if rk == rp[m] else " ←")
            lines.append(f"| {r['map_ko']} | {SLOT_KO[r['slot']]} | {r['pref_43_2']}% ({rp[m]}위) | "
                         f"{100 * float(r['pref_43_2']) / pref_sum:.1f}% | "
                         f"{r['human_share']}% ({mark(rh[m])}) | {r['human_time_share']}% ({mark(rt[m])}) | "
                         f"{r['match_share']}% |")
        same_h = sum(rh[m] == rp[m] for m in rp)
        same_t = sum(rt[m] == rp[m] for m in rp)
        gap = lambda key: sum(abs(float(r[key]) - 100 * float(r["pref_43_2"]) / pref_sum) for r in w) / len(w)
        lines += ["", f"순위 일치: 사람 비중 {same_h}/5개, 사람×시간 비중 {same_t}/5개 맵 (← 표시는 공식 순위와 다른 칸)",
                  f"환산 선호도와의 평균 차이: 사람 비중 {gap('human_share'):.1f}%p, "
                  f"사람×시간 비중 {gap('human_time_share'):.1f}%p, 매치 비중 {gap('match_share'):.1f}%p", ""]


def q2_section(lines):
    rows = [r for r in csv.DictReader(open(PROC / "weekly_map_by_band.csv", encoding="utf-8"))
            if r["group"] == "squad"]
    lines += ["## Q2·제안. 시간대별 봇 비율과 정원 대비 사람 비율",
              "> 기준: **스쿼드만(1인칭 포함)**, 사람 0명 매치 제외. 시간대는 한국 시간 피크 20~01시, 오후 14~19시, 비피크 02~13시.",
              "> 정원 대비 사람 = 한 판 사람 수 ÷ 최대 인원(카라킨·파라모 64명, 나머지 100명). 괄호는 매치 수.", ""]
    for week in WEEKS:
        w = [r for r in rows if r["week"] == week]
        maps = []
        for r in w:
            if r["map_en"] not in [m["map_en"] for m in maps]:
                maps.append(r)
        lines += [f"### {week}", "",
                  "| 맵 | 자리 | 봇 비율 피크 | 오후 | 비피크 | 정원 대비 사람 피크 | 오후 | 비피크 |",
                  "|---|---|---|---|---|---|---|---|"]
        for m in maps:
            cell = {r["band"]: r for r in w if r["map_en"] == m["map_en"]}
            bot = [f"{cell[b]['bot_ratio']}% ({cell[b]['matches']})" for b in BANDS]
            fill = [f"{cell[b]['human_fill']}%" for b in BANDS]
            lines.append(f"| {m['map_ko']} | {SLOT_KO[m['slot']]} | " + " | ".join(bot + fill) + " |")
        lines.append("")
    lines += ["표본 주의: 비피크 칸은 맵당 14~198건. 30건 미만 칸은 몇 판에 따라 크게 바뀌므로 경향 수준으로만 해석.", ""]


def main():
    lines = ["# 최종 표 (자동 생성: src/make_tables.py)", "",
             "분석 대상: 스팀 아시아(as) 일반 매치, 43.1 W4·W5 (10/2 08:35 ~ 10/14 11:00 KST), 사람 0명 매치 제외", ""]
    q1_section(lines)
    q2_section(lines)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n저장: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
