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
| T-000 자동 주입 (scaffold 프로파일 보유 + 미부트스트랩 시, v0.20.0) | 자동 가드 | — (LLM 이 직접 T-000 작성 시 중복 주입 skip) |

### /ha-build
| 게이트 | severity | 우회 |
|---|---|---|
| frozen gate (HITL 미완료 시 진입 차단) | BLOCK | `--skip-frozen-gate` |
| skeleton drift gate (freeze 후 외부 수정) | BLOCK | `--accept-skeleton-drift` |
| depends_on 미충족 / 병렬 그룹 내 의존 | BLOCK | — (직렬화 필요) |
| scaffold 선행 게이트 (T-000 미해결 시 다른 태스크 차단, v0.20.0) | BLOCK | `--skip-scaffold-gate` |
| 스텁 미구현 게이트 (declared 파일에 HARNESS-STUB 잔존 시 done 차단, v0.20.0) | BLOCK | — (구현 또는 파일 삭제가 조치) |
| LESSON-021 toolchain (test+lint+type, done 전용) | BLOCK | `--skip-toolchain` |
| git repo/설치 사전 조건 (not-git 시 done 차단 — 빌드 전 기간 보안훅 무검사 방지, v0.19.3 P0) | BLOCK | `--skip-security` |
| security gate | BLOCK | `--skip-security` |
| no-tests 우회 감지 (B3) | advisory(WARN) | — |
| built 전이 시 skipped 공개 | advisory(WARN) | — |
| scaffold complete 의 `--skip-toolchain` 특례 (갓 스캐폴드된 앱 test 스크립트 부재, v0.20.0) | advisory(정당한 우회) | security gate 는 유지 (`--skip-security` 미적용) |
| rework 재진입 — prepare 가 done/skipped/needs_rebuild 를 in-progress 로 되돌림 (v0.21.1). 안 되돌리면 배치의 첫 complete 가 built 로 전이해 형제 태스크의 게이트가 실행되지 않음 | 자동 가드 | — |

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
| REJECT 시 재작업 T-ID 필수 (violations 의 `T-NNN` 또는 `--rework-tasks`, v0.21.1) | BLOCK | `--no-rework` |
| REJECT → 지목 태스크 `needs_rebuild` 전이 + 미전이 T-ID 경고 (v0.21.1) | 자동 가드 | — |

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
| 부적격 `--endpoint` (경로가 `/` 로 시작 안 함 — Git Bash MSYS 변환) → 기동 전 FAIL (v0.21.1) | BLOCK | — (`MSYS_NO_PATHCONV=1` 로 재실행) |
| probe detail 에 실제 타격/skip 개수 노출 — "0개 OK" 가 성공으로 위장되지 않게 (v0.21.1) | 자동 가드 | — |

### /ha-accept
| 게이트 | severity | 우회 |
|---|---|---|
| verified/reviewed 상태에서만 실행 (prepare/record) | BLOCK(exit 2) | — |
| acceptance.yaml 스키마/미선언 엔드포인트 참조/비활성 프로파일 (validate, v0.21.0) | BLOCK | — (파생 수정이 조치) |
| run `--profile` 매칭 시나리오 0개 — 공허 통과 차단 | BLOCK(exit 2) | — (오타/파생 누락 수정) |
| GWT 시나리오 실행 FAIL / 부팅 실패 (run) — `verify_history` step=`accept` 기록 | advisory(상태 전이 없음) | HITL 판단 (smoke 동일) |
| 커버리지 (시나리오 0개 확정 기능 / underivable 집계) | advisory | — |

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
- BLOCK 계열: **25** · advisory/HITL 계열: **20+** (2026-07-13 v0.21.0 /ha-accept 반영 — 상태 BLOCK(exit 2)·validate BLOCK·공허 매칭 BLOCK 3건 + run/커버리지 advisory 2건 추가. 직전 재집계는 2026-07-12 v0.20.0: scaffold 선행 게이트 BLOCK + scaffold complete `--skip-toolchain` 특례 advisory + 스텁 미구현 게이트 BLOCK. T-000 자동 주입은 BLOCK/advisory 어디에도 속하지 않는 "자동 가드" — done→needs_rebuild 전이와 동일 부류라 이 집계에서 제외. 기준: severity 가 BLOCK 표기인 행. 보안훅/ai-slop findings 행은 BLOCK/WARN 혼합이라 "+" 계상)
- 다이어그램/README 의 "8개 게이트" 는 이 표 기준으로 갱신할 것.
