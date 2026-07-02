#!/usr/bin/env python3
"""HarnessAI — /ha-run 자동 드라이버의 결정 코어.

파이프라인 운전(다음 스킬 선택)을 사람 대신 계산한다. 스킬 실행 자체는
SKILL.md 절차(부모 Claude 세션)가 수행 — 이 스크립트는 harness-plan.md
상태 판독 + 다음 행동 JSON 출력만 담당한다. BLOCK 게이트는 각 /ha-*
스킬에 그대로 있다 (여기서 복제하지 않음 — 단일 진실원천).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from utils import PlanManager, find_plan_path, project_root  # noqa: E402

from src.orchestrator.pipeline_advisor import advise  # noqa: E402
from src.orchestrator.plan_manager import PlanSchemaError  # noqa: E402


def cmd_next(args: argparse.Namespace) -> int:
    proj = Path(args.project).resolve() if args.project else project_root()
    plan_path = find_plan_path(proj)
    plan = None
    if plan_path.exists():
        try:
            plan = PlanManager().load(plan_path)
        except PlanSchemaError as exc:
            print(f"[FAIL] harness-plan.md 스키마 오류: {exc}", file=sys.stderr)
            return 3
    advice = advise(plan)
    print(
        json.dumps(
            {
                "action": advice.action,
                "mode": advice.mode,
                "skill": advice.skill,
                "args": advice.args,
                "reason": advice.reason,
                "current_step": plan.pipeline.current_step if plan else None,
                "frozen_status": plan.frozen_status if plan else None,
                "project": str(proj),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-run")
    sub = parser.add_subparsers(dest="cmd", required=True)
    nx = sub.add_parser("next", help="현재 파이프라인 상태 기준 다음 행동 JSON 출력")
    nx.add_argument("--project", default=None, help="프로젝트 루트 (기본: git root 또는 cwd)")
    args = parser.parse_args()
    if args.cmd == "next":
        return cmd_next(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
