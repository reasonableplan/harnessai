"""Skeleton 섹션 매핑 + 컨텍스트 주입."""

from __future__ import annotations

import re
from pathlib import Path

# 에이전트별 skeleton 섹션 매핑 테이블
# skeleton_template.md의 14-3에서 정의한 규칙과 동기화
SECTION_MAP: dict[str, list[int | str]] = {
    "architect": ["*"],  # 전체
    "designer": [1, 2, "3-frontend", 7, 8, "9-frontend", 10, "14-1", "14-4"],
    "orchestrator": [1, 2, 4, "14-1", "14-2", 15, 16, 17],
    "backend_coder": [1, 2, "3-backend", 5, 6, 7, "9-backend", 10, "14-4", 18],
    "frontend_coder": [1, 2, "3-frontend", 7, 8, "9-frontend", 10, "14-4", 18],
    "reviewer": ["*"],  # 전체 (요약 버전)
    "qa": [1, 2, 7, 9, 10, "14-2", "14-4", "14-5", 18],
}

# 에이전트별 추가 문서
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


def extract_section(skeleton_text: str, section_num: int | str) -> str:
    """Skeleton에서 특정 섹션을 추출한다.

    Args:
        skeleton_text: skeleton.md 전체 텍스트
        section_num: 섹션 번호 (예: 1, 7, "14-1", "3-frontend")

    Returns:
        해당 섹션의 텍스트. 없으면 빈 문자열.
    """
    # "3-frontend" 같은 특수 키 처리
    if isinstance(section_num, str) and "-" in section_num:
        parts = section_num.split("-", 1)
        if parts[1] in ("frontend", "backend"):
            # 섹션 전체를 추출 후 서브섹션 필터링은 호출자에 위임
            # 지금은 섹션 전체를 반환
            section_num = parts[0]
            if section_num.isdigit():
                section_num = int(section_num)

    if isinstance(section_num, str) and section_num == "*":
        return skeleton_text

    # "## 7." 또는 "## 14." 또는 "### 14-1." 패턴 매칭
    section_str = str(section_num)
    pattern = rf"^(#{{2,4}})\s+{re.escape(section_str)}[\.\s]"
    lines = skeleton_text.split("\n")

    start_idx = None
    start_level = None

    for i, line in enumerate(lines):
        match = re.match(pattern, line)
        if match:
            start_idx = i
            start_level = len(match.group(1))  # # 개수
            break

    if start_idx is None:
        return ""

    # 같은 레벨 이상의 다음 헤딩까지 추출
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        heading_match = re.match(r"^(#{2,4})\s+\d", lines[i])
        if heading_match and len(heading_match.group(1)) <= start_level:
            end_idx = i
            break

    return "\n".join(lines[start_idx:end_idx]).strip()


def fill_skeleton_template(
    template_text: str,
    sections: list[dict[str, str]],
) -> str:
    """템플릿의 섹션을 채워진 내용으로 교체한다.

    Args:
        template_text: skeleton_template.md 전체 텍스트
        sections: [{"section_num": "6", "content": "..."}, ...] 형태의 채워진 섹션 목록

    Returns:
        섹션이 교체된 skeleton 텍스트
    """
    if not sections:
        return template_text

    # section_num → content 매핑 (나중에 온 것이 이전 것을 덮어씀)
    filled: dict[str, str] = {s["section_num"]: s["content"] for s in sections}
    lines = template_text.split("\n")
    result: list[str] = []
    i = 0

    while i < len(lines):
        heading_match = re.match(r"^(#{2,4})\s+(\d+(?:-\d+)?)[.\s]", lines[i])
        if heading_match:
            section_num = heading_match.group(2)
            heading_level = len(heading_match.group(1))

            if section_num in filled:
                result.append(filled[section_num])
                # 템플릿 내 해당 섹션 범위 스킵
                i += 1
                while i < len(lines):
                    nxt = re.match(r"^(#{2,4})\s+\d", lines[i])
                    if nxt and len(nxt.group(1)) <= heading_level:
                        break
                    i += 1
                continue

        result.append(lines[i])
        i += 1

    return "\n".join(result)


def build_context(
    agent: str,
    skeleton_path: Path,
    docs_dir: Path,
    prompt_path: Path | None = None,
) -> str:
    """에이전트에 주입할 전체 컨텍스트를 조합한다.

    Args:
        agent: 에이전트 이름
        skeleton_path: skeleton.md 경로
        docs_dir: docs/ 디렉토리 경로
        prompt_path: 에이전트별 CLAUDE.md 경로

    Returns:
        조합된 컨텍스트 문자열
    """
    parts: list[str] = []

    # 1. 에이전트 시스템 프롬프트 (CLAUDE.md)
    if prompt_path and prompt_path.exists():
        parts.append(prompt_path.read_text(encoding="utf-8").strip())

    # 2. skeleton 섹션 추출
    if skeleton_path.exists():
        skeleton_text = skeleton_path.read_text(encoding="utf-8")
        sections = SECTION_MAP.get(agent, [])

        if sections == ["*"]:
            parts.append(f"# Skeleton\n{skeleton_text.strip()}")
        else:
            extracted: list[str] = []
            for sec in sections:
                content = extract_section(skeleton_text, sec)
                if content:
                    extracted.append(content)
            if extracted:
                parts.append(f"# Skeleton (관련 섹션)\n\n" + "\n\n".join(extracted))

    # 3. 추가 문서
    extra = EXTRA_DOCS.get(agent, [])
    for doc_name in extra:
        if doc_name.endswith("/"):
            # 디렉토리 — 하위 .md 파일 전부 읽기
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
