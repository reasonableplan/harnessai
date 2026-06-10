# Skeleton Fragment 작성 가이드 (단일 진실원천)

> `_` prefix 파일은 fragment 가 아니라 메타 문서 — assembler/테스트가 제외한다.
> 이 가이드를 어기면 깨지는 것들이 코드에 박혀 있다 (각 항목에 명시).

## 1. 3중 제목 동기 (강제 — 테스트가 고정)

다음 셋이 **토씨까지** 일치해야 한다. `test_fragment_title_sync` 가 검증한다.

1. frontmatter `name:` 필드
2. 본문 헤딩 `## {{section_number}}. <제목>`
3. `backend/src/orchestrator/context.py` 의 `SECTION_TITLES[id]`

어긋나면: 섹션 추출(extract_section_by_id) / consistency checker / 섹션 hash /
역방향 contract 검증이 해당 섹션을 **조용히 못 본다** (2026-06-10 environments,
error_ux 에서 실제 발생).

## 2. Placeholder 컨벤션

| 용도 | 표기 | 비고 |
|------|------|------|
| 일반 placeholder | `<예: ...>` 또는 `<설명>` | ha-design 의 `<...>` 잔재 카운트 대상 |
| HITL(LOCKED) 영역 | `<AI 채움>` / `<기능 1>` 등 uppercase/한국어 | assembler `_ANGLE_PLACEHOLDER_RE` 는 lowercase snake_case 만 잡으므로 hook 통과 |
| 미작성 마커 | `_미작성_` / `_미정_` | ha-design `_PLACEHOLDER_RE` 대상 |

실값처럼 보이는 예시는 반드시 `<예: ...>` 마커로 — 마커 없는 실값은
ha-design 이 placeholder 인지 못 하고 그대로 남긴다 (HabitFlow 잔재 사고의 원인).

## 3. AI 후보 표 (LOCKED fragments)

`requirements` / `user_journey` 의 AI 제안 후보 표는 **3행 고정** —
런타임 `/ha-design` 이 후보 3개를 생성한다. 행 수를 바꾸면 placeholder
잔재 또는 후보 누락이 생긴다 (스킬과 fragment 를 같이 바꿀 것).

## 4. Load-bearing 표기 (파서가 읽는 형식)

| 표기 | 위치 | 의존 코드 |
|------|------|----------|
| **`METHOD /path`** (backtick+bold) | interface.http 엔드포인트 | ha-review 역방향 contract 검증 |
| `## {{section_number}}. <제목>` | 모든 fragment 헤딩 | skeleton_assembler 번호 치환 + SKELETON_HEADING_RE |
| Phase 테이블 5컬럼 (ID/에이전트/의존성/설명/상태) | tasks | `_TASK_ROW_RE` 파서 |
| `<!-- HUMAN-LOCKED:<id> -->` ... `<!-- /HUMAN-LOCKED:<id> -->` | LOCKED 3종 | ha-design 세션 재개 감지 |
| `<!-- AI-WRITABLE:... -->` ... `<!-- /AI-WRITABLE -->` | LOCKED 후보 영역 | ha-design 후보 작성 위치 |
| `Given <전제> / When <행동> / Then <결과>` | requirements 수용 기준 | ha-design Step D 작성 + (예정) ha-smoke 체크리스트 파서 |

## 5. 스택 중립성

fragment 는 `required_when` 조건을 만족하는 **모든 프로파일**에 활성된다.
특정 스택 규칙(CVA/Tailwind, Riverpod 등)을 본문에 나열하지 말 것 —
스택별 규칙은 `guidelines/<profile>/` 가 단일 진실원천. fragment 에는
"프로파일 guidelines 따름" 위임 + 예시 1줄까지만.

## 6. 신규 fragment 추가 절차

1. `<id>.md` 작성 (frontmatter: id / name / required_when / description)
2. `context.py` SECTION_TITLES 에 같은 id+name 추가
3. `pytest tests/orchestrator/test_fragment_title_sync.py` 통과 확인
4. 필요 시 ha-init SKILL.md 의 프로파일 트리 / capability atom 갱신
