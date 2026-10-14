# Day 1 API 테스트 결과 (2026-10-15)

> PUBG 공식 API로 steam·kakao 샤드의 samples와 매치 데이터 구조를 확인한 기록.
> API 키, 플레이어 닉네임, 계정 ID는 적지 않았고, 매치 ID는 앞 8자리만 남겼다.

## 1. 준비
- `git init` 후 `git check-ignore -v .env` 결과: `.gitignore:2:.env	.env` → **.env는 업로드 제외됨**
- 테스트 코드: `src/test_api.py` (실행: `python3 src/test_api.py steam kakao`)
  - `.env`의 `PUBG_API_KEY`를 읽어 샤드별로 samples 1회 → 첫 매치 1회 조회
  - python-dotenv가 설치되어 있지 않아 표준 라이브러리(urllib)만 사용
- 원본 응답은 `data/raw/` (git 제외)에만 저장

## 2. 결과 요약

| 항목 | steam | kakao |
|---|---|---|
| samples HTTP 상태 코드 | 200 | 200 |
| samples 기준일 (createdAt) | 2026-10-13T00:00:00Z | 2026-10-13T00:00:00Z |
| 받은 매치 ID 개수 | 426 | 93 |
| 첫 매치 ID (앞 8자리) | d73cf152 | e06c4a6d |
| 매치 조회 HTTP 상태 코드 | 200 | 200 |
| mapName | Chimera_Main | Desert_Main |
| gameMode | solo-fpp | squad |
| duration (초) | 1471 | 2091 |
| participant 수 | 62 | 100 |
| └ 사람 (`account.`) / 봇 (`ai.`) | 14 / 48 | 6 / 94 |
| roster(팀) 수 | 62 | 27 |
| 매치 본문의 지역 정보 | 없음 | 없음 |
| 텔레메트리 MatchId의 지역 코드 | **na** | **kakao** |

## 3. data.attributes 전체

**steam (d73cf152)**
```json
{
  "seasonState": "progress",
  "stats": null,
  "gameMode": "solo-fpp",
  "tags": null,
  "mapName": "Chimera_Main",
  "createdAt": "2026-10-12T23:37:19Z",
  "duration": 1471,
  "titleId": "bluehole-pubg",
  "shardId": "steam",
  "isCustomMatch": false,
  "matchType": "official"
}
```

**kakao (e06c4a6d)**
```json
{
  "mapName": "Desert_Main",
  "isCustomMatch": false,
  "seasonState": "progress",
  "createdAt": "2026-10-13T00:00:58Z",
  "duration": 2091,
  "stats": null,
  "shardId": "kakao",
  "matchType": "official",
  "gameMode": "squad",
  "titleId": "bluehole-pubg",
  "tags": null
}
```

→ 문제정의서의 확인 항목 중 mapName, gameMode, duration, createdAt, matchType은 매치 본문에 있음. 일반/커스텀 구분은 `matchType`, `isCustomMatch`로 가능.

## 4. included 구성

| type | steam 개수 | kakao 개수 | attributes 키 |
|---|---|---|---|
| participant | 62 | 100 | actor, shardId, stats |
| roster | 62 | 27 | shardId, stats, won |
| asset | 1 | 1 | URL, createdAt, description, name |

- `participant.attributes.stats` 키: DBNOs, assists, boosts, damageDealt, deathType, headshotKills, heals, killPlace, killStreaks, kills, longestKill, name, playerId, revives, rideDistance, roadKills, swimDistance, teamKills, timeSurvived, vehicleDestroys, walkDistance, weaponsAcquired, winPlace
  - `name`(닉네임), `playerId`(계정 ID)는 개인 정보 → 결과물에 쓰지 않음
- `participant.attributes.actor`: 두 매치 모두 빈 문자열
- `roster.attributes.stats` 예시: `{rank, teamId}`
- `asset`: name = `telemetry`, description은 비어 있음, URL은 텔레메트리 파일 주소
  - 형태: `https://telemetry-cdn.pubg.com/bluehole-pubg/{shard}/YYYY/MM/DD/HH/mm/<파일명>`
- `data.relationships` 키: rosters, assets

## 5. 지역(region) 정보

**매치 API 응답:** 응답 전체에서 키 이름에 region / server / location / zone이 들어간 항목을 검색 → **없음**. (텔레메트리 URL 경로에도 샤드만 있고 지역은 없음)

**텔레메트리(매치당 1개 파일, 호출 제한 미포함):** `LogMatchDefinition.MatchId`에 지역 코드가 들어 있음.

| 샤드 | 파일 크기 | 이벤트 수 | MatchId 형태 |
|---|---|---|---|
| steam | 7.3MB | 12,535 | `match.bro.official.pc-2018-43.steam.solo-fpp.`**`na`**`.2026.10.12.23.d73cf152…` |
| kakao | 18.4MB | 31,540 | `match.bro.official.pc-2018-43.kakao.squad.`**`kakao`**`.2026.10.12.23.e06c4a6d…` |

- steam 첫 매치는 **북미(na)** 서버 → steam samples에는 여러 지역이 섞여 있음
- kakao는 지역이 하나뿐
- `LogMatchStart`에도 mapName, teamSize, isCustomGame, isEventMode, characters(시작 인원: steam 62, kakao 100)가 있음

## 6. 참가자 수
- `included`의 participant 개수로 셀 수 있음. roster 안 participant 합계와 일치(steam 62 = 62, kakao 100 = 100)
- `playerId`가 `ai.`로 시작하면 봇, `account.`로 시작하면 사람
- 두 매치 모두 봇이 대부분 → Q3(한 판 참가 인원)은 **전체 인원과 사람 인원을 나눠서** 봐야 함

## 7. 첫날 확인 항목 체크

| 항목 | 결과 |
|---|---|
| 서버 지역 정보 | 매치 API에는 없음, 텔레메트리에는 있음 |
| mapName, gameMode, duration, createdAt, matchType, 참가자 수 | 모두 있음 |
| 직접 선택 / 빠른 참가 구분 | 매치 본문에서 관련 항목 발견 못 함 (한계 후보) |
| 14일 주차·로테이션 표 | 아직 확인 안 함 |

## 8. 남은 결정 / 확인
1. **스팀 아시아 분석 여부:** 지역을 알려면 매치마다 텔레메트리(7~18MB)를 받아야 함 → 문제정의서의 "텔레메트리 제외" 범위를 바꿀지, 카카오로 바꿀지 결정 필요
2. **카카오 표본 수:** 하루 samples가 93건 → 14일 다 모아도 약 1,300건으로 3,000건 기준에 못 미칠 수 있음 (하루치만 확인했으므로 다른 날짜 추가 확인 필요)
3. 이번 결과는 각 샤드 매치 **1건씩만** 본 것이므로 봇 비율 등은 일반화하면 안 됨
