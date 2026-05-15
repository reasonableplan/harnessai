#!/usr/bin/env python3
"""HarnessAI v0.10.0 마이그레이션 — frozen_status 필드 추가.

v0.9.x → v0.10.0:
  - harness-plan.md frontmatter 에 frozen_status / frozen_at / locked_sections /
    ai_drafted_sections 4 필드 박힘. legacy parse 는 default ("drafting" / "" / [] / [])
    로 자동 로드되지만, 마이그레이션은 *명시적으로* frontmatter 에 박음 (audit trail).
  - default = drafting (사용자가 /ha-design 으로 다시 freeze 해야 ha-build 진입 가능).
  - --auto-freeze 옵트인: 사용자 *이미 디자인 완료* 라고 선언. included 중 LOCKED
    후보 섹션 (requirements/user_journey/view.screens) 을 즉시 freeze.

사용법:
  harness migrate-v10 <project_root>            # default: drafting 박음
  harness migrate-v10 <project_root> --auto-freeze  # 즉시 freeze
  harness migrate-v10 <project_root> --dry-run  # 변경 안 하고 미리보기
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# UTF-8 stdout/stderr 강제 (Windows cp949 호환성)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

# harness bin 에서 호출 시 backend src 경로를 sys.path 에 추가.
# HARNESS_AI_HOME 환경변수 우선 → 없으면 이 스크립트 기준 상대 탐색.
import os

_HARNESS_AI_HOME = os.environ.get("HARNESS_AI_HOME")
if _HARNESS_AI_HOME:
    _backend_dir = Path(_HARNESS_AI_HOME) / "backend"
else:
    # ~/.claude/harness/bin/migrate_v10.py → parents[2] = ~/.claude
    # 레포 레이아웃: harness/bin/ → parents[2] = 레포 루트
    _script_dir = Path(__file__).resolve().parent
    _backend_dir = _script_dir.parent.parent / "backend"

# backend/__init__.py 가 없으므로 backend/ 를 sys.path 에 추가.
# orchestrator/__init__.py 가 `from src.orchestrator.*` 로 절대 import 하므로
# backend/src/ 는 추가하지 않는다 — backend/ 하나만 있으면 `src.orchestrator` 해소.
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from src.orchestrator.plan_manager import (  # noqa: E402
    PlanManager,
    PlanNotFoundError,
    PlanSchemaError,
)

# HITL gate 대상 섹션 — ha-design 인터뷰 시 사용자가 확인해야 하는 핵심 섹션.
_LOCKED_CANDIDATES = ("requirements", "user_journey", "view.screens")


def migrate(project: Path, *, auto_freeze: bool, dry_run: bool) -> int:
    """v0.9.x harness-plan.md → v0.10.0 frozen_status 필드 박기.

    Args:
        project: 프로젝트 루트 경로 (docs/harness-plan.md 위치).
        auto_freeze: True 면 included 중 LOCKED 후보 섹션을 즉시 freeze.
        dry_run: True 면 파일 변경 없이 미리보기만 출력.

    Returns:
        exit code (0: 성공/skip/dry-run, 1: 실패).
    """
    plan_path = project / "docs" / "harness-plan.md"
    if not plan_path.exists():
        print(f"[FAIL] harness-plan.md 없음: {plan_path}", file=sys.stderr)
        return 1

    backup_path = plan_path.with_suffix(".md.v9.bak")
    pm = PlanManager()

    try:
        plan = pm.load(plan_path)
    except PlanNotFoundError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1
    except PlanSchemaError as e:
        print(f"[FAIL] frontmatter schema error: {e}", file=sys.stderr)
        return 1

    # 이미 v0.10.0 마이그레이션됐는지 확인.
    # frozen_status != "drafting" 또는 frozen_at 이 존재하면 이미 마이그레이션됨.
    # backup 파일 존재도 마이그레이션 완료 신호.
    if plan.frozen_status != "drafting" or plan.frozen_at:
        print(
            f"[SKIP] 이미 마이그레이션됨 (frozen_status={plan.frozen_status})",
            file=sys.stderr,
        )
        return 0
    if backup_path.exists():
        print(
            f"[SKIP] 이미 마이그레이션됨 (backup 존재: {backup_path.name})",
            file=sys.stderr,
        )
        return 0

    # auto_freeze: included 섹션 중 LOCKED 후보가 있으면 freeze
    included = set(plan.skeleton_sections.included)
    locked_candidates = [s for s in _LOCKED_CANDIDATES if s in included]

    if auto_freeze:
        if not locked_candidates:
            print(
                "[WARN] --auto-freeze 박았지만 included 에 LOCKED 후보 없음. drafting 유지.",
                file=sys.stderr,
            )
        else:
            print(
                f"[WARN] --auto-freeze: 사용자가 이미 LOCKED 섹션 ({', '.join(locked_candidates)}) "
                "디자인 완료라고 선언. 가짜 frozen 위험 — 사용자 책임.",
                file=sys.stderr,
            )
            pm.freeze(plan, locked_sections=locked_candidates)

    if dry_run:
        print(
            f"[DRY-RUN] {plan_path}\n"
            f"  frozen_status={plan.frozen_status}\n"
            f"  locked_sections={list(plan.locked_sections)}\n"
            f"  backup_path={backup_path}",
        )
        return 0

    # 백업 먼저 — OSError 시 원본 무결성 보장
    try:
        backup_path.write_text(plan_path.read_text(encoding="utf-8"), encoding="utf-8")
    except OSError as exc:
        print(f"[FAIL] 백업 생성 실패 ({backup_path}): {exc}", file=sys.stderr)
        return 1

    try:
        pm.save(plan, plan_path)
    except OSError as exc:
        print(f"[FAIL] plan 저장 실패: {exc}", file=sys.stderr)
        # 백업은 이미 생성됨 — 롤백 안 함 (백업 자체가 원본)
        return 1

    print(
        f"[OK] {plan_path.name} 마이그레이션 완료\n"
        f"  frozen_status={plan.frozen_status}\n"
        f"  locked_sections={list(plan.locked_sections)}\n"
        f"  backup={backup_path.name}\n"
        "\n다음 단계:\n"
        "  - frozen_status=drafting 이면 /ha-design 인터뷰 후 freeze 필요.\n"
        "  - frozen_status=frozen 이면 /ha-build 진입 가능.",
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="migrate_v10",
        description="HarnessAI v0.9.x → v0.10.0 마이그레이션 (frozen_status 필드 추가)",
    )
    parser.add_argument("project", help="프로젝트 루트 경로 (docs/harness-plan.md 위치)")
    parser.add_argument(
        "--auto-freeze",
        action="store_true",
        dest="auto_freeze",
        help="included LOCKED 후보 섹션 즉시 freeze (사용자 책임 - 가짜 frozen 위험).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="변경 안 하고 미리보기.",
    )
    args = parser.parse_args()
    return migrate(
        Path(args.project).resolve(),
        auto_freeze=args.auto_freeze,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
