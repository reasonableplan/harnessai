#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-deepinit` 백엔드 (코드베이스 스캔)."""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from utils import info, load_plan, project_root, save_plan  # noqa: E402, I001


_EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".git", ".pytest_cache", ".ruff_cache", ".mypy_cache", "target",
    "coverage", ".next", ".nuxt", ".turbo", ".cache", ".idea", ".vscode",
}

_LANG_BY_EXT = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".rs": "rust",
    ".go": "go", ".java": "java", ".kt": "kotlin", ".swift": "swift",
    ".md": "markdown", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".json": "json", ".html": "html", ".css": "css",
}


def _scan_dir(path: Path, depth: int, max_depth: int) -> dict:
    """디렉토리 재귀 스캔."""
    if depth > max_depth or path.name in _EXCLUDE_DIRS:
        return {"path": str(path), "skipped": True}

    entries = []
    file_count = 0
    lang_counter: Counter = Counter()

    try:
        for child in sorted(path.iterdir()):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                if child.name in _EXCLUDE_DIRS:
                    continue
                entries.append(_scan_dir(child, depth + 1, max_depth))
            elif child.is_file():
                file_count += 1
                lang = _LANG_BY_EXT.get(child.suffix.lower())
                if lang:
                    lang_counter[lang] += 1
    except (PermissionError, OSError):
        pass

    # 자식들 합산
    total_files = file_count
    total_lang: Counter = Counter(lang_counter)
    sub_dirs = []
    for entry in entries:
        if entry.get("skipped"):
            continue
        total_files += entry.get("total_files", 0)
        for k, v in entry.get("languages", {}).items():
            total_lang[k] += v
        sub_dirs.append(entry)

    return {
        "path": str(path),
        "name": path.name,
        "depth": depth,
        "direct_files": file_count,
        "total_files": total_files,
        "languages": dict(total_lang),
        "sub_dirs": sub_dirs,
    }


def _flatten_significant(tree: dict, min_files: int = 3) -> list[dict]:
    """의미 있는 디렉토리만 flat 리스트로."""
    out = []
    if tree.get("total_files", 0) >= min_files and tree.get("depth", 0) > 0:
        out.append({
            "path": tree["path"],
            "name": tree["name"],
            "depth": tree["depth"],
            "total_files": tree["total_files"],
            "primary_language": (
                max(tree["languages"], key=tree["languages"].get)
                if tree["languages"] else None
            ),
            "languages": tree["languages"],
        })
    for sub in tree.get("sub_dirs", []):
        out.extend(_flatten_significant(sub, min_files))
    return out


def cmd_scan(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve() if args.project else project_root()
    if not project.exists():
        info(f"[FAIL] project not found: {project}")
        return 1

    tree = _scan_dir(project, depth=0, max_depth=args.depth)
    significant = _flatten_significant(tree, min_files=args.min_files)

    # include 필터
    if args.include:
        keep = set(args.include.split(","))
        significant = [s for s in significant if any(k in s["path"] for k in keep)]

    output = {
        "project": str(project),
        "tree_summary": {
            "total_files": tree.get("total_files", 0),
            "languages": tree.get("languages", {}),
            "primary_language": (
                max(tree["languages"], key=tree["languages"].get)
                if tree["languages"] else None
            ),
        },
        "significant_dirs": significant,
        "agents_md_targets": [
            {"path": s["path"], "agents_md_path": str(Path(s["path"]) / "AGENTS.md")}
            for s in significant
        ],
        "root_agents_md": str(project / "AGENTS.md"),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_augment_plan(args: argparse.Namespace) -> int:
    """G1: harness-plan.md 의 user_description_original 을 코드베이스 분석 요약으로 보강.

    SKILL.md §5: "/ha-init 이 실행됐다면 user_description_original 을 분석 결과 요약으로 보강."
    - 모든 pipeline 상태 허용 (assert_state 없음)
    - 기존 내용 끝에 분석 요약 append (덮어쓰기 아님)
    - --no-backup 없으면 .harness-plan.md.bak-<ts> 자동 생성
    """
    plan, plan_path, project = load_plan()

    # 백업 (기본 활성화)
    if not args.no_backup:
        ts = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_path = plan_path.with_name(f".{plan_path.name}.bak-{ts}")
        try:
            backup_path.write_text(plan_path.read_text(encoding="utf-8"), encoding="utf-8")
            info(f"[INFO] backup: {backup_path}")
        except OSError as e:
            info(f"[WARN] backup 실패 (계속 진행): {e}")

    # 코드베이스 스캔 — scan 결과를 직접 계산 (재사용)
    scan_project = Path(args.project).resolve() if args.project else project
    tree = _scan_dir(scan_project, depth=0, max_depth=2)
    significant = _flatten_significant(tree, min_files=3)

    total_files = tree.get("total_files", 0)
    languages = tree.get("languages", {})
    primary_lang = max(languages, key=languages.get) if languages else "unknown"  # type: ignore[arg-type]

    top_dirs = [s["name"] for s in significant[:10]]
    lang_list = ", ".join(
        f"{lang}({cnt})" for lang, cnt in sorted(languages.items(), key=lambda x: -x[1])
    )

    ts_display = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary_block = (
        f"\n\n## 자동 분석 (ha-deepinit augment — {ts_display})\n\n"
        f"- 총 파일: {total_files}\n"
        f"- 주 언어: {primary_lang}\n"
        f"- 언어 분포: {lang_list or '없음'}\n"
        f"- 주요 디렉토리: {', '.join(top_dirs) or '없음'}\n"
    )

    # AGENTS.md 가 있으면 경로 참조 추가
    root_agents_md = scan_project / "AGENTS.md"
    if root_agents_md.exists():
        summary_block += f"- AGENTS.md: {root_agents_md} (ha-deepinit 생성)\n"

    plan.user_description_original = plan.user_description_original + summary_block

    try:
        save_plan(plan, plan_path)
    except OSError as e:
        info(f"[FAIL] harness-plan.md 쓰기 실패: {e}")
        return 1

    output = {
        "plan_path": str(plan_path),
        "project": str(scan_project),
        "augmented": True,
        "total_files": total_files,
        "primary_language": primary_lang,
        "top_dirs": top_dirs,
        "backup": str(backup_path) if not args.no_backup else None,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-deepinit")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="프로젝트 디렉토리 스캔 + 의미 있는 디렉토리 식별")
    s.add_argument("--project", default="", help="(기본: git root 또는 cwd)")
    s.add_argument("--depth", type=int, default=3, help="최대 깊이 (기본 3)")
    s.add_argument("--min-files", type=int, default=3, help="significant 임계값")
    s.add_argument("--include", default="", help="콤마 구분 디렉토리 키워드 필터")

    a = sub.add_parser("augment-plan", help="harness-plan.md 의 user_description_original 을 코드베이스 분석 요약으로 보강")
    a.add_argument("--project", default="", help="스캔할 프로젝트 경로 (기본: harness-plan.md 의 project)")
    a.add_argument("--no-backup", action="store_true", help="backup 생성 skip")

    args = parser.parse_args()
    if args.cmd == "scan":
        return cmd_scan(args)
    if args.cmd == "augment-plan":
        return cmd_augment_plan(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
