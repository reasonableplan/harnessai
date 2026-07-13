"""Agent prompts must stay consistent with the v2 /ha-* pipeline contracts.

Regression for the 2026-07-08 audit:
- orchestrator offered `qa` in its allowed-agent enum while the ha-plan
  guardrail forbids assigning reviewer/qa tasks in v2 (the prompt would make
  the LLM emit a qa task that the pipeline then rejects).
- frontend_coder's §3 checklist asserted Zustand-only unconditionally while
  its own 자율 결정 금지 table defers the server-state strategy to
  conventions.md (Zustand only vs +TanStack Query hybrid) — and the Designer
  prompt allows the hybrid per conventions.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENTS_DIR = REPO_ROOT / "backend" / "agents"


def test_orchestrator_agent_enum_excludes_qa() -> None:
    text = (AGENTS_DIR / "orchestrator" / "CLAUDE.md").read_text(encoding="utf-8")
    enum_lines = [line for line in text.splitlines() if line.startswith("- 에이전트는 반드시")]
    assert enum_lines, "orchestrator: allowed-agent enum 라인 없음"
    assert "`qa`" not in enum_lines[0], (
        "orchestrator: v2 태스크 enum 에 qa 잔존 (ha-plan 의 reviewer/qa 배정 금지와 상충)"
    )


def test_frontend_coder_state_checklist_defers_to_conventions() -> None:
    text = (AGENTS_DIR / "frontend_coder" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "서버 데이터 포함 모든 상태는 Zustand store" not in text, (
        "frontend_coder: §3 이 Zustand-only 를 무조건 문형으로 강제 (conventions 결정권과 모순)"
    )
    assert "### 3. 상태 관리 — 전략은 conventions" in text, (
        "frontend_coder: §3 헤딩이 conventions 조건부임을 명시해야 함"
    )
