# Changelog

HarnessAI 의 모든 주요 변경 사항. 형식은 [Keep a Changelog](https://keepachangelog.com/) 기준, 버전은 [SemVer](https://semver.org/) 준수 (pre-1.0 단계).

---

## [0.21.0] — 2026-07-13 — "수용검증 계층 /ha-accept: GWT 수용 기준 → 실행 시나리오"

검증 사다리의 마지막 빈 칸 — test/lint/type(verify) → 기동(smoke) → **"요구사항대로
동작하는가"(accept)**. ha-design Step D 에서 사용자와 확정한 GWT 수용 기준이 문서에서
실행 가능한 게이트로 격상. 조사 근거: SDD 수렴(Spec Kit/Kiro)·EARS 표기법·선언적 러너
landscape (Tavern/Hurl/StepCI — 의존성 대비 래핑 비용 동일해 stdlib 자체 구축 결정).
설계: `backend/docs/acceptance-layer-design.md`

### Added

- **/ha-accept 스킬** — prepare (skeleton 에서 GWT/확정기능/선언 엔드포인트 추출,
  구버전 skeleton 은 `legacy_skeleton` 명시) → LLM 파생 (`docs/acceptance.yaml` —
  파생은 LLM, 실행은 결정론, ha-plan 패턴) → validate (스키마 BLOCK + skeleton
  교차검증 BLOCK + 커버리지 advisory) → run (http=booted_server / cli=subprocess,
  stdlib 미니 러너 — dotted path 단언·{var} 캡처/치환) → record (verify_history
  step=`accept`, advisory — 상태 전이 없음). 도출 불가 GWT 는 `underivable` 에 사유
  명시 (Kiro EARS 차용 — 조용한 커버리지 구멍 차단)
- **`skills/_ha_shared/runtime.py`** — kill_tree/wait_ready/booted_server 공용 추출.
  ha-smoke 도 동일 모듈로 리팩터 (동작 불변, 기존 테스트 무수정 그린)
- **pipeline_advisor accept 통합** — smoke passed → accept 제안 (앱 부팅 전제),
  accept FAIL → HITL (smoke 와 동일 시맨틱)
- **공허 통과 3중 차단** — kind 별 expect 허용 키 분리 (http 스텝의 `exit` 같은 교차
  키는 조용한 무시 대신 BLOCK) / run `--profile` 매칭 0개 BLOCK (오타가 공허 통과로
  둔갑 방지) / 부팅 실패 시 전 시나리오 실행-불가 FAIL (발명된 PASS 금지)
- 회귀 65 tests (accept 56 + runtime + advisor). GATES 집계 BLOCK 25

### Fixed

- **파이프라인 순서 문서↔실행 불일치** — advisor(실제 드라이버)는
  verify→smoke→accept→review 로 운전하는데 CLAUDE.md/README×2/ha-verify next 힌트가
  verify→review→smoke (advisor 도입 전 stale) → 코드 1곳 + 문서 5곳을 실행 현실에 정렬

---

## [0.20.0] — 2026-07-12 — "스캐폴딩 흡수: T-000 결정론 부트스트랩 + 스텁 스탬퍼"

"결정론으로 처리 가능한 구조는 LLM 에게 맡기지 않는다" — 설정 보일러플레이트와 파일
구조를 기계가 잡고 LLM 은 로직만 채우는 형태로 전환. LLM 손작성 보일러플레이트가
"test 통과해도 앱이 안 뜨는" 산출물의 주 발생원이라는 진단(런타임 깨짐 최우선 피드백)
에서 출발. 조사 근거: Plop/Hygen(스텁 원리)·Projen(생성물 게이트)·create-next-app v16
플래그 검증. 설계: `backend/docs/scaffolding-design.md`

### Added

- **`toolchain.scaffold` 프로파일 필드** — 비대화 스캐폴드 명령 (nextjs =
  `create-next-app@16` + `--no-agents-md` 로 생성 CLAUDE.md 충돌 차단 / react-vite =
  `create-vite --no-interactive`). 공식 스캐폴더 없는 프로파일은 null 유지
- **T-000 결정론 부트스트랩** — ha-plan commit 이 자동 주입 (scaffold 프로파일 보유 +
  detect 불일치 시, 중복 주입 방지). ha-build `scaffold` 서브커맨드 = 샌드박스 실행 →
  무덮어쓰기 병합 → install → detect 재평가 (멱등). `scaffold` 는 예약 의사 에이전트
- **스텁 스탬퍼** — ha-build prepare 가 declared_files 부재분을 HARNESS-STUB 마커
  스텁으로 선생성 (확장자별 주석 문법, 디렉토리/글롭/.json 제외, `--no-stamp` 옵트아웃)
  — 경로/파일명 드리프트를 프롬프트 준수 문제에서 물리적 불가능으로 격상
- **게이트 3** — scaffold 선행 BLOCK (`--skip-scaffold-gate`) / 스텁 미구현 BLOCK
  (우회 없음 — 구현 또는 삭제가 조치) / T-000 complete `--skip-toolchain` 특례
  (갓 스캐폴드된 앱은 test 스크립트 부재 — security gate 는 유지). GATES 집계 BLOCK 22
- 회귀 49 tests (scaffold 20 + stamper 26 + profile_loader 3)

---

## [0.19.5] — 2026-07-08 — "프롬프트 전수 평가 후속 + 유사도구 조사 채택 배치 3건"

v0.19.4 전수 평가에서 남긴 결함 수정 + 외부 유사도구 조사(Ralph 루프/DeepWiki 인용 방식)
에서 채택한 3건.

### Fixed

- web coder 프롬프트 whitelist 단일소스 백포트 (모바일 4종과 동일 원칙 — v0.19.4 후속)
- frontend coder §3 모순 표현 정리, orchestrator 프롬프트 qa 잔재 제거

### Added

- **ha-review FP 학습 루프** — `--allow-block` 처리 내역을 `[FP 후보]` lesson 으로
  자동 추출 (origin 태그) — 같은 오탐을 다음 리뷰가 반복하지 않게 누적
- **ha-deepinit validate 인용 게이트** — Agent 가 쓴 AGENTS.md 의 백틱 파일 인용
  실존/라인 범위 검증 (DeepWiki 방식) — 환각 경로 차단
- **`harness/bin/ha-loop`** — Ralph 식 외부 루프 (스텝마다 fresh `claude -p` 세션,
  옵트인) — 긴 자율 런의 컨텍스트 부패/30루프 상한 해소
- 회귀 27 tests (pytest 1441)

---

## [0.19.4] — 2026-07-06 — "push 전 전면 감사: 프롬프트/문서 stale 제거 + whitelist 단일소스화"

프롬프트 표면 전수 감사 (SKILL.md 15 + 에이전트 프롬프트 12 + 프로파일/문서) + 외부
리서치 (모델 라인업/Expo 생태계/차트 라이브러리/경량 임베딩) 결과 반영. 코드 경로는
clean (구형 모델명·dead code·TODO 전부 0건) — stale 은 프롬프트/문서에 집중돼 있었다.

### Fixed

- **모바일 코더 4개 프롬프트 whitelist 단일소스화** — "(프로파일과 동기)" 를 주장하던
  인라인 목록이 실제 프로파일과 대폭 불일치 (ios 는 프로파일에 없는 Apollo/Realm 을
  허용 기재 — 위반 유도). 인라인 목록을 제거하고 "ha-build prepare 출력의 프로파일
  whitelist = 단일 소스" 참조로 교체 — drift 원인 자체를 제거. 회귀 테스트 신설
  (`test_agent_prompt_whitelist.py`, 6 tests)
- SETUP.md "/ha-* 스킬 7종" → 15종 (stale count)
- ha-init SKILL.md §6.5 번호 중복 (conventions 확인 / git baseline) → git baseline 을 §6.6
- ha-review SKILL.md 훅 요약에 v0.19.3 신설 db-guard `.exec` 보간/concat 패턴 반영
- ha-smoke 명령 도출 표에 django (url: `manage.py runserver`) +
  react-native-expo (exit: `bunx expo export` 번들 프록시) 행 추가
- ha-log SKILL.md 역할 문구 — 리포지토리 고정 경로 표현을 프로젝트별 해석 규칙과 일치시킴
- GUIDELINES_NOTE.md 프로파일 표에 django/claude-skill (0건) 행 추가
- coder/orchestrator 프롬프트의 v1 잔재 표현 정리 — "branch 생성 + PR 제출" 을
  v2 `ha-build complete` 기준으로, "Phase 리뷰 트리거" 에 v1 전용 주석

### Added

- **react-native-expo whitelist 에 `react-native-svg` + `react-native-gifted-charts`**
  — workout dogfood #14 실수요 (차트 요구를 로컬 우회로 처리했던 것) + 2026 생태계
  조사 (gifted-charts/victory-native 양강) 근거로 승격
- **ha-design 디자인 레퍼런스 모바일 폴백** (dogfood #11) — 특별 가드 옵션이 프로파일
  기준으로 분기: 웹=shadcn/ui, 모바일=Mobbin 해당 도메인 앱 패턴 (+도메인 키워드 메모).
  shadcn(웹 라이브러리)이 모바일 폴백으로 박히던 결함 해소

### Research (기록)

- 모델 티어 재평가: judge=opus-4-8 / code=sonnet-5 유지 확정 (Fable 5 는 2배 가격 +
  refusal/retention 제약으로 subprocess judge 부적합. Sonnet 5 인트로가 2026-08-31 종료)
- #4 키워드→임베딩 백로그 재평가: Model2Vec (정적 임베딩 8~30MB, CPU 500x) /
  FastEmbed (ONNX) 로 "비쌈" 가정 완화 — 한국어 매칭 검증 후 도입 가능
- Expo SDK 55+ 는 New Architecture 강제 (54 가 마지막 opt-out), 현행 SDK 56 (RN 0.85)

---

## [0.19.3] — 2026-07-06 — "운동관리앱 dogfood 빌드→리뷰 전 구간: 게이트/훅 결함 5건 수정"

운동관리앱 실주행 (ha-plan → ha-build ×13 → ha-verify → ha-smoke → ha-review APPROVE,
2026-07-06) 에서 발굴. 공통 뿌리 둘 — ① 게이트 전제(git repo)가 강제되지 않아 조용히
무력화, ② 백엔드 shell/Python 기준 훅 패턴이 mobile/SQLite 문맥을 모름 (LESSON-030 계열).

### Fixed

- **P0 — 빌드 기간 보안 게이트 무력화** — git repo 아니면 ha-build security_gate 가
  WARN 후 silent pass → 13개 태스크 내내 무검사 (실주행 확인). 이중 수정:
  (a) `ha-init write` 가 git baseline (init + 초기 커밋) 자동 보장 — 출력 JSON
  `git_baseline` 필드. (b) `ha-build` not-git 시 done **차단** (의도적 skip 은
  `--skip-security` 명시). git 미설치는 환경 문제로 WARN 유지.
- **command-guard `.exec()` 오탐 (LESSON-041 pending)** — SQLite 드라이버 메서드
  `db.exec("PRAGMA…")` 를 Python builtin exec() 코드 인젝션으로 BLOCK (실주행 7건 FP).
  regex 에 `(?<![\w.])` — bare `exec(` 만 차단. 약화 방지로 db-guard 에 `.exec()`
  템플릿 보간/문자열 concat SQL BLOCK 2패턴 신설 (진짜 인젝션 경로는 더 정확히).
- **테스트 픽스처 훅 스캔 오탐** — 테스트의 `DROP TABLE` 에러경로 시뮬이 데이터 파괴
  BLOCK (실주행 2건 FP). `strip_test_files_from_diff` 신설, ha-build/ha-review 양쪽
  적용 — 리뷰 §2.6/§2.7 이 테스트 픽스처를 FP 로 분류하는 정책과 정합 (LESSON-030
  문서 제외와 동일 메커니즘).
- **dependency-check subpath 미해석** — `drizzle-orm/sqlite-core`, `expo-router/…`,
  `expo/config` 등 화이트리스트 부모의 subpath 를 전부 "화이트리스트 외" WARN (실주행
  노이즈 15건 — 진짜 신호 1건이 묻힘). import 경로를 설치 패키지 루트로 정규화
  (`@scope/pkg/sub`→`@scope/pkg`) + bare Node builtin (fs/path 등) skip (#19 scope-out
  과 동일 근거). react-native-expo 프로파일 dev whitelist 에 drizzle-kit 추가
  (drizzle-orm 의 표준 동반 도구 누락).
- **file_structure drift 좌표계 모순** — 프로파일 트리는 `mobile/`/`backend/` 래퍼
  루트로 선언하는데 스캔은 profile path 기준 상대경로 → path="." 루트 배치에서
  전 디렉토리가 유령 missing (실주행: extras 20 + missing 19 오보고). single-root
  래퍼가 actual 에 없으면 내용물 기준 재비교 (`_reroot_single_wrapper`) — backend
  audit + bin/harness 인라인 복제본 양쪽 (KEEP IN SYNC).
- **ha-build SKILL.md guideline 경로 혼동** — Agent prompt 의 `docs/guidelines/` 참조를
  서브에이전트들이 실파일로 오인 (실주행 3회 보고). "없으면 건너뜀 — prepare 출력의
  guideline_paths 절대경로가 단일 소스" 명시.

### Notes

- 실주행 재스캔 효과: 9 BLOCK + 16 WARN → 1 PLAUSIBLE BLOCK (실보간 — fp-check 대상)
  + 1 정당 WARN (화이트리스트 확장 신호). backend 1407 passed.
- 미수정 (기록만): 빌드 게이트가 번들 성립을 못 봄 (T-001 NativeWind preset 누락이
  T-005 에서야 발견 — toolchain.smoke 설계 논의 필요), jest-expo ↔ expo-sqlite 네이티브
  로드 불가 (node:sqlite 어댑터 우회가 워크어라운드 — LESSON 승격 후보).
- 사전 존재 실패 1건 별개: `test_ha_design_run.py::test_commit_passes_when_lessons_md_missing`
  (stash 검증으로 본 변경 무관 확인 — ha-design 경로).

## [0.19.2] — 2026-07-06 — "운동관리앱 dogfood 드라이런: 설계 진입부 결함 5건 수정"

비전문가 페르소나 드라이런(ha-init → ha-design, 2026-07-05)에서 발굴된 결함 전건 수정.
공통 뿌리 = 트리거/검사기의 문맥 무시 매칭 (LESSON-030 계열).

### Fixed

- **#1 `environments` fragment 트리거 오활성** — `has.ui or has.navigation` 제거 →
  `(has.http_server or has.cli_entrypoint) and (규모 조건)`. CORS/보안 헤더/dev-staging-prod
  는 http_server 개념 — 서버 없는 모바일/SPA 에서 섹션이 통째로 오활성되던 결함.
  모바일 환경 분리는 mobile.build_config 소유 (경계 명확화).
- **#21 `consistency_checker` offline 오탐** — 라인 기반 + 최근접 헤딩 컨텍스트 스캔으로
  재작성. 레퍼런스/문서 문맥의 URL 제외, 스토어 배포 문맥의 다운로드 동사 제외,
  동사 단독 매치는 critical → warn 강등 (URL = 강신호, 동사 = 약신호).
- **#19 `skeleton_checklist` vague-word 오탐** — `\b` 가 하이픈 경계에서 fire 하여
  `fast-check`/`type-safe` 같은 고유명사/복합어를 모호어로 오판 → lookaround
  `(?<![\w-])…(?![\w-])` 로 교체. bare "fast" 는 여전히 탐지.
- **#6 `data_model` ↔ `persistence` 스키마 중복** — 둘 다 has.storage 트리거라 항상
  동시 활성인데 ERD/스키마/인덱스/마이그레이션 서브섹션이 양쪽에 존재 → ERD 이중 작성
  강요. data_model = 스키마 단일 소스로 확정, persistence = 저장소 타입/동시성/파일/백업.
  multi_tenant/soft_delete decision_points 도 내용 따라 이동 (detect 는 섹션 본문 한정 —
  답을 data_model 에 쓰면 persistence 쪽이 미해소 오탐). ha-design/ha-map SKILL.md ·
  architect CLAUDE.md 동기. 부수로 #18 일부 해소 (soft delete/hard delete 영어 detect).

### Added

- **#20 ha-design commit "> 작성 가이드" 잔재 BLOCK 게이트** — 가이드 블록이 산출물에
  남은 채 커밋되는 것을 차단 (tasks/notes 제외). 제거가 항상 올바른 조치라 override
  플래그 없음. GATES.md 등재.

## [0.19.1] — 2026-07-03 — "Personal Jira dogfood: detect/추천 휴리스틱 결함 3+1건 수정"

v0.16~0.19 누적 변경을 Personal Jira 재구축 dogfood 로 실전 검증 — 설계 진입부에서
발견된 결함 전건 수정. 공통 뿌리 = 키워드 detect 휴리스틱 양방향 결함
(#2 너무 좁아 miss / #3·#3b 너무 넓어 false-resolve).

### Fixed

- **#1 `profile_recommendation`** — python-cli 신호에서 "도구"/"tool" 제거 (너무 일반적 —
  "지라 같은 **웹 도구**"가 CLI 와 동점 1위 오탐). 실제 CLI 설명은 명령줄/cli/script 로 여전히 매칭.
- **#2 `capability_inference`** — storage/users 키워드 대폭 확장 (관리/이슈/할일/태스크/등록/조회/
  댓글… + manage/track/todo/issue…, 담당자/멤버/작성자 + member/assignee). "할 일 관리 앱"이
  storage 추론 실패 → persistence/data_model 섹션 통째 누락되던 v0.16 #11 재발 차단.
- **#3 `decision_coverage`** — detect 스캔 전에 미기입 플레이스홀더(`<...>`) 포함 라인 전체 제외.
  빈 템플릿 예시("동시성: `<mutex / WAL / …>`")가 concurrency 를 "결정됨"으로 오판해
  안전 크리티컬 질문(원자적 선점/TOCTOU)을 은폐하던 결함.
- **#3b `decision_coverage`** — fragment **자신의 템플릿 본문**(헤딩 "### 백업/복구",
  체크리스트 "- [ ] 비밀번호 해시", 가이드 "OAuth 선택 시…")에 이미 존재하는 detect 키워드를
  load 시점에 제외 — 사용자 결정과 무관하게 항상 fire 하는 구별력 없는 노이즈.
  실패 모드는 over-ask(안전) 방향. dogfood skeleton 실측: suppress 3건 → 0건 (11/11 질문).
