#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-deepinit` 백엔드 (코드베이스 스캔)."""
from __future__ import annotations

import argparse
import datetime
import json
import re
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


_CITATION_TOKEN_RE = re.compile(r"`([^`]+)`")
_CITATION_PATH_RE = re.compile(r"(?P<path>[\w\-./\\]+?)(?::(?P<line>\d+)(?:-\d+)?)?")


def _extract_citations(text: str) -> list[tuple[str, int | None]]:
    """백틱 토큰에서 파일 인용 (`path` / `path:line`) 만 추출.

    URL(://), 공백 포함 명령, 점 표기 코드 식별자는 제외 — 경로 구분자가 있거나
    확장자가 _LANG_BY_EXT 에 있는 토큰만 인용으로 취급 (오탐 방지).
    """
    citations: list[tuple[str, int | None]] = []
    for token in _CITATION_TOKEN_RE.findall(text):
        token = token.strip()
        if not token or " " in token or "://" in token:
            continue
        m = _CITATION_PATH_RE.fullmatch(token)
        if not m:
            continue
        path_part = m.group("path").removeprefix("./")
        has_sep = "/" in path_part or "\\" in path_part
        known_ext = Path(path_part).suffix.lower() in _LANG_BY_EXT
        if not (has_sep or known_ext):
            continue
        line = int(m.group("line")) if m.group("line") else None
        citations.append((path_part, line))
    return citations


def _find_agents_md(project: Path) -> list[Path]:
    """검증 대상 AGENTS.md 목록 (제외 디렉토리/숨김 경로 밖)."""
    out = []
    for p in project.rglob("AGENTS.md"):
        parents = p.relative_to(project).parts[:-1]
        if any(part in _EXCLUDE_DIRS or part.startswith(".") for part in parents):
            continue
        out.append(p)
    return sorted(out)


def cmd_validate(args: argparse.Namespace) -> int:
    """AGENTS.md 인용 게이트 — 백틱 파일 인용의 실재 + 최소 개수 + 라인 범위 검증.

    인용 없는 요약 = 검증 불가 주장. 주 실패 모드는 Agent 가 쓴 환각 경로 —
    경로 실재 검증이 이를 기계적으로 차단한다 (DeepWiki 식 source citation 이식).
    """
    project = Path(args.project).resolve() if args.project else project_root()
    if not project.exists():
        info(f"[FAIL] project not found: {project}")
        return 1

    min_citations: int = args.min_citations
    agents_files = _find_agents_md(project)
    if not agents_files:
        info(f"[FAIL] AGENTS.md 없음: {project} — /ha-deepinit 생성 단계(§3~4) 선행 필요")
        return 3

    files_out = []
    passed = True
    for agents_md in agents_files:
        text = agents_md.read_text(encoding="utf-8")
        citations = _extract_citations(text)
        missing: list[str] = []
        line_overflow: list[str] = []
        for path_part, line in citations:
            resolved = None
            for base in (agents_md.parent, project):
                candidate = base / path_part
                if candidate.exists():
                    resolved = candidate
                    break
            if resolved is None:
                missing.append(path_part if line is None else f"{path_part}:{line}")
                continue
            if line is not None and resolved.is_file():
                try:
                    n_lines = len(
                        resolved.read_text(encoding="utf-8", errors="replace").splitlines()
                    )
                except OSError as e:
                    info(f"[WARN] 인용 파일 읽기 실패 (라인 검증 skip): {resolved} — {e}")
                    continue
                if line > n_lines:
                    line_overflow.append(f"{path_part}:{line} (파일 {n_lines}줄)")

        count_ok = len(citations) >= min_citations
        file_ok = count_ok and not missing and not line_overflow
        passed = passed and file_ok
        files_out.append(
            {
                "file": str(agents_md),
                "citation_count": len(citations),
                "count_ok": count_ok,
                "missing": missing,
                "line_overflow": line_overflow,
            }
        )

    if not passed:
        info(
            "[FAIL] AGENTS.md 인용 게이트 위반 — 환각 경로/라인 초과/인용 부족.\n"
            "       해당 AGENTS.md 를 수정 후 validate 재실행 (완화: --min-citations 0)."
        )
    output = {
        "project": str(project),
        "passed": passed,
        "min_citations": min_citations,
        "files": files_out,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if passed else 1


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

    v = sub.add_parser("validate", help="AGENTS.md 인용 게이트 — 백틱 파일 인용 실재/최소개수/라인범위 검증")
    v.add_argument("--project", default="", help="(기본: git root 또는 cwd)")
    v.add_argument(
        "--min-citations", type=int, default=1, help="AGENTS.md 당 최소 파일 인용 수 (0=완화)"
    )

    args = parser.parse_args()
    if args.cmd == "scan":
        return cmd_scan(args)
    if args.cmd == "augment-plan":
        return cmd_augment_plan(args)
    if args.cmd == "validate":
        return cmd_validate(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
