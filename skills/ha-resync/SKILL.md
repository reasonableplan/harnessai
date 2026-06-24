---
name: ha-resync
description: |
  HarnessAI v2 — skeleton.md 수동 수정 후 skeleton_hash + section_hashes 전체 재동기.
  ha-redesign applied 이후 정당한 수동 편집을 재계산. Use when: skeleton 손수정 후 해시 stale, "해시 재동기", "/ha-resync"
allowed-tools:
  - Bash
  - Read
---

## 역할

`docs/skeleton.md` 를 수동으로 수정한 뒤 `harness-plan.md` 의 `skeleton_hash` + `section_hashes` 가 stale 해졌을 때 전체 재계산·덮어쓰기.

**입력**: `docs/skeleton.md` (수동 수정된 상태) + `docs/harness-plan.md`
**출력**: `harness-plan.md` 의 `skeleton_hash` / `section_hashes` 갱신

## 언제 쓰나 (#14)

- `/ha-redesign --status applied` 이후 사용자가 `skeleton.md` 를 직접 편집한 경우
- 어떤 이유로든 skeleton 을 손수정하여 plan 의 해시가 stale 이 된 경우
- `[WARN] skeleton 외부 수정 감지` 메시지가 반복해서 뜨는 경우

## migrate-skeleton-hash 와의 차이

| | `migrate-skeleton-hash` | `/ha-resync` |
|---|---|---|
| 기존 해시 있으면 | **거부** (덮어쓰기 방지) | **무조건 덮어쓰기** |
| section_hashes | 손대지 않음 | 함께 재계산 |
| 용도 | legacy plan 최초 백필 | 수동 수정 후 재동기 |

## 실행

```bash
# 실제 적용 (plan 파일 갱신 + 자동 백업 생성)
python ~/.claude/skills/ha-resync/run.py

# 미리보기 (파일 미수정, 변경될 내용만 출력)
python ~/.claude/skills/ha-resync/run.py --dry-run
```

## 출력 JSON

```json
{
  "plan_path": "...",
  "skeleton_path": "...",
  "old_skeleton_hash": "abcdef012345",
  "new_skeleton_hash": "fedcba987654",
  "section_diff": {
    "added": [],
    "removed": [],
    "changed": ["overview", "stack"]
  },
  "dry_run": false,
  "applied": true,
  "backup_path": "docs/.harness-backup-20260622-120000.md"
}
```

## 가드레일

- skeleton.md 없으면 exit 3 (에러) — `/ha-design` 완료 후 실행 필요
- apply 시 plan 수정 전 자동 백업 (`.harness-backup-<ts>.md`)
- `--dry-run` 은 파일 미수정
