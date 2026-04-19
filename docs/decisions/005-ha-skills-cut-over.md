# ADR-005: /my-\* 스킬 완전 삭제, /ha-\* 로 single cut-over

- **Status**: Accepted — Phase 4a + 4b 실행 완료 (2026-04-19)
- **Date**: 2026-04-10 (결정), 2026-04-19 (Phase 4a + 4b 실행)
- **Depends on**: [ADR-001 프로파일 기반 아키텍처](001-profile-based-architecture.md)

## Context

v1 의 `/my-*` 스킬 12종 과 v2 의 `/ha-*` 스킬 7종 이 **현재 병행** 운영 중.

### 병행 상태 분석

| 측면 | /my-* (v1) | /ha-* (v2) |
|---|---|---|
| 스택 지원 | hardcoded 4개 (fastapi/nextjs/react-native/electron) | 프로파일 기반 N개 |
| 스킬 수 | 12종 | 7종 |
| skeleton | 번호 기반 19 섹션 | ID 기반 20 섹션 |
| 상태 관리 | 없음 (호출 시점 기반) | `harness-plan.md` state machine |
| 실제 프로젝트 | HabitFlow, 금칙어게임 (완료), Personal Jira | code-hijack (완료), ui-assistant (진행) |

### 공존 비용

1. **스킬 중복 유지** — 같은 역할 (예: API 구현) 을 `/my-api` 와 `/ha-build T-<api>` 양쪽에서 관리.
2. **LESSON 적용 drift** — LESSON-018/019/020 은 v2 에만 반영. v1 프로젝트는 새 교훈 못 받음.
3. **문서 혼란** — README 에 "v1 / v2 둘 다 동작" 이라 적어도 신규 사용자 혼란.
4. **레거시 코드** — `SECTION_MAP`, `fill_skeleton_template`, `extract_section` (번호 기반) 이 test + production 양쪽에 남아 코드 복잡도 증가.

## Decision

**v2 기반 1 개 프로젝트 완주 검증 후 `/my-*` 12종 + 레거시 코드 일괄 삭제**. "Single cut-over" (점진적 deprecation 없음).

### 삭제 조건 (전제)

- ✅ v2 로 Phase 3 E2E 1차 완주 (code-hijack) — 완료
- ⏳ v2 로 Phase 3 E2E 2차 완주 (ui-assistant, monorepo) — 진행 중
- ⏳ 3개 이상 프로파일 (fastapi + react-vite + python-cli) 실전 검증

### 삭제 대상

**Phase 4 실행 시**:

| 대상 | 파일 |
|---|---|
| /my-* 스킬 12종 | `skills/my-db-design/`, `my-architect/`, `my-designer/`, `my-skeleton-check/`, `my-tasks/`, `my-db/`, `my-api/`, `my-ui/`, `my-logic/`, `my-type-check/`, `my-review/`, `my-lessons/` |
| 번호 기반 섹션 매핑 | `backend/src/orchestrator/context.py::SECTION_MAP`, `fill_skeleton_template`, `extract_section` |
| skeleton_template.md | 이미 commit `595ef88` 에서 삭제 완료 |
| Orchestra.materialize_skeleton v1 경로 | `backend/src/orchestrator/orchestrate.py` 내 레거시 fallback |
| `docs/workflow-unified.md` 등 v1 워크플로우 문서 | 아카이브 처리 |

### Evaluated alternatives

1. **점진적 deprecation (6개월 warn → 삭제)** — 리젝트. 사용자 혼자 쓰는 툴이라 "deprecation warning" 을 받을 외부 사용자 없음. 유지 비용만 증가.
2. **/my-\* 를 wrapper 로 전환 (내부는 /ha-\* 호출)** — 리젝트. 이중 인터페이스 = 버그 표면적 2배.
3. **완전 병행 유지** — 리젝트. 위 "공존 비용" 4가지 누적.
4. **Single cut-over (채택)** — 2차 E2E 완주 확인 후 한 PR 로 삭제.

## Consequences

### Positive

