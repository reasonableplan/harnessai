---
id: configuration
name: 설정 / 환경변수
required_when: has.env_config
description: 환경변수, 피처 플래그, 런타임 설정
---

## {{section_number}}. 설정 / 환경변수

### 환경변수
| 이름 | 타입 | 필수 | 기본값 | 설명 |
|------|------|:---:|--------|------|
| `<NAME>` | `<type>` | ✅ | — | `<설명>` |
| `<NAME>` | `<type>` | ❌ | `<default>` | `<설명>` |

### 피처 플래그
| 플래그 | 타입 | 기본 | 의미 |
|--------|------|-----|------|
| `<FLAG_NAME>` | `bool` | `false` | <기능 on/off> |

### `.env.example` 위치
- `<경로 — 예: backend/.env.example>`

### 런타임 설정
- <런타임 시 로드하는 설정 파일 — 예: `config.toml`, `settings.py`>
- 로드 우선순위: <예: env > .env > defaults>

> 작성 가이드:
> - 시크릿(토큰/키/비밀번호)은 `.env`에만. 기본값 `-` 또는 없음.
> - 환경변수 추가/변경 시 `.env.example` 동기화 필수 (CLAUDE.md §8).
> - 피처 플래그는 기본값을 "가장 보수적"으로 (예: 새 기능은 기본 off).
