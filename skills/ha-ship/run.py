#!/usr/bin/env python3
"""HarnessAI — 파이프라인 라스트마일: reviewed → shipped 상태 마킹.

배포/PR 자체는 외부 도구 (gstack /ship 등) 가 수행한다. 이 스크립트는
상태머신에 정의돼 있었지만 운전자가 없어 도달 불가였던 shipped 전이만 담당
(2026-06-10 시스템 리뷰 ⑦).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from utils import assert_state, load_plan, save_plan, transition  # noqa: E402


def cmd_mark(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["reviewed"], "/ha-ship")
    transition(plan, "shipped", completed_step="ha-ship")
    save_plan(plan, plan_path)
    print(json.dumps(
        {
            "current_step": plan.pipeline.current_step,
            "project": str(project),
            "note": "배포/PR 자체는 외부 도구(/ship 등)로 — 이 명령은 파이프라인 상태만 마킹",
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-ship")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("mark")
    args = parser.parse_args()
    if args.cmd == "mark":
        return cmd_mark(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
