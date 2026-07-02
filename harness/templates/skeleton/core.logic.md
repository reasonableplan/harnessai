---
id: core.logic
name: 도메인 로직
required_when: always
description: 핵심 비즈니스 규칙, 알고리즘, 순수 함수 vs I/O 분리
---

## {{section_number}}. 도메인 로직

### 핵심 비즈니스 규칙
번호 붙은 규칙 목록:
1. <예: "완료 기록은 `completed_date`가 오늘 이전일 수 없다">
2. <예: "습관 삭제는 소프트 딜리트 — is_active=false, 데이터 보존">

### 알고리즘
각 핵심 알고리즘에 대해:

#### `<알고리즘 이름>`
- **입력**: `<type>`
- **출력**: `<type>`
- **전제조건**: <precondition>
- **사후조건**: <postcondition>
- **복잡도**: `<O(n)>`

**의사 코드**:
```
<pseudocode>
```

### 순수 함수 vs I/O 분리

**pure (core/)** — I/O 없음, 테스트 쉬움:
- `calculate_streak(completions: List[Date], today: Date) -> int`
- `validate_email(email: str) -> bool`

**impure (io/)** — DB/네트워크/파일:
- `save_habit(habit: Habit) -> None`  [DB]
- `fetch_user(id: int) -> User`       [DB]
- `send_notification(...) -> None`    [HTTP]

### 에지 케이스 목록
- <예: 빈 완료 기록 → streak = 0>
- <예: 미래 날짜 요청 → ValidationError>
- <예: 음수 나이 → ValidationError>

### 테스트 전략
> `test_strategy` 섹션이 활성인 프로젝트는 그쪽이 우선 — 여기는 core/ 모듈 원칙만.
- **단위 테스트**: pure 함수는 property-based test (hypothesis/fast-check) 권장
- **통합 테스트**: impure 함수는 실제 DB/파일로
- **커버리지 목표**: core/ 모듈 ≥ 90%, io/ 모듈 ≥ 70%

> 작성 가이드:
> - 비즈니스 규칙은 "`<조건>`이면 `<결과>`" 형식
> - 알고리즘은 의사 코드로 — 실제 언어 코드는 구현 단계에서
> - 순수/비순수 분리를 파일 레벨로 명시 (core/ vs io/)
