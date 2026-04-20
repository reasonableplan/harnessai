# Contributing to HarnessAI

HarnessAI 에 기여해주셔서 감사합니다. 이 문서는 기여 시 지켜야 할 원칙과 실제 워크플로우를 정리합니다.

> 상세 아키텍처는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), 코드 품질 기준은 [CLAUDE.md](CLAUDE.md) 참조.

---

## 기여 전에

1. **이슈로 제안 먼저** — PR 전에 이슈로 의도 공유. 중복 작업 방지.
2. **CLAUDE.md 의 "현업전문가 수준, 느려도 완벽하게" 원칙** 을 동의하는 기여자만. 쓰레기 코드 / 임시 해킹 / 의미 없는 추상화 허용 X.
3. **한국어 / 영어 둘 다 OK** — 기존 문서는 한국어 중심. 커밋 메시지도 한국어 가능.

---

## 개발 환경

```bash
git clone https://github.com/reasonableplan/harnessai.git
cd harnessai

# 1) 스킬 + 프로파일을 ~/.claude/ 로 설치
./install.sh                       # Windows: .\install.ps1

# 2) env 설정 (스크립트가 안내) — /ha-* 스킬이 v2 모듈을 import 할 때 참조.
#    미설정 시 스킬 실행만 실패 (backend tests/ruff/pyright 는 영향 없음).
export HARNESS_AI_HOME="$(pwd)"

# 3) backend 의존성
cd backend
uv sync

# 4) 검증
uv run pytest tests/ --rootdir=.   # 357 tests
uv run ruff check src/             # 0 errors
uv run pyright src/                # 0 errors (타입 체크)
python ../harness/bin/harness validate  # 프로파일 스키마 검증
```

**필수 도구**: Python 3.12+, uv, git. (프론트엔드 작업 시 pnpm + Node 20+.)

---

## 기여 유형별 가이드

### A. 새 프로파일 추가

예: `flutter`, `swift-ui`, `rust-axum` 등.

1. `harness/profiles/<stack>.md` 작성 — YAML frontmatter + Markdown body
2. `harness/profiles/_registry.yaml` 에 감지 규칙 추가
3. `harness/templates/skeleton/` 에 스택 특화 섹션 조각 필요 시 추가
4. `python harness/bin/harness validate` 로 스키마 통과 확인
5. (선택) `backend/docs/shared-lessons.md` 에 스택 고유 LESSON 추가 + 프로파일 `lessons_applied` 에 등록
6. `backend/tests/` 에 프로파일 단위 테스트 (감지 + 화이트리스트 적용)

**템플릿**: 기존 `harness/profiles/fastapi.md` 또는 `python-cli.md` 참고.

### B. 새 LESSON 추가

과거 실수 패턴 문서화 — 모든 미래 `/ha-review` 가 참조하게 됨.

1. `backend/docs/shared-lessons.md` 파일 끝에 `## LESSON-<NNN>: <title>` 추가
2. 구조: **문제 → 규칙 → bad/good 코드 예시 → 자동 검출 가능 여부**
3. 번호 중복 확인: 현재 021 까지 사용 중 (다음 신규 = 022)
4. 적용 대상 프로파일의 `lessons_applied` 필드에 LESSON ID 추가
5. (선택) ai-slop 정규식으로 자동 감지 가능하면 `skills/ha-review/run.py::_AI_SLOP_PATTERNS` 에 패턴 추가

### C. 새 품질 게이트 추가

예: 순환 의존성 감지, 번역 누락 검사 등.

1. 게이트 로직 구현
   - **프로젝트 로컬 검사**: `skills/ha-review/run.py` 에 `_check_*` 함수
   - **범용 CLI**: `harness/bin/harness` 에 서브커맨드
2. `backend/tests/skills/` 에 단위 테스트 (최소 7-8 케이스)
3. `skills/ha-verify/SKILL.md` 또는 `skills/ha-review/SKILL.md` 에 호출 단계 문서화
4. `docs/ARCHITECTURE.md` §6 "품질 게이트" 표에 추가

