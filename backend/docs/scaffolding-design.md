# 스캐폴딩 흡수 설계 — T-000 결정론 부트스트랩 + 스텁 스탬퍼 (v0.20.0)

> 2026-07-12. 조사 근거: Plop/Hygen(마이크로-제너레이터), Projen(생성 파일=산출물),
> Copier(진화형 템플릿), shadcn CLI v4, arXiv 2603.05344(scaffolding vs harness 분리).
> 원칙: **결정론으로 처리 가능한 구조는 LLM 에게 맡기지 않는다.**
> 목표: "test/lint 통과해도 앱이 안 뜨는" 산출물의 주 발생원(LLM 손작성 보일러플레이트) 제거
> — feedback_runtime_breakage_priority 직결.

## 채택 범위

| Phase | 내용 | 이번 구현 |
|---|---|---|
| A | `toolchain.scaffold` + T-000 결정론 부트스트랩 | ✅ |
| B | declared_files 스텁 스탬퍼 + 스텁 미구현 게이트 | ✅ |
| C | Projen 식 설정파일 anti-tamper (advisory) | 후속 (설계만 §7) |
| D | shadcn CLI 통합 (UI 프리미티브 LLM 작성 금지) | 후속 (설계만 §8) |

## 1. Phase A — 프로파일 스키마

`toolchain.scaffold: str | null` (optional). 비대화(non-interactive) 스캐폴드 명령.
**계약: 명령은 반드시 cwd(`.`) 를 대상으로 해야 한다** (샌드박스 실행 전제, §3).

```yaml
# nextjs.md — create-next-app v16 문서 검증 완료 (nextjs.org/docs/app/api-reference/cli/create-next-app)
toolchain:
  scaffold: >-
    pnpm create next-app@16 . --ts --tailwind --eslint --app --no-src-dir
    --import-alias "@/*" --use-pnpm --skip-install --disable-git --no-agents-md --yes
# react-vite.md — create-vite --no-interactive (vite.dev/guide + GH discussion 20846)
toolchain:
  scaffold: "pnpm create vite . --template react-ts --no-interactive"
```

플래그 결정 근거:
- `--no-agents-md`: 기본값이 AGENTS.md+CLAUDE.md 생성 — HarnessAI 프롬프트 체계와 충돌하므로 반드시 끔.
- `--disable-git` / `--skip-install`: git baseline 은 ha-init 소유, install 은 scaffold 서브커맨드가 target 에서 별도 실행 (§3).
- `--no-src-dir`: 프로파일 file_structure 가 app/ 루트 + src/(비라우트 코드) 구조.
- 버전 핀: next 는 `@16` (major 핀 — @latest 드리프트 방지, 문서 검증한 버전). create-vite 는
  현행 major 미검증이라 핀 없이 시작 — 드리프트 발생 시 핀 추가.
- **이번 구현은 nextjs + react-vite 2개만.** fastapi 는 공식 스캐폴더 부재로 null 유지 (정직).
  나머지 프로파일은 후속 (flutter create / nest new / uv init 등).

loader: `Toolchain.scaffold: str | None = None` (profile_loader.py:52 Toolchain dataclass)
+ `_dict_to_profile` 의 `tc.get("scaffold")`. `harness validate` 는 필수 키만 검사하므로
변경 불필요 (harness:299 — install/test/lint 만 필수).

## 2. Phase A — T-000 주입 (ha-plan cmd_commit)

- 시점: agent-mismatch + schema 검증 통과 후, tasks.md 쓰기 전. `args.tasks_content` 에
  주입해 tasks.md 와 skeleton §태스크 분해 sync 양쪽에 동일 반영.
- 조건 (전부 만족 시 주입):
  1. 활성 프로파일 중 `toolchain.scaffold` 보유 프로파일 존재
  2. 해당 프로파일의 `detect` 가 그 profile path 에서 **불일치** (= 아직 부트스트랩 안 됨.
     `_matches_detect` 재사용 — deepinit 기존 코드베이스 멱등성)
  3. tasks_content 에 T-000 행이 이미 없음 (LLM 이 넣었으면 중복 주입 금지)
- 주입 행 (첫 태스크 표의 헤더 구분행 직후):
  `| T-000 | scaffold | - | 결정론 스캐폴드 부트스트랩 (<profile ids>) | 대기 |`
- `T-000` 은 `^T-\d{3}$` 계약 (tasks_schema.py:30) 을 만족하고 `tid_num=0` 으로
  select_ready_tasks 큐 최우선 — depends_on 컬럼 전면 수정 불필요 (§4 선행 게이트가 보완).
