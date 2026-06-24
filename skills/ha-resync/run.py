#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-resync` 백엔드 스크립트.

skeleton.md 수동 수정 후 skeleton_hash + section_hashes 를 전체 재계산해
harness-plan.md 에 덮어쓴다. migrate-skeleton-hash 와 달리 기존 해시가 있어도
무조건 덮어쓴다 (가드 없음).

종료 코드:
  0 — 정상 (apply 또는 dry-run)
  1 — I/O 오류 (백업/쓰기 실패)
  3 — 내부 오류 (skeleton.md 없음 등)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Shared util import — same pattern as ha-design/run.py
sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from utils import (  # noqa: E402
    info,
    load_plan,
    save_plan,
)

# backend src import — utils.py guarantees backend is on sys.path
from src.orchestrator.skeleton_hash import (  # noqa: E402
    compute_section_hashes,
    compute_skeleton_hash,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ha-resync",
        description="skeleton_hash + section_hashes 전체 재동기 (덮어쓰기)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="파일 미수정 — 재계산 결과만 출력",
    )
    args = parser.parse_args()

    plan, plan_path, _project = load_plan()

    skeleton_path = plan_path.parent / "skeleton.md"
    if not skeleton_path.exists():
        info(f"[FAIL] skeleton.md 없음: {skeleton_path}")
        info("       /ha-design 완료 후 실행하세요.")
        return 3

    # Compute new hashes
    new_skeleton_hash = compute_skeleton_hash(skeleton_path)
    new_section_hashes = compute_section_hashes(skeleton_path)

    old_skeleton_hash = plan.skeleton_hash or ""
    old_section_hashes = dict(plan.section_hashes) if plan.section_hashes else {}

    # Diff section keys to summarise changes
    old_keys = set(old_section_hashes.keys())
    new_keys = set(new_section_hashes.keys())
    added_keys = new_keys - old_keys
    removed_keys = old_keys - new_keys
    changed_keys = {
        k for k in (old_keys & new_keys)
        if old_section_hashes[k] != new_section_hashes[k]
    }
    changed_count = len(added_keys) + len(removed_keys) + len(changed_keys)

    result: dict = {
        "plan_path": str(plan_path),
        "skeleton_path": str(skeleton_path),
        "old_skeleton_hash": old_skeleton_hash[:12] if old_skeleton_hash else "",
        "new_skeleton_hash": new_skeleton_hash[:12],
        "section_diff": {
            "added": sorted(added_keys),
            "removed": sorted(removed_keys),
            "changed": sorted(changed_keys),
        },
        "dry_run": args.dry_run,
        "applied": False,
        "backup_path": None,
    }

    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        info(
            f"[DRY-RUN] skeleton_hash {old_skeleton_hash[:12] or '(없음)'}→"
            f"{new_skeleton_hash[:12]}, "
            f"section 변경 {changed_count}개"
        )
        return 0

    # Create timestamped backup before modifying plan
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backup_name = f".harness-backup-{ts}.md"
    backup_file = plan_path.parent / backup_name
    try:
        backup_file.write_text(plan_path.read_text(encoding="utf-8"), encoding="utf-8")
    except OSError as exc:
        info(f"[FAIL] 백업 생성 실패 ({backup_file}): {exc}")
        return 1

    # Overwrite hashes unconditionally (no guard — that's the point of ha-resync)
    plan.skeleton_hash = new_skeleton_hash
    plan.section_hashes = new_section_hashes

    try:
        save_plan(plan, plan_path)
    except OSError as exc:
        info(f"[FAIL] plan 저장 실패: {exc}")
        return 1

    result["applied"] = True
    result["backup_path"] = str(backup_file)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    info(
        f"[OK] 해시 재동기 완료.\n"
        f"     skeleton_hash: {old_skeleton_hash[:12] or '(없음)'}→{new_skeleton_hash[:12]}\n"
        f"     section 변경: 추가 {len(added_keys)}개 / "
        f"변경 {len(changed_keys)}개 / 삭제 {len(removed_keys)}개\n"
        f"     백업: {backup_file}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
