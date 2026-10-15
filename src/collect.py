"""steam samples 매치를 모두 조회해 매치별 집계 정보를 모은다.

사용법: python3 src/collect.py   (중간에 멈춰도 다시 실행하면 이어서 진행)
저장: data/raw/collect_steam.jsonl (매치 1건 = 1줄, 닉네임·계정 ID는 저장하지 않음)
      오류였던 매치는 다시 실행할 때 재시도하므로, 같은 매치가 여러 줄일 수 있다 → 분석 때 마지막 줄 사용
"""
import glob
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from check_region import read_region
from test_api import BASE_URL, ROOT, load_api_key

SHARD = "steam"
WORKERS = 4         # 동시에 처리할 매치 수 (/matches 와 텔레메트리는 호출 제한 없음)
RETRIES = 3         # 네트워크 오류 시 재시도 횟수
REPORT_EVERY = 500  # 진행 상황을 몇 건마다 출력할지
OUT = ROOT / "data" / "raw" / f"collect_{SHARD}.jsonl"


def fetch_match(match_id, api_key):
    """매치 1건 조회해 JSON을 돌려준다. (오류는 호출한 쪽에서 처리)"""
    req = urllib.request.Request(f"{BASE_URL}/{SHARD}/matches/{match_id}", headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/vnd.api+json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def human_survived(match):
    """사람(account.)들의 생존 시간(초) → {합 = 실제 이용 시간, 최대 = 사람 기준 경기 시간}
    duration은 마지막 봇이 사라질 때까지의 시간이라 경기 시간으로 쓰지 않는다."""
    times = [i["attributes"]["stats"]["timeSurvived"] for i in match["included"]
             if i["type"] == "participant"
             and i["attributes"]["stats"]["playerId"].startswith("account.")]
    return {"human_survived_sec": sum(times), "human_max_survived_sec": max(times, default=0)}


def process(match_id, sample_date, api_key):
    """매치 1건을 조회해 저장할 한 줄(dict)을 만든다. 일반 매치만 텔레메트리로 지역 확인."""
    rec = {"match_id": match_id, "sample_date": sample_date}
    for attempt in range(RETRIES):
        try:
            match = fetch_match(match_id, api_key)
            break
        except urllib.error.HTTPError as e:
            # 404(보관 기간 지남) 등은 재시도해도 같으므로 그대로 기록
            rec.update(error=f"HTTP {e.code}", error_msg=e.read().decode("utf-8", "replace")[:200])
            return rec
        except Exception as e:  # 연결 끊김, 시간 초과 등
            if attempt == RETRIES - 1:
                rec.update(error=type(e).__name__, error_msg=str(e)[:200])
                return rec
            time.sleep(2 * (attempt + 1))

    a = match["data"]["attributes"]
    inc = match["included"]
    player_ids = [i["attributes"]["stats"]["playerId"] for i in inc if i["type"] == "participant"]
    rec.update(human_survived(match))
    rec.update(
        created_at=a["createdAt"], map=a["mapName"], mode=a["gameMode"],
        match_type=a["matchType"], custom=a["isCustomMatch"], duration=a["duration"],
        players=len(player_ids),
        humans=sum(p.startswith("account.") for p in player_ids),
        bots=sum(p.startswith("ai.") for p in player_ids),
        teams=sum(1 for i in inc if i["type"] == "roster"),
        region=None,
    )
    # 지역은 분석 대상 후보(일반 + 비커스텀)만 확인해서 시간 절약
    if a["matchType"] == "official" and not a["isCustomMatch"]:
        url = next(i["attributes"]["URL"] for i in inc if i["type"] == "asset")
        for attempt in range(RETRIES):
            try:
                rec["region"] = read_region(url)[0]
                break
            except Exception as e:
                if attempt == RETRIES - 1:
                    rec.update(error="telemetry " + type(e).__name__, error_msg=str(e)[:200])
                time.sleep(2 * (attempt + 1))
    return rec


def main():
    api_key = load_api_key()

    # 오래된 날짜부터 (보관 기간 14일이 지나면 사라지므로)
    todo = []
    for f in sorted(glob.glob(str(ROOT / "data" / "raw" / "samples" / f"{SHARD}_*.json"))):
        d = Path(f).stem.split("_", 1)[1]
        todo += [(mid, d) for mid in json.loads(open(f, encoding="utf-8").read())]

    # 이미 처리한 매치는 건너뛰기 (오류였던 매치는 다시 시도)
    done = set()
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if "error" not in r:
                done.add(r["match_id"])
    todo = [t for t in todo if t[0] not in done]
    print(f"전체 대상 {len(todo) + len(done)}건 중 이미 완료 {len(done)}건, 이번에 처리 {len(todo)}건", flush=True)

    start = time.time()
    n = target = errors = 0
    with open(OUT, "a", encoding="utf-8") as out, ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(process, mid, d, api_key) for mid, d in todo]
        for fut in as_completed(futures):
            rec = fut.result()
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            n += 1
            errors += "error" in rec
            target += rec.get("region") == "as"
            if n % REPORT_EVERY == 0 or n == len(todo):
                elapsed = time.time() - start
                left = elapsed / n * (len(todo) - n)
                print(f"[{time.strftime('%H:%M:%S')}] {n}/{len(todo)}건 처리 | "
                      f"일반+아시아 {target}건 | 오류 {errors}건 | "
                      f"경과 {elapsed / 60:.0f}분, 남은 시간 약 {left / 60:.0f}분", flush=True)

    print(f"완료: 이번 실행에서 일반+아시아 {target}건, 오류 {errors}건", flush=True)


if __name__ == "__main__":
    main()
