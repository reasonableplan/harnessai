# HarnessAI 게이트 전수 목록 (v2 파이프라인)

> "8개 게이트" 가 아니다 — ha-review 한 단계의 훅 수(7 보안훅+ai-slop)만 센 옛 집계.
> 아래가 2026-06-10 기준 전수. **BLOCK** = run.py 가 exit≠0 으로 차단 (우회는 명시
> 플래그만), **advisory** = 경고/JSON 보고 후 진행 (LLM/사용자 판단).

## 단계별 게이트

### /ha-init · /ha-design
| 게이트 | severity | 우회 |
|---|---|---|
| consistency_violations 표시 (atom 미충족) | HITL 승인 | "의도적 모순" 선택 |
| HITL LOCKED 인터뷰 (requirements/user_journey/view.screens) | 강제 | `--ai-draft` 옵트인 (기록됨) |
| LESSON 인용 검증 (미정의 LESSON-NNN) | BLOCK | `--allow-unknown-lessons` |
| placeholder 잔재 카운트 | advisory | — |
| "> 작성 가이드" 잔재 (tasks/notes 제외) | BLOCK | — (제거가 항상 올바른 조치) |

### /ha-plan (commit)
| 게이트 | severity | 우회 |
|---|---|---|
| agent-mismatch (활성 프로파일과 안 맞는 배정) | BLOCK | `--allow-agent-mismatch` |
| tasks.md schema 검증 (5컬럼/상태값/의존성) | BLOCK | `--allow-format-drift` |
| skeleton hash 비교 | advisory | — |
| tasks/skeleton 쓰기 실패 시 전이 중단 | BLOCK | — |

### /ha-build
| 게이트 | severity | 우회 |
|---|---|---|
| frozen gate (HITL 미완료 시 진입 차단) | BLOCK | `--skip-frozen-gate` |
| skeleton drift gate (freeze 후 외부 수정) | BLOCK | `--accept-skeleton-drift` |
| depends_on 미충족 / 병렬 그룹 내 의존 | BLOCK | — (직렬화 필요) |
| LESSON-021 toolchain (test+lint+type, done 전용) | BLOCK | `--skip-toolchain` |
| git repo/설치 사전 조건 (not-git 시 done 차단 — 빌드 전 기간 보안훅 무검사 방지, v0.19.3 P0) | BLOCK | `--skip-security` |
| security gate | BLOCK | `--skip-security` |
| no-tests 우회 감지 (B3) | advisory(WARN) | — |
| built 전이 시 skipped 공개 | advisory(WARN) | — |

### /ha-verify
| 게이트 | severity | 우회 |
|---|---|---|
| skeleton integrity (filesystem 블록 ↔ 실재) | BLOCK | — (design 복귀) |
| rework T-ID 필수 (passed=false) | BLOCK | `--no-rework` |
| 가짜 FAIL 가드 (`test_dir_warning` — cwd 에 테스트 디렉토리 부재) | advisory(실행 전 경고) | profiles[].path 수정 |
| 동일 T-ID 3회째 FAIL 루프 가드 | BLOCK | `--force-continue` |
| skeleton hash 비교 | advisory | — |
| 런타임 인코딩 스모크 (cli_entrypoint `toolchain.smoke` 실제 invoke — cp949 등) | advisory(WARN) | smoke 미설정 시 권고 |

### /ha-review
| 게이트 | severity | 우회 |
|---|---|---|
| git repo 사전 조건 | BLOCK(exit 2) | git init |
| 7 보안훅 (secret/command/db/dependency/code-quality/contract/auth) | BLOCK/WARN findings | record `--allow-block` |
| ai-slop + mobile 룰 | BLOCK/WARN findings | 〃 |
| fp-check 체인 (TRUE/FALSE 판정 후 집계) | LLM 절차 | — |
| 역방향 contract (선언-미구현 엔드포인트) | advisory | — |
| test distribution | advisory | — |
| APPROVE+BLOCK 차단 / REJECT+violations 필수 | BLOCK | `--allow-block` / — |

### /ha-redesign
| 게이트 | severity | 우회 |
|---|---|---|
| affected §N/T-ID 실존 검증 | BLOCK | — |
| done→needs_rebuild 자동 전이 (affected ∪ hash 파생) | 자동 가드 | 사용자가 status 직접 복원 |
| cross-section consistency | advisory | — |

### /ha-smoke
| 게이트 | severity | 우회 |
|---|---|---|
| verified/reviewed 상태에서만 실행 | BLOCK(exit 2) | — |
| 런타임 기동 probe (exit 0 / URL readiness) — `verify_history` step=`smoke` 기록 | advisory(상태 전이 없음) | — |
| 계층2 — 기동 후 선언 GET 엔드포인트 타격 (404/5xx=FAIL, 떠도 라우트 깨짐) | advisory | — |

### /ha-converge
| 게이트 | severity | 우회 |
|---|---|---|
| built/verified/reviewed 상태에서만 실행 | BLOCK(exit 2) | — |
| 선언-미구현 엔드포인트 → tasks.md `대기` 태스크 회수 (멱등) | advisory(actionable, 상태 전이 없음) | prepare 로 의도적 skipped 걸러냄 |

### /ha-ship
| 게이트 | severity | 우회 |
|---|---|---|
| reviewed 상태에서만 마킹 | BLOCK | — |

## 집계
- BLOCK 계열: **20** · advisory/HITL 계열: **17+** (2026-07-06 전수 재집계 — v0.19.2 "작성 가이드" 잔재 + v0.19.3 ha-build git 사전 조건 반영. 기준: severity 가 BLOCK 표기인 행. 보안훅/ai-slop findings 행은 BLOCK/WARN 혼합이라 "+" 계상)
- 다이어그램/README 의 "8개 게이트" 는 이 표 기준으로 갱신할 것.
