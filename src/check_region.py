"""텔레메트리 앞부분만 받아 지역 코드를 읽을 수 있는지 테스트.

사용법: python3 src/check_region.py [샤드] [매치 수]   (기본값: steam 20)
"""
import glob
import json
import random
import re
import sys
import time
import urllib.request
import zlib
from collections import Counter

from test_api import BASE_URL, ROOT, call_api, load_api_key

CHUNK = 16 * 1024  # 한 번에 받는 크기 (16KB)
MATCH_ID_PATTERN = re.compile(rb'"MatchId"\s*:\s*"([^"]+)"')


def read_region(telemetry_url):
    """텔레메트리를 조금씩 받다가 MatchId를 찾으면 멈춘다. (지역, 받은 바이트, 전체 바이트, 초)"""
    start = time.time()
    req = urllib.request.Request(telemetry_url, headers={"Accept-Encoding": "gzip"})
    received, text = 0, b""
    decomp = None
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        while True:
            chunk = resp.read(CHUNK)
            if not chunk:
                break
            received += len(chunk)
            if decomp is None:  # 첫 조각을 보고 압축 여부 판단
                decomp = zlib.decompressobj(47) if chunk[:2] == b"\x1f\x8b" else False
            text += decomp.decompress(chunk) if decomp else chunk
            found = MATCH_ID_PATTERN.search(text)
            if found:
                # 예: match.bro.official.pc-2018-43.steam.solo-fpp.as.2026.10.12.23.<매치ID>
                parts = found.group(1).decode().split(".")
                prefix = ".".join(parts[:7])  # 날짜·매치ID 앞까지 (검증용)
                return parts[6], prefix, received, total, time.time() - start
    return None, None, received, total, time.time() - start


def main():
    shard = sys.argv[1] if len(sys.argv) > 1 else "steam"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    api_key = load_api_key()

    all_ids = []
    for f in sorted(glob.glob(str(ROOT / "data" / "raw" / "samples" / f"{shard}_*.json"))):
        all_ids += json.loads(open(f, encoding="utf-8").read())
    random.seed(42)  # 다시 돌려도 같은 매치가 뽑히도록 고정
    picked = random.sample(all_ids, n)

    rows = []
    for mid in picked:
        t0 = time.time()
        status, match = call_api(f"{BASE_URL}/{shard}/matches/{mid}", api_key)
        match_sec = time.time() - t0
        if match is None:
            continue
        a = match["data"]["attributes"]
        url = next(i["attributes"]["URL"] for i in match["included"] if i["type"] == "asset")
        region, prefix, got, total, tel_sec = read_region(url)
        humans = sum(1 for i in match["included"] if i["type"] == "participant"
                     and i["attributes"]["stats"]["playerId"].startswith("account."))
        players = sum(1 for i in match["included"] if i["type"] == "participant")
        rows.append(dict(id8=mid[:8], region=region, prefix=prefix, map=a["mapName"], mode=a["gameMode"],
                         type=a["matchType"], custom=a["isCustomMatch"], players=players,
                         humans=humans, got_kb=got / 1024, total_mb=total / 1e6,
                         match_sec=match_sec, tel_sec=tel_sec))
        r = rows[-1]
        print(f"{r['id8']} | 지역 {region} | {r['map']} {r['mode']} {r['type']} | "
              f"사람 {humans}/{players} | 받은 {r['got_kb']:.0f}KB / 전체 {r['total_mb']:.1f}MB | "
              f"매치 {match_sec:.1f}초 + 텔레메트리 {tel_sec:.1f}초")

    out = ROOT / "data" / "raw" / f"region_check_{shard}_{n}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    k = len(rows)
    print(f"\n성공 {k}/{n}건")
    print("지역 분포:", dict(Counter(r["region"] for r in rows).most_common()))
    print("MatchId 앞부분 종류:", dict(Counter(r["prefix"] for r in rows).most_common()))
    print("matchType 분포:", dict(Counter(r["type"] for r in rows).most_common()))
    print("모드 분포:", dict(Counter(r["mode"] for r in rows).most_common()))
    print(f"평균 받은 용량: {sum(r['got_kb'] for r in rows) / k:.0f}KB "
          f"(전체 파일 평균 {sum(r['total_mb'] for r in rows) / k:.1f}MB)")
    per_match = sum(r["match_sec"] + r["tel_sec"] for r in rows) / k
    print(f"매치 1건당 평균 소요: {per_match:.2f}초 → 전체 {len(all_ids)}건이면 약 "
          f"{per_match * len(all_ids) / 3600:.1f}시간 (순서대로 1건씩 처리할 때)")

    # 분석 대상(일반 + 아시아) 비율과 95% 신뢰구간(Wilson)으로 전체 건수 추정
    hit = sum(1 for r in rows if r["type"] == "official" and not r["custom"] and r["region"] == "as")
    p, z = hit / k, 1.96
    center = (p + z * z / (2 * k)) / (1 + z * z / k)
    half = z * ((p * (1 - p) / k + z * z / (4 * k * k)) ** 0.5) / (1 + z * z / k)
    lo, hi = center - half, center + half
    print(f"official + as: {hit}/{k}건 ({p:.0%}), 95% 신뢰구간 {lo:.0%} ~ {hi:.0%}")
    print(f"→ 전체 {len(all_ids)}건 중 약 {p * len(all_ids):,.0f}건 "
          f"(범위 {lo * len(all_ids):,.0f} ~ {hi * len(all_ids):,.0f}건)")


if __name__ == "__main__":
    main()
