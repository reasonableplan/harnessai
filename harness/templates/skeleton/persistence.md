---
id: persistence
name: 저장소 / 스키마
required_when: has.storage
description: 저장소 타입 선택 근거, 동시성 제어, 파일 저장, 백업/복구. 스키마/ERD/마이그레이션은 data_model 이 단일 소스.
decision_points:
  - id: concurrency
    ask: "같은 데이터를 동시에 수정할 때 충돌을 어떻게 다루나요?"
    detect: [동시, 충돌, 락, lock, 낙관적, 비관적, version, 단일 쓰레드, WAL, 마지막 우선]
    hint: "웹/다중 사용자면 낙관적 락(version 컬럼) 흔함; 단일 사용자 CLI면 '없음'으로 확정"
---

## {{section_number}}. 저장소 / 스키마

### 저장소 타입
<프로젝트에서 사용하는 영속 저장 수단>
- 예: PostgreSQL + 마이그레이션 도구 / SQLite + expo-sqlite / JSON 파일 / Redis / 파일 시스템
- 선택 근거: <왜 이 저장소인가 — /ha-redesign 의 보존/번복 판단 기준>

> ERD / 컬럼 명세 / 관계 / 인덱스 / 마이그레이션 정책은 `data_model` 섹션이 단일 소스 —
> 이 섹션에 중복 작성하지 않는다.

### 동시성 제어
- 동시 수정 충돌 처리: `<낙관적 락(version 컬럼) / 비관적 락 / 단일 쓰레드 전제 / 없음(단일 사용자)>`

### 파일 저장 (DB 대신 파일 기반일 때)
- 위치: `<경로 — platformdirs.user_data_dir 등 권장>`
- 포맷: `<JSON / TOML / SQLite / CSV / Parquet>`
- 동시성: `<mutex / WAL / 단일 쓰레드 전제>`

### 백업 / 복구 (해당 시)
- 백업 주기
- 복구 절차

> 작성 가이드:
> - 스키마 / ERD / 인덱스 / 마이그레이션은 `data_model` 섹션에 작성 — 여기 중복 금지
> - 구체 모델 예시 코드는 프로파일 본문 참조 (SQLModel/Drizzle/Prisma 등)