- **`test_check_locked`** — subprocess 파이프 인코딩 utf-8 고정 (부모 cp949 디코드 ×
  자식 utf-8 출력 불일치로 Windows 로컬에서 4건 비결정 실패).
- **`test_e2e_rework_loop`** — ruff format 위반 잔존분 정리 (CI quality 게이트).

## [0.19.0] — 2026-07-02 — "P2 실패 자동회수 루프: rework 회귀는 정상 흐름"

`/ha-run` 드라이버(P1)의 결함 마감 — verify FAIL 시 rework 대상 태스크가 done 에 머물러
재빌드가 선택되지 않던 문제. "rework 회귀는 정상 흐름" 설계를 실제 구현.

### Added

- **`plan_manager.mark_for_rebuild()`** — verify FAIL + rework 대상 태스크를
  done → `needs_rebuild` 로 전이 (사유 기록 포함).
- **ha-verify `record`** — FAIL + `--rework-tasks` 시 mark_for_rebuild 자동 호출.
- **ha-build `select_ready_tasks`** — `needs_rebuild` 태스크 최우선 선택
  (`_INPROGRESS_STATES`/`_PENDING_STATES`/`_RESOLVED_STATES` 상태 분류).
- **pipeline_advisor `_rework_reason()`** — building 회귀 사유를 advice 에 노출.
- ha-run/ha-verify SKILL.md 배선. E2E rework 루프 테스트 포함 (pytest 1358).

## [0.18.1] — 2026-07-02 — "블루프린트 흡수 (B) 마감: 6축 평문화 + 결정 근거 기록"

v0.18.0 조각1(프로파일 추천)에 이어 B 잔여 2조각 완료 — `/blueprint` 흡수 종결.

### Changed

- **조각2 — 6축 인터뷰 평문화** (ha-init SKILL.md §3-2): "예상 DAU?" / "가용성 99.9%+" /
  "poc/mvp/ga" 같은 jargon 질문을 평문으로 재작성 — "몇 명이나 쓸 것 같나요?" /
  "서비스가 잠깐 멈추면 얼마나 곤란한가요?" / "지금 어느 단계인가요?". 라벨은 평문 +
  괄호에 enum 토큰 병기(CLI 인자 매핑은 토큰 기준 — `--user-scale` 등 계약 무변경).
  follow-up 질문(민감 데이터/수익 모델)도 동일 처방. 용어를 아는 사용자만 통과하는
  인터뷰는 원맨툴("누구든지") 실격 — deferred P5 심화(6축 평문 번역) 해소.

### Added

- **조각3 — `--decision-rationale`** (ha-init write): §2 추천 수락 시점의 "이유 +
  트레이드오프" 서술(1~2줄)을 plan body 판단 근거에 "결정 근거" 블록으로 기록 —
  비전문가가 나중에 "왜 이 스택인가"를 이해. 미전달 시 블록 없음(기존 동작 유지).
  SKILL.md §2-5·§6 배선. 테스트 +2

## [0.18.0] — 2026-07-02 — "블루프린트 흡수 (B): 설명 기반 프로파일 추천"

원맨툴 자기완결성 — "다른 스킬 없이 ha-* 만으로" 의 최대 구멍(설계 진입) 첫 조각.
ha-init 프로파일 선택 트리는 사용자가 스택(nextjs vs vite, postgres vs mongo 등)을
*알아야* 고를 수 있어 비전문가가 이탈했다. `/blueprint` 의 핵심 가치("unsure → 강하게
추천: 선택+이유+트레이드오프")를 별도 문서(BLUEPRINT.md) 없이 ha-init 에 흡수(방식 B —
6축·프로파일 감지·capability 추론과 ~80% 겹치는 문자적 이식 대신 고유 가치만).

### Added

- **`profile_recommendation.py`** — 설명 텍스트 → 후보 프로파일 점수순. 결정론 키워드
  스코어링(13 confirmed 프로파일별 판별 신호, 한국어 substring / 영어 word-boundary =
  capability_inference 규약). 이유·트레이드오프 서술은 LLM(ha-init 스킬)이 프로파일 본문으로
  담당 — 정적 지식 데이터 중복 없음(코드/LLM 경계). 테스트 +11
- **ha-init `recommend` 서브커맨드** (`--description` / `--candidates` / `--top`) —
  `recommendations[]`(profile_id / score / signals / guideline_paths) JSON.
- **ha-init SKILL.md §2** — detect 매칭 0건 시 트리 fallback **전에** 설명 기반 추천 먼저:
  top 1 강력 추천(선택+이유+트레이드오프) → `추천 수락` / `다른 후보` / `직접 트리`.
  트러블슈팅 "매칭 0건" 안내도 실제 `recommend` 명령으로 갱신.

## [0.17.0] — 2026-07-02 — "의미 기반 인터뷰: decision_points 커버리지 (설계 탄탄 + HITL)"

원맨툴 비전 재정의("자동화 아님 — 다른 스킬 없이 HarnessAI 만으로, HITL 중심, 설계부터 탄탄")에 따라
설계 단계의 근본 약점을 처리. 기존 인터뷰 질문 생성은 전부 **어휘(lexical) 정규식**(미정량어/실패경로
단어 스캔)이라 비전문가가 남기는 **의미적 빈칸**(다중 사용자·soft delete·동시성·로딩 상태 등)을 못 잡았다.
2025 연구 근거: taxonomy("common mistake types")로 유도한 질문이 zero-shot 보다 우수(arXiv 2507.02858),
커버리지가 곧 "언제 멈출지" 정지 조건(arXiv 2502.04485).

### Added

- **`decision_coverage.py`** — fragment frontmatter 신필드 `decision_points`(그 섹션에서 반드시 결정돼야
  할 의미 항목 — 과거 LESSON/실패 taxonomy)를 읽어, 채워진 skeleton 본문에 `detect` 키워드가 하나도
  없으면 **미결정**으로 판정. `load_decision_points` / `find_unresolved_decisions`. 결정론(코드=커버리지+정지
  조건, LLM=질문·해소 판단). `decision_points` 미선언 fragment 는 기존과 완전 동일(additive). 테스트 +12
- **5 섹션 11 항목 시딩** — requirements(multi_user/unhappy_path), persistence(multi_tenant/soft_delete/
  concurrency), auth(login_identity/account_lifecycle), interface.http(idempotency/list_query),
  view.screens(loading_state/navigation_model). 템플릿이 이미 예시多인 섹션은 기본값에 없는 진짜 갭만
  선별(detect 오탐 회피).
- **ha-design `clarify` → `decision_candidates`** 필드 + SKILL.md §4.5①-a 배선 — 어휘 후보보다 **우선**
  처리(강제 질문, "해당 없음"도 유효 선택지, 자동 처리 금지 = 결정권 분리 HITL).
- **`harness validate` decision_points 경량 검증** — 오작성(비-list, id/ask 누락) warn 표면화.
- **`test_harness_cli_validate.py`** — `harness` bin 첫 회귀 커버리지(importlib SourceFileLoader). 테스트 +13

### Fixed

- **required_when 괄호 false-reject** — `harness validate` 의 `_validate_required_when_expression` 가 괄호
  표현식을 통째 거부해 v0.16.0 environments 의 `(a or b) and (c or d)` 가 실제로 validate red 였음
  (테스트/drift 가 `harness validate` 를 미실행이라 미검출). 런타임 backend `scale_expression.parse()` 는
  괄호 정상 처리. 수정 = 균형 검사 + 괄호→공백 치환 후 atom 검증(standalone 유지, backend import 안 함).
- **`_README.md` fragment 오검사** — `validate fragments` 서브커맨드만 `_` 접두 skip 누락(전체 `validate`
  엔 있음)이라 두 경로 불일치 → 서브커맨드에도 skip 추가. 이제 validate/validate fragments 둘 다 green.
- **미러 drift 정리** — `~/.claude` 에만 있던 `django.md`(confirmed/harness-core 완결 프로파일) + `_registry.yaml`
  django 룰을 레포로 **백포트**(삭제 아님 — 이전 세션 백포트 누락, 유실 방지). drift 0건(125 files).

## [0.16.0] — 2026-07-02 — "인터뷰 지능화 (P5): capability 추론 + 활성화 정확도 (#1·#3·#11)"

웹앱 dogfood(nextjs)로 확정한 공통 뿌리 — "6축+프로파일 활성화가 비전문가 의도를 못 잡음" — 를 묶어서 해소. 원맨툴 비전("누구든지 완벽하게")의 정면 과제.

### Added

- **#11 `capability_inference.py`** — 설명 텍스트 → `has.*` 신호 결정론적 추론(한국어+영어 키워드). "할 일 CRUD" → `storage`(→persistence/data_model), "로그인/계정" → `users`, "API/엔드포인트" → `http_server`, "화면/대시보드" → `ui`. ha-init write 가 아직 활성 안 된 신호를 `capability_suggestions` 로 출력 → SKILL.md 가 AskUserQuestion 으로 확인 후 `--external-capabilities` 재작성(**자동 활성화 아님 — 결정권 분리 HITL**). "할 일 관리 앱" 이라고만 써도 DB 설계 섹션이 안 빠지게. 테스트 +9

### Fixed

- **#3 environments 과활성화** — `required_when` 을 `(진입점) and (lifecycle in [mvp, ga] or availability in [standard, high])` 로 게이트. poc+casual 장난감 CLI 가 dev/staging/prod·CORS·HSTS 를 물려받지 않음. mvp+ 또는 standard+ 는 유지. 테스트 +3, README(en/ko) 적응 예시 정확화(기존 18/14 stale → 실제 17/9)
- **#1 detect 빈결과** — ha-init SKILL.md: 매칭 0건 시 "설명 기반 프로파일 추천을 먼저 제시" 안내 명문화(트리 fallback 은 이미 존재 — 비전문가 이탈 방지 강화). advisor init reason 도 lockable 유무 분기(#2 연장). 테스트 +2

### Changed

- 전체 테스트 **1296 → 1308** (+12). #1/#3/#11 은 dogfood(urlshort CLI + taskflow 웹앱) 2표본으로 근거 확정 후 수정

## [0.15.4] — 2026-07-02 — "file_structure drift 오탐 + 드라이버 reason 정확도 (dogfood #6·#2)"

`/ha-run` dogfood 잔여 마찰 2건 정리.

### Fixed

- **#6 file_structure drift 오탐** — (1) 표준 `src/` 레이아웃: 프로파일이 `src/<pkg>/`(placeholder)를 선언하면 실재 `src/` 가 extras 로 오탐되던 것을, placeholder 리프의 **구체적 조상 디렉토리**(`src/`)를 declared 로 인정해 해소. (2) `docs/` (harness 가 harness-plan.md/skeleton.md 를 두는 상태 디렉토리 — 모든 프로젝트에 존재)를 `_BENIGN_EXTRA_DIRS` 로 extras 에서 제외. advisory WARN 노이즈 제거. 테스트 +2
- **#2 드라이버 reason 정확도** — pipeline_advisor 의 init→design reason 이 CLI/라이브러리에도 "페르소나/기능/화면" 을 언급하던 것을, `requires_hitl_freeze` 여부로 분기(`페르소나/기능/화면` vs `기능/로직`). 테스트 +2

### Changed

- 전체 테스트 **1292 → 1296** (+4)

## [0.15.3] — 2026-07-02 — "ha-smoke 기동 명령 자동 제안 (dogfood #8)"

`/ha-run` dogfood 에서 발견: `toolchain.smoke` 미설정 CLI 프로젝트는 ha-smoke prepare 가 `smoke: null` 만 내보내 비전문가가 "기동 명령이 뭐지?" 에서 막힘.

### Fixed

- **`suggest_smoke_command(cwd)`** — cwd + cwd/src 에서 실행 가능 Python 패키지(`__init__.py` + `__main__.py`)를 탐지해 `python -m <pkg> --help` 제안. ha-smoke prepare 가 `smoke` 미설정 시 `smoke_suggested` 필드로 제공. 실행 가능 패키지 없으면 None(비-Python/라이브러리 — 잘못된 추측 대신 사용자 질문 유도). SKILL.md 명령 결정 우선순위에 편입. 테스트 +3

### Changed

- 전체 테스트 **1289 → 1292** (+3)

## [0.15.2] — 2026-07-02 — "Profile-aware print 룰 (dogfood #10)"

