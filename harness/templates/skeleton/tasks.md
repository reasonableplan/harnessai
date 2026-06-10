---
id: tasks
name: 태스크 분해
required_when: always
description: /ha-plan이 채운다 — skeleton의 타 섹션을 읽어 구현 태스크 목록 생성
---

## {{section_number}}. 태스크 분해

> 이 섹션은 `/ha-plan` 스킬이 자동으로 채웁니다. 직접 편집하지 마세요.
> 수동 변경이 필요하면 skeleton 의 타 섹션 보완 후 `/ha-plan` 을 재실행하세요
> (이 섹션과 tasks.md 가 함께 재생성됨).

### 태스크 목록 (Phase 테이블 — 파서 고정 5컬럼, 순서 변경 금지)
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|---|---|---|---|---|
| T-001 | backend_coder | - | <한 줄 설명> | 대기 |

### 의존성 그래프
```
(ha-plan이 생성)
```

### 병렬 실행 가능 조합
(ha-plan이 생성)

### 진행 상태
- `대기` — 아직 시작 안 함
- `in-progress` — `/ha-build` 실행 중
- `done` — 구현 + toolchain 게이트 통과
- `blocked` — 스펙 미비 / 의존성 미해결 (에스컬레이션)
- `skipped` — 의도적 보류 (Phase 2+ 등 — 게이트 미통과 상태)
- `needs_rebuild` — /ha-redesign 으로 spec 변경됨 — 재구현 필요