- `_validate_agent_mappings`: `scaffold` 는 예약 의사(pseudo) 에이전트 — agents.yaml 대조 면제.
  (예약어 상수 `SCAFFOLD_AGENT = "scaffold"` — ha-plan/ha-build 공용, _ha_shared/utils.py)
- SKILL.md: "T-000/scaffold 에이전트는 예약 — run.py 가 자동 주입, LLM 은 생성하지 말 것" 명시.

## 3. Phase A — 실행 (ha-build `scaffold` 서브커맨드)

`python run.py scaffold --task T-000` — prepare 가 in-progress 마킹한 후 호출.
Agent 위임 없음 (결정론 스텝 — SKILL.md 에 scaffold 분기 명시).

프로파일별 (toolchain.scaffold 보유 + detect 불일치인 것만):
1. `target = project / profile_path` (mkdir parents 허용)
2. **샌드박스 실행**: `tempfile.mkdtemp(prefix="ha-scaffold-")` (시스템 temp — 프로젝트 밖,
   untracked 스캔 오염 방지) 에서 `subprocess.run(cmd, shell=True, cwd=sandbox, timeout=600)`.
   shell=True 근거: toolchain gate 와 동일 (프로파일 frontmatter = 레포 내 신뢰 소스).
   rc≠0 → 즉시 FAIL (네트워크 부재 등 — fallback 없음, fail fast).
3. **무덮어쓰기 병합**: 샌드박스 → target. 파일이 target 에 이미 존재하면 **절대 덮지 않고**
   skipped 목록에 기록. 디렉토리는 재귀 병합. `.git`/`node_modules` 는 이동 제외.
   → 제너레이터별 "비어있지 않은 디렉토리 거부" 동작 차이를 전부 우회 + 기존 파일 보호 불변식.
4. `toolchain.install` 을 target 에서 실행 (timeout 900). rc≠0 → FAIL.
5. 종료 후 `detect` 재평가 — 불일치면 FAIL ("스캐폴드 산출물이 profile detect 를 만족하지 않음").
6. finally: 샌드박스 제거 (shutil.rmtree, ignore_errors).

출력 JSON: `{profiles: [{id, path, scaffolded, moved, skipped[], install_ok}], next: "complete --task T-000 --status done --skip-toolchain"}`

완료: `complete --task T-000 --status done --skip-toolchain`
- **--skip-toolchain 이 정당한 이유**: 갓 스캐폴드된 앱은 test 스크립트가 없어 LESSON-021
  게이트가 항상 실패 — 스캐폴드 직후의 test 부재는 결함이 아님 (T-001+ 부터 정상 게이트).
- **security gate 는 유지**: untracked_pseudo_diff 가 스캐폴드 산출물(package.json 의존성 등)을
  whitelist 훅으로 검사 — create-next-app 산출 의존성은 nextjs whitelist 로 커버 확인 완료.
  (node_modules/.next 는 _UNTRACKED_SKIP_SEGMENTS 제외, 락파일은 200KB 상한 자동 제외)

## 4. Phase A — 선행 게이트 (ha-build prepare)

tasks.md 에 미해결(status ∉ resolved) scaffold 태스크가 있는데 `--task` 대상에 없으면 BLOCK:
"T-000 부트스트랩 선행 필요". 우회: `--skip-scaffold-gate` (기존 게이트 플래그 관례 동일).
prepare 의 scaffold 태스크 출력: `agent_prompt`/`guideline_paths` 대신
`scaffold: true` + `scaffold_commands: [{profile, path, command}]`. 스탬퍼(§5) 미적용.

## 5. Phase B — 스텁 스탬퍼 (ha-build prepare)

reentry 블록(run.py:324-352) 직후, **비-reentry·비-scaffold** 태스크의 declared_files 중
부재 파일을 스텁으로 선생성:
- 제외 토큰: `/` 로 끝남(디렉토리), `*`/`?` 포함(글롭), 주석 불가 확장자(.json 등 — 미생성,
  `unstamped` 로 보고).
- 스텁 내용 = 주석 1줄: `HARNESS-STUB T-XXX: ha-build prepare 선생성 스텁 — 구현 시 이 줄 제거`
  (확장자별 주석 문법: py/yml/sh→`#`, ts/tsx/js/jsx/kt/swift/dart/go/rs/java→`//`,
  css→`/* */`, md/html→`<!-- -->`, sql→`--`)