`/ha-run` dogfood(URL 단축 CLI) 를 shipped 까지 완주하며 발견한 code-quality 오탐 수정. CLI 도구의 정당한 `print()`(stdout=결과 / stderr=에러)를 code-quality 훅이 "logger 필수" WARN 5건으로 잡던 것 — 웹 백엔드 가정을 CLI 에 부적절 적용.

### Fixed

- **code-quality print 룰 프로파일 인지** — `check_code_quality(text, *, allow_stdout_print=False)` + `SecurityHooks.allow_stdout_print` (from_profile 이 프로파일 frontmatter `allow_stdout_print` 를 raw 에서 읽음, 스키마 필드 추가 없음). **python-cli / claude-skill 만 print 억제**(stdout 이 출력 채널) — **fastapi(웹 디버그 print 냄새) · python-lib(라이브러리는 return/logging) 은 유지**. print 외 룰(빈 except 등)은 영향 없음. 테스트 +3

### Changed

- 전체 테스트 **1286 → 1289** (+3)

## [0.15.1] — 2026-07-02 — "Frozen Gate Fix: CLI/라이브러리 무한루프 (dogfood urlshort)"

`/ha-run` 을 실제 dogfood(URL 단축 CLI) 로 돌리다 발견한 근본 결함 수정. v0.10.0 HITL 게이트가 "모든 프로젝트가 페르소나/화면 섹션을 가진다"는 웹앱 암묵 가정 위에 만들어져, **HITL-lockable 섹션(requirements/user_journey/view.screens)이 없는 프로젝트(CLI 도구·라이브러리)는 freeze 대상이 없어 영구 `drafting` → ha-build 영구 BLOCK → 드라이버 designed→design 무한루프.**

### Fixed

- **frozen 게이트 vacuous-pass** — `plan_manager.requires_hitl_freeze(plan)` 신설 (활성 섹션 ∩ `HITL_LOCKABLE_SECTIONS` 가 공집합이면 False). ha-build 진입 게이트 2곳(prepare/complete) + pipeline_advisor 의 designed 분기가 이 헬퍼를 공유 — lockable 섹션이 없으면 frozen 불필요로 간주해 바로 plan/build 진행. 하드코딩 3곳(`_LOCKED_SECTION_IDS` 등) 대신 backend 단일 상수 `HITL_LOCKABLE_SECTIONS` 도입. 테스트 +4 (requires_hitl_freeze 단위 2 + advisor no-lockable 1 + ha-build 게이트 회귀 1)

### Changed

- 전체 테스트 **1282 → 1286** (+4)

## [0.15.0] — 2026-07-02 — "One-Command Driver: /ha-run (원맨툴 P1)"

"이것만 있으면 누구든지 설계부터 결과물까지" 비전의 첫 단계. 지금까지 사용자가 스킬 10개를 순서대로 직접 호출하며 파이프라인을 운전하던 것을, `/ha-run` 하나가 상태기계 기준으로 자동 운전한다. **게이트 우회 0** — 드라이버는 순서만 자동화하고 판정은 전부 기존 게이트 소유.

### Added

- **`backend/src/orchestrator/pipeline_advisor.py`** — 결정 코어. `advise(plan) -> Advice(action/mode/skill/args/reason)` 순수 함수 (파일시스템 접근 없음, 게이트 복제 없음). 상태 8종 전이 지도 + verify_history 기반 smoke advisory 판단 (이전 rework 사이클의 stale smoke 기록은 무효 — 마지막 성공 ha-verify 이후 기록만 인정). HITL 지점 명시: init/design 인터뷰 · smoke FAIL 판단 · ship 확인 (배포는 외부 행위 — 자동 마킹 금지). 테스트 +14
- **`/ha-run` 스킬** — `run.py next` 가 다음 행동 JSON 출력, SKILL.md 루프 절차가 해당 스킬을 Skill 툴로 호출. 가드레일: 게이트 BLOCK 시 우회 플래그 자동 부착 금지(선택지를 사용자에게 평문 제시), 무전이 3회 반복 정지, 세션당 최대 15루프. 테스트 +3 (JSON 계약)

### Changed

- README(en/ko) 30초 사용법에 `/ha-run` 원커맨드 경로 추가, CLAUDE.md 파이프라인 등재
- 전체 테스트 **1265 → 1282** (+17)

## [0.14.3] — 2026-07-02 — "Drift Gate: 미러 동기 기계 검사 + 잔손질"

v0.14.2 가 손으로 잡은 미러 drift 를 재발 방지 게이트로 승격. 반복 결함 1위 원인(미러 2벌 수동 cp 동기)을 커밋 전 1커맨드 검사로 대체.

### Added

- **`harness drift` 서브커맨드** — repo(`HARNESS_AI_HOME`) ↔ 설치 미러(`CLAUDE_HOME`/`~/.claude`) 정합성 검사. 비교 범위 = installer 복사 범위 동일(`harness/` + `skills/{ha-*,_ha_shared}`), CRLF 차이 무시, `__pycache__`/`.pyc`/`.install-manifest.json` 제외. `[MISSING]`(설치본 누락)/`[DIFF]`(내용 차이)/`[EXTRA]`(레포 미백포트 — 유실 위험) 3분류, drift 시 exit 1. CLAUDE.md 자가검증 체크리스트에 편입. 테스트 +8 (`test_harness_drift.py`)

### Fixed

- **worklog 호출 경로 하드코딩** — ha-build/ha-design/ha-redesign 이 ha-log 를 `Path.home()/.claude/...` 절대 경로로 호출 → installer 가 지원하는 `CLAUDE_HOME` 커스텀 설치에서 조용히 실패(WARN). `Path(__file__).parent.parent` 상대 참조로 교체 — repo 사본은 repo ha-log, 설치본은 설치 ha-log 호출 (자기 완결)

### Removed

- **`routes/agents.py` dead code** — 참조 라우트가 없는 `AgentConfigUpdate` + `_ALLOWED_MODELS` 제거 (PATCH 라우트 계획 시 그때 재도입). 모델 별칭 동기화처 1곳 감소

### Changed

- **gate-coverage 재측정 (2026-07-02)** — 2026-04-19 이후 게이트 진화분 반영 재실행: 35 fixtures **precision/recall/accuracy 100% 유지**, 문서 날짜 갱신
- 전체 테스트 **1257 → 1265** (+8)

## [0.14.2] — 2026-07-02 — "Mirror Reconciliation: #15 Strict Placeholder Backport"

전체 점검(미러 2벌 정규화 해시 감사)에서 발견된 양방향 drift 18파일 일소. **#15(strict placeholder 정규식 + 템플릿 백틱 규약)가 `~/.claude` 에만 존재해 `install -Force` 한 번이면 유실될 상태**였고, 반대로 모델 별칭 갱신(`9b39198`)은 실사용 미러에 미전파돼 python-cli 프로파일이 구모델을 가리키고 있었다.

### Fixed

