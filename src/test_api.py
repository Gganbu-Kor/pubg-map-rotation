"""PUBG API 연결 테스트.

사용법: python3 src/test_api.py [steam|kakao ...]   (기본값: steam kakao)
"""
import json
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://api.pubg.com/shards"


def load_api_key():
    """.env 파일에서 PUBG_API_KEY 값만 읽는다. (키 값은 절대 출력하지 않는다)"""
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("PUBG_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(".env 파일에 PUBG_API_KEY 가 없습니다.")


def call_api(url, api_key):
    """API를 호출해 (상태 코드, JSON) 을 돌려준다. 오류면 상태 코드와 메시지를 그대로 보여준다."""
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/vnd.api+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[오류] HTTP {e.code} {e.reason}")
        print(f"[오류 메시지] {e.read().decode('utf-8', errors='replace')}")
        return e.code, None


def find_keys(obj, words, path=""):
    """JSON 전체를 뒤져서 이름에 words 중 하나가 들어간 키의 위치를 모은다."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if any(w in k.lower() for w in words):
                found.append(p)
            found += find_keys(v, words, p)
    elif isinstance(obj, list):
        for item in obj:
            found += find_keys(item, words, f"{path}[]")
    return found


def test_shard(shard, api_key):
    print(f"\n{'=' * 60}\n샤드: {shard}\n{'=' * 60}")

    # 1) samples 1회 호출
    status, samples = call_api(f"{BASE_URL}/{shard}/samples", api_key)
    print(f"[samples] HTTP 상태 코드: {status}")
    if samples is None:
        return
    match_refs = samples["data"]["relationships"]["matches"]["data"]
    print(f"[samples] 받은 매치 ID 개수: {len(match_refs)}")
    print(f"[samples] samples 자체의 attributes: {samples['data'].get('attributes')}")
    if not match_refs:
        return
    match_id = match_refs[0]["id"]
    print(f"[samples] 첫 매치 ID: {match_id}")

    # 2) 첫 매치 조회
    status, match = call_api(f"{BASE_URL}/{shard}/matches/{match_id}", api_key)
    print(f"\n[match] HTTP 상태 코드: {status}")
    if match is None:
        return
    # 원본은 닉네임이 있으므로 git 제외 폴더(data/raw)에만 저장
    raw_path = ROOT / "data" / "raw" / f"sample_match_{shard}.json"
    raw_path.write_text(json.dumps(match, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n[match] data.attributes 전체:")
    print(json.dumps(match["data"]["attributes"], ensure_ascii=False, indent=2))

    included = match.get("included", [])
    print("\n[match] included 안의 type별 개수:")
    for t, n in Counter(item["type"] for item in included).items():
        keys = sorted({k for item in included if item["type"] == t
                       for k in item.get("attributes", {}).keys()})
        print(f"  - {t}: {n}개  (attributes 키: {keys})")
    # participant 안쪽 stats 키 이름 (값은 닉네임이 있으므로 출력 안 함)
    stat_keys = sorted({k for item in included if item["type"] == "participant"
                        for k in item["attributes"].get("stats", {}).keys()})
    print(f"  participant.attributes.stats 키: {stat_keys}")

    # 3) 지역 정보 찾기
    print("\n[지역] 키 이름에 region/server/location/zone 이 들어간 위치:")
    hits = sorted(set(find_keys(match, ["region", "server", "location", "zone"])))
    print("  " + ("\n  ".join(hits) if hits else "없음"))

    # 4) 참가자 수 세기
    participants = [i for i in included if i["type"] == "participant"]
    rosters = [i for i in included if i["type"] == "roster"]
    in_rosters = sum(len(r["relationships"]["participants"]["data"]) for r in rosters)
    bots = sum(1 for p in participants
               if p["attributes"]["stats"].get("playerId", "").startswith("ai."))
    print("\n[참가자 수]")
    print(f"  participant 개수: {len(participants)}  (그중 봇 추정 'ai.' ID: {bots})")
    print(f"  roster(팀) 개수: {len(rosters)}, roster 안 participant 합계: {in_rosters}")


def main():
    api_key = load_api_key()
    for shard in sys.argv[1:] or ["steam", "kakao"]:
        test_shard(shard, api_key)


if __name__ == "__main__":
    main()