- 부모 디렉토리 자동 생성. OSError → WARN 후 계속 (in-progress 마킹 실패 처리와 동일 패턴).
- 출력: `stamped_files` / `unstamped` 를 태스크 JSON 에 추가. reentry 시엔 스탬프하지 않고
  기존 파일 중 스텁 마커 잔존 파일을 `stub_files` 로 보고 (부분복구 판단 보조 — "존재하지만 미구현").
- opt-out: `prepare --no-stamp`.

효과: 경로/네이밍/파일 누락이 프롬프트 준수 문제에서 **물리적 불가능**으로 격상.
LLM 은 채우기만 한다 (Plop 원리의 결정론 이식 — 단 v1 은 확장자 기반 미니 스텁.
프로파일별 리치 템플릿(harness/templates/code/)은 후속).

## 6. Phase B — 스텁 미구현 게이트 (ha-build complete)

`--status done` 시 toolchain 게이트 앞에서: 해당 태스크 declared_files 중 실존 파일의
**첫 3줄**에 `HARNESS-STUB` 마커가 남아 있으면 BLOCK ("스텁 미구현 잔존: <목록>").
우회 플래그 없음 — 조치는 구현 완료 또는 (스펙상 불필요해진 파일이면) 삭제.
Projen 의 anti-tamper 를 뒤집은 형태: "생성물 손대지 마라" 가 아니라 "스텁은 반드시 손대라".

## 7. Phase C (후속) — 설정파일 anti-tamper

T-000 산출 설정 파일(next.config.ts 등) 해시를 plan frontmatter 에 기록,
ha-verify 가 손편집 감지 시 advisory WARN ("변경은 profile/skeleton 경유 권장").
skeleton drift 게이트의 코드판. 이번 스코프 제외 — 수요 확인 후.

## 8. Phase D (후속) — shadcn CLI v4

nextjs/react-vite 에서 UI 프리미티브(Button/Dialog/Toast)는 LLM 작성 금지 →
`npx shadcn add`. whitelist 의 `@radix-ui/` prefix 기존 커버. components.json 세팅이
T-000 과 엮여야 해서(shadcn init) Phase A 안정화 후.

## 9. 변경 파일 전수

| 파일 | 변경 |
|---|---|
| backend/src/orchestrator/profile_loader.py | Toolchain.scaffold 필드 + 파싱 |
| skills/_ha_shared/utils.py | SCAFFOLD_AGENT 상수 |
| skills/ha-plan/run.py | T-000 주입 + scaffold 에이전트 mismatch 면제 |
| skills/ha-plan/SKILL.md | T-000 예약 규칙 |
| skills/ha-build/run.py | prepare scaffold 분기·선행게이트·스탬퍼 / scaffold 서브커맨드 / complete 스텁 게이트 |
| skills/ha-build/SKILL.md | scaffold 흐름 + 스텁 지시 (Agent prompt 템플릿) |
| harness/profiles/nextjs.md, react-vite.md | toolchain.scaffold |
| backend/docs/GATES.md | 신규 게이트 3 등재 (T-000 선행 BLOCK / 스텁 미구현 BLOCK / scaffold complete --skip-toolchain 특례) |
| backend/tests/skills/test_ha_scaffold_bootstrap.py | 신규 (주입/면제/서브커맨드/병합/멱등) |
| backend/tests/skills/test_ha_stub_stamper.py | 신규 (스탬프/제외/reentry/게이트) |
| backend/tests/orchestrator/test_profile_loader*.py | scaffold 필드 회귀 |
| 미러 (~/.claude/skills, ~/.claude/harness) | cp 동기 + harness drift 0 |

## 10. 리스크와 대응

- **네트워크 의존**: scaffold rc≠0 → 즉시 FAIL + 명확한 메시지 (fallback 없음).
- **@latest 드리프트**: next 는 @16 핀. 산출물 검증은 detect 재평가(§3-5)가 최소 방어.
- **제너레이터 산출 ↔ file_structure 규약 차이**: T-000 은 부트스트랩만 담당,
  규약 구조(src/containers 등)는 T-001+ 스텁 스탬퍼가 물리적으로 강제 — 충돌 없음.
- **Windows**: shell=True + pnpm .cmd 래퍼 → shell 경유로 해소. 샌드박스는 동일 드라이브
  (%TEMP% = C:) 라 shutil.move 저비용. cp949 → run.py 들 기존 UTF-8 reconfigure 상속.
- **스텁 lint 통과**: 주석 1줄 파일은 eslint/ruff/tsc 통과 (unused import 없음).
