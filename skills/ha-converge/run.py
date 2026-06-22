#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-converge` 백엔드 (코드↔스펙 미구현 회수, actionable 게이트).

ha-review 의 역방향 contract(선언-미구현 엔드포인트)는 advisory WARN 에 그친다.
이 스킬은 같은 신호를 **actionable** 하게: skeleton 에 선언됐지만 소스에 없는
컴포넌트를 tasks.md 에 신규 `대기` 태스크로 회수(append)한다. 멱등 — 두 번 돌려도
중복 추가 안 함. 상태 전이는 없음 (회수된 태스크는 /ha-build 가 빌드).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from utils import (  # noqa: E402, I001
    assert_state,
    info,
    load_plan,
)

# backend src import — utils.py 가 backend/ 를 sys.path 에 추가 보장
from src.orchestrator.converge import (  # noqa: E402
    append_tasks,
    filter_uncovered,
    find_missing_endpoints,
)

# 회수 게이트는 코드가 존재하는 빌드 이후에만 의미 있음.
_ALLOWED_STATES = ["built", "verified", "reviewed"]

_SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".kt", ".swift", ".dart"}
_SKIP_DIRS = {
    "node_modules", ".venv", "venv", "dist", "build", "__pycache__",
    ".git", "docs", ".orchestra",
}


def _iter_source_texts(project: Path) -> list[str]:
    """프로젝트 소스 파일 내용 목록 (벤더/빌드/문서 디렉토리 제외)."""
    texts: list[str] = []
    stack = [project]
    while stack:
        d = stack.pop()
        try:
            entries = list(d.iterdir())
        except OSError:
            continue
        for e in entries:
            if e.is_dir():
                if e.name not in _SKIP_DIRS:
                    stack.append(e)
            elif e.suffix in _SOURCE_EXTS:
                try:
                    texts.append(e.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
    return texts


def _gather(project: Path, plan_path: Path):  # type: ignore[no-untyped-def]
    skel_path = plan_path.parent / "skeleton.md"
    tasks_path = plan_path.parent / "tasks.md"
    skel_text = skel_path.read_text(encoding="utf-8") if skel_path.exists() else ""
    tasks_text = tasks_path.read_text(encoding="utf-8") if tasks_path.exists() else ""
    findings = find_missing_endpoints(skel_text, _iter_source_texts(project))
    return tasks_path, tasks_text, findings


def cmd_prepare(_args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, _ALLOWED_STATES, "/ha-converge")
    tasks_path, tasks_text, findings = _gather(project, plan_path)
    uncovered = filter_uncovered(findings, tasks_text)
    uncovered_ids = {f.identifier for f in uncovered}
    print(
        json.dumps(
            {
                "findings": [
                    {"kind": f.kind, "identifier": f.identifier, "detail": f.detail}
                    for f in findings
                ],
                "uncovered": sorted(uncovered_ids),
                "already_covered": sorted(
                    f.identifier for f in findings if f.identifier not in uncovered_ids
                ),
                "tasks_path": str(tasks_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_commit(_args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, _ALLOWED_STATES, "/ha-converge")
    tasks_path, tasks_text, findings = _gather(project, plan_path)
    if not tasks_path.exists():
        print(
            "[FAIL] tasks.md 없음 — /ha-plan 을 먼저 실행하세요.",
            file=sys.stderr,
        )
        return 3

    new_text, added = append_tasks(tasks_text, findings)
    if not added:
        info("[OK] /ha-converge — 회수할 미구현 컴포넌트 없음 (또는 이미 태스크화됨).")
        return 0

    try:
        tasks_path.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        print(f"[FAIL] tasks.md 쓰기 실패: {exc}", file=sys.stderr)
        raise

    for tid, identifier in added:
        info(f"  + {tid}: {identifier}")
    info(
        f"[OK] /ha-converge — {len(added)}개 미구현 컴포넌트를 태스크로 회수했습니다.\n"
        f"다음: /ha-build 로 회수된 태스크 구현 (reviewed 상태면 building 으로 회귀)."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-converge")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare", help="미구현 컴포넌트 보고 (read-only, JSON)")
    sub.add_parser("commit", help="미구현 컴포넌트를 tasks.md 에 회수 (멱등)")
    args = parser.parse_args()

    if args.cmd == "prepare":
        return cmd_prepare(args)
    if args.cmd == "commit":
        return cmd_commit(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
