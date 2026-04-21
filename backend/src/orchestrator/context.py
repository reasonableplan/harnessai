"""Skeleton section-ID based context injection (Harness v2).

Provides `SECTION_TITLES`, `AGENT_SECTIONS_BY_ID`, `extract_section_by_id`,
and `build_context` — all keyed by section ID. The legacy number-based API
(`SECTION_MAP`, `extract_section`, `fill_skeleton_template`) was removed in
Phase 4b (2026-04-19).
"""

from __future__ import annotations

import re
from pathlib import Path

# Standard 20 section IDs → heading titles matching fragment frontmatter `name`.
# Must stay in sync with ~/.claude/harness/templates/skeleton/<id>.md name fields.
SECTION_TITLES: dict[str, str] = {
    "overview": "프로젝트 개요",
    "requirements": "기능 요구사항",
    "stack": "기술 스택",
    "configuration": "설정 / 환경변수",
    "errors": "에러 핸들링",
    "auth": "인증 / 권한",
    "persistence": "저장소 / 스키마",
    "integrations": "외부 통합",
    "interface.http": "HTTP API",
    "interface.cli": "CLI 커맨드",
    "interface.ipc": "IPC 채널",
    "interface.sdk": "Public API (SDK)",
    "view.screens": "화면 목록",
    "view.components": "컴포넌트 트리",
    "state.flow": "상태 흐름",
    "core.logic": "도메인 로직",
    "observability": "로깅 / 모니터링",
    "deployment": "배포 설정",
    "tasks": "태스크 분해",
    "notes": "구현 노트",
}

# Per-agent section ID mapping. "*" means all sections.
AGENT_SECTIONS_BY_ID: dict[str, list[str]] = {
    "architect": ["*"],
    "designer": [
        "overview",
        "requirements",
        "stack",
        "interface.http",
        "view.screens",
        "view.components",
        "state.flow",
        "errors",
    ],
    "orchestrator": ["overview", "requirements", "stack", "tasks"],
    "backend_coder": [
        "overview",
        "requirements",
        "stack",
        "auth",
        "persistence",
        "interface.http",
        "errors",
        "state.flow",
        "core.logic",
        "notes",
    ],
    "frontend_coder": [
        "overview",
        "requirements",
        "stack",
        "interface.http",
        "view.screens",
        "view.components",
        "state.flow",
        "errors",
        "core.logic",
        "notes",
    ],
    "reviewer": ["*"],
    "qa": [
        "overview",
        "requirements",
        "interface.http",
        "errors",
        "state.flow",
        "core.logic",
        "notes",
    ],
}

# Additional docs per agent
EXTRA_DOCS: dict[str, list[str]] = {
    "architect": ["conventions.md", "shared-lessons.md", "adr/"],
    "designer": ["conventions.md", "shared-lessons.md", "guidelines/frontend/style.md"],
    "orchestrator": ["conventions.md", "shared-lessons.md"],
    "backend_coder": [
        "conventions.md",
        "shared-lessons.md",
        "guidelines/backend/structure.md",
        "guidelines/backend/services.md",
        "guidelines/backend/api.md",
    ],
    "frontend_coder": [
        "conventions.md",
        "shared-lessons.md",
        "guidelines/frontend/components.md",
        "guidelines/frontend/state.md",
        "guidelines/frontend/api.md",
        "guidelines/frontend/style.md",
    ],
    "reviewer": ["conventions.md", "shared-lessons.md", "adr/"],
    "qa": ["conventions.md", "shared-lessons.md"],
}


def extract_section_by_id(skeleton_text: str, section_id: str) -> str:
    """Extract a section from skeleton.md by section ID.

    Looks up the heading title via SECTION_TITLES, finds the matching
    `## N. <title>` heading, and returns text up to the next same-level heading.

    Returns:
        Section text, or empty string if the ID is unknown or heading not found.
    """
    if section_id == "*":
        return skeleton_text

    title = SECTION_TITLES.get(section_id)
    if not title:
        return ""

    # Match `## N. <title>` or `### N-M. <title>` (exact title match)
    title_pattern = re.escape(title)
    pattern = rf"^(#{{2,4}})\s+\d+(?:-\d+)?\.\s+{title_pattern}\s*$"
    lines = skeleton_text.split("\n")

    start_idx: int | None = None
    start_level: int | None = None
    for i, line in enumerate(lines):
        m = re.match(pattern, line.rstrip())
        if m:
            start_idx = i
            start_level = len(m.group(1))
            break

    if start_idx is None or start_level is None:
        return ""

    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        nxt = re.match(r"^(#{2,4})\s+\d", lines[i])
        if nxt and len(nxt.group(1)) <= start_level:
            end_idx = i
            break

    return "\n".join(lines[start_idx:end_idx]).strip()


def build_context(
    agent: str,
    skeleton_path: Path,
    docs_dir: Path,
    prompt_path: Path | None = None,
    project_root: Path | None = None,
) -> str:
    """Assemble the full context to inject into an agent (section-ID based)."""
    parts: list[str] = []

    # 1. Agent system prompt (CLAUDE.md)
    if prompt_path and prompt_path.exists():
        parts.append(prompt_path.read_text(encoding="utf-8").strip())

    # 2. Project root CLAUDE.md — present in all agents, higher authority than agent prompt
    if project_root is not None:
        root_claude = project_root / "CLAUDE.md"
        if root_claude.exists():
            content = root_claude.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"# Project CLAUDE.md\n{content}")

    # 4. Extract skeleton sections (ID-based)
    if skeleton_path.exists():
        skeleton_text = skeleton_path.read_text(encoding="utf-8")
        sections = AGENT_SECTIONS_BY_ID.get(agent, [])
        if sections == ["*"]:
            parts.append(f"# Skeleton\n{skeleton_text.strip()}")
        else:
            extracted: list[str] = []
            for sid in sections:
                content = extract_section_by_id(skeleton_text, sid)
                if content:
                    extracted.append(content)
            if extracted:
                parts.append("# Skeleton (relevant sections)\n\n" + "\n\n".join(extracted))

    # 5. Extra docs
    extra = EXTRA_DOCS.get(agent, [])
    for doc_name in extra:
        if doc_name.endswith("/"):
            # Directory — read all child .md files
            dir_path = docs_dir / doc_name.rstrip("/")
            if dir_path.is_dir():
                for md_file in sorted(dir_path.glob("*.md")):
                    content = md_file.read_text(encoding="utf-8").strip()
                    if content:
                        parts.append(f"# {md_file.stem}\n{content}")
        else:
            doc_path = docs_dir / doc_name
            if doc_path.exists():
                content = doc_path.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(f"# {doc_name}\n{content}")

    return "\n\n---\n\n".join(parts)
