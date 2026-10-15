"""최근 14일 날짜별 samples 매치 수 확인.

사용법: python3 src/check_samples.py [steam|kakao ...]   (기본값: steam kakao)
"""
import json
import sys
import time
from datetime import date, timedelta

from test_api import BASE_URL, ROOT, call_api, load_api_key

DAYS = 14
WAIT_SECONDS = 6.5  # 분당 10회 제한을 넘지 않도록 호출 사이에 쉬는 시간
OUT_DIR = ROOT / "data" / "raw" / "samples"


def main():
    api_key = load_api_key()
    shards = sys.argv[1:] or ["steam", "kakao"]
    today = date.today()
    days = [today - timedelta(days=i) for i in range(DAYS, 0, -1)]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    counts = {}
    for shard in shards:
        for d in days:
            url = f"{BASE_URL}/{shard}/samples?filter[createdAt-start]={d}T00:00:00Z"
            status, body = call_api(url, api_key)
            n = None
            if body is not None:
                ids = [m["id"] for m in body["data"]["relationships"]["matches"]["data"]]
                n = len(ids)
                # 매치 ID 목록만 저장 (다음 단계에서 매치 조회에 사용)
                (OUT_DIR / f"{shard}_{d}.json").write_text(json.dumps(ids), encoding="utf-8")
            counts[(shard, d)] = n
            print(f"{shard} {d}: HTTP {status}, 매치 {n if n is not None else '-'}개")
            time.sleep(WAIT_SECONDS)

    print("\n| 날짜 (UTC) | " + " | ".join(shards) + " |")
    print("|---|" + "---|" * len(shards))
    for d in days:
        cells = [str(counts[(s, d)]) if counts[(s, d)] is not None else "오류" for s in shards]
        print(f"| {d} | " + " | ".join(cells) + " |")
    totals = [sum(counts[(s, d)] or 0 for d in days) for s in shards]
    print("| 합계 | " + " | ".join(map(str, totals)) + " |")


if __name__ == "__main__":
    main()
