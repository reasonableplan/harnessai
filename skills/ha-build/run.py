#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-build` 백엔드."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from utils import (  # noqa: E402, I001
    HARNESS_HOME,
    assert_state,
    get_active_profiles,
    info,
    load_plan,
    save_plan,
    transition,
)


_TASK_ROW_RE = re.compile(
    r"^\|\s*(T-\d+)\s*\|\s*(\w+)\s*\|\s*([^|]*)\|\s*([^|]*)\|\s*([^|]+)\|\s*$",
    re.MULTILINE,
)


def _parse_tasks(tasks_text: str) -> dict[str, dict[str, str]]:
    """tasks.md 에서 태스크 dict 파싱: {T-001: {agent, depends_on, description, status}}"""
    out: dict[str, dict[str, str]] = {}
    for m in _TASK_ROW_RE.finditer(tasks_text):
        tid = m.group(1)
        agent = m.group(2).strip()
        deps_raw = m.group(3).strip()
        depends_on = (
            [d.strip() for d in deps_raw.split(",") if d.strip() and d.strip() != "-"]
        )
        desc = m.group(4).strip()
        status = m.group(5).strip()
        out[tid] = {
            "agent": agent,
            "depends_on": depends_on,
            "description": desc,
            "status": status,
        }
    return out