- **유지보수 단순화** — 스킬 1 벌, 문서 1 버전.
- **LESSON/게이트 일관 적용** — v2 가 모든 프로젝트의 기본이 됨.
- **레거시 코드 감소** — backend pytest 시간 감소 기대 (현재 359 → 추정 320 수준).
- **사용자 학습 곡선 단일화** — 신규 기여자가 두 버전 혼란 없음.

### Negative

- **기존 v1 프로젝트 (HabitFlow, 금칙어게임) 재방문 시** 이미 완료 상태라 영향 낮음. 그러나 `/my-lessons` 같은 retro 스킬 사라지면 회고 스킬 migration 필요. 대응: `/ha-deepinit` + `/ha-review` 조합으로 대체 흐름 문서화.
- **skeleton 번호 참조한 오래된 문서/메모리** 도 함께 정리 필요.
- **첫 시도 실패 시 복구 어려움** — single cut-over 는 올-오어-너싱. 대응: 삭제 PR 은 별도 브랜치에서 신중히, revert 명시.

### Neutral

- 사용자 중 1인 (reasonableplan) 만 영향 — rollout 복잡도 낮음.
- /my-* 삭제가 LESSON 시스템에는 영향 없음 (LESSON 은 shared-lessons.md 에 있고 v2 도 사용).

## Implementation

**Phase 4a** — 스킬 + 문서 정리 (2026-04-19 완료):

- [x] 2차 E2E (ui-assistant) Phase 1 완주 확인
- [x] `~/.claude/skills/my-*` 12 디렉토리 삭제 (backup: `~/.claude/.my-skills-backup-20260419-062118/`)
- [x] `README.md` "v1 (레거시)" 섹션 제거
- [x] `CHANGELOG.md` Breaking Change 섹션 기록
- [x] ADR-005 status 갱신 (Proposed → Accepted 부분)

**Phase 4b** — backend production 레거시 제거 (2026-04-19 완료):

- [x] `backend/src/orchestrator/context.py` 의 `SECTION_MAP` / `fill_skeleton_template` / `extract_section` 제거
- [x] `backend/src/orchestrator/context.py` 의 `build_context(use_section_ids=False)` 분기 제거 (기본 ID 기반)
- [x] `backend/src/orchestrator/orchestrate.py` 의 `materialize_skeleton` 템플릿 치환 경로 제거
  (`skeleton_template.md` 는 commit `595ef88` 에서 이미 삭제됨)
- [x] `backend/src/orchestrator/orchestrate.py::_extract_allowed_endpoints` 레거시 섹션 7 폴백 제거
- [x] `backend/tests/orchestrator/test_context.py` v1 테스트 삭제 (테스트 수 365 → 347)

**Phase 4b 후속** (2026-04-19 완료):

- [x] `Orchestra.materialize_skeleton_v2` + `run_pipeline_with_phases(profile_ids=...)` —
  v2 스킬 경로 (`/ha-*`) 와 동일한 profile → empty skeleton → section_id merge 계약을
  Orchestra backend 에도 적용. legacy `materialize_skeleton` 은 back-compat 용으로만 유지.
- [x] `pyright` dev 의존성 추가 + `src/` 타입 에러 14건 정리. CLAUDE.md 자가검증
  체크리스트에 `uv run pyright src/` 추가.

**참고**:
- `docs/` 디렉토리 전체가 `.gitignore` 대상이므로 `workflow-unified.md` 등 로컬 v1 문서는 공개 포트폴리오에 포함되지 않음 (아카이브 불필요).
- `install.sh` / `install.ps1` — my-\* 관련 제거 불필요 (원래 복사 대상 아님).

## References

- [ADR-001: 프로파일 기반 아키텍처](001-profile-based-architecture.md) — 이 ADR 의 전제
- [ADR-002: Skeleton 섹션 ID](002-skeleton-section-ids.md) — 번호 → ID 전환이 /my-* 의 skeleton_template.md 와 비호환
- `TODOS.md` — Phase 4 실행 항목 체크리스트
- commit `595ef88` (skeleton_template.md 삭제 — Phase 4 의 첫 단계)
