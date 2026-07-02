---
id: stack
name: 기술 스택
required_when: scale.small_or_larger
description: 런타임/프레임워크/라이브러리/빌드/테스트 도구
---

## {{section_number}}. 기술 스택

### 런타임 / 언어
- <예: Python 3.12 / Node.js 20 / Rust 1.75>

### 프레임워크 / 주요 라이브러리
- <예: FastAPI, SQLAlchemy / React 19, Vite>
- 선택 근거: <왜 이 조합인가 — /ha-redesign 의 보존/번복 판단 기준이 된다>

### 빌드 / 패키지 관리
- <예: uv / pnpm / cargo>

### 테스트
- <예: pytest + httpx / vitest / cargo test>

### 린트 / 포맷 / 타입체크
- <예: ruff + pyright / eslint + tsc>

### 허용 라이브러리 화이트리스트
> 프로파일의 `whitelist.runtime/dev` 에서 가져온다. 여기는 프로젝트 특화 추가만 명시.

**추가 허용 (프로파일 기본 + 이 목록)**:
- <패키지 이름>: `<사유>`

> 작성 가이드:
> - 프로파일 화이트리스트와 중복 나열 금지 — 오직 프로젝트 특화 추가만.
> - 각 추가는 반드시 사유 (왜 필요한가) 명시.
