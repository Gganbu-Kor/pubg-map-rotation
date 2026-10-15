"""이미 수집한 일반+아시아 매치를 다시 조회해 사람들의 생존 시간 합·최대를 추가로 저장한다.

사용법: python3 src/add_survival.py   (중간에 멈춰도 다시 실행하면 이어서 진행)
저장: data/raw/survival_steam.jsonl  ({"match_id", "human_survived_sec", "human_max_survived_sec"} 1건 = 1줄, 같은 매치는 마지막 줄 사용)
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from collect import RETRIES, WORKERS, fetch_match, human_survived
from test_api import ROOT, load_api_key

SRC = ROOT / "data" / "raw" / "collect_steam.jsonl"
OUT = ROOT / "data" / "raw" / "survival_steam.jsonl"


def work(match_id, api_key):
    for attempt in range(RETRIES):
        try:
            return {"match_id": match_id, **human_survived(fetch_match(match_id, api_key))}
        except Exception as e:
            if attempt == RETRIES - 1:
                return {"match_id": match_id, "error": f"{type(e).__name__}: {str(e)[:200]}"}
            time.sleep(2 * (attempt + 1))


def main():
    api_key = load_api_key()
    targets = set()
    for line in open(SRC, encoding="utf-8"):
        r = json.loads(line)
        if r.get("region") == "as" and r.get("match_type") == "official" and not r.get("custom"):
            targets.add(r["match_id"])
    done = set()
    if OUT.exists():
        for line in open(OUT, encoding="utf-8"):
            r = json.loads(line)
            if "error" not in r and "human_max_survived_sec" in r:
                done.add(r["match_id"])
    todo = sorted(targets - done)
    print(f"대상 {len(targets)}건 중 이미 완료 {len(done)}건, 이번에 처리 {len(todo)}건", flush=True)

    errors = 0
    with open(OUT, "a", encoding="utf-8") as out, ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(work, mid, api_key) for mid in todo]
        for n, fut in enumerate(as_completed(futures), 1):
            rec = fut.result()
            errors += "error" in rec
            out.write(json.dumps(rec) + "\n")
            out.flush()
            if n % 1000 == 0 or n == len(todo):
                print(f"[{time.strftime('%H:%M:%S')}] {n}/{len(todo)}건, 오류 {errors}건", flush=True)
    print(f"완료: 오류 {errors}건", flush=True)


if __name__ == "__main__":
    main()
