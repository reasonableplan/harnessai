---
id: _base
name: Base Profile
description: 모든 프로파일이 상속하는 공통 원칙. 스택과 무관하게 항상 적용.
extends: null
provides_capabilities: []
---

# Base Profile — 공통 원칙

스택이 Python이든 TypeScript든 Rust든 상관없이 **모든 HarnessAI 프로젝트**에 적용되는 규칙들.

개별 프로파일(fastapi.md, python-cli.md 등)은 이 파일을 암묵적으로 상속한다. 프로파일에서 명시적으로 override하지 않으면 여기 규칙이 그대로 적용된다.

---

## 1. 테스트

- **테스트 먼저, 코드 나중**: 실패하는 테스트를 먼저 작성하고 구현한다.
- **실제 동작 검증 > mock**: 핵심 로직은 실제 동작을 검증. mock은 외부 경계(네트워크, 시계, 랜덤)에서만.
- **테스트 없는 코드 = 미완성**: `/ha-verify`는 테스트 커버리지 없는 태스크를 통과시키지 않는다.

## 2. Git

- **원자적 커밋**: 한 커밋 = 한 논리적 변경. "수정 + 리팩터링" 섞지 않는다.
- **커밋 메시지**: 명령형(imperative). 첫 줄 72자 이내.
- **force-push 금지** (특히 main/master). 반드시 승인 후에만.
- **훅 우회 금지** (`--no-verify`). 실패하면 원인 고치고 재시도.

## 3. 에러 핸들링

- **빈 catch 금지**: `except Exception: pass`, `catch {}` 전부 금지. 최소 `logger.error`.
- **내부 에러 외부 유출 금지**: 외부 응답(HTTP/CLI stderr)엔 에러 코드만. 스택 트레이스 노출 X.
- **dev는 시끄럽게, prod는 우아하게**: 개발 중 예외는 assertion처럼 터져야 함.

## 4. 보안 (스택 무관)

- **시크릿 하드코딩 절대 금지**: 환경변수로만. `.env`는 gitignore, `.env.example`은 커밋.
- **경계에서 입력 검증**: 진입점에서 parse/validate. 내부는 신뢰.
- **로그에 시크릿 노출 금지**: 토큰, 키, 비밀번호 → 로그 라인 절대 금지.
- **path traversal 방어**: 파일명/경로 입력은 반드시 화이트리스트 검증.

## 5. 코드 품질

- **dead code 금지**: 안 쓰는 import/함수/변수는 커밋 전 제거.
- **주석 처리된 코드 금지**: git history를 쓴다.
- **TODO는 이슈 번호 + 담당자 필수**: 없는 TODO는 코드에 남길 수 없다.
- **의미 있는 이름**: `data`, `tmp`, `helper` 같은 이름 금지. 의도를 드러낸다.

## 6. 문서

- **public 함수 docstring 필수**: 한 줄이라도. WHY를 적는다 (WHAT은 코드가 말한다).
- **README.md 최신 상태**: 설치/테스트/실행 명령. 바뀔 때마다 업데이트.
- **아키텍처 결정은 `docs/skeleton.md`**: 인라인 주석 X.

## 7. 의존성

- **화이트리스트 방식**: 각 프로파일이 `whitelist.runtime`/`whitelist.dev` 선언. 외부 추가는 명시적 승인 필요.
- **버전 고정**: 락 파일에 `latest` 금지.
- **추가 전 질문**: "이 의존성 없이 할 수 있나?" 먼저 묻는다.

## 8. 타입 안전성

- **`any` / `Any` 금지**: 진짜 동적이면 이유를 주석으로 남긴다.
- **Union/Enum exhaustive 매칭**: 기본 분기(default)에서 unreachable 보장.
- **boundary에서 strong typing**: API/CLI/IPC 입출력은 Pydantic/Zod/serde로 반드시 검증.

## 9. 검증 파이프라인

모든 프로파일은 다음을 반드시 정의한다:

```yaml
toolchain:
  test:   "<테스트 명령>"
  lint:   "<린트 명령>"
  type:   "<타입체크 명령>"   # 타입 시스템 없는 언어는 null 가능
  format: "<포맷 명령>"        # 선택
```

`/ha-verify`는 test → lint → type 순서로 실행. 셋 다 통과해야 태스크 완료 인정.

## 10. 설정 중앙화

- **하드코딩 상수 3개 이상 → 중앙화**: 매직 숫자/문자열이 3군데 이상 분산되면 반드시 단일 소스로 통합한다. 프로파일이 구체화 방법 지정 (예: `core/config.py`, `pyproject.toml [tool.<name>]`, `pydantic-settings`, `vite env`).
- **비밀값은 env만**: 토큰/키/비밀번호는 절대 설정 파일에 X. 환경변수 전용. 기본값도 금지.
- **환경별 오버라이드**: `env > config file > defaults` 우선순위 유지. 리비전 달라도 동일 코드가 작동하도록.
- **하드코딩 탐지**: `/ha-review` 의 ai-slop 훅이 매직 숫자/경로/URL 리터럴 밀집도 경고. LESSON-018 (dead 상수) 과 함께 감지.

## 11. 두 가지 절대 원칙

- **One change, one PR**: 태스크 하나 = PR 하나. 스코프 확장 금지.
- **느려도 정확하게**: "대충 돌아가면 됨" 불허. 재확인, 재테스트, 재읽기.

---

## 프로파일이 override 할 수 있는 것

개별 프로파일(예: `fastapi.md`)은 이 파일의 기본값을 다음과 같이 덮어쓴다:

| Base | Override 가능 여부 |
|------|-------------------|
| 테스트 철학 (§1) | ❌ 항상 적용 |
| Git 규칙 (§2) | ❌ 항상 적용 |
| 에러 핸들링 일반론 (§3) | ⚠️ 언어별 구체화 가능 (에러 클래스 등) |
| 보안 (§4) | ❌ 항상 적용 |
| 코드 품질 일반론 (§5) | ⚠️ 언어별 구체화 가능 |
| 문서 (§6) | ⚠️ 구체 형식만 |
| 의존성 화이트리스트 (§7) | ✅ 프로파일이 정의 |
| 타입 안전성 (§8) | ⚠️ 언어별 구체화 |
| `toolchain` (§9) | ✅ 프로파일이 정의 (필수) |
| 설정 중앙화 (§10) | ⚠️ 구체화 방법만 (core/config.py, pydantic-settings, vite env 등) |
| 두 가지 원칙 (§11) | ❌ 항상 적용 |

## 프로파일이 **반드시** 정의해야 하는 것

```yaml
---
id: <프로파일 ID>
name: <사람이 읽을 이름>
extends: _base.md

components:
  - id: <컴포넌트 타입 ID>
    required: true | false
    skeleton_section: <섹션 ID>
  ...

skeleton_sections:
  required: [...]
  optional: [...]
  order:    [...]

toolchain:
  test: "..."
  lint: "..."
  type: "..."

whitelist:
  runtime: [...]
  dev:     [...]

file_structure: |
  <프로젝트 파일 구조 예시>
---

# <프로파일 이름>
<구현 원칙, 컴포넌트별 가이드, 금지 사항 등 자유 형식>
```
