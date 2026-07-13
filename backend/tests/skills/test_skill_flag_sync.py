"""SKILL.md 가 언급하는 CLI 플래그가 실제 run.py 에 존재하는지 기계 검사.

dogfood 에서 `/ha-build --skip-done` 이라는 **존재하지 않는 플래그**가 ha-redesign
SKILL.md 와 코드 주석 6곳에 퍼져 있었다 (한 번도 구현된 적 없음). 문서가 유령 플래그를
안내하면 사용자는 실행 불가능한 조치를 시도하고, 에이전트는 그것을 근거로 잘못된 계획을
세운다 — 사람 눈으로는 못 잡히는 부류라 기계로 고정한다.

검사 범위: skills/ha-*/SKILL.md 의 코드 스팬/블록 중 특정 ha-* 스킬을 지목하는 것.
그 안의 `--flag` 는 그 스킬 run.py 의 argparse 에 실재해야 한다.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = REPO_ROOT / "skills"

# argparse 정의: add_argument("--flag", ...) — 인자가 다음 줄에 오는 형태도 포함.
_ADD_ARGUMENT_RE = re.compile(r'add_argument\(\s*"(--[a-z0-9-]+)"')
# 문서의 코드 스팬(`...`) 과 펜스 블록 내부 라인.
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_FENCE_RE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
# 스팬이 그 스킬을 **호출**해야 플래그를 귀속한다: `/ha-build ...` 또는 `.../ha-build/run.py ...`.
# 산문 속 단순 언급("# ha-build 시작 시점 커밋")에 옆 명령(git log --oneline)의 플래그를
# 귀속하면 오탐이 난다.
_SKILL_INVOCATION_RE = re.compile(r"(?:^|\s|/)(?:/)?(ha-[a-z]+)(?:/run\.py|\s|$)")
_FLAG_RE = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)")

# 스킬 이름이 붙어도 그 스킬의 플래그가 아닌 것 (외부 도구 인자).
_EXTERNAL_FLAGS = frozenset({"--help", "--version"})


def _skill_flags() -> dict[str, frozenset[str]]:
    flags: dict[str, frozenset[str]] = {}
    for run_py in sorted(SKILLS_DIR.glob("ha-*/run.py")):
        source = run_py.read_text(encoding="utf-8")
        flags[run_py.parent.name] = frozenset(_ADD_ARGUMENT_RE.findall(source))
    return flags


def _code_spans(text: str) -> list[str]:
    """코드 스팬 + 펜스 블록의 각 라인 (플래그와 스킬이 같은 문맥에 있는 것만 본다)."""
    spans: list[str] = []
    for fence in _FENCE_RE.findall(text):
        spans.extend(line for line in fence.splitlines() if line.strip())
    spans.extend(_INLINE_CODE_RE.findall(_FENCE_RE.sub("", text)))
    return spans


def test_skill_md_flags_exist_in_run_py() -> None:
    """SKILL.md 코드 스팬이 지목한 ha-* 스킬의 플래그는 그 스킬 run.py 에 실재해야 한다."""
    flags_by_skill = _skill_flags()
    assert flags_by_skill, "skills/ha-*/run.py 를 하나도 못 찾음 — 경로 가정 확인"

    phantom: list[str] = []
    for skill_md in sorted(SKILLS_DIR.glob("ha-*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        for raw_span in _code_spans(text):
            span = raw_span.split("#", 1)[0]  # 주석부의 산문/외부 명령은 제외
            invoked = [s for s in _SKILL_INVOCATION_RE.findall(span) if s in flags_by_skill]
            if len(invoked) != 1:
                # 호출이 없거나(외부 명령) 둘 이상(스킬 비교 문장) → 귀속 불가, 건너뜀
                continue
            skill = invoked[0]
            for flag in _FLAG_RE.findall(span):
                if flag in _EXTERNAL_FLAGS or flag in flags_by_skill[skill]:
                    continue
                phantom.append(
                    f"{skill_md.relative_to(REPO_ROOT)}: /{skill} {flag} — {span.strip()}"
                )

    assert not phantom, "존재하지 않는 플래그를 문서가 안내함:\n" + "\n".join(phantom)


def test_no_skip_done_flag_anywhere() -> None:
    """`--skip-done` 은 구현된 적 없는 유령 플래그 — 문서/주석에서 부활 금지."""
    haunted: list[str] = []
    for path in [*SKILLS_DIR.rglob("*.py"), *SKILLS_DIR.rglob("*.md")]:
        if "--skip-done" in path.read_text(encoding="utf-8"):
            haunted.append(str(path.relative_to(REPO_ROOT)))
    for path in (REPO_ROOT / "backend" / "src").rglob("*.py"):
        if "--skip-done" in path.read_text(encoding="utf-8"):
            haunted.append(str(path.relative_to(REPO_ROOT)))

    assert not haunted, "유령 플래그 --skip-done 참조: " + ", ".join(haunted)
