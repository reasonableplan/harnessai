---
name: ha-smoke
description: |
  HarnessAI v2 — 런타임 기동 검증 (advisory 게이트). test/lint/type 이 전부 통과해도
  앱이 안 뜨는 산출물을 잡는다 — 검증 사다리의 최상단.
  Use when: /ha-verify 통과 후 또는 /ha-review 후 배포 전, "앱 떠지는지 확인", "/ha-smoke"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
---

## 역할

빌드 산출물이 **실제로 기동하는지** 검증하고 결과를 `verify_history` 에 기록 (step=`smoke`).
test/lint/type 은 코드 조각의 정합성만 본다 — import 누락, 엔트리포인트 오타, 환경변수 미설정,
포트 충돌 같은 "앱이 안 뜨는" 결함은 이 게이트만 잡는다.

**입력**: verified 또는 reviewed 상태
**출력**: 기동 PASS/FAIL + verify_history 갱신 (상태 전이 없음 — advisory)
**다음**: PASS 시 `/ha-accept` (GWT 수용 검증) 진행, FAIL 시 원인 수정 후 `/ha-verify` 부터 재검증

## 실행 순서

### 1. 사전 조건 + 프로파일 정보
```bash
python ~/.claude/skills/ha-smoke/run.py prepare
```
JSON 출력: 프로젝트 상태, 활성 프로파일별 `{id, path, cwd, smoke}`.
`smoke` 가 null 이면 실행 가능 Python 패키지(`__main__.py`)를 자동 탐지해
`smoke_suggested` (예: `python -m urlshort --help`) 를 함께 제공한다 (#8).

### 2. smoke 명령 결정

우선순위:
1. **`profiles[].smoke` 가 있으면 그대로 사용** (프로파일 toolchain.smoke 또는 사용자 정의)
2. **`profiles[].smoke_suggested` 가 있으면 그대로 사용** (run.py 가 `__main__.py` 에서 도출한 CLI 기동 명령)
3. 둘 다 없으면 **프로젝트 파일에서 도출** — package.json scripts / pyproject / 엔트리포인트를 Read 로 확인 후 아래 휴리스틱 적용:

| 프로파일 | 모드 | 명령 도출 | url |
|---|---|---|---|
| fastapi | url | `uv run uvicorn <app모듈>:app --port <빈포트>` | `http://127.0.0.1:<port>/docs` 또는 헬스 엔드포인트 |
| react-vite | url | `npm run dev -- --port <빈포트> --strictPort` | `http://127.0.0.1:<port>/` |
| nextjs | url | `npm run dev -- --port <빈포트>` | `http://127.0.0.1:<port>/` |
| nestjs | url | `PORT=<빈포트> npm run start` | `http://127.0.0.1:<port>/` |
| django | url | `uv run python manage.py runserver 127.0.0.1:<빈포트>` | `http://127.0.0.1:<port>/` |
| express 류 | url | `PORT=<빈포트> npm start` | `http://127.0.0.1:<port>/` |
| electron | exit | `npx electron . --no-sandbox` 가 어려우면 main 프로세스 단독: `node -e "require('./dist/main.js')"` 류 — 최소한 `npx tsc --noEmit` 가 아닌 **번들 로드** 확인 | — |
| CLI/스크립트 | exit | `<엔트리포인트> --help` 또는 `python -m <pkg> --help` | — |
| flutter | exit | `flutter build <플랫폼> --debug` (기동 대신 빌드 성공) | — |
| react-native-expo | exit | `bunx expo export` (JS 번들 성공 = import/모듈 해석 검증 — 네이티브 빌드 프록시) | — |
| android-kotlin | exit | `./gradlew assembleDebug` | — |
| ios-swift | exit | `swift build` (macOS 외에는 skip + summary 에 명시) | — |

- **포트는 프로젝트마다 다르다** — skeleton.md / .env.example / 설정 파일에서 확인하고,
  사용 중일 수 있으니 가능하면 빈 포트를 명시적으로 지정.
- 어떤 명령도 도출할 수 없으면 사용자에게 질문 — 임의 명령 발명 금지.

### 2.5. (백엔드 url 모드) 선언 엔드포인트 추출

url 모드는 root 하나만 200 이면 PASS 라 **"떠도 라우트가 깨진"** 결함 (라우터 미등록 404,
핸들러 import 누락 크래시 5xx) 을 못 잡는다. skeleton.md 의 `interface.http` 섹션에서
선언된 엔드포인트를 뽑아 기동 후 실제 타격한다:

- `interface.http` 에서 `` `GET /path` `` 토큰만 추출 (변경계 POST/PUT/PATCH/DELETE 는
  상태를 바꾸므로 제외 — 시나리오 스모크의 몫).
- path 파라미터 (`/items/{id}`, `/users/:id`) 가 있는 경로는 실제 값 없이 못 때리므로
  넘긴다 (run.py 가 자동 skip — 그대로 `--endpoint` 로 줘도 됨).
- 각 GET 경로를 `--endpoint /api/...` 로 반복 전달. 404/5xx = FAIL,
  2xx/3xx/401/403/422 = OK (라우트 존재 + 핸들러 도달).

### 3. probe 실행
```bash
# url 모드 (dev server 류) — 백엔드는 선언 GET 엔드포인트를 함께 타격
python ~/.claude/skills/ha-smoke/run.py probe \
  --command "<smoke 명령>" --cwd "<profile.cwd>" \
  --url "http://127.0.0.1:<port>/" --ready-timeout 60 \
  --endpoint "/api/users" --endpoint "/api/issues"

# exit 모드 (CLI/빌드 류)
python ~/.claude/skills/ha-smoke/run.py probe \
  --command "<smoke 명령>" --cwd "<profile.cwd>" --timeout 120
```
JSON 출력: `{passed, mode, detail, output_tail}`. url 모드는 판정 후 프로세스 트리를 자동 정리한다
(직접 백그라운드로 띄우고 kill 하지 말 것 — 자식 프로세스가 남는다).

복수 프로파일 (모노레포) 은 프로파일별로 probe 를 각각 실행.

### 3.5. (선택) 브라우저 콘솔 확인 — web/electron

url 모드 PASS 후 여력이 있으면 gstack `/browse` 로 해당 URL 을 열어 콘솔 에러를 확인.
HTTP 200 이어도 JS 런타임 에러로 빈 화면인 케이스를 잡는다. 콘솔 에러 발견 시 FAIL 로 취급.

### 4. 결과 기록
```bash
python ~/.claude/skills/ha-smoke/run.py record \
  --passed true|false \
  --summary "<예: fastapi HTTP 200 @ /docs (3.2s), frontend HTTP 200 @ / >"
```
- `verify_history` 에 step=`smoke` 엔트리 추가
- **상태 전이 없음** — advisory 게이트. FAIL 이어도 verified/reviewed 유지
- FAIL 시 summary 에 `detail` + `output_tail` 핵심 (스택트레이스 마지막 줄 등) 포함

### 5. 다음 안내

통과:
```
✅ /ha-smoke PASS
  backend: HTTP 200 @ http://127.0.0.1:8137/docs (uvicorn 기동 3.2s)
다음: /ha-accept (GWT 수용 기준 시나리오 검증)
```

실패:
```
❌ /ha-smoke FAIL (advisory — 상태는 유지되지만 배포 강행 비권장)
  backend: 프로세스가 ready 전에 종료 (exit code 1)
  원인: ModuleNotFoundError: No module named 'src.routes.health'
조치: 해당 T-ID 수정 → /ha-verify → /ha-smoke 재실행
```

## 가드레일

- probe 는 반드시 run.py 경유 — 직접 `npm run dev &` 식 백그라운드 기동 금지 (좀비 프로세스)
- 기동 실패를 "환경 문제겠지" 로 PASS 기록 금지 — 판단 불가면 passed=false + 사유 기록
- ready-timeout 은 60s 기본, cold start 가 긴 스택 (gradle 등) 만 늘릴 것
- DB 등 외부 의존성이 없어 못 뜨는 경우: docker compose 등 기동을 먼저 시도, 불가하면
  summary 에 "외부 의존성 미기동으로 skip" 명시 후 passed=false 가 아닌 **기록 자체를 보류**하고 사용자에게 보고