- **#15 strict placeholder 정규식 백포트 (TDD)** — `harness/bin/harness` `_PLACEHOLDER_RE` + `skeleton_assembler._ANGLE_PLACEHOLDER_RE` 를 lenient `<[a-z_][a-z0-9_]*>` → strict `<(?![A-Z])[^\W\d]\w*>` 로 통일. 한글 `<본문>`/`<설명>` 잔재를 미치환 placeholder 로 검출하면서 ASCII 대문자 시작(`<T>`, `<K,V>` — TS 제네릭)과 공백 포함(`<기능 1>` — HITL 영역) 토큰은 보호. 스켈레톤 템플릿 13파일의 bare 단일어 한글 토큰(`<설명>`/`<사유>`/`<기능>`/`<임계>` 등)을 백틱으로 통일(인라인 코드는 스캔 전 strip → 통과) + `_README.md` placeholder 컨벤션 문서 갱신. 테스트 +5 (한글 검출 / TS 제네릭 제외 / 백틱 제외 — assembler `find_placeholders` · `harness integrity` 양쪽)
- **미러 drift 재동기** — `~/.claude/harness/profiles/python-cli.md` 가 `claude-sonnet-4-6` 잔존(레포는 `claude-sonnet-5`) → install 재실행으로 전파. `ha-plan/SKILL.md` 상태 목록 `skipped` 누락, `ha-redesign/SKILL.md` 표기 규칙(#15) 레포 백포트. 정규화(CRLF 무시) diff 기준 **drift 0** 복구

### Changed

- 전체 테스트 **1247 → 1257** (0.14.1 이후 랜딩분 +5, 이번 신규 +5). README(en/ko)·CLAUDE.md 의 stale 테스트 수 동기

## [0.14.1] — 2026-06-26 — "Skill Audit: ha-map Induction & Defect Sweep"

`/ha-map` 레포 편입 + 14개 스킬 결함 일소 + `/ha-eval` 보류 포지셔닝 문서. 코드 결함은 미러·테스트가 없던 유일한 스킬(ha-map) 하나에 몰려 있었다 — "테스트 스위트 = eval 하네스"의 실증.

### Added

- **`/ha-map` 레포 편입** — skeleton.md → `docs/architecture.md`(Mermaid 3종) 파생 뷰를 만드는 독립 보조 스킬이 그동안 `~/.claude/skills/` 에만 있고 레포 미러·테스트가 전무한 유일한 `ha-*` 였다. `skills/ha-map/{run.py,SKILL.md}` 로 추적 + 단위 테스트 9개(`_extract_mermaid_blocks` LF/CRLF/non-mermaid, `_render_one` timeout/launch-fail, `_find_skeleton`, render 루프 쓰기실패).
- **`backend/docs/eval-harness-positioning.md` (+ `.en.md`)** — "#3 Agent Eval(`/ha-eval`)" 추가 제안을 전 사이클(개념→oracle→자료조사→적대적 자가평가→error analysis→생태계 조사) 검토 후 **보류**한 분석. 검증 사다리(pytest + GATES + `/ha-smoke`)가 이미 eval 하네스이며, Promptfoo/DeepEval/OpenAI skill-regression 어느 것도 "파이프라인 → 전체 레포" eval 단위를 오케스트레이션하지 않음을 기록.

### Fixed

- **ha-map 결함 3건** — (1) `subprocess.TimeoutExpired` 미처리로 `mmdc` 행 시 렌더 루프 전체 크래시 → `(SubprocessError, OSError)` 포착 후 `ok:false` 반환. (2) `` ```mermaid `` 펜스 정규식이 `mermaid\n` 라 CRLF(`\r\n`)에서 silent no-render → `\r?\n`(`_extract_mermaid_blocks` 헬퍼로 추출). (3) 렌더 루프 tmp 쓰기 `OSError` 미가드 → 블록별 실패 기록 후 계속.
- **`_ha_shared/utils.py::project_root`** — `git rev-parse --show-toplevel` 에 `timeout` 부재(형제 `untracked_pseudo_diff` 는 보유) → `timeout=10` + `TimeoutExpired` 폴백 추가. 테스트 +2.

### Changed

- 14개 스킬 + `_ha_shared` 결함 일소(subprocess timeout/except, CRLF 정규식, bare/broad except, `write_text` OSError, `json.load`) — ha-map 외 전부 clean(bare `except: pass` 0건, ha-map 식 CRLF 클론 0건, `write_text` 13지점은 경계 `cmd_*` 에서 OSError 처리 확인).
- 전체 테스트 **1236 → 1247** (+11), ruff/format clean.

## [0.14.0] — 2026-06-24 — "Spec Kit Absorption Wrap-up: Clarify Gate & Status Consistency"

Spec Kit 흡수 로드맵 마감 — A3 clarify 게이트 + 유실됐던 작업(#14/#8) 복구 + skipped 상태 일관성. 핵심 가치(A1~A5 + Track B 스캐폴딩 + A3) 완료, P6(멀티에이전트 Tier2/3 + Track C 훅) 보류.

### Added

- **A3 — `/ha-design clarify` (Spec Kit `/clarify` 흡수)** — A1 `skeleton_checklist` 의 품질 findings(clarity/edge_case)를 사용자 질문 후보로 변환하는 `build_clarification_candidates()` + read-only `clarify` 서브커맨드(JSON 출력, freeze/commit 없음, skeleton 없으면 exit 3). `/ha-design` SKILL.md §4.5 Step8 에 배선 — clarify 실행 → `AskUserQuestion`(≤5) → 답을 해당 섹션에 역기록 → 재실행. "vague 탐지(코드) → 질문(HITL) → 채움" 고리 완성. 테스트 +11 (단위 9 + 통합 2)
- **`/ha-resync` 신규 스킬** — `applied` 이후 skeleton.md 를 손수정하면 plan 의 `skeleton_hash`/`section_hashes` 가 stale 되는데 재동기 1급 경로가 없던 결함. `compute_skeleton_hash`+`compute_section_hashes` 를 재사용해 **무조건 재계산·덮어쓰기**(migrate-skeleton-hash 와 달리 가드 없음) + 자동 백업 + `--dry-run`. `/ha-build` BLOCK 메시지를 추적(`/ha-redesign`)/재동기(`/ha-resync`)/일회우회(`--accept-skeleton-drift`) 3분기로 명확화, `/ha-plan`·`/ha-redesign` WARN 에도 안내. 테스트 +4

### Fixed

- **#8 `/ha-review` 빈 diff vacuous-APPROVE 가드** — 빈 diff 로 `record approve` 시 보안/슬롭 훅이 검사할 입력이 없어 false-green(vacuous) 통과하던 갭 차단. `not diff.strip()`(raw diff 기준) → exit 1, 의도적 우회는 `--allow-empty`. 기존 #19 dependency-check + `--allow-block` 보존. `prepare` 빈 diff WARN. 테스트 +3
- **skipped 상태 일관성 (사전 존재 결함)** — `/ha-build` record 가 `--status skipped` 를 받으나 `tasks_schema.VALID_STATUSES` 엔 없어 schema 가 거부, 게다가 ha-build 내부 "resolved" 판정이 3집합(`_DONE_STATES` / `--task` dep 인라인 튜플 / `_resolved`)으로 갈려 skipped 포함 여부가 달랐다 → **skipped 의존성의 dependent 가 영원히 ready 안 됨**(`--resume` 미선택 + `--task` 차단)인데 빌드 완료엔 skipped 인정되는 자기모순. 결정: skipped = 종료/해결 상태 → 의존성 충족(plan_manager 의 done→needs_rebuild 마킹은 skipped 제외 유지). `VALID_STATUSES += skipped` + 3집합을 단일 `_RESOLVED_STATES` 로 통합 + 교차 일관성 테스트(record choices ⊆ VALID_STATUSES). 테스트 +6

### Changed

- Spec Kit 흡수 로드맵 마감 (`docs/spec-kit-absorption-design.md`) — P3(A3) ✅, P6 ⏸ 보류(주력 에이전트 미정 YAGNI). 미러 2벌(`~/.claude` ↔ repo) drift 정리 — ha-build `_RECORD_STATUS_CHOICES` 동기로 diff 0
- 전체 테스트 **1212 → 1236** (+24), ruff/format/pyright clean

### Known / Backlog

- **#15** strict placeholder 정규식(한글 `<설명>` 검출) 유실 — 실제 게이트(`harness/bin/harness`, `skeleton_assembler.py`)는 여전히 lenient `<[a-z_][a-z0-9_]*>`. 정식 재구현은 backport 아닌 신규 TDD 작업

## [0.13.0] — 2026-06-22 — "Dogfood Harvest 2: Runtime L2 & Handoff Fixes"

code-mate dogfood 2차 수확 — 런타임 검증 사다리 **계층2**(떠도 라우트 깨짐) 보강 + ha-plan→ha-build→ha-review→ha-redesign **단계 간 정합성** 결함 다수(#1~#9, #13).

### Added

- **`/ha-smoke` 계층2 — 선언 엔드포인트 타격** — url 모드 기동 PASS 후 `interface.http` 의 선언 GET 경로를 실제 타격해 "프로세스는 떠도 라우트가 깨진" 산출물(404 미등록 / 5xx 핸들러 크래시)을 잡는다. `2xx/3xx/401/403/422` = OK (라우트 존재 + 핸들러 도달). path 파라미터(`{id}`/`:id`)는 실제 값이 없어 v1 skip. `run_probe(..., endpoints=[...])` + `_check_endpoints` + CLI `--endpoint`(반복). `consistency_checker._ENDPOINT_TOKEN_RE` 재활용. 회귀 +5 (probe 계약)
- LESSON-033 (Windows cp949 콘솔 — CLI 진입점 UTF-8 강제 / 기본 출력 ASCII-safe), LESSON-034 (파생 경로·캐시키 단일 함수 = single source of truth), LESSON-035 (LLM 출력 환각 비파괴 annotate), LESSON-036 (다언어 파이프라인: 언어 특정 도구는 파일타입으로 게이트 — #11 run_ruff-on-ts) 추출 (code-mate dogfood)
- **#2 `/ha-plan --replan`** — `/ha-redesign`(cross-cutting 스킬이라 `planned` 유지) 후 태스크 전체를 재분해할 공식 경로 신설. prepare/commit 이 `planned` 상태 재실행 허용 (기본은 `designed` 만). `transition` 의 same-state 멱등성 활용
- **#6 `/ha-verify` 런타임 인코딩 스모크** — test/lint/type green ≠ 앱 기동. `cli_entrypoint` 프로파일의 `toolchain.smoke` 를 verify 단계에서 실제 subprocess invoke (자식 인코딩 미강제 = cp949 재현)해 import/기동/콘솔 인코딩 크래시(em-dash `UnicodeEncodeError` 등)를 잡는다 — CliRunner(utf-8 버퍼)가 못 잡는 클래스. smoke 미설정 시 WARN. LESSON-033 을 python-cli 프로파일에 wire-in (기본 출력 ASCII-safe)
- **#7 `/ha-build` 부분 완료 복구** — prepare 가 대기 태스크를 `in-progress` 로 착수 마킹 + 재진입(이미 in-progress) 감지 → spec 의 "생성/수정 파일" 존재 보고(`reentry`/`declared_files`/`existing_files`). 서브에이전트 중단 시 흔적 + "이어서/처음부터" 판단 근거
- 회귀 테스트 누적 +13 (#1·#2·#3 5 + #5 1 + #6 4 + #7 3) → 전체 **1109 pass**

#### Spec Kit 흡수 (설계품질 게이트 + 멀티에이전트)

- **A1 — `skeleton_checklist.py` (설계품질 advisory 게이트)** — Spec Kit `/checklist` 흡수. `check_skeleton_quality()` 가 skeleton.md 에서 (1) clarity: 정량 수치 없는 모호 표현(빠른/적절한/fast 등), (2) edge_case: I/O 경계 섹션의 실패 경로 키워드 누락 을 advisory(WARN)로 표면화. 코드펜스/인라인백틱/태스크분해·구현노트 섹션은 skip. `/ha-design` commit 에 `checklist_findings` 배선. Q3 결정대로 advisory 시작(FP 관찰 후 BLOCK 승격). 테스트 +22 → 1135
- **A2 — `consistency_checker.check_offline_network_violation` (cross-artifact critical)** — Spec Kit `/analyze` 흡수. skeleton 이 오프라인/무네트워크/시크릿금지 제약을 선언했는데 본문에 비-루프백 URL·다운로드 동사가 있으면 `critical` 보고(`run_all_checks` → `/ha-design` 자동). + `/ha-redesign` impact-analysis 프롬프트에 `nfr_conflicts` 단계 추가(신규 의존/외부호출 ↔ NFR 제약 충돌 = blocker, dogfood #10 정조준). 테스트 +8 → 1143
- **축A 패턴1 — `utils.reenter_or_assert` (상태머신 재진입 일원화, bounded)** — 설계서 §4.6 버그-처리 패턴1(forward-only 경직, #2/#9/#12). prerequisite 미만 차단 / working 이하 진행 / working 초과는 regress(재진입). `--replan`(#2)·`_enter_build_state`(#9) 두 밴드에이드를 한 함수로 통합. 풀 마이그레이션은 보류(사용자 결정=bounded). 테스트 +6 → 1145
- **Track B — `agent_scaffold` + `harness scaffold` CLI (멀티에이전트 호환)** — Spec Kit `integrations/` 패턴 흡수. 중립 SKILL.md 1벌 → Claude(`.claude/skills/{n}/SKILL.md`)·Gemini(`.gemini/commands/{n}.toml`)·Copilot(`.github/prompts/{n}.prompt.md`) 명령 파일 + 컨텍스트 파일(GEMINI.md / copilot-instructions.md) 생성. args 토큰($ARGUMENTS↔{{args}}) + `~/.claude/` 경로(skills/ **및** harness/bin → `${HARNESS_AI_HOME}/`, claude 제외) 치환. `harness scaffold --agent {claude|gemini|copilot|all} [--skill] [--out] [--dry-run]`. agent_scaffold 는 standalone 로드(orchestrator 패키지 __init__ 우회). 테스트: agent_scaffold 모듈 29 + CLI e2e 8 → 전체 **1182**
- **A5 — `ha-build --resume` (다음 ready 태스크 자동 선택)** — Spec Kit `[X]` resume 패턴(§4.6 패턴2) 흡수. `select_ready_tasks`(순수: status 대기/in-progress + depends_on 전부 done, in-progress 우선→대기, T-ID 순) + `prepare --resume`(--task 생략 시 다음 ready 태스크 자동 선택, 없으면 exit 0). `_enter_build_state`(상태 회귀) 호출 전에 처리해 ready 없을 때 built/verified/reviewed 플랜 불필요 회귀 방지. `--task` argparse required 해제(--task XOR --resume). 범위지정은 기존 `--task` CSV 가 제공 → #7 부분복구·iteration 후 "다음 뭘 빌드?" 를 tasks.md 수동 독해 없이 해결. 테스트 +9(select_ready_tasks 6 + cmd_prepare --resume 3) → 전체 **1212**
- **A4 — `ha-converge` 스킬 (코드↔스펙 미구현 회수)** — Spec Kit `/converge` 흡수. `ha-review` 의 역방향 contract(skeleton 에 선언했는데 미구현인 엔드포인트)가 advisory WARN 에 그치던 것을 **actionable** 하게: `backend/src/orchestrator/converge.py`(순수 로직) + 신규 `skills/ha-converge/`(prepare 보고 / commit 회수). skeleton `interface.http` 선언 ↔ 소스 대조 → 미구현 엔드포인트를 tasks.md 에 신규 `대기` 태스크로 **멱등 append**(identifier 중복 가드, 새 상태 어휘 도입 X). 상태 전이 없음 — 빌드는 `/ha-build` 담당(reviewed 면 building 회귀). 상태 가드 built/verified/reviewed. 테스트: converge 모듈 17 + 스킬 4 → 전체 **1203**

### Fixed

- **#1 · #5 ha-plan 이 §태스크 분해 sync 후 skeleton hash baseline 미갱신** — `ha-plan commit` 이 §태스크 분해를 skeleton.md 에 동기화하면서 `skeleton_hash`/`section_hashes` 를 갱신하지 않아, 후속 `/ha-redesign` 이 거짓 "외부 수정" 경고(FP) + `/ha-build` prepare 가 매 빌드 BLOCK (정상 ha-plan→ha-build 경로에서 `--accept-skeleton-drift` 상시 필요). sync 시 baseline refresh (`/ha-redesign` apply 와 동일 패턴). drift 게이트 주석 정정 (ha-plan 도 hash 갱신자임을 명시)
- **#3 worklog split-brain** — `ha-log` 가 항상 `docs/worklog.md` 에 쓰는데 사람/메모리는 루트 `worklog.md` 를 봐 히스토리 분열. `_resolve_worklog_path` 가 루트 `worklog.md` 존재 시 우선, 없으면 `docs/worklog.md` (프로젝트당 한 파일로 수렴, backward-compatible)
- **#4 SKILL.md 하드코딩 섹션 번호** — `§19 구현 노트`/`§16 태스크` 가 작은 skeleton(§12 까지)과 불일치(doc drift). 이름 기반 참조(「구현 노트」 섹션)로 교체
- **#8 `/ha-review` 빈 diff vacuous pass** — base 미결정 + 워킹트리/untracked 모두 빔(main 직작업+전부 커밋+원격 없음)이면 보안훅이 빈 입력으로 무조건 0건 통과(false-green APPROVE)하던 잔여. `_extract_diff` 가 빈 경우 `git diff <empty-tree> HEAD` 로 **전체 트래킹 소스를 검토 입력으로 폴백**. (기존 issue #18 `_resolve_diff_base` 위 보강.)
- **#9 reviewed 상태가 Phase 추가 빌드를 가둠** — forward-only 가 reviewed 이후 신규 태스크 `/ha-build` 를 차단(`허용 상태 ['planned','building']`). `_enter_build_state` 가 built/verified/reviewed 에서 `building` 으로 회귀시켜 새 코드가 verify/review 게이트를 다시 거치게 함 (iteration 허용). #2 와 동일 뿌리
- **#13 ha-build `--parallel` doc 불일치** — SKILL.md 는 `--parallel T-...` 안내하나 run.py 는 `--task <csv>` 만 존재(첫 호출 argparse 에러). 문서를 `--task T-001,T-002` 로 정정 (ha-build/ha-plan SKILL.md)

### Notes

- 설계: `backend/docs/spec-kit-absorption-design.md` — Spec Kit 흡수(설계품질 게이트 + 멀티 에이전트) 설계서. dogfood 갭 #10(dep↔NFR)·#11(mock 경계)·#12(태스크 분할)을 흡수 항목 A1/A2/A5 로 매핑.

---

## [0.12.0] — 2026-06-12 — "Runtime Smoke Gate"

검증 사다리 최상단 보강: test/lint/type 이 전부 통과해도 **앱이 안 뜨는** 산출물을 잡는 `/ha-smoke` 신설 + dogfood P1 (untracked 파일 보안 스캔 우회) root fix.

### Added

- **`/ha-smoke` 스킬** — 런타임 기동 검증 (advisory 게이트, 상태 전이 없음). exit 모드 (명령 exit 0 = PASS — CLI/빌드 류) / url 모드 (dev server 백그라운드 기동 + readiness 폴링 + 프로세스 트리 정리: win32 `taskkill /F /T` · POSIX `killpg`). 결과는 `verify_history` 에 step=`smoke` 로 기록 — 스키마 변경 0. verified/reviewed 상태에서만 실행 (exit 2 가드)
- **`toolchain.smoke` 프로파일 필드** (optional) — 프로파일/사용자가 smoke 명령을 고정 가능. 포트는 프로젝트마다 달라 디폴트 프로파일엔 비워두고 SKILL.md 의 프로파일별 휴리스틱 표가 도출
- 회귀 테스트 +8 (probe 계약 6 + toolchain.smoke 파싱 2) — 1025 → **1033**
- **electron / nextjs / nestjs 디폴트 guidelines** (11 파일) — 기존 0개였던 v0.7.0 프로파일 3종의 컨벤션 문서 보충. electron: ipc (IpcResult 봉투 + 채널 상수) / state (store-action-IPC) / structure (프로세스 3분할 + colocation) / style. nextjs: routing (Route Group + 렌더링 전략) / components (Server·Client 분리) / data (Server Actions + Drizzle 싱글턴) / style. nestjs: api (DTO 검증 + 에러 래퍼) / services (트랜잭션 + core 순수함수) / structure. sosel dogfood 에서 검증된 kalpie 계열 규칙 (IpcResult, container colocation, CVA) 역수출. `resolve_guideline_paths` 핀 테스트 +3 — 1033 → **1036**

### Fixed

- **dogfood P1: untracked 파일 보안 스캔 우회** (`32b4ffd`) — 방금 생성된 파일은 `git diff` 에 안 잡혀 `/ha-build` BLOCK 게이트와 `/ha-review` 보안 스캔을 통째로 우회. `untracked_pseudo_diff` 가 `git ls-files --others` 결과를 `diff --git` 의사 diff 로 합성해 양쪽 스캔에 합류 (바이너리/대용량/벤더 디렉토리 제외). 회귀 +10 (1015 → 1025)
- **cp949 디코딩 크래시 root fix** (`32b4ffd`) — Windows locale 에서 `subprocess.run(text=True)` 가 UTF-8 출력을 cp949 로 디코딩하다 크래시. skills 6개 지점 `encoding="utf-8", errors="replace"` 통일
- **ha-design `locked_section_status` 백포트 누락** — v0.10.0+ 세션 중단 복구 기능 (`_locked_section_status`: HUMAN-LOCKED 블록의 empty/filled/not_included 판정) 이 설치 런타임 (`~/.claude`) 에만 있고 repo 소스에 없었음. repo SKILL.md (§0, 복구 절차) 는 이 필드를 참조 → 외부 설치본이 존재하지 않는 필드를 참조하는 명세-코드 격차. 미러 전수 해시 비교 점검에서 적발, 미러 → repo 백포트 + 핀 테스트 +2 (1036 → **1038**)

---

## [0.11.1] — 2026-06-11 — "Dogfood Harvest: FP Flood & CI Green"

code-hijack dogfood Phase 3~4 실전 수확 (LESSON-030 promote) + 6/1부터 깨져 있던 CI 복구.

### Fixed

- **보안 훅 FP 홍수 (LESSON-030)** — command-guard/code-quality/dependency-check 가 문서 diff 산문을 코드로 오인 (실전: harness-plan.md rationale `'external eval ('` → BLOCK 3건, SKILL.md 인라인 예시 → WARN 16/16 FP). `strip_doc_files_from_diff` 로 `.md/.rst/.txt`·`docs/`·`templates/` diff 블록을 보안 훅 입력에서 제외 — `/ha-review` `_collect_findings` (SecurityHooks + mobile 룰) 와 `/ha-build` security gate 양쪽 적용. `.py` 코드의 eval() BLOCK 은 유지
- **dependency-check stdlib/자기 패키지 오인** — `sys.stdlib_module_names` 상시 허용 (tomllib/pathlib FP), `detect_local_packages` 가 `<project>[/<child>][/src]/<pkg>/__init__.py` 스캔으로 자기 패키지 import (`import hijack` WARN 25건) 를 `extra_python_allowed` 로 면제. import 스캔만 — `pip install <자기패키지>` 는 여전히 BLOCK
- **CI 6/1부터 red 였던 2개 잡 복구** — install-snapshot: ha-* 스킬 수 `7` 하드코딩 → 레포 소스에서 동적 파생 (현재 10개). quality: 테스트 7파일이 설치된 런타임 (`~/.claude`) 에 의존하는데 러너에 미설치 → pytest 전 `install.sh --force` 스텝 추가

### Added

- LESSON-030 main 승격 (자동학습 루프 2회째 완주) + 회귀 테스트 21개 (994 → **1015**)

---

## [0.11.0] — 2026-06-10 — "Design Integrity & Intent Capture"

전체 시스템 리뷰 (프롬프트 감사 + 코드/아키텍처 리뷰 에이전트 2종 병렬 + 최신 기법 리서치) 의 결함 수정 + 사용자 dogfood 피드백 ("작동은 하는데 의도와 다르게 작동") 대응. 설계 게이트 3→6개, 의도 손실 깔때기 5지점 봉합.

### Added

- **skeleton drift 게이트** (`/ha-build prepare`) — freeze 후 외부 수정 감지 시 BLOCK. `--accept-skeleton-drift` 로만 우회. 기존엔 skeleton 을 가장 많이 소비하는 build 단계에 hash 검사가 없었음
- **섹션별 hash 결정론 rebuild** — `plan.section_hashes` snapshot (ha-design commit / ha-redesign apply 기록). `/ha-redesign` 이 변경 섹션을 diff 해 `skeleton 참조` 하는 done task 를 **agent recall 과 무관하게** `needs_rebuild` 파생 (`hash_derived_rebuild_candidates`)
- **역방향 contract 검증** (`/ha-review prepare`) — `interface.http` 에 선언됐는데 소스에 정적 prefix 가 없는 엔드포인트 보고 (`missing_declared_endpoints`, SKILL §2.9). 기존 contract-validator (초과 구현) 와 합쳐 양방향 완성
- **설계-시점 cross-section 검증** (`/ha-design commit`, `design_findings`) — error_ux 코드↔errors 정의 / 화면 참조 API↔interface.http 선언 / Auth 칸 공백을 기계 대조 — §4 충돌 검토 (LLM 절차) 의 기계 보강
- **의도 포착 배치** (`/ha-design`) — Intent Echo (후보 생성 전 이해 재서술 + 모호점 질문) · 기능별 **Given/When/Then 수용 기준** HITL 확정 (Step D) · 게이트 **행동 워크스루** (구조 표 + 사용 장면 서사) · **모호어 스캔** §4.5 (알아서/적절히/자동으로 → 질문화) · **적대적 자가비판** §4.7 (깨지는 시나리오 3개 → 막는 섹션 확인)
- **루프 탈출 가드** (`/ha-verify record`) — 동일 T-ID 3회째 FAIL 은 차단 (`--force-continue` 우회). build↔verify 무한 왕복 방지
- **`/ha-ship`** — `reviewed → shipped` 라스트마일 마킹 (상태머신에 정의만 있고 운전자가 없던 고아 상태 해소)
- **6축 모순 경고** (`/ha-init`, `axis_warnings`) — `monetization=payment + data_sensitivity=none` / `availability=high + lifecycle=poc`
- **conventions.md 생성 경로** (`/ha-init` §6.5) — 모든 에이전트 권위 1순위 문서의 생성 단계 공석 해소 (/code-hijack 연결 / 스텁 생성)
- **시니어 핸드오프 노트** — 활성 에이전트 9종 프롬프트 (한 일 / 우려 1가지 / 이견 / 다음 역할에게) + ha-build/ha-plan/ha-design 의 사용자 노출 relay
- **3중 제목 동기 테스트** — fragment frontmatter name = 본문 헤딩 = SECTION_TITLES. 첫 실행에서 실제 drift 2건 적발
- 문서: `backend/docs/GATES.md` (게이트 전수 — BLOCK 15 + advisory 10+), `harness/templates/skeleton/_README.md` (fragment 작성 가이드), `backend/docs/prompt-evaluation-2026-06-10.md` (프롬프트 감사)

### Fixed

- **SECTION_TITLES drift** — `environments`("환경 분리") / `error_ux`("에러 처리 UX") 가 fragment 와 어긋나 제목 키잉 기능 전부에 invisible 이었음
- **consistency checker ID-키잉** — 하드코딩 §13/14/15 가 동적 섹션 번호 체계에서 엉뚱한 섹션을 검사하던 결함 (리뷰 에이전트 2종이 독립 수렴한 최대 발견)
- **fail-open 5곳** — ha-plan/ha-init 파일쓰기 가드 (실패 시 상태 전이 중단), ha-plan re.sub 람다화 (LLM 출력 `` 주입), 프로파일 로드 blind except 협소화 (agent-mismatch 게이트 공허 통과 차단), ha-review git diff timeout, profile_loader 부모 누락 stderr 경고
- **fragment de-rot** — tasks 의 가짜 6컬럼 스키마 → 실제 파서 5컬럼 + 실상태값, 존재하지 않는 `--reset` 안내 제거, AI 후보 표 5→3행 (런타임 ha-design 과 동기), view.components 의 HabitFlow 잔재 + 고정 다크 팔레트 시드 제거 (LESSON-014 모순), state.flow 중복 소절 삭제, 웹 전용 CVA 규칙 → 프로파일 위임
- **ha-deepinit Agent model 핀** — `model: "sonnet"` 누락으로 1M 컨텍스트 부모 상속 시 크레딧 에러 (실증 후 수정)
- `built` 전이 시 skipped 태스크 목록 공개 (`skipped_tasks` — 사일런트 게이트 우회 차단)

### Changed / Deprecated

- **v1 Orchestra 경로 deprecated** — `reviewer`/`qa` CLAUDE.md + `orchestrate.py` 에 표시. v2 에선 `/ha-review` (fp-check + LESSON + 7훅) / `/ha-verify` 가 대체. 코드/테스트는 유지
- guideline 블록 dedup — `_ha_shared/GUIDELINES_NOTE.md` 단일 원천으로 6개 스킬 통일
- 모바일 코더 4종 프롬프트 섹션 순서 통일 (권위 → 자율결정금지 → 골든원칙)
- repo↔`~/.claude` 미러 정리 — stale backport 해소 + byte-identical 동기 운영 (ha-design run.py 만 의도적 divergence)

**후반 추가 (같은 날)**: canonical 섹션 삽입 (`user_journey` 가 notes 뒤 dangling 하던 결함 — `CANONICAL_SECTION_ORDER`), ha-verify **가짜 FAIL 가드** (`test_dir_warning` — profile cwd 오매칭 시 실행 전 경고, python-cli paths 의 `backend/` 제거), `harness validate` 0 errors/0 warnings (stale ID 셋·`_`파일 스캔·slo 괄호식), 약모델 프롬프트 다이어트 (architect/designer 체크리스트→인변량 ≤7, backend_coder JWT 3중사본→포인터 264→219줄, ha-design 519→391줄 + 실행 진행표 + 게이트 8블록→표), assert 누락 테스트 3건 수정, LESSON 자동학습 루프 첫 완주 (**LESSON-029** promotion).

테스트 939 → **994** (+55). ruff check/format · pyright · validate · gate benchmark 전부 clean.

---

## [0.10.0] — 2026-05-15 — "HITL Gate"

ChatDev Experiential Co-Learning + aider confirm gate 영감으로 *사람-AI 결정권 분리* 강화. LESSON-014 / DESIGN-1 / ARCH-2 처럼 AI 추측 채우기로 발생하던 밋밋한 결과 패턴 차단.

### Added

- **HITL gate** — 페르소나 / 시나리오 / 화면 시안 = 사용자 인터뷰로만 채움. AI 추측 차단.
  - `<!-- HUMAN-LOCKED:<section_id> -->` 마커 + `~/.claude/harness/bin/check_locked.py` PreToolUse hook (Edit/Write 차단)
  - `HarnessPlan.frozen_status` (drafting/frozen), `frozen_at`, `locked_sections`, `ai_drafted_sections` 4 필드
  - `PlanManager.freeze()` — one-way gate (no unfreeze; rollback 은 `/ha-redesign` audit 통해)
- **`/ha-design` HITL 인터뷰** — LOCKED 섹션마다 AI 후보 5 개 → AskUserQuestion → 사용자 선택. `--ai-draft` 옵트인으로 AI 추측 채우기 (사용자 후속 promotion 필요)
- **`/ha-build` 진입 게이트** — `frozen_status="frozen"` 필수. `--skip-frozen-gate` 마이그레이션용 escape hatch
- **`/ha-review extract-lesson`** — 리뷰에서 패턴 발견 시 `shared-lessons.md` 의 Pending Lessons 섹션에 auto-append. 사용자 수동 promotion 으로만 main 진입 (가짜 LESSON 자동 적용 방지). ChatDev 영감
- **`/ha-log` 마이크로 스킬** — `worklog.md` 수동 append (discussion / change / next 카테고리). `/ha-design`, `/ha-build` (done), `/ha-redesign` (apply) 자동 append (subprocess)
- **`harness migrate-v10`** — v0.9.x → v0.10.0 마이그레이션. default drafting + `--auto-freeze` + `--dry-run` + `*.v9.bak` 백업
- Reviewer-driven hardening: `freeze(ai_drafted_sections=None vs [])` 분리, `_plan_to_dict` `frozen_status` validation, fragment placeholder 컨벤션 주석
- fragment 3 강화 — `requirements` / `user_journey` / `view.screens` 에 LOCKED 마커 + AI 제안 후보 슬롯 + HITL gate 가이드 + Mobbin/Dribbble 디자인 레퍼런스 URL 슬롯

### Fixed

- `test_context.py::test_all_36_standard_sections_present` — expected_ids 에 `environments` / `error_ux` / `rate_limiting` 3 개 추가 (실제 SECTION_TITLES 와 동기화)

### Migration

v0.9.x → v0.10.0 흐름:
1. `python ~/.claude/harness/bin/harness migrate-v10 <project>` — frontmatter 에 lock 필드 박음 (drafting default)
2. `/ha-design` 재실행 — HITL 인터뷰 통과 + freeze
3. `/ha-build` 정상 진행

또는 escape hatch (개발용): `--auto-freeze` (사용자 책임), `/ha-build --skip-frozen-gate`

backward-compat: legacy v0.9.x plan 은 `frozen_status` 미존재 시 default `"drafting"` 으로 자동 로드.

### Tests

- pytest **939/939 pass** (+39 신규 — T1~T9 + reviewer hardening 합산)
- ruff / pyright clean
- mirror sync: 모든 스킬 양쪽 (`~/.claude/skills/` ↔ `<repo>/skills/`) 바이트 동일

### 비교 분석

OSS 비교 (MetaGPT / ChatDev / OpenHands / aider / CrewAI) 결과 — HITL gate 는 ChatDev / aider / CrewAI 3 개에 있고 HarnessAI 만 없었음. v0.10.0 으로 따라잡음. 자동 LESSON 추출 (ChatDev) 도 함께 박음. 벡터 메모리 (CrewAI) + 실행 sandbox (OpenHands) 는 v1.0.0 백로그.

---

## [0.9.2] — 2026-05-12 — "audit cleanup"

Final verification: **pytest 893 pass / ruff clean / pyright 0 errors**.

핵심 가치: mirror sync (repo ↔ `~/.claude` 5파일 drift 회복), profile 보강 (LESSON-STYLE-001 정의 + whitelist/detect 항목 추가), 명세-코드 격차 3건 (G1 ha-deepinit augment-plan, G2 ha-verify integrity gate 자동 실행, G3 ha-build git WARN) 구현으로 설계 문서와 실제 코드가 일치하도록 정비.

### Added

- **`ha-deepinit augment-plan`** — G1: `ha-deepinit` 의 augment-plan 명령 구현. 기존 코드베이스 분석 결과를 harness-plan.md 에 반영 (신규 회귀 +23).
- **LESSON-STYLE-001** — profile 공통 원칙에 코딩 스타일 컨벤션 정의 항목 신규 추가.

### Changed

- **mirror sync** — `c760762`: repo 내 5개 파일 (`skeleton_hash.py`, `skeleton_stale.py`, `consistency.py`, `capabilities.py`, `agent_matching.py`) 과 `~/.claude` 사본 간 drift 회복. `skeleton_hash` frontmatter 미저장 버그 수정.
- **profile 보강** — `10a5432`: `python-lib` entry_points 추가, `drizzle-orm` / `python-multipart` / `@types/express` whitelist 추가, `android-kotlin` env_config 보강.
- **ha-verify integrity gate 자동 실행** — G2: `harness integrity` 를 `/ha-verify` 가 자동으로 실행하도록 명세 반영.
- **ha-build git WARN** — G3: ha-build 가 uncommitted 변경 감지 시 WARN 출력.

---

## [0.9.1] — 2026-05-12 — "graph CLI backfill"

Final verification: **pytest 870 pass / ruff clean / pyright 0 errors**.

핵심 가치: v0.8.0 CHANGELOG + 메모리에 `harness graph` CLI 가 추가됐다고 기록됐으나 실제 미구현이었던 사실을 dogfooding 중 발견 → 보충 구현. test_graph_cli.py 의 pre-existing failure 4건 해소.

### Added

- **`harness graph <tasks-path>`** — tasks.md → Mermaid 의존성 그래프 렌더링 CLI (142 lines). `--inject` 로 tasks.md 에 그래프 삽입, `--no-phases` 로 Phase 구분 없이 플랫 출력. 회귀 테스트 +4.

### Fixed

- **`test_graph_cli.py` pre-existing failure 4건** — v0.8.0 시점부터 존재하던 실패 해소.

---

## [0.9.0] — 2026-05-12 — "챙겼니 dogfood fixes"

Final verification: **pytest 866 pass / ruff clean / pyright 0 errors**.

핵심 가치: 챙겼니 (React Native/Expo) dogfooding 으로 노출된 결함 11건 (V1~V6, R1~R6, B1~B6) 전체 수정. 신규 CLI 2개 (`migrate-skeleton-hash`, `analyze-failure`), 회귀 테스트 +105.

### Added

- **`harness migrate-skeleton-hash`** — legacy plan 에 `skeleton_hash` 필드 없거나 잘못된 경우 마이그레이션 CLI. `--apply` 로 실제 갱신.
- **`harness analyze-failure`** — `/ha-build` 실패 시 원인 분류 + 권고 출력 CLI (B3/V5).
- **신규 회귀 테스트 +105** — v0.9.0 결함 fix 에 대한 regression coverage.

### Fixed

- **V3: RN profile bun test** — `react-native-expo` 프로파일 toolchain test 명령 `bun test` 로 정정.
- **R1: ha-review not-git silent fail** — git 저장소 아닌 디렉토리에서 `/ha-review` 가 조용히 실패하던 버그. fail-fast WARN 출력으로 변경.
- **B5/B1: ha-build state machine + atomic plan/tasks** — `building` 중복 진입 차단 + plan/tasks 파일 atomic 쓰기.
- **R2/R5/R6/V6: record gate** — `/ha-review` 와 `/ha-verify` 가 실행 기록(verify_history / review_history)을 저장하지 않던 버그. security hooks + violations/rework 결과 기록.
- **V1/R4 + B6: hash migration + file_structure drift** — legacy `skeleton_hash` 미저장 → 마이그레이션 + `file_structure` 섹션 drift audit 추가 (B6).
- **B3/V2/V5: no-tests WARN + integrity verbose + analyze-failure** — 테스트 파일 0개 시 WARN, `harness integrity` verbose 모드, `analyze-failure` CLI.

---

## [0.8.0] — 2026-05-11 — "design defect fixes"

Final verification: **pytest 761 pass / ruff clean / pyright 0 errors / harness validate 0 errors**.

핵심 가치: 챙겼니 dogfooding reverse-engineering 으로 5개 그룹 + 보강 결함 발견 → 인프라 모듈 7개 신설, frontmatter 필드 4개 추가, CLI 1개 (`migrate-plan`). 기존 설계 문서와 실제 코드 사이 구조적 격차를 대규모 수정.

### Added

- **신규 인프라 모듈 7개** (`backend/src/orchestrator/`):
  - `capabilities.py` — `KNOWN_CAPABILITY_ATOMS` (14개 atom single source of truth), `derive_axes_capabilities`, `validate_capability_set`
  - `consistency.py` — `find_consistency_violations`, `_HAS_KEY_PROVIDERS` (atom → provider profile 셋)
  - `lessons.py` — `extract_known_lessons`, `find_unknown_lesson_references`
  - `agent_matching.py` — `match_task_to_agent`, `find_best_agent_for_task`, `AgentMatchResult`
  - `tasks_schema.py` — `validate_tasks_md` (T-NNN 강제), `TaskNode/TaskGraph`, `extract_task_graph`, `render_mermaid`
  - `skeleton_hash.py` — `compute_skeleton_hash` (CRLF/LF 정규화), `check_skeleton_hash`
  - `skeleton_stale.py` — `preview_skeleton_stale`, `mark_skeleton_stale`

- **신규 frontmatter 필드 4개** (`HarnessPlan`):
  - `activation_trace` — 활성 섹션별 `required_when` 표현식 audit trail
  - `skeleton_hash` — skeleton.md SHA-256, 외부 수정 감지
  - `eng_review_history` — `/plan-eng-review` 등 외부 도구 audit trail
  - `external_capabilities` — BaaS/Firebase 등 외부 backend escape hatch

- **`harness migrate-plan <path>`** — stale plan 정정 + skeleton STALE 마킹 CLI (`--apply` / `--mark-skeleton-stale` / `--no-backup`).

- **신규 escape flags** — `--allow-agent-mismatch`, `--allow-format-drift`, `--allow-unknown-lessons`, `--external-capabilities`.

- **회귀 테스트 +220** (541 → 761).

### Fixed

- **mobile-only false-positive** — `interface.http` / `rate_limiting` / `slo` 섹션이 mobile-only 프로젝트에서 활성화되던 버그.
- **`auth` / `persistence` false-negative** — mobile-only 프로젝트에서 필수 섹션이 빠지던 버그.
- **`mobile_coder_rn` backend task 라우팅** — RN coder 에게 auth API 같은 backend task 가 잘못 배분되던 버그.
- **fractional task ID** — `T-024.5` 같은 소수 ID 생성 방지 (`tasks_schema.py` T-NNN 강제).
- **`/plan-eng-review` skeleton 직접 수정** — `skeleton_hash` 로 외부 수정 사후 감지.
- **`adapt_diff` TypeError** — `3ea95c1` review feedback.

### Migration

기존 v0.7.0 사용자:
- `./install.ps1 -Force` 또는 `./install.sh --force` 재실행 — 신규 모듈 7개 + harness bin 변경 동기화 필수.
- `harness migrate-plan <path> --apply` — 기존 `harness-plan.md` 에 신규 frontmatter 필드 추가 (선택, 하위 호환).

---

## [0.7.0] — 2026-05-11 — "web + desktop profiles"

Final verification snapshot at release time:
**pytest 569 pass / ruff clean / pyright 0 / harness validate 50 files 0 errors**.

핵심 사용자 가치: Next.js / NestJS / Electron 3개 프로파일 추가로 HarnessAI 커버리지를 풀스택 웹(App Router) · Node.js 백엔드 · 데스크톱까지 확장. 신규 skeleton fragment 3개 (environments / error_ux / rate_limiting) 로 HTTP/UI/CLI 프로젝트 계약서 품질 향상. 상태 머신 버그 2건 + 크로스 플랫폼 테스트 버그 수정.

### Added

- **3 web/desktop profiles** (`harness/profiles/`):
  - `nextjs.md` — Next.js App Router (Server Components 기본 · Server Actions 뮤테이션 · better-auth/NextAuth · Drizzle ORM · Zustand 클라이언트 UI 상태만)
  - `nestjs.md` — NestJS 백엔드 (TypeORM · class-validator · ValidationPipe · Passport JWT 2-strategy · GlobalExceptionFilter → `{ error, code, details }`)
  - `electron.md` — Electron 데스크톱 (Context Isolation 필수 · preload contextBridge IPC · 채널명 상수화 · electron-updater 자동 업데이트 · 코드 서명)

- **3 new skeleton fragments** (`harness/templates/skeleton/`):
  - `environments.md` — 환경별 config (dev/staging/prod) + 시크릿 관리 (`required_when: has.http_server or has.ui or has.navigation or has.cli_entrypoint`)
  - `error_ux.md` — 사용자 에러 경험 설계 (에러 메시지 계층 · fallback UI · 재시도 UX, `required_when: has.ui`)
  - `rate_limiting.md` — API rate limit 설계 (전략 · 임계값 · 응답 형식 · 클라이언트 가이드, `required_when: has.http_server`)

- **`_registry.yaml`** detection rules 3개 추가 (nextjs · nestjs · electron)

- **lessons_applied** per new profile:
  - nextjs: LESSON-006, 022, 023, 027, STYLE-001
  - nestjs: LESSON-002, 003, 004, 007, 018, 022, 023, 024, 027
  - electron: LESSON-006, 022, 023, 027, STYLE-001

### Changed

- **`slo.md`** `required_when`: `user_scale in [medium, large] or availability in [standard, high]` → `scale.medium_or_larger or availability == high`. Solo/S 프로젝트에서 `availability=standard` 만으로 SLO 섹션이 활성화되던 과잉 포함 방지.
- **`observability.md`** `required_when`: `has.production_concerns` → `has.production_concerns and scale.medium_or_larger`. S 규모 프로젝트에서 observability 섹션 과부하 방지.
- **`ha-design/SKILL.md`** auth gate: 프론트엔드/모바일 프로파일이 포함된 경우에만 silent refresh / 탭 동기화 항목 확인하도록 조건 추가.
- **테스트 +55** (496 → 551, 회귀 0): 신규 ha-redesign 스킬 + consistency_checker 테스트, toolchain gate 크로스 플랫폼 수정 포함.

### Fixed

- **ha-review state machine**: `assert_state(["verified", "building"])` → `assert_state(["verified"])` — `building` 상태에서 review 가 실행되던 버그.
- **ha-verify state machine**: `assert_state(["built", "building"])` → `assert_state(["built"])` — `building` 상태에서 verify 가 실행되던 버그.
- **`error_ux.md` required_when**: `has.frontend` → `has.ui` — `has.frontend` 가 `_SECTION_TO_HAS_KEY` 에 없어 항상 False 로 평가되던 버그.
- **toolchain gate 테스트**: `true`/`false` Unix 명령 → `subprocess.run` monkeypatch — Windows 에서 5개 테스트 전부 실패하던 크로스 플랫폼 버그.
- **paired-profile section ordering**: 2차 프로파일(mobile.*) 섹션이 tasks/notes 뒤에 추가되던 버그. 모든 프로파일 `order` 배열 병합 후 tasks/notes 마지막 배치로 수정.
- **`security_hooks` auth-guard 모바일 분리**: `is_mobile=True` 시 `_AUTH_MOBILE_PATTERNS` 독립 적용 — AsyncStorage / SharedPreferences / UserDefaults 토큰 저장 BLOCK, `.getString` 토큰 읽기 WARN. 기존엔 `is_frontend=True` 로 합산돼 백엔드 전용 룰(logout no-op 등)이 모바일 코드에도 적용되던 버그 수정.
- **`security_hooks` false positive 2건**: (1) `func.max()+1` 패턴 — 쓰기 연산(`session.add` / `bulk_save_objects` 등) 없는 순수 조회에서 WARN 미발생. (2) `author*` 식별자(`authorName`, `authorId`) — `auth` 앵커 정규식으로 오탐 제거.
- **`security_hooks` LESSON-024 severity**: `RefreshRequest` body schema → BLOCK → WARN (휴리스틱 패턴이라 확정 위반이 아님).
- **`ha-build/run.py` security gate 2건**: (1) git diff 추가 줄만 스캔 (`+` prefix) — 삭제된 코드가 BLOCK 트리거하던 버그. (2) `git log` returncode 비정상 시 조용히 건너뛰던 버그 수정 (명시적 `continue`).
- **`ha-build` `--skip-security` 플래그**: toolchain 과 독립적으로 security_hooks 게이트만 우회 가능. 기존 `--skip-toolchain` 이 security 까지 묶어서 우회하던 혼선 해소.

### Migration

기존 v0.6.0 사용자:
- `./install.ps1 -Force` 또는 `./install.sh --force` 재실행 — 신규 프로파일 3개 + fragment 3개 글로벌 install 동기화 필수
- 기존 프로젝트는 영향 없음 (새 프로파일은 감지 규칙에 매칭될 때만 활성)

---

## [0.6.0] — 2026-05-07 — "mobile expansion"

Final verification snapshot at release time:
**pytest 496 pass / ruff clean / pyright 0 / harness validate 44 files 0 errors / 글로벌 install 82 files**.

핵심 사용자 가치: HarnessAI 의 9 quality gates + 21 LESSONs + skeleton contract + profile system 가치를 모바일 (React Native + Expo / Flutter / Android Kotlin + Compose / iOS Swift + SwiftUI) 까지 확장. 외부 사용자가 자기 모바일 프로젝트에서 `HARNESS_AI_HOME` 설정 + `/ha-init` 만으로 production-grade 컨벤션 + 가이드라인 + 보안 룰을 즉시 받음.

### Added

- **4 mobile profiles** (`harness/profiles/`):
  - `react-native-expo.md` — Expo SDK + Bun + Zustand + NativeWind + Expo Router
  - `flutter.md` — Flutter SDK + Riverpod + go_router + drift + dio + Material3
  - `android-kotlin.md` — Jetpack Compose + StateFlow + Room + Retrofit + Hilt + Gradle Version Catalog
  - `ios-swift.md` — SwiftUI + `@Observable` + NavigationStack + CoreData/SwiftData + URLSession + Keychain (Win 호스트 제약 명시)

- **3 mobile fragments** (`harness/templates/skeleton/mobile.{navigation,build_config,lifecycle}.md`)

- **4 mobile_coder agents** + 공통 prefix `mobile_coder_shared.md` (10 원칙, 4 prompts 에 인라인됨)

- **16 framework guidelines** (`harness/templates/guidelines/<profile>/*.md` × 4 frameworks × 4 files)

- **`/ha-*` skill 모바일 awareness**:
  - 6 skill cmd_prepare 출력에 `guideline_paths` 필드 (Phase A) — `skills/_ha_shared/utils.py` 의 `resolve_guideline_paths(profile_id)` helper
  - `/ha-init detect` 의 `is_mobile: bool` 필드 + stderr `[INFO]` 안내 (Phase B1)
  - `/ha-review` 의 4 mobile 보안 룰 — AsyncStorage/UserDefaults/SharedPreferences/shared_preferences 시크릿 저장 BLOCK / 권한 일괄 요청 WARN / CocoaPods 신규 추가 WARN / RN CLI 직접 사용 WARN (Phase B2)
  - `/ha-verify` 의 `platform_warnings` (`shutil.which` 점검 + iOS-on-Windows 가드 + JAVA_HOME 가드, Phase B3)
  - 6 SKILL.md 모바일 워크플로우 예시 섹션 (Phase B4)

- **신규 atom + 매핑** (`profile_loader._SECTION_TO_HAS_KEY` + `harness/bin/harness REQUIRED_WHEN_ATOMS`):
  `has.navigation` / `has.build_config` / `has.lifecycle`

- **`files_any` registry 매처** — Android Gradle (`build.gradle.kts` OR `build.gradle` OR `settings.gradle.kts`) / iOS (`Package.swift` OR `Podfile`) 등 OR 매칭 케이스

- **Backend Orchestra path 보강** (대시보드 사용자):
  - `OrchestratorConfig` Pydantic 7→11 agent fields (4 mobile_coder)
  - `AGENT_SECTIONS_BY_ID` mobile_coder × 4 + Designer 의 mobile.navigation/lifecycle
  - `EXTRA_HARNESS_DOCS` + `build_context.harness_dir` 파라미터 — harness-global guidelines 직접 로드
  - `_resolve_prompt_path` HARNESS_AI_HOME fallback (외부 프로젝트에서 `agent_prompts` 경로 자동 해결)
  - `is_mobile` 플래그 플러밍 (verify / implement_with_retry / run_phases / SecurityHooks.run_all, frontend 와 상호배타)

- **테스트 +76** (420 → 496, 회귀 0):
  - 매처 확장 / 4 mobile profile 통합 / context 매핑 / harness-global doc 로딩 / HARNESS_AI_HOME fallback / mobile 보안 룰 / platform_warnings / SKILL.md 모바일 예시 / guideline_paths 출력 (12 파라미터 통합 테스트 포함)

### Changed

- **Architect / Designer 시스템 프롬프트** — "## 모바일 프로파일 — 추가 책임" 섹션 신설. Architect 는 mobile.build_config / mobile.lifecycle / persistence (mobile DB), Designer 는 mobile.navigation / mobile.lifecycle UX / view.screens (mobile 변형)
- **Frontend Coder 시스템 프롬프트** — "web only" 명시. 모바일 task 잘못 라우팅 시 즉시 에스컬레이션
- **Orchestrator 시스템 프롬프트** — Task→Agent 매핑 표 6-row 확장 (mobile_coder × 4) + 모노레포 dispatch 우선순위
- **`SECTION_TITLES` / `STANDARD_SECTION_IDS` / `_BATCH_MODE_DIRECTIVE`** — 20 → 33 정합 (v0.5.0 가 추가했지만 미동기였던 fragment 10개도 동시 회복)
- **`_FRONTEND_PROFILES`** — `("react-vite",)` 단일화 (`nextjs.md` 미구현 → 룰 제거, R1)

### Fixed

- **v0.5.0 partial drift 회복** — `data_model` / `threat_model` / `audit_log` / `slo` / `runbook` / `test_strategy` / `user_journey` / `authorization_matrix` / `ci_cd` / `external_deps` 10 fragment 가 SECTION_TITLES + STANDARD_SECTION_IDS + _BATCH_MODE_DIRECTIVE 에 누락되어 있던 silent drift 동시 회복
- **글로벌 install drift** — v0.5.0 release 이후 `./install.sh` 재실행 누락으로 사용자 컴퓨터 글로벌 install 이 27 files 에서 정지. v0.6.0 작업 중 발견 + `./install.ps1 -Force` 실행으로 27 → 37 → 82 동기화
- **사용자 흐름 결함 D1~D6 + 2차 점검 결함** — backend Orchestra path 와 /ha-* skill path 가 분리된 두 codepath 임을 발견 + 양쪽 모두 fix
- **R1: nextjs registry stub** — `_registry.yaml` 에 룰만 있고 `harness/profiles/nextjs.md` 미구현 → 잠재 사용자 silent fail. 룰 제거. Next.js 사용자는 react-vite 프로파일 + frontend_coder 시스템 프롬프트 수정 (SETUP.md 예시 2)

### Migration

기존 v0.5.0 사용자:
- `./install.ps1 -Force` 또는 `./install.sh --force` 재실행 — 글로벌 install 동기화 필수
- `HARNESS_AI_HOME` 환경변수 설정 권장 (외부 모바일 프로젝트에서 mobile_coder 사용 시)
- 기존 web/CLI 프로젝트는 영향 없음

알려진 제약 (Phase 7 후속):
- iOS native 의 `xcodebuild` 빌드 검증은 Windows 호스트에서 불가능 — macOS GitHub Actions runner CI 추가 예정
- examples/<framework>-todo/ 등 sample app E2E 는 별도 (LLM 비용 + 실 빌드 필요)
- 라이브 LLM dispatch 검증 (D7) 은 외부 사용자 첫 dogfood 시 자동 검증으로 대체

---

## [0.5.0] — 2026-05-02 — "auto-fit skeleton"

Final verification snapshot at release time:
**pytest 420 pass / ruff 0 / pyright 0 / harness validate 37 files 0 errors / install snapshot 12/12 PASSED / CI green**.

핵심: 사용자가 6축만 답하면 적합한 skeleton 섹션이 자동 활성화. PII+mvp →
audit_log/threat_model/test_strategy/ci_cd/slo 자동 포함, none+poc → 모두
정확히 제외 (POC 비계 가볍게 유지). 표준 섹션 20 → 30, backend tests
357 → 420 (+ 신규 63), skeleton fragment 신규 10개.

### Added
- **scale_axes 6축 + /ha-init 자동 맞춤 skeleton** (Phase 1+2, `c33197a` →
  `36a0451`) — 사용자가 6축 (user_scale / data_sensitivity / team_size /
  availability / monetization / lifecycle) 만 답하면 적합한 fragment 가
  자동 활성화 → "맞춤 skeleton" 이 실제로 동작.
  - **Phase 1 — scale_axes 데이터 모델** (`c33197a`, `47212fb`):
    `ScaleAxes` frozen dataclass + `HarnessPlan.scale_axes` 필드 + frontmatter
    `scale_axes:` 직렬화. 하위 호환 (legacy frontmatter 도 default 로 로드).
    `/ha-init` 인터뷰 단계 추가 — S/M/L 프리셋 분기 + 6축 직접 답. argparse
    6개 인자 + cmd_write 통합. `--scale` 은 `--user-scale` 로 강제 동기화.
    `_AXIS_NAMES_CLI` ↔ `ScaleAxes` drift 방지 sync 테스트.
  - **Phase 2-a — 신규 skeleton fragment 10개** (`34359e4`):
    `data_model` (ERD Mermaid + PII + cascade + 마이그레이션 정책),
    `threat_model` (STRIDE/OWASP), `audit_log` (compliance), `slo`
    (p50/p95/p99 + 가용성 + RPS), `runbook` (알람→대응),
    `test_strategy` (Test pyramid + contract test), `user_journey`
    (Mermaid sequence/state), `authorization_matrix` (역할×리소스×액션),
    `ci_cd` (파이프라인+환경+롤백), `external_deps` (3rd-party SLA+폴백+
    webhook idempotency). 표준 섹션 20 → 30.
  - **Phase 2-b-1 — scale_expression 파서/평가기** (`077dcdc`, `7ce07a6`):
    `backend/src/orchestrator/scale_expression.py` 신규 — AST + tokenizer +
    재귀 하강 parser + evaluator. `data_sensitivity in [pii, payment] or
    availability == high` 같은 표현식을 ScaleAxes 인스턴스에 평가. 6축 axis
    이름은 `dataclasses.fields(ScaleAxes)` 동적 추출 → 새 axis 자동 인식.
    24+5 unit tests (atom/comparison/membership/boolean/precedence/error/
    parse-AST).
  - **Phase 2-b-2 — harness validator vocabulary 확장** (`ff6d8d0`):
    CLI validator 가 6축 표현식 syntax 인정 (atom + or/and/+ 결합 + 정규식
    sanity). 9 fragment 의 `required_when` 을 description 의 의도 표현식
    그대로 교체 (`always` → `data_sensitivity in [pii, payment]` 등).
    괄호 표현식은 명시적 reject (validator 신뢰성 보존, 정식 평가는
    backend parser).
  - **Phase 2-b-3 — ProfileLoader 활성 섹션 결정** (`b4952a0`):
    `compute_active_sections` / `compute_has_keys` / `compute_scale_tokens` /
    `load_fragments_metadata` 4개 method. `_SECTION_TO_HAS_KEY` (19개
    매핑) + `_USER_SCALE_TO_TOKENS` (cumulative). 17 unit tests.
  - **Phase 2-b-4 — /ha-init cmd_write auto-determine** (`b2682e1`,
    `4e8da81`): `--included` optional. 빈 값/`auto` 면 `compute_active_sections`
    호출 → 활성 섹션 자동 결정. SkeletonAssembler 의 `harness_dir` 통일
    (dev mode + install mode 둘 다 안전). `view.components` 의 `+` → `and`
    (parser 일관). Smoke 검증: PII+mvp → 18 sections / none+poc →
    13 sections (audit_log/threat_model/test_strategy/ci_cd/slo 자동
    포함 vs 정확히 제외).
  - **README 노출** (`36a0451`): "What it actually adapts" 섹션 추가
    (PII vs none 비교표 + 실 smoke 결과). 30개 섹션 ID 목록 + 6축 anchor
    링크. test count 361 → 420 동기화 (.md 9개).
- **결정권 분리 원칙 전면 적용** (`36c026d`, `8dd11f7`) — Architect/Designer 는
  skeleton 에 DB/화면/레이아웃 세부까지 확정, Orchestrator 는 tasks.md 에 태스크별
  구현 스펙 블록 작성, Coder 는 자율 결정 금지 + 미정의 시 `--status blocked`
  에스컬레이션. 5 에이전트 CLAUDE.md + ha-plan/ha-build SKILL.md 일관 업데이트.
  - **Architect CLAUDE.md** — DB 세부 완비 체크리스트 (컬럼/타입/NULL/UNIQUE/
    기본값/인덱스/FK ondelete/`DateTime(timezone=True)`), 모호함 금지 원칙
    ("적절한 인덱스" 같은 표현 금지), 백엔드 레이아웃 결정 책임 (src/ vs flat,
    디렉토리 구조, 파일 경로 예시).
  - **Designer CLAUDE.md** — 화면당 8 필드 체크리스트 (경로/레이아웃/인증/초기
    로딩/API/store/에러/flow), 컴포넌트별 파일 경로 + props 타입 명시, store
    state/action 시그니처 완비, 프론트엔드 레이아웃·파일명 결정 책임, React
    Query 하드코딩 제거 (conventions 위임).
  - **Orchestrator CLAUDE.md** — tasks.md 에 Phase 5컬럼 테이블 + 태스크별
    스펙 블록 (생성/수정 파일, skeleton 참조, 구현 세부, 참조 파일, 완료 기준)
    포맷 추가. 파서 호환성 유지 (5컬럼 regex 불변).
  - **Backend/Frontend Coder CLAUDE.md** — 권위 순서 섹션 (conventions > 루트
    CLAUDE.md > agent CLAUDE.md > tasks.md 스펙 블록 > skeleton), 자율 결정
    금지 테이블 (레이아웃/DB 필드/API 경로/파일명), 에스컬레이션 절차.
  - **ha-plan SKILL.md** — 출력 포맷 예시에 "태스크별 구현 스펙 블록" 추가,
    스펙 없는 태스크는 미완성 산출물로 간주.
  - **ha-build SKILL.md** — 읽기 순서에 tasks.md 스펙 블록 1순위 배치, 스펙
    불완전 시 blocked 에스컬레이션 절차 명시, 하위 호환 폴백 안내.
- **실측 검증 완료** — `bench-personaljira-v3` Stage B smoke test 로 결정권
  분리 효과 정량 확인: skeleton `persistence` 0→11 테이블, FK ondelete 0→16,
  `CustomException` subclass 0→15 (conventions 위반→완비), Sonnet Backend
  Coder Phase 1 10 태스크 실행 pytest **194 / ruff 0 / pyright 0** clean.
  자율 결정 14건 모두 자발 보고, 스펙 위반 0건. (리포트는 bench 디렉토리
  내부, 레포 외부).
- **`docs/ARCHITECTURE.md` 영어 버전 신규** — 현재 한국어는 `ARCHITECTURE.ko.md`
  로 이전, 양쪽 상단에 언어 토글 배너. 영어 버전은 섹션 11로 나누어 condensed
  ~200 라인 (한국어 원본은 worklog-style 상세).
- **`backend/.env.example` 전면 재작성** — stale 엔트리 (DATABASE_URL /
  GITHUB_* / ANTHROPIC_API_KEY — 미사용) 제거, 실제 읽히는 env 변수만 남김
  (HARNESS_AI_HOME / GEMINI_API_KEY / DASHBOARD_* / PROJECT_DIR).
- **CONTRIBUTING.md** `HARNESS_AI_HOME` 설명 보강 — /ha-* 스킬 v2 모듈
  import 용. 미설정 시 스킬만 실패 (backend tests 는 영향 없음) 명시.

### Changed
- **`install.sh` + `install.ps1` 메시지 전면 영어화** — 국제 사용자 대상.
  도움말 · progress · 변경 요약 · y/N 프롬프트 · 완료 안내 전부 영어.
  한국어는 README.ko.md 에서 제공.

### Fixed
- (항목 추가되는대로)

---

## [0.4.0] — 2026-04-20 — "portfolio-ready"

Final verification snapshot at release time:
**pytest 357 pass / ruff 0 / pyright 0 / gate_benchmark 35/35 (100% precision/recall/accuracy) / harness validate 27 files 0 errors**.

First tagged release. Goal: the repository is ready for public GitHub
disclosure — bilingual README, community standards (LICENSE/CoC/SECURITY),
CI, GitHub templates, working examples/, English code comments, profile-based
v2 pipeline in both skill and Orchestra paths, 9 quality gates benchmarked.

### Added
- **`docs/decisions/` ADR 5개** (B4) — Architecture Decision Records.
  - ADR-001: 프로파일 기반 아키텍처로의 전환
  - ADR-002: Skeleton 섹션 번호 → ID 전환
  - ADR-003: 파이프라인 상태를 `harness-plan.md` 단일 파일로
  - ADR-004: ai-slop 감지를 Reviewer 7번째 훅으로 통합
  - ADR-005: /my-\* 완전 삭제, /ha-\* single cut-over (Phase 4a + 4b 실행 완료)
- **`scripts/benchmark.py` + `docs/benchmarks/`** (B5 — 측정 가능한 부분) —
  LLM 호출 없이 5가지 핵심 연산 latency 측정. 30 iter 기준:
  profile 감지 **4.7 ms**, skeleton 조립 **0.13 ms**,
  `harness validate` **149 ms**, `harness integrity` **104 ms**,
  `find_placeholders` 100KB **0.14 ms** (선형 스케일).
- README 에 ADR / CONTRIBUTING / CHANGELOG / benchmarks / e2e-reports 링크 추가.
- **`docs/e2e-reports/` 신규** (B7 부분 착수) — dogfooding 증거.
  - `code-hijack.md`: 1차 E2E Phase 1+2 완주 기록 (pytest 127 → 169, 4 갭 발견 → v2 반영)
  - `ui-assistant-initial.md`: 2차 E2E 진행 중 + 2 false positive 발견/수정 기록
  - `README.md`: 인덱스 + 형식 가이드 + 다음 계획
- **LESSON-021 신규** — ui-assistant 2차 E2E 중 발견. "태스크 `done` = toolchain 전체 통과
  (test + lint + **type**)". 단위 테스트만 통과시키면 `done` 으로 mark 되는 흐름 때문에
  pyright 15 errors + eslint config 누락이 Phase 1 끝까지 숨어 있었음. 실제 `/ha-verify`
  돌려서 발견 → 수정 → 최초 verify_history 갱신.
- **LESSON-021 구현** — `skills/ha-build/run.py::_run_toolchain_gate` 신규. `--status done`
  마킹 전 프로파일 toolchain (test + lint + type) 강제 실행. 실패 시 BLOCK + done 거부.
  `--skip-toolchain` 으로 문서/설계 태스크 opt-out. 회귀 테스트 5개 추가.
- **B3 design doc 재구조화** — `docs/harness-v2-design.md` 앞부분에 "이 문서 읽는 법"
  내비게이션 추가. 다른 문서 (README/ARCHITECTURE/ADR/E2E reports/benchmarks/lessons) 우선
  권장. D1-D6 결정 테이블을 ADR cross-reference 로 교체.

### Added — Phase 4b 후속
- **`Orchestra.materialize_skeleton_v2` + `run_pipeline_with_phases(profile_ids=...)`** —
  Orchestra backend 가 `/ha-*` 스킬 경로와 동일한 "profile → empty skeleton → section_id
  merge" 계약을 공유. legacy `materialize_skeleton` (raw concat) 은 `profile_ids`
  미지정 시 back-compat 경로로 유지.
- **`pyright` dev 의존성 + 자가검증 필수 항목**. `src/` 14개 pre-existing 타입 에러
  전부 정리 (0 errors 달성). `CLAUDE.md` 에 `uv run pyright src/` 추가.

### Added — 비교 실험
- **`scripts/gate_benchmark.py` + `docs/benchmarks/gate-coverage.md`** — 9개 품질
  게이트 중 정규식/AST 기반 **7개** × 35 fixtures 커버리지 벤치마크. positive/negative
  fixture 기반 TP/TN/FP/FN
  → **precision 100% / recall 100% / accuracy 100%**. 초기 2 fixture 실패가 게이트 정책
  경계 재확인 + LESSON-018 dead 상수 정규식이 walrus operator 미커버 발견 (미래 개선
  후보). CI 통합 가능 (`exit 1` on miss/false-alarm).
- **`docs/benchmarks/dogfooding-catches.md`** — 21개 LESSON ↔ 원천 프로젝트 (Personal
  Jira / HabitFlow / 금칙어게임 / code-hijack / ui-assistant) ↔ 현재 감지 게이트 매핑.
  LESSON-013/018/021 이 단순 기록에서 **자동 감지 게이트**로 올라간 흐름을 추적.
  plain Claude 와의 **구조적 차이** 정성 비교 포함.

### Added — 공개 준비
- **`README.md` 영어 버전** 신규 + 기존 한국어는 `README.ko.md` 로 이전. 양쪽 상단에
  언어 토글 배너. 영어 README 에 shields.io 배지 6종 (tests / pyright / ruff /
  gate-coverage / python / license) + Tech stack 의 latency summary 추가.
- **커뮤니티 표준 파일** — `LICENSE` (MIT, copyright 2026 reasonableplan),
  `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1 축약), `SECURITY.md` (취약점
  보고 프로세스 + 응답 SLA critical 7d / high 30d + scope).
- **GitHub 템플릿** — `.github/ISSUE_TEMPLATE/{bug,feature,profile_request}.md`
  3종 + `.github/pull_request_template.md` (CONTRIBUTING PR 체크리스트 재사용,
  pyright / gate_benchmark / harness validate 항목 포함).
- **`examples/python-cli-hello/`** — 최소 재현 가능한 예시 프로젝트 (pyproject.toml
  + docs/harness-plan.md + docs/skeleton.md + README). 신규 사용자가 `/ha-init`
  결과를 실행 전에 미리 볼 수 있음. Korean skeleton heading 관련 로컬라이제이션
  메모 포함.

### Changed — 공개 준비
- **`.github/workflows/ci.yml` 전면 재작성** — 기존은 postgres/alembic 참조하는
  stale template (이 프로젝트엔 DB 없음). 새 workflow: ruff lint + format check +
  pyright + pytest + harness validate + gate_benchmark + install-snapshot.
- **15 파일 주석/docstring 영어화** (orchestrator/* + scripts/*). `pipeline_runner`
  의 에이전트 프롬프트 · `print()` · `input()` 한국어 UX 메시지, `output_parser`
  의 한글 regex 파싱 패턴, `security_hooks` 의 Finding 메시지 문자열은 의도적 유지.
  변경된 테스트 5개에서 에러 메시지 matcher 동기화.

### Removed — **BREAKING** (Phase 4a + 4b)

**Phase 4a** (스킬/문서 정리):
- **`/my-*` 스킬 12종 전체 삭제** — `~/.claude/skills/my-db-design/`, `my-architect/`,
  `my-designer/`, `my-skeleton-check/`, `my-tasks/`, `my-db/`, `my-api/`, `my-ui/`,
  `my-logic/`, `my-type-check/`, `my-review/`, `my-lessons/`. v1 의 4-스택 하드코딩
  (fastapi/nextjs/react-native/electron) 파이프라인이 v2 프로파일 기반 (`/ha-*` 7종) 으로
  완전 대체됨. [ADR-005](docs/decisions/005-ha-skills-cut-over.md) 참조.
- **README `v1 (레거시)` 섹션 제거** — 신규 사용자의 혼란 제거.

**Phase 4b** (backend production 레거시 코드 제거):
- **`backend/src/orchestrator/context.py`** — `SECTION_MAP` (번호 기반 에이전트 매핑),
  `extract_section` (번호 기반 추출), `fill_skeleton_template` (구 템플릿 치환) 3개 삭제.
- **`build_context` 시그니처** — `use_section_ids: bool = False` 파라미터 제거.
  기본 동작이 섹션 ID 기반 (`AGENT_SECTIONS_BY_ID` + `extract_section_by_id`) 으로 고정.
- **`orchestrate.py::materialize_skeleton`** — `skeleton_template.md` 부재 전제
  (commit `595ef88` 에서 삭제됨) 로 template 치환 분기 제거. 추출된 섹션을 바로 concat.
- **`orchestrate.py::_extract_allowed_endpoints`** — 레거시 섹션 번호 7 폴백 제거.
  `interface.http` ID 기반 추출만 유지.
- **`runner.py`** — `build_context(..., use_section_ids=True)` 호출에서 kwarg 제거.
- **테스트 수 흐름**: 365 → 347 (v1 테스트 18개 삭제) → 357 (v2 테스트 10개 추가).
  최종 backend pytest **357**.

**마이그레이션 가이드**: 기존 HabitFlow / 금칙어게임 / Personal Jira 는 이미 완료 상태라
영향 없음. 새 프로젝트는 전부 `/ha-init → /ha-design → /ha-plan → /ha-build → /ha-verify
→ /ha-review` 흐름 사용. `/my-lessons` 회고 흐름은 `/ha-deepinit` + `/ha-review` 조합으로 대체.

### Fixed — 포트폴리오 공개 직전 종합 점검
- **`Orchestra.verify` 가 프로파일 whitelist 무시 버그** — `_get_security_hooks()` 신설.
  첫 감지된 프로파일로 `SecurityHooks.from_profile()` 을 지연 생성/캐싱. 이전에는 빈
  기본 whitelist 만 적용돼 프로파일 선언이 무의미했음.
- **`pipeline_runner.run(profile_ids=...)` v2 경로 추가** — 기존 인터랙티브 CLI 러너가
  legacy `materialize_skeleton` 만 호출해 v2 profile 기반 구조가 적용되지 않던 문제.
  `--profile <id>` CLI 옵션 복수 지정 가능.
- **`runner.py::run_many` 의 `CancelledError` 취소 전파 회복** — `isinstance(r, BaseException)`
  가 `CancelledError` 를 `RunResult(success=False)` 로 둔갑시켜 graceful shutdown 시
  취소 신호가 소실되던 문제. `Exception` 만 캐치 + `BaseException` 은 재발생으로 수정.

---

## [0.3.0] — 2026-04-18 — "포트폴리오 정점 업그레이드"

### Added — 신규 품질 게이트 2개

- **`harness integrity` 서브커맨드** — `~/.claude/harness/bin/harness` 에 신규. skeleton.md 의 ` ```filesystem ` 블록 선언 경로 ↔ 실재 FS 일치 + 미치환 placeholder (`<pkg>`, `<cmd_a>` 등) 감지. `/ha-verify` 가 toolchain 실행 전에 호출. (A5)
- **테스트 분포 체크** — `/ha-review` 가 프로파일별 src ↔ 테스트 파일 대응 집계. src 모듈 있는데 테스트 0개 → BLOCK, 편차 10x 이상 → WARN. Python (AST `def test_*`) + JS/TS (`describe/it/test` 정규식) 지원. 모노레포 대응. (A6)

### Added — 신규 LESSON 3개

- **LESSON-018** 상수 정의 범위 vs 실제 사용 범위 불일치 (dead 상수) — ai-slop 정규식 자동 감지 통합 (7번째 패턴)
- **LESSON-019** 외부 명령 stderr → 사용자 친화 메시지 번역
- **LESSON-020** 진행 표시 `[N/M]` 은 실제 작동해야 — 껍데기 금지

### Added — 설치 체계 신설

- **`install.sh` (Unix/WSL/Git Bash) + `install.ps1` (Windows PowerShell)** — 단일 명령으로 `harness/` + `skills/ha-*` + `skills/_ha_shared` 를 `~/.claude/` 로 복사. (B8)
- **SHA256 manifest** (`~/.claude/harness/.install-manifest.json`) — 재실행 시 diff 감지 (added/modified/unchanged/removed), 투명한 덮어쓰기 확인.
- **`--force` / `--dry-run`** 옵션 + `CLAUDE_HOME=/custom ./install.sh` env override.
- **`install.ps1` UTF-8 BOM** — Windows PS 5.1 의 cp949 기본값과 호환.
- **non-interactive 가드** (`install.ps1`) — CI / stdin redirect 환경에서 `Read-Host` hang 방지.
- **post-install env 안내** — `HARNESS_AI_HOME` 설정 명령 출력.

### Added — 레포 구조 (소스 이관)

- **`harness/` 루트 디렉토리 신설** — 이전엔 `~/.claude/harness/` 에만 존재. 29 파일 (profiles × 6, templates/skeleton × 20, bin × 2).
- **`skills/` 루트 디렉토리 신설** — ha-init / ha-design / ha-plan / ha-build / ha-verify / ha-review / ha-deepinit 7개 + `_ha_shared` 공용 유틸. 15 파일.
- 소스 이관으로 git 이력에 모든 스킬 변경이 추적됨.

### Added — 회귀 방지 테스트 (+41)

- `backend/tests/orchestrator/test_skeleton_assembler.py` +9 — find_placeholders 단위 테스트 (HTML 태그 제외 / 백틱 인라인 제외 / 라인 번호 보존 등).
- `backend/tests/skills/test_harness_integrity.py` +9 — A5 게이트 회귀 방지.
- `backend/tests/skills/test_ha_review_distribution.py` +13 — A6 분포 게이트 회귀 (python/JS 양쪽 + monorepo).
- `tests/install/test_install_snapshot.sh` — B8 install 시나리오 12 assertion (fresh / re-run / source-modified / dry-run).

### Added — 포트폴리오 수준 문서

- **`docs/ARCHITECTURE.md` 신규** (406 lines) — 전체 구조 ASCII 다이어그램, 프로파일 시스템 설계 의도, skeleton 20 섹션 ID 규약, state machine, 스킬 ↔ 에이전트 매핑, 품질 게이트 8개 상세, 설계 결정 D1-D6 요약, 확장 방법.
- **`CONTRIBUTING.md` 신규** — 프로파일/LESSON/게이트/스킬 추가 가이드, PR 체크리스트, 커밋 메시지 컨벤션.
- **`CHANGELOG.md` 신규** (이 파일).

### Changed — 프로파일 강화

- **`_base.md` §10 "설정 중앙화" 신설** — "하드코딩 상수 3개 이상이면 중앙화" 공통 원칙 + 비밀값 env 전용. 기존 §10 은 §11 (2대 절대 원칙) 로 이동.
- **`python-cli.md`** — `core/config.py` 또는 `[tool.<name>]` 구체화 섹션 추가. `lessons_applied` 에 LESSON-010/012 외 018/019/020 추가.
- **`fastapi.md`** — `pydantic-settings BaseSettings` 구체화 섹션 + LESSON-018 안전 예시 (`(1.0, 2.0)` + `for delay in ...:` 소비 루프). `lessons_applied` 확장.

### Changed — 스킬 강화

- **`/ha-verify/SKILL.md`** — "1.5. skeleton 정합성 게이트" 단계 삽입 (toolchain 실행 전).
- **`/ha-plan/SKILL.md`** — "테스트 태스크 동반" 원칙 강화 (구현 1 = 테스트 최소 1, I/O 경계 2+).
- **`/ha-review/run.py`** — ai-slop 정규식 7번째 패턴 (LESSON-018 dead 상수) + `_check_test_distribution()` 함수 + 프로파일별 분리 집계.

### Changed — README 전면 재작성 (709 → 293 lines)

- **30초 사용법 섹션** 추가 — Hook + Install + 파이프라인 순차 사용 한눈에
- **파이프라인 ASCII 다이어그램**
- **핵심 개념 3개** — 프로파일 / Skeleton / Shared Lessons
- **비교 테이블** — Cursor / Copilot / Claude Code / aider 대비
- **품질 게이트 8개** 정리 + **에이전트 7개** 매핑
- **한계 + Roadmap** 명시
- **v1 레거시** (`/my-*` 12종) 섹션 축소

### Fixed

- **하드코딩된 개인 로컬 경로 제거** (CRITICAL) — `skills/_ha_shared/utils.py` 의 `Path("C:/Users/juwon/OneDrive/Desktop/agent")` fallback 을 `__file__` 기반 자동 탐지 + env 필수 에러로 전환. 공개 포트폴리오 가능 상태 확보.
- **harness CLI `_check_placeholders` 라인 번호 왜곡** (HIGH) — 코드 블록을 빈 문자열로 치환해 placeholder 보고 라인이 최대 20줄 밀리는 문제. `"\n" * count` 로 개행 보존.
- **placeholder false positive 2건** (2차 E2E 발견) — HTML/SVG 태그 85개 (`<div>`, `<pre>` 등) + 백틱 인라인 템플릿 예시 (`` `<pkg>` ``) 제외.
- **` ```filesystem ` 블록 WARN → opt-in** — 블록 없으면 silent pass. 모든 프로젝트에서 발생하던 noise 제거.
- **`install.sh` `__pycache__/ + *.pyc` 제외** — 런타임 캐시 복사 방지.
- **ruff pre-existing 경고** — `harness/bin/harness` F541 + SIM102, `ha-review/run.py` F541 + I001 정리.
- **README pytest 카운트** — 327 → 356 (+12 install).
- **테스트 카운트 정확성** — SIM300 Yoda condition + F401 unused import 정리.

### Internal — 검증 지표

- **backend pytest**: 327 → **359** (+32)
- **install snapshot**: 0 → **12** (bash assertion)
- **harness validate**: 27 files, 0 errors, 0 warnings
- **ruff**: all clean
- **ui-assistant 2차 E2E** (backend fastapi + frontend react-vite): 초기 4 errors → **0 errors, 0 warnings**

### Meta

- 1차 E2E (code-hijack, Python CLI) 학습 → v2 로 직접 반영 완료
- 2차 E2E (ui-assistant, fastapi + react-vite 모노레포) 실전 검증에서 false positive 2건 발견 → 즉시 수정
- `/plan-eng-review` 를 이 업그레이드 계획에 적용 → HIGH 1 + MEDIUM 4 + LOW 3 발견 → 수정 후 진행

**커밋 10개**:
- `9531f4c` docs: README + CLAUDE + TODOS + SETUP + design doc 업데이트 (Phase 3 반영)
- `caaebf9` docs(lessons): LESSON-018/019/020 추가 — code-hijack 1차 E2E 학습 반영
- `715f585` feat(skeleton): find_placeholders 유틸 추가 — A5 정합성 게이트 지원
- `d06c037` feat(install): B8 단일 명령 설치 + ~/.claude 소스 레포 이관
- `19e6a86` test: C — A5/A6/B8 회귀 방지 테스트 29 + 12
- `03f3b51` fix: 리뷰 후속 — 하드코딩 경로 제거 + CI 안전 + pycache 필터
- `1dc7c7e` docs: B1 README 전면 재작성 + B2 ARCHITECTURE.md 신규
- `273fdb5` fix(integrity): placeholder 정규식 false positive 2건 차단 — 2차 E2E 발견
- `e9ab925` fix(integrity): ```filesystem 블록을 opt-in 으로 전환

---

## [0.2.x] — 2026-04-02 ~ 04-16 — HarnessAI v2 재설계

### Added — v2 프로파일 시스템

- `~/.claude/harness/profiles/` 에 프로파일 5개 (fastapi, react-vite, python-cli, python-lib, claude-skill) + `_base.md` 공통 원칙 + `_registry.yaml` 감지 규칙.
- 20개 표준 skeleton 섹션 ID 체계 (번호 기반 → ID 기반 전환).
- `profile_loader.py` (감지 + 상속), `skeleton_assembler.py` (조각 조립), `plan_manager.py` (상태 전이).
- `docs/harness-plan.md` 단일 파일 + YAML frontmatter 상태 관리 (init → designed → planned → building → built → verified → reviewed → shipped).

### Added — /ha-* 스킬 7종

- `/ha-init` 스택 자동감지 + 인터뷰 → harness-plan.md + 빈 skeleton.md
- `/ha-design` Architect+Designer 역할 (협의 최대 3회)
- `/ha-plan` Orchestrator 역할 → tasks.md 생성
- `/ha-build` Coder 역할 [sonnet] + `--parallel` ultrawork 패턴
- `/ha-verify` 프로파일 toolchain (test/lint/type) [sonnet]
- `/ha-review` 보안 훅 6 + LESSON + ai-slop (7번째 훅) 종합 리뷰
- `/ha-deepinit` 기존 코드베이스 → hierarchical AGENTS.md

### Added — LESSON 시스템

- `backend/docs/shared-lessons.md` 에 LESSON-001 ~ LESSON-017 (17개).
- 프로파일의 `lessons_applied` 필드로 강제 적용 대상 지정.

### Added — 품질 게이트 (v2 기반)

- `SecurityHooks.from_profile()` — 프로파일 whitelist 동적 주입.
- ai-slop 감지 6패턴 (장황한 docstring, 의미 없는 try/except, TODO/FIXME, unused 함수, 임시 pass).

### Changed

- agents/\*/CLAUDE.md 27개 섹션 번호 → ID 참조 전환.
- `runner.py::build_context(use_section_ids=True)` 활성화.
- backend pytest: 248 → 327 (+79).

---

## [0.1.x] — 2026-03-16 ~ 04-01 — 초기 구현

### Added

- Director/Worker 구조 (후에 재설계로 폐기).
- 7개 에이전트 (Architect/Designer/Orchestrator/Backend Coder/Frontend Coder/Reviewer/QA).
- `/my-*` 스킬 12종 (fastapi/nextjs/react-native/electron 하드코딩).
- FastAPI + WebSocket 대시보드 (포트 3002).
- `agents.yaml` 설정 (provider, model, timeout, on_timeout).
- Claude CLI subprocess provider (향후 Gemini/local 교체 가능 구조).

---

**참고**:
- [README.md](README.md) — 사용자 관점 소개
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 시스템 구조 상세
- [CONTRIBUTING.md](CONTRIBUTING.md) — 기여 가이드
