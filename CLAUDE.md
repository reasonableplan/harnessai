# CLAUDE.md — HarnessAI

## 핵심 원칙: 현업전문가 수준, 느려도 완벽하게

**코드 품질 기준: 현업 시니어 엔지니어가 프로덕션에 배포할 수 있는 수준.**
- 쓰레기 코드(dead code, 임시 핵, 의미 없는 추상화) 일절 금지
- 효율적이고 효과적인 코드 — 불필요한 연산, 중복, 과도한 할당 없이
- 모든 코드는 세밀하게 점검 — "대충 돌아가면 됨"은 이 프로젝트에서 허용하지 않음

속도보다 정확성. 코드를 한 줄 쓸 때마다 "이게 틀릴 수 있는 모든 경우"를 먼저 생각한다.
빠르게 만들고 나중에 고치는 방식은 이 프로젝트에서 금지한다.

---

## 코드 작성 규칙

### 1. 테스트 먼저, 코드 나중
- 새 함수/모듈 작성 시 **테스트를 먼저 작성**하고, 테스트가 실패하는 것을 확인한 후 구현
- 테스트 없는 코드는 완성이 아님
- mock 기반 테스트만으로는 부족 — 핵심 로직은 실제 동작을 검증하는 테스트 필요

### 2. 한 번에 완벽하게
- 수정할 때 관련된 **모든 파일**을 함께 수정 (하나 고치고 다른 곳 깨지는 일 방지)
- 인터페이스 변경 시: 타입 → 구현 → mock → 테스트 → 호출처 **전부** 한 번에
- 새 MESSAGE_TYPE 추가 시: types → publisher → subscriber → event-mapper → 테스트 전부

### 3. 외부 API 호출 체크리스트
모든 Claude API / GitHub API 호출 시 반드시 확인:
- [ ] 타임아웃 설정 있는가? (`agents.yaml`의 `timeout_seconds`)
- [ ] 응답이 비어있을 수 있는가? → `output.strip()` 가드
- [ ] 에러 시 에스컬레이션 로직 있는가? (`on_timeout: escalate`)
- [ ] subprocess 실패 → `RunResult.success=False` 로 처리 (throw 아님)

### 4. 비동기 안전성
- `asyncio.create_task()` → 반드시 참조 유지 (`_background_tasks.add(task)`)
- task done callback → `_background_tasks.discard(task)` + exception 로깅
- `asyncio.gather(*coros, return_exceptions=True)` — 한 코루틴 실패가 나머지 취소 금지
- `run_in_executor` → EOFError/KeyboardInterrupt 처리 필수

### 5. 에러 처리
- `except Exception: pass` (빈 catch) 금지 — 최소한 `logger.error` 필수
- "존재 확인" 패턴의 catch → FileNotFoundError/None만 삼키고 나머지는 re-raise
- 파일 쓰기 (`write_text`) → `OSError` 처리 + re-raise
- JSON 로드 (`json.load`) → `JSONDecodeError` 처리 + fallback 또는 None 반환
- shutdown/cleanup 함수 → 멱등성 가드

### 6. 타입 안전성
- `Any` 캐스트 최소화 — 불가피할 때만, `# type: ignore` 사유 주석 필수
- `RunResult | None` 반환 함수 → 호출처에서 None 체크 필수
- Pydantic 모델 → `model_validator` 로 cross-field 검증
- WS/API payload → 알려진 필드만 `.get()`, raw spread 금지

### 7. 보안
- CLI 인자에 토큰/시크릿 전달 금지 → 환경변수만
- 에이전트 프롬프트에 사용자 입력 → XML 딜리미터 (`<task>`, `<review_feedback>`)
- HTTP 500 응답에 내부 에러 메시지 미포함
- `_safe_filename()` — 파일명에 path traversal 문자 제거 필수

### 8. 환경/설정
- 환경변수 추가/변경 시 → `agents.yaml` + `.env.example` + `MEMORY.md` **3곳 동기화**
- `agents.yaml` 변경 시 → `config.py` Pydantic 모델도 같이 확인
- 정규식에서 `\n` → `\r?\n` (CRLF 호환)
- **v2 프로파일 변경 시** → `~/.claude/harness/profiles/` + `harness validate` 로 스키마 확인
- **HARNESS_AI_HOME** env (`/ha-*` 스킬이 v2 모듈 import 시 사용, 기본: 이 레포 절대 경로)

### 9. Orchestra / 대시보드 연동
- 에이전트 실행은 반드시 `Orchestra` 경유 — `AgentRunner.run()` 직접 호출 금지
  (SecurityHooks + Reviewer 검증이 Orchestra에만 있음)
- IMPLEMENTING phase 명령 → `orchestra.implement_with_retry()` 사용
- 새 emit 이벤트 추가 시 → `event_mapper.py` + 테스트 **동시** 업데이트