def cmd_prepare(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["planned", "building"], "/ha-build")

    tasks_path = plan_path.parent / "tasks.md"
    if not tasks_path.exists():
        info(f"[FAIL] tasks.md 없음: {tasks_path}")
        return 1
    tasks = _parse_tasks(tasks_path.read_text(encoding="utf-8"))

    target_ids = args.task.split(",") if args.task else []
    if not target_ids:
        info("[FAIL] --task <T-ID> 또는 --task T-001,T-002 필요")
        return 2

    # depends_on 만족 검사
    issues: list[str] = []
    for tid in target_ids:
        if tid not in tasks:
            issues.append(f"태스크 '{tid}' 없음 in tasks.md")
            continue
        for dep in tasks[tid]["depends_on"]:
            if dep not in tasks:
                issues.append(f"{tid} depends_on '{dep}' 가 tasks.md 에 없음")
            elif tasks[dep]["status"].lower() not in ("done", "완료", "completed"):
                issues.append(f"{tid} depends_on '{dep}' 가 미완료 (status={tasks[dep]['status']})")

    if issues:
        for i in issues:
            info(f"[BLOCK] {i}")
        return 1

    # 병렬 모드 검증 — 같은 그룹 내 서로 depends_on X
    if len(target_ids) > 1:
        targets_set = set(target_ids)
        for tid in target_ids:
            for dep in tasks[tid]["depends_on"]:
                if dep in targets_set:
                    info(f"[FAIL] 병렬 그룹 내 의존: {tid} → {dep}. 직렬 실행 필요.")
                    return 1

    profiles = get_active_profiles(plan, project)

    output = {
        "project": str(project),
        "plan_path": str(plan_path),
        "tasks_path": str(tasks_path),
        "tasks": [
            {
                "id": tid,
                **tasks[tid],
                "agent_prompt": str(HARNESS_HOME / "backend" / "agents" / tasks[tid]["agent"] / "CLAUDE.md"),
            }
            for tid in target_ids
        ],
        "profiles": [
            {
                "id": p.id,
                "path": str(plan.profiles[i].path) if i < len(plan.profiles) else ".",
                "toolchain_test": p.toolchain.test,
                "whitelist_runtime": list(p.whitelist.runtime),
            }
            for i, p in enumerate(profiles)
        ],
        "parallel": len(target_ids) > 1,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def _run_toolchain_gate(project: Path, plan) -> list[str]:
    """LESSON-021: done 마킹 전 프로파일의 toolchain.test + .lint + .type 전부 실행.

    반환: 실패한 체크 설명 리스트. 비어있으면 통과.
    """
    failures: list[str] = []
    profiles = get_active_profiles(plan, project)
    for i, p in enumerate(profiles):
        path = str(plan.profiles[i].path) if i < len(plan.profiles) else "."
        cwd = str((project / path).resolve()) if path != "." else str(project)
        checks = [
            ("test", p.toolchain.test),
            ("lint", p.toolchain.lint),
            ("type", p.toolchain.type),
        ]
        for name, cmd in checks:
            if not cmd:
                continue
            try:
                r = subprocess.run(
                    cmd, shell=True, cwd=cwd,
                    capture_output=True, timeout=300,
                )
                if r.returncode != 0:
                    failures.append(
                        f"[{p.id} @ {path}] {name} 실패 (rc={r.returncode}): {cmd}"
                    )
            except subprocess.TimeoutExpired:
                failures.append(f"[{p.id} @ {path}] {name} 타임아웃 (>5분): {cmd}")
            except FileNotFoundError:
                # shell not found 등 극단 케이스
                failures.append(f"[{p.id} @ {path}] {name} 실행 불가: {cmd}")
    return failures


def cmd_complete(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["planned", "building"], "/ha-build")

    if args.status not in ("done", "blocked", "in-progress"):
        info(f"[FAIL] --status: done|blocked|in-progress, 현재 '{args.status}'")
        return 2

    # LESSON-021: done 마킹 전 toolchain 전체 강제 (test + lint + type)
    # --skip-toolchain 로 opt-out (문서/설계 태스크 등).
    if args.status == "done" and not args.skip_toolchain:
        info("[gate] LESSON-021: toolchain (test/lint/type) 검증 중 …")
        failures = _run_toolchain_gate(project, plan)
        if failures:
            info(f"[BLOCK] toolchain 실패 {len(failures)}건 — done 마킹 거부:")
            for f in failures:
                info(f"  · {f}")
            info("수정 후 재시도하거나, 의도적 skip 이면 --skip-toolchain 명시.")
            return 1
        info("[gate] toolchain 전부 통과 — done 마킹 진행")

    tasks_path = plan_path.parent / "tasks.md"
    text = tasks_path.read_text(encoding="utf-8")

    # 해당 태스크 행의 상태 컬럼만 교체
    new_text = re.sub(
        rf"(\|\s*{re.escape(args.task)}\s*\|.*?\|.*?\|.*?\|\s*)([^|]+)(\|\s*$)",
        lambda m: f"{m.group(1)}{args.status:<10}{m.group(3)}",
        text, count=1, flags=re.MULTILINE,
    )
    if new_text == text:
        info(f"[WARN] 태스크 '{args.task}' 행 못 찾음 — 변경 없음")
    else:
        tasks_path.write_text(new_text, encoding="utf-8")

    # 모든 태스크 done?
    tasks = _parse_tasks(new_text)
    statuses = {tid: t["status"].lower() for tid, t in tasks.items()}
    all_done = statuses and all(s in ("done", "완료", "completed") for s in statuses.values())
    any_done = any(s in ("done", "완료", "completed") for s in statuses.values())

    if plan.pipeline.current_step == "planned" and any_done:
        transition(plan, "building", completed_step=f"ha-build:{args.task}")
    if plan.pipeline.current_step == "building" and all_done:
        transition(plan, "built", completed_step="ha-build:all-done")
    elif plan.pipeline.current_step == "building":
        # building 유지, completed_steps 만 업데이트 — transition 우회
        completed = list(plan.pipeline.completed_steps)
        step_id = f"ha-build:{args.task}"
        if step_id not in completed:
            completed.append(step_id)
        from src.orchestrator.plan_manager import Pipeline
        plan.pipeline = Pipeline(
            steps=plan.pipeline.steps,
            current_step=plan.pipeline.current_step,
            completed_steps=tuple(completed),
            skipped_steps=plan.pipeline.skipped_steps,
            gstack_mode=plan.pipeline.gstack_mode,
        )

    save_plan(plan, plan_path)

    output = {
        "task": args.task,
        "new_status": args.status,
        "all_tasks_done": all_done,
        "current_step": plan.pipeline.current_step,
        "next": "/ha-verify" if all_done else "/ha-build <next T-ID>",
    }
    if args.reason:
        output["reason"] = args.reason
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-build")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("--task", required=True, help="T-001 또는 T-001,T-002 (병렬)")

    c = sub.add_parser("complete")
    c.add_argument("--task", required=True)
    c.add_argument("--status", required=True, choices=["done", "blocked", "in-progress"])
    c.add_argument("--reason", default="")
    c.add_argument(
        "--skip-toolchain",
        action="store_true",
        help="LESSON-021 toolchain 게이트 스킵 (문서/설계 태스크 등 의도적일 때만)",
    )

    args = parser.parse_args()
    if args.cmd == "prepare":
        return cmd_prepare(args)
    return cmd_complete(args)


if __name__ == "__main__":
    sys.exit(main())