### D. 새 `/ha-*` 스킬 추가

예: `/ha-lesson` (자동 LESSON 추출), `/ha-ship` (gstack /ship wrapper).

1. `skills/<name>/SKILL.md` + `run.py` 작성 — 기존 `ha-review` 템플릿 참고
2. `skills/_ha_shared/utils.py` 의 공통 유틸 재사용
3. `backend/tests/skills/` 에 smoke 테스트 추가
4. `README.md` + `docs/ARCHITECTURE.md` §5 에 매핑 추가

---

## 코드 스타일

- **Python**: ruff + pyright strict. 기존 `src/orchestrator/` 컨벤션 따름.
- **Bash**: `set -eo pipefail` 필수. nounset 은 bash 3.2 호환성 문제로 제외.
- **PowerShell**: UTF-8 BOM 필수 (Windows PS 5.1 cp949 호환).
- **Markdown**: 한국어 내용 OK. 코드 블록 언어 명시.

핵심 원칙 (자세한 건 [CLAUDE.md](CLAUDE.md)):
- 테스트 먼저, 코드 나중
- 한 번에 완벽하게 — 인터페이스 변경 시 호출처 전부
- 빈 `except Exception: pass` 금지
- 주석 최소 — WHAT 은 코드가, WHY 만 주석

---

## PR 체크리스트

제출 전 확인:

- [ ] `cd backend && uv run pytest tests/` — 모두 통과 (현재 357개)
- [ ] `uv run ruff check src/` — 0 errors
- [ ] `uv run pyright src/` — 0 errors
- [ ] `python harness/bin/harness validate` — 0 errors
- [ ] 신규 코드에 테스트 동반 (구현 1 = 테스트 최소 1)
- [ ] `./tests/install/test_install_snapshot.sh` — install 수정 시
- [ ] README / ARCHITECTURE.md 에 영향 있으면 동기화
- [ ] CHANGELOG.md 에 Unreleased 섹션 추가

---

## 커밋 메시지

**Conventional Commits + 한국어 본문** 패턴:

```
<type>(<scope>): <한 줄 요약>

<본문 — 왜 (핵심) + 무엇이 바뀌는지>

<메타 라인 — 플랜 참조, 검증 결과, Co-Authored-By>
```

**type**: `feat` / `fix` / `docs` / `test` / `refactor` / `chore` / `perf`

**scope** 예: `install`, `integrity`, `lessons`, `skeleton`, `profile`

**예시** (실제 이번 세션 커밋):

```
fix(integrity): placeholder 정규식 false positive 2건 차단 — 2차 E2E 발견

ui-assistant 2차 E2E 실전 검증에서 <div>/<pre> HTML 태그 + 백틱 인라인
템플릿 예시 (`<pkg>` 등) 가 placeholder 로 오탐. 양쪽 프로파일 (fastapi,
react-vite) 초기 integrity 4개 false positive → 0.

검증: pytest 전수 통과 (회귀 테스트 +3 추가)
```

---

## 검증

여러 층의 자동 게이트가 있습니다:

| 레벨 | 명령 | 역할 |
|---|---|---|
| pytest | `uv run pytest tests/` | 357개 단위/통합 테스트 |
| ruff | `uv run ruff check src/` | 코드 스타일 |
| pyright | `uv run pyright src/` | 타입 체크 |
| harness validate | `python harness/bin/harness validate` | 프로파일/스킬 스키마 |
| harness integrity | `python harness/bin/harness integrity --project .` | skeleton ↔ 실재 FS 정합성 |
| install snapshot | `./tests/install/test_install_snapshot.sh` | 설치 시나리오 |

CI 는 아직 없음 (Phase 5 에서 GitHub Actions 추가 예정).

---

## 질문 / 논의

- GitHub Issues: 버그 리포트, 기능 제안, 아키텍처 논의
- 리포지토리: https://github.com/reasonableplan/harnessai

---

## License

기여물은 레포의 MIT 라이센스에 따릅니다.