---

## 코드 완료 전 자가 검증 체크리스트

코드를 "완료"라고 말하기 전에 반드시 확인:

```
[ ] 전체 테스트 통과 (cd backend && uv run pytest tests/)
[ ] 린트 0 errors (uv run ruff check src/)
[ ] 타입 체크 0 errors (uv run pyright src/)
[ ] 새 함수에 테스트 작성했는가?
[ ] 인터페이스 변경 시 호출처 전부 업데이트했는가?
[ ] 에이전트 실행이 Orchestra 경유인가? (AgentRunner 직접 호출 금지)
[ ] 파일 쓰기/JSON 로드에 예외 처리 있는가?
[ ] 환경변수 변경 시 .env.example 동기화했는가?
[ ] asyncio.create_task() 참조 유지했는가?
```

---

## 프로젝트 구조 요약

- **스택**: Python 3.12 / FastAPI + WebSocket / uv / pytest / ruff / pyright
- **에이전트 실행**: Claude CLI subprocess (`claude` 명령어, provider 교체 가능)
- **테스트**: `cd backend && uv run pytest tests/ --rootdir=.`
- **린트**: `cd backend && uv run ruff check src/`
- **타입체크**: `cd backend && uv run pyright src/`
- **서버 실행**: `cd backend && uv run python -m src.main`
- **설계 문서**: `~/.gstack/projects/reasonableplan-agent-orchestration/` (office-hours 생성)

### 디렉토리 구조
```
backend/
  agents.yaml              — 에이전트 설정 (provider, model, timeout)
  agents/
    architect/CLAUDE.md    — Architect 에이전트 시스템 프롬프트
    designer/CLAUDE.md     — Designer 에이전트 시스템 프롬프트
    orchestrator/CLAUDE.md — Orchestrator 에이전트 시스템 프롬프트
    backend_coder/CLAUDE.md
    frontend_coder/CLAUDE.md
    reviewer/CLAUDE.md
    qa/CLAUDE.md
  docs/
    skeleton.md            — 실행 시 생성 (Architect+Designer 출력으로 채워짐, v2)
    harness-plan.md        — v2 파이프라인 상태 (YAML frontmatter)
    shared-lessons.md      — 과거 실수 패턴 LESSON-NNN
    GATES.md               — 게이트 전수표 (BLOCK 15 + advisory 10+)
  src/
    main.py                — FastAPI 서버 진입점 (포트 3002)
    dashboard/             — REST API + WebSocket 대시보드
      server.py            — FastAPI 앱 생성, WS 핸들러
      routes/
        command.py         — POST /api/command (에이전트 실행)
        deps.py            — 의존성 주입 (Orchestra 싱글톤)
    orchestrator/
      orchestrate.py          — Orchestra 클래스 (전체 워크플로우) + v2 assemble_skeleton_for_profiles
      pipeline_runner.py      — 인터랙티브 CLI 러너 (게이트 승인)
      runner.py               — AgentRunner (타임아웃/재시도/에스컬레이션)
      state.py                — StateManager (.orchestra/ JSON 저장)
      output_parser.py        — LLM 출력 파싱 (phases, review, tasks) + 섹션 ID 추론
      security_hooks.py       — 보안 훅 6개 + from_profile (v2 프로파일 whitelist 주입)
      pipeline.py             — ValidationPipeline (lint/type/test)
      context.py              — SECTION_MAP + AGENT_SECTIONS_BY_ID + extract_section_by_id
      profile_loader.py       — v2: 프로파일 로드/상속/모노레포 감지
      skeleton_assembler.py   — v2: 조각 조립 ({{section_number}} 치환)
      plan_manager.py         — v2: harness-plan.md 상태 전이
      providers/
        base.py               — BaseProvider 추상 인터페이스
        claude_cli.py         — Claude CLI subprocess provider
  tests/
    orchestrator/             — 1038개 테스트 (E2E 통합 포함, tests/skills 포함 전체)
    dashboard/                — EventMapper 17개 테스트

## HarnessAI v2 파이프라인 (`/ha-*` 스킬)

```
/ha-init → /ha-design → /ha-plan → /ha-build (sonnet) → /ha-verify → /ha-review → /ha-smoke (advisory) → /ha-ship
        + /ha-redesign (결정 변경 propagation) + /ha-deepinit (기존 코드 → AGENTS.md) + /ha-log (worklog)
```

- 스킬 위치: `~/.claude/skills/ha-*/`
- 공유 유틸: `~/.claude/skills/_ha_shared/utils.py`
- v2 인프라: `~/.claude/harness/` (profiles, templates, bin/harness)
```

---

## 의사소통 스타일

- 한국어로 소통
- 간결하게 — 불필요한 설명 생략
- 작업 전 계획을 먼저 공유하고 확인 받기
- 확실하지 않으면 추측하지 말고 질문하기
