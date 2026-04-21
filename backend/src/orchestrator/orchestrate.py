"""Main orchestrator — entry point that coordinates the full agent workflow."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.orchestrator.config import OrchestratorConfig, load_agents_config
from src.orchestrator.context import SECTION_TITLES, extract_section_by_id
from src.orchestrator.logger import AgentLogger
from src.orchestrator.output_parser import (
    DesignVerdict,
    PhaseReviewResult,
    QaResult,
    ReviewVerdict,
    TaskItem,
    extract_filled_sections,
    parse_design_verdict,
    parse_phase_review,
    parse_phases,
    parse_pr_review,
    parse_qa_report,
)
from src.orchestrator.phase import InvalidTransitionError, Phase, PhaseManager
from src.orchestrator.pipeline import ValidationPipeline, ValidationResult
from src.orchestrator.profile_loader import ProfileLoader, ProfileNotFoundError
from src.orchestrator.runner import AgentRunner, RunResult
from src.orchestrator.security_hooks import SecurityHooks, SecurityResult
from src.orchestrator.skeleton_assembler import FragmentNotFoundError, SkeletonAssembler
from src.orchestrator.state import StateManager

logger = logging.getLogger(__name__)

# Phase-to-agent mapping (ordered tuples) — internal pipeline use
_PHASE_AGENTS: dict[Phase, tuple[str, ...]] = {
    Phase.DESIGNING: ("architect", "designer"),
    Phase.TASK_BREAKDOWN: ("orchestrator",),
    Phase.VERIFYING: ("reviewer",),
}

# Phase → single agent mapping — for dashboard REST/WS command dispatch.
# None means no direct agent execution in that phase.
PHASE_AGENT_MAP: dict[str, str | None] = {
    "planning": None,
    "designing": "architect",
    "task_breakdown": "orchestrator",
    "implementing": "backend_coder",
    "verifying": "reviewer",
    "deploying": None,
    "done": None,
}


def _extract_section_body(section_text: str) -> str:
    """Return section body text with the heading line stripped."""
    parts = section_text.split("\n", 1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()


def _replace_section_body_in_skeleton(skeleton_text: str, section_id: str, new_body: str) -> str:
    """Replace the body of a section in the skeleton while preserving the heading.

    The heading line (`## N. <title>`) is kept intact to preserve the numbering
    scheme. Body is replaced up to the next same-level heading.

    Returns:
        Updated skeleton text, or the original if section_id is not found.
    """
    title = SECTION_TITLES.get(section_id)
    if not title:
        return skeleton_text

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
        return skeleton_text

    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        nxt = re.match(r"^(#{2,4})\s+\d", lines[i])
        if nxt and len(nxt.group(1)) <= start_level:
            end_idx = i
            break

    heading = lines[start_idx]
    new_section = [heading, "", new_body.rstrip(), ""] if new_body.strip() else [heading, ""]
    result = lines[:start_idx] + new_section + lines[end_idx:]
    return "\n".join(result)


@dataclass
class Orchestra:
    """Orchestrator that coordinates the full agent workflow."""

    project_dir: Path
    config: OrchestratorConfig = field(init=False)
    state: StateManager = field(init=False)
    phase_manager: PhaseManager = field(init=False)
    runner: AgentRunner = field(init=False)
    pipeline: ValidationPipeline = field(init=False)
    agent_logger: AgentLogger = field(init=False)
    # Per-task lock — serializes retries within a task, no interference between tasks
    _task_locks: dict[str, asyncio.Lock] = field(init=False)
    # Lazy-cached SecurityHooks — profile detected and injected on first verify() call.
    _security_hooks: SecurityHooks | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.project_dir = Path(self.project_dir).resolve()
        self.config = load_agents_config(self.project_dir / "agents.yaml")
        self.state = StateManager(self.project_dir)
        self.phase_manager = PhaseManager(self.state)
        self.agent_logger = AgentLogger(self.project_dir / "logs" / "agents")
        self.runner = AgentRunner(
            config=self.config,
            project_dir=self.project_dir,
            logger=self.agent_logger,
        )
        self.pipeline = ValidationPipeline(self.project_dir)
        self._task_locks: dict[str, asyncio.Lock] = {}
        self._security_hooks = None

    def _get_security_hooks(self) -> SecurityHooks:
        """Lazily create and cache profile-based SecurityHooks (v2).

        Injects whitelist.runtime + whitelist.dev union from the first detected
        profile. Falls back to default module whitelist on detection failure
        (legacy compat). Built once per project and cached.
        """
        if self._security_hooks is not None:
            return self._security_hooks
        try:
            loader = ProfileLoader(project_dir=self.project_dir)
            matches = loader.detect()
        except (FileNotFoundError, ProfileNotFoundError, OSError) as exc:
            # File/dir absence or registry load failure — fallback with logging.
            # Programming errors (TypeError/AttributeError) propagate to caller.
            logger.info("프로파일 감지 실패 — 기본 SecurityHooks 사용: %s", exc)
            self._security_hooks = SecurityHooks()
            return self._security_hooks

        if not matches:
            logger.info("매칭 프로파일 없음 — 기본 SecurityHooks 사용")
            self._security_hooks = SecurityHooks()
            return self._security_hooks

        # Use first matching profile (monorepo uses top-level root)
        profile = matches[0].profile
        logger.info(
            "SecurityHooks v2 — 프로파일 '%s' whitelist 주입 (runtime=%d, dev=%d)",
            profile.id,
            len(profile.whitelist.runtime),
            len(profile.whitelist.dev),
        )
        self._security_hooks = SecurityHooks.from_profile(profile)
        return self._security_hooks

    def _get_task_lock(self, task_id: str) -> asyncio.Lock:
        """Return a per-task lock, creating one if needed."""
        if task_id not in self._task_locks:
            self._task_locks[task_id] = asyncio.Lock()
        return self._task_locks[task_id]

    @classmethod
    def from_project_dir(cls, project_dir: str | Path) -> Orchestra:
        """Factory method — create an Orchestra instance from a project directory."""
        return cls(project_dir=Path(project_dir))

    async def design(
        self,
        requirements: str,
        max_negotiation_rounds: int = 3,
    ) -> dict[str, RunResult]:
        """Design phase — Architect / Designer negotiation loop.

        If the Designer outputs ``## Design Verdict: CONFLICT``, the API
        requests are forwarded to the Architect for redesign. ACCEPT or
        no marker is treated as agreement.

        Returns:
            {"architect": RunResult, "designer": RunResult} from the last round.
        """
        self.phase_manager.transition(Phase.DESIGNING)

        _no_result = RunResult(agent="", output="", success=False, duration_ms=0, attempts=0)
        architect_result: RunResult = _no_result
        designer_result: RunResult = _no_result
        architect_prompt = requirements

        for round_num in range(1, max_negotiation_rounds + 1):
            architect_result = await self.runner.run("architect", architect_prompt)
            self._log_result("architect", architect_result)

            if not architect_result.success or not architect_result.output.strip():
                logger.error("Architect 실패 또는 빈 출력 — design() 중단 (라운드 %d)", round_num)
                return {
                    "architect": architect_result,
                    "designer": RunResult(
                        agent="designer",
                        output="",
                        success=False,
                        duration_ms=0,
                        attempts=0,
                        error="Architect 실패로 인해 Designer 실행 취소",
                    ),
                }

            designer_prompt = (
                f"{requirements}\n\n"
                f"<architect_output>\n{architect_result.output}\n</architect_output>"
            )
            designer_result = await self.runner.run("designer", designer_prompt)
            self._log_result("designer", designer_result)

            verdict = parse_design_verdict(designer_result.output)

            if verdict is None or verdict.verdict == DesignVerdict.ACCEPT:
                logger.info("설계 합의 완료 (라운드 %d/%d)", round_num, max_negotiation_rounds)
                break

            if round_num < max_negotiation_rounds:
                requests_text = (
                    "\n".join(f"- {r}" for r in verdict.api_requests) or "(세부 요청 없음)"
                )
                architect_prompt = (
                    f"{requirements}\n\n"
                    f"<design_conflicts>\n"
                    f"Designer가 다음 API 추가를 요청했습니다 (라운드 {round_num}/{max_negotiation_rounds}):\n"
                    f"{requests_text}\n"
                    f"</design_conflicts>"
                )
                logger.warning(
                    "설계 충돌 — 재협의 라운드 %d/%d (API 요청 %d개)",
                    round_num,
                    max_negotiation_rounds,
                    len(verdict.api_requests),
                )
            else:
                logger.warning(
                    "설계 충돌 해소 실패 — 최대 라운드 %d 도달. 마지막 결과로 진행.",
                    max_negotiation_rounds,
                )

        results: dict[str, RunResult] = {
            "architect": architect_result,
            "designer": designer_result,
        }
        self.state.save_task_result(
            "design",
            {
                "architect": self._result_to_dict(architect_result),
                "designer": self._result_to_dict(designer_result),
            },
        )
        return results

    def materialize_skeleton(
        self,
        architect_output: str,
        designer_output: str,
    ) -> Path:
        """Parse Architect + Designer output and write docs/skeleton.md.

        Extracts sections from agent output and concatenates them. Once this
        file exists, runner.py auto-injects it into all subsequent agents.

        Returns:
            Path to the generated skeleton.md.
        """
        skeleton_path = self.project_dir / "docs" / "skeleton.md"

        # Extract sections from both outputs. Architect first, then Designer.
        raw_sections = extract_filled_sections(architect_output)
        raw_sections += extract_filled_sections(designer_output)
        if not raw_sections:
            raise ValueError(
                "skeleton 섹션 추출 실패 — Architect/Designer 출력에서 유효한 섹션을 찾을 수 없음"
            )

        # Same section_num → Designer overwrites Architect (Python dict preserves
        # first-insertion order, so Architect-declared sections come first).
        deduped: dict[str, str] = {s.section_num: s.content for s in raw_sections}
        filled_text = "\n\n".join(deduped.values())

        skeleton_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            skeleton_path.write_text(filled_text, encoding="utf-8")
        except OSError as exc:
            logger.error("skeleton.md 쓰기 실패: %s", exc)
            raise

        logger.info("skeleton.md 생성 완료 — %d개 섹션 채움", len(deduped))
        return skeleton_path

    def materialize_skeleton_v2(
        self,
        architect_output: str,
        designer_output: str,
        profile_ids: list[str],
        *,
        harness_dir: Path | None = None,
        included_overrides: list[str] | None = None,
    ) -> Path:
        """v2 — assemble empty skeleton from profiles, then merge agent output by section_id.

        Unlike v1 which concatenates raw agent output, v2 lets the profile
        template define structure first; agents fill section bodies only.

        Raises:
            ValueError: No section_id matches found in either agent output.
        """
        skeleton_path = self.assemble_skeleton_for_profiles(
            profile_ids,
            harness_dir=harness_dir,
            included_overrides=included_overrides,
        )
        skeleton_text = skeleton_path.read_text(encoding="utf-8")

        # Architect first, then Designer — same section_id means Designer wins.
        raw = extract_filled_sections(architect_output) + extract_filled_sections(designer_output)
        merged_by_id: dict[str, str] = {
            s.section_id: _extract_section_body(s.content) for s in raw if s.section_id is not None
        }
        if not merged_by_id:
            raise ValueError(
                "skeleton 섹션 추출 실패 — 에이전트 출력에서 SECTION_TITLES 매칭되는 "
                "헤딩을 찾지 못함. 에이전트가 표준 섹션 제목을 쓰는지 확인."
            )

        for sid, body in merged_by_id.items():
            skeleton_text = _replace_section_body_in_skeleton(skeleton_text, sid, body)

        try:
            skeleton_path.write_text(skeleton_text, encoding="utf-8")
        except OSError as exc:
            logger.error("skeleton.md v2 쓰기 실패: %s", exc)
            raise

        logger.info(
            "skeleton.md v2 생성 완료 — 프로파일 %s, %d 섹션 merge",
            profile_ids,
            len(merged_by_id),
        )
        return skeleton_path

    def assemble_skeleton_for_profiles(
        self,
        profile_ids: list[str],
        *,
        title: str | None = None,
        harness_dir: Path | None = None,
        included_overrides: list[str] | None = None,
    ) -> Path:
        """Assemble an empty skeleton from profile templates (Harness v2).

        Uses the union of each profile's skeleton_sections.required
        (or included_overrides if given), ordered by the first profile's
        skeleton_sections.order.

        Returns:
            Path to the generated skeleton.md.
        """
        if not profile_ids:
            raise ValueError("profile_ids 비어 있음")

        loader = ProfileLoader(harness_dir=harness_dir, project_dir=self.project_dir)
        profiles = []
        for pid in profile_ids:
            try:
                profiles.append(loader.load(pid))
            except ProfileNotFoundError as exc:
                logger.error("프로파일 '%s' 로드 실패: %s", pid, exc)
                raise

        if included_overrides is not None:
            included = list(included_overrides)
        else:
            seen: set[str] = set()
            included: list[str] = []
            for p in profiles:
                for sid in p.skeleton_sections.required:
                    if sid not in seen:
                        seen.add(sid)
                        included.append(sid)

        # Primary profile's order first — remaining IDs appended at end
        primary_order = list(profiles[0].skeleton_sections.order)
        ordered: list[str] = []
        seen_o: set[str] = set()
        for sid in primary_order:
            if sid in included and sid not in seen_o:
                ordered.append(sid)
                seen_o.add(sid)
        for sid in included:
            if sid not in seen_o:
                ordered.append(sid)
                seen_o.add(sid)

        assembler = SkeletonAssembler(harness_dir=harness_dir, project_dir=self.project_dir)
        try:
            content = assembler.assemble(
                ordered, title=title or f"Project Skeleton — {self.project_dir.name}"
            )
        except FragmentNotFoundError as exc:
            logger.error("skeleton 조각 누락: %s", exc)
            raise

        skeleton_path = self.project_dir / "docs" / "skeleton.md"
        skeleton_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            skeleton_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            logger.error("skeleton.md 쓰기 실패: %s", exc)
            raise

        logger.info(
            "skeleton.md 조립 완료 — 프로파일=%s, 섹션=%d개",
            profile_ids,
            len(ordered),
        )
        return skeleton_path

    async def implement(self, task_id: str, agent: str, prompt: str) -> RunResult:
        """Implementation phase — run a single task with the given agent."""
        current = self.phase_manager.current_phase
        if current != Phase.IMPLEMENTING:
            self.phase_manager.transition(Phase.IMPLEMENTING)

        result = await self.runner.run(agent, prompt)
        self._log_result(agent, result)
        self.state.save_task_result(task_id, self._result_to_dict(result))
        return result

    async def verify(
        self,
        task_id: str,
        *,
        is_frontend: bool = False,
        allowed_endpoints: list[str] | None = None,
    ) -> dict[str, Any]:
        """Verification phase — SecurityHooks + ValidationPipeline + Reviewer agent.

        Returns:
            {"security", "pipeline", "reviewer", "passed"}.
            On failure, transitions back to IMPLEMENTING.
        """
        if self.phase_manager.current_phase != Phase.VERIFYING:
            try:
                self.phase_manager.transition(Phase.VERIFYING)
            except InvalidTransitionError:
                # Another parallel task already transitioned to VERIFYING — ignore
                logger.debug(
                    "VERIFYING 전이 생략 — 현재 Phase: %s", self.phase_manager.current_phase
                )

        # 1. Security hooks — analyze agent output code
        task_result = self.state.load_task_result(task_id)
        agent_output = (
            (task_result or {}).get("output", "") if isinstance(task_result, dict) else ""
        )
        security_result: SecurityResult = self._get_security_hooks().run_all(
            agent_output,
            is_frontend=is_frontend,
            allowed_endpoints=allowed_endpoints,
        )
        if security_result.blocked:
            block_msgs = [
                f.message for f in security_result.findings if f.severity.value == "BLOCK"
            ]
            logger.error(
                "보안 훅 BLOCK — task_id=%s findings=%s",
                task_id,
                block_msgs,
            )

        # 2. Lint / type-check / test pipeline
        pipeline_result: ValidationResult = await self.pipeline.run_all()

        # 3. Reviewer agent
        reviewer_prompt = (
            f"태스크 ID: {task_id}\n\n"
            f"<security_summary>\n{security_result.summary}\n</security_summary>\n\n"
            f"<validation_summary>\n{pipeline_result.summary}\n</validation_summary>\n\n"
            f"<task_output>\n{agent_output or '결과 없음'}\n</task_output>"
        )
        reviewer_result = await self.runner.run("reviewer", reviewer_prompt)
        self._log_result("reviewer", reviewer_result)

        pipeline_passed = pipeline_result.passed
        reviewer_passed = self._is_reviewer_approved(reviewer_result)
        security_passed = not security_result.blocked

        all_passed = security_passed and pipeline_passed and reviewer_passed

        if not all_passed:
            logger.warning(
                "검증 실패 — task_id=%s security=%s pipeline=%s reviewer=%s. IMPLEMENTING으로 전이.",
                task_id,
                security_result.summary,
                pipeline_result.summary,
                "pass" if reviewer_passed else "reject",
            )
            try:
                self.phase_manager.transition(Phase.IMPLEMENTING)
            except InvalidTransitionError:
                logger.error(
                    "VERIFYING → IMPLEMENTING 전이 실패. 현재 Phase: %s",
                    self.phase_manager.current_phase,
                )

        outcome: dict[str, Any] = {
            "security": security_result,
            "pipeline": pipeline_result,
            "reviewer": reviewer_result,
            "passed": all_passed,
        }
        self.state.save_task_result(
            f"verify_{task_id}",
            {
                "security_summary": security_result.summary,
                "security_blocked": security_result.blocked,
                "pipeline_summary": pipeline_result.summary,
                "pipeline_passed": pipeline_passed,
                "reviewer": self._result_to_dict(reviewer_result),
                "passed": all_passed,
            },
        )
        return outcome

    async def implement_with_retry(
        self,
        task_id: str,
        agent: str,
        prompt: str,
        max_retries: int = 3,
        *,
        is_frontend: bool = False,
        allowed_endpoints: list[str] | None = None,
    ) -> dict[str, Any]:
        """Implement + verify in a retry loop until Reviewer APPROVE.

        Returns:
            {"implement": RunResult, "verify": dict, "attempts": int, "passed": bool}
        """
        last_impl: RunResult | None = None
        last_verify: dict[str, Any] = {}
        original_prompt = prompt  # preserve original — avoid nesting on retries

        # Per-task-id lock: serializes retry cycles within a task.
        # Different task_ids run in parallel — phase transitions are best-effort.
        async with self._get_task_lock(task_id):
            for attempt in range(1, max_retries + 1):
                impl_result = await self.implement(task_id, agent, prompt)
                verify_result = await self.verify(
                    task_id,
                    is_frontend=is_frontend,
                    allowed_endpoints=allowed_endpoints,
                )
                last_impl = impl_result
                last_verify = verify_result

                if verify_result.get("passed", False):
                    logger.info("태스크 %s APPROVE (시도 %d/%d)", task_id, attempt, max_retries)
                    return {
                        "implement": impl_result,
                        "verify": verify_result,
                        "attempts": attempt,
                        "passed": True,
                    }

                if attempt < max_retries:
                    raw_reviewer = verify_result.get("reviewer")
                    violations: list[str] = []
                    if isinstance(raw_reviewer, RunResult):
                        parsed_review = parse_pr_review(raw_reviewer.output)
                        violations = parsed_review.violations if parsed_review else []
                        if not violations and raw_reviewer.output:
                            violations = [raw_reviewer.output[:500]]
                    # Always append feedback to original prompt — prevent nesting
                    prompt = (
                        f"{original_prompt}\n\n"
                        f"<review_feedback>\n"
                        f"이전 구현이 REJECT되었습니다 (시도 {attempt}/{max_retries}).\n"
                        f"수정 사항:\n"
                        + "\n".join(f"- {v}" for v in violations)
                        + "\n</review_feedback>"
                    )
                    logger.warning("태스크 %s REJECT — 재시도 %d/%d", task_id, attempt, max_retries)
                else:
                    logger.error(
                        "태스크 %s — 최대 재시도 %d회 초과. 에스컬레이션 필요.",
                        task_id,
                        max_retries,
                    )
                    self.agent_logger.log_escalation(
                        agent=agent,
                        reason=f"태스크 {task_id} REJECT {max_retries}회 — PM 에스컬레이션",
                        escalated_to="PM",
                    )

            return {
                "implement": last_impl,
                "verify": last_verify,
                "attempts": max_retries,
                "passed": False,
            }

    async def review_phase(
        self,
        phase_num: int,
        task_ids: list[str],
    ) -> PhaseReviewResult | None:
        """Review an entire phase after all its tasks are complete.

        Returns:
            PhaseReviewResult, or None if parsing fails.
        """
        task_summaries: list[str] = []
        for tid in task_ids:
            result = self.state.load_task_result(tid)
            if result:
                output = result.get("output", "")[:500]  # summary only
                task_summaries.append(f"[{tid}]\n{output}")

        phase_prompt = (
            f"Phase {phase_num} 리뷰를 수행하세요.\n\n"
            f"<phase_tasks>\n" + "\n\n".join(task_summaries) + f"\n</phase_tasks>\n\n"
            f"Phase {phase_num}의 모든 태스크가 완료되었습니다. "
            f"Phase 리뷰 형식으로 결과를 출력하세요."
        )

        if self.phase_manager.current_phase != Phase.VERIFYING:
            self.phase_manager.transition(Phase.VERIFYING)
        reviewer_result = await self.runner.run("reviewer", phase_prompt)
        self._log_result("reviewer", reviewer_result)
        self.state.save_task_result(
            f"phase_{phase_num}_review",
            self._result_to_dict(reviewer_result),
        )

        parsed = parse_phase_review(reviewer_result.output)
        if parsed is None:
            logger.warning("Phase %d 리뷰 결과 파싱 실패.", phase_num)
        return parsed

    async def qa_phase(
        self,
        phase_num: int,
        task_ids: list[str],
    ) -> QaResult | None:
        """Phase QA — verify API contract, state flow, and doc consistency.

        Called after review_phase() APPROVE. The QA agent writes tests only
        (no functional code changes) and returns a health score (0-10).

        Returns:
            QaResult, or None on parse failure (treated as pass).
        """
        task_summaries: list[str] = []
        for tid in task_ids:
            result = self.state.load_task_result(tid)
            if result:
                output = result.get("output", "")[:500]
                task_summaries.append(f"[{tid}]\n{output}")

        skeleton_path = self.project_dir / "docs" / "skeleton.md"
        skeleton_text = skeleton_path.read_text(encoding="utf-8") if skeleton_path.exists() else ""

        qa_prompt = (
            f"Phase {phase_num} QA를 수행하세요.\n\n"
            f"<skeleton>\n{skeleton_text}\n</skeleton>\n\n"
            f"<phase_tasks>\n" + "\n\n".join(task_summaries) + "\n</phase_tasks>\n\n"
            "QA Report 형식으로 결과를 출력하세요."
        )

        qa_result = await self.runner.run("qa", qa_prompt)
        self._log_result("qa", qa_result)
        self.state.save_task_result(
            f"qa_{phase_num}",
            self._result_to_dict(qa_result),
        )

        parsed = parse_qa_report(qa_result.output)
        if parsed is None:
            logger.warning("Phase %d QA 리포트 파싱 실패 — 통과 처리.", phase_num)
        else:
            logger.info(
                "Phase %d QA — health_score=%d/10 passed=%s issues=%d",
                phase_num,
                parsed.health_score,
                parsed.passed,
                len(parsed.issues),
            )
        return parsed

    async def run_breakdown(
        self,
        requirements: str,
        design_results: dict[str, RunResult],
    ) -> tuple[list[list[TaskItem]], dict[str, Any]]:
        """Task breakdown — run the Orchestrator agent and parse phases.

        Returns:
            (phases, breakdown_dict) where phases is a list of TaskItem lists
            per phase (empty list on parse failure).
        """
        self.phase_manager.transition(Phase.TASK_BREAKDOWN)
        breakdown_prompt = (
            f"{requirements}\n\n"
            f"skeleton.md 에 Architect + Designer 합의 결과가 모두 병합되어 있다. "
            f"해당 문서의 섹션들을 참조해 태스크 분해하라."
        )
        breakdown_result = await self.runner.run("orchestrator", breakdown_prompt)
        self._log_result("orchestrator", breakdown_result)
        breakdown_dict = self._result_to_dict(breakdown_result)
        self.state.save_task_result("task_breakdown", breakdown_dict)

        phases: list[list[TaskItem]] = parse_phases(breakdown_result.output)
        if not phases:
            logger.warning("Orchestrator 태스크 분해 실패 — 파싱된 Phase 없음")

        return phases, breakdown_dict

    async def run_phases(
        self,
        phases: list[list[TaskItem]],
        *,
        max_task_retries: int = 3,
        max_phase_retries: int = 2,
    ) -> dict[str, Any]:
        """Execute tasks per phase with review and QA gates.

        Returns:
            {"phases": [{"phase_num", "tasks", "review", "passed"}], "success": bool}
        """
        results: list[dict[str, Any]] = []
        all_passed = True
        allowed_endpoints = self._extract_allowed_endpoints()

        for phase_num, phase_tasks in enumerate(phases, start=1):
            if not phase_tasks:
                logger.warning("Phase %d — 태스크 없음, 건너뜀", phase_num)
                results.append(
                    {"phase_num": phase_num, "tasks": {}, "review": None, "passed": True}
                )
                continue

            phase_result: dict[str, Any] = {
                "phase_num": phase_num,
                "tasks": {},
                "review": None,
                "qa": None,
                "passed": False,
            }
            # Skip already-passed tasks on phase retry
            passed_task_ids: set[str] = set()

            for phase_attempt in range(1, max_phase_retries + 1):
                task_ids: list[str] = [t.id for t in phase_tasks]
                pending = [t for t in phase_tasks if t.id not in passed_task_ids]

                if not pending:
                    logger.debug("Phase %d — 모든 태스크 이미 통과", phase_num)
                else:

                    async def _run_task(task: TaskItem) -> tuple[str, dict[str, Any]]:
                        tid = task.id
                        is_frontend: bool = task.agent == "frontend_coder"
                        try:
                            result = await self.implement_with_retry(
                                tid,
                                task.agent,
                                task.description,
                                max_retries=max_task_retries,
                                is_frontend=is_frontend,
                                allowed_endpoints=allowed_endpoints,
                            )
                        except Exception as exc:
                            logger.error("태스크 %s 실행 중 예외: %s", tid, exc)
                            result = {"output": "", "error": str(exc), "passed": False}
                        return tid, result

                    batch = await asyncio.gather(
                        *[_run_task(t) for t in pending],
                        return_exceptions=True,
                    )
                    for item in batch:
                        # Swallow Exception only; re-raise BaseException (CancelledError etc.)
                        # — same propagation pattern as runner.py::run_many.
                        if isinstance(item, Exception):
                            logger.error("병렬 태스크 예외 (gather): %s", item)
                            continue
                        if isinstance(item, BaseException):
                            raise item
                        tid, task_result = item
                        phase_result["tasks"][tid] = task_result
                        if task_result.get("passed", False):
                            passed_task_ids.add(tid)

                review = await self.review_phase(phase_num, task_ids)
                phase_result["review"] = review

                if review is not None and review.verdict == ReviewVerdict.APPROVE:
                    # Reviewer APPROVE → QA verification (API contract / state flow / docs)
                    qa = await self.qa_phase(phase_num, task_ids)
                    phase_result["qa"] = qa
                    qa_passed = qa is None or qa.passed  # treat parse failure as pass
                    if qa_passed:
                        phase_result["passed"] = True
                        logger.info(
                            "Phase %d APPROVE + QA PASS (시도 %d/%d)",
                            phase_num,
                            phase_attempt,
                            max_phase_retries,
                        )
                        break
                    logger.warning(
                        "Phase %d QA FAIL — health_score=%d/10 issues=%s",
                        phase_num,
                        qa.health_score if qa else 0,
                        [i[:80] for i in (qa.issues if qa else [])],
                    )

                if phase_attempt < max_phase_retries:
                    logger.warning(
                        "Phase %d REJECT — 재시도 %d/%d",
                        phase_num,
                        phase_attempt,
                        max_phase_retries,
                    )
                else:
                    logger.error("Phase %d — 최대 재시도 초과.", phase_num)
                    all_passed = False

            results.append(phase_result)

            if not phase_result["passed"]:
                all_passed = False
                logger.error("Phase %d 실패 — 이후 Phase 중단.", phase_num)
                break

        return {"phases": results, "success": all_passed}

    async def run_pipeline_with_phases(
        self,
        requirements: str,
        max_task_retries: int = 3,
        max_phase_retries: int = 2,
        *,
        profile_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Full pipeline in a single call (non-interactive).

        For interactive gates, use pipeline_runner.run() instead.
        When profile_ids is set, uses v2 path (materialize_skeleton_v2).

        Returns:
            {"design", "breakdown", "phases", "success"}
        """
        # 1. Design
        design_results = await self.design(requirements)
        if not design_results["architect"].success:
            logger.error("Architect 실패 — run_pipeline_with_phases() 중단")
            return {"design": design_results, "breakdown": {}, "phases": [], "success": False}
        try:
            if profile_ids:
                self.materialize_skeleton_v2(
                    architect_output=design_results["architect"].output,
                    designer_output=design_results["designer"].output,
                    profile_ids=profile_ids,
                )
            else:
                self.materialize_skeleton(
                    architect_output=design_results["architect"].output,
                    designer_output=design_results["designer"].output,
                )
        except ValueError as exc:
            logger.error("skeleton 생성 실패 — run_pipeline_with_phases() 중단: %s", exc)
            return {"design": design_results, "breakdown": {}, "phases": [], "success": False}

        # 2. Task breakdown
        phases, breakdown_dict = await self.run_breakdown(requirements, design_results)
        if not phases:
            return {
                "design": design_results,
                "breakdown": breakdown_dict,
                "phases": [],
                "success": False,
            }

        # 3. Phase execution
        phase_results = await self.run_phases(
            phases,
            max_task_retries=max_task_retries,
            max_phase_retries=max_phase_retries,
        )

        if phase_results["success"]:
            self.phase_manager.transition(Phase.DEPLOYING)
            self.phase_manager.transition(Phase.DONE)
            logger.info("전체 파이프라인 완료 — Phase.DONE")

        return {
            "design": design_results,
            "breakdown": breakdown_dict,
            "phases": phase_results["phases"],
            "success": phase_results["success"],
        }

    def _is_reviewer_approved(self, result: RunResult) -> bool:
        """Parse APPROVE/REJECT from Reviewer output.

        Falls back to subprocess success if no marker is found.
        """
        parsed = parse_pr_review(result.output)
        if parsed is not None:
            return parsed.verdict == ReviewVerdict.APPROVE
        # Parse failure fallback — use subprocess success
        return result.success and not result.escalated

    def _log_result(self, agent: str, result: RunResult) -> None:
        """Log the run result at the appropriate level."""
        if result.escalated:
            logger.warning(
                "에이전트 에스컬레이션 — agent=%s error=%s",
                agent,
                result.error,
            )
        elif not result.success:
            logger.error(
                "에이전트 실행 실패 — agent=%s error=%s",
                agent,
                result.error,
            )

    @staticmethod
    def _result_to_dict(result: RunResult) -> dict[str, Any]:
        """Convert a RunResult into a JSON-serializable dict."""
        return {
            "agent": result.agent,
            "output": result.output,
            "success": result.success,
            "duration_ms": result.duration_ms,
            "attempts": result.attempts,
            "error": result.error,
            "escalated": result.escalated,
        }

    # Extract endpoint rows from interface.http section markdown table
    # | GET | /api/projects | ... |  → "GET /api/projects"
    _ENDPOINT_ROW = re.compile(
        r"^\|\s*(GET|POST|PUT|PATCH|DELETE)\s*\|\s*(/[^|\s]+)",
        re.MULTILINE | re.IGNORECASE,
    )

    def _extract_allowed_endpoints(self) -> list[str]:
        """Extract allowed endpoints from skeleton.md `interface.http` section.

        Returns:
            List like ["GET /api/projects", ...]. Empty if skeleton.md is
            missing or the section is empty (disables contract validator).
        """
        skeleton_path = self.project_dir / "docs" / "skeleton.md"
        if not skeleton_path.exists():
            return []

        skeleton_text = skeleton_path.read_text(encoding="utf-8")
        section_text = extract_section_by_id(skeleton_text, "interface.http")
        if not section_text:
            return []

        return [
            f"{m.group(1).upper()} {m.group(2).rstrip()}"
            for m in self._ENDPOINT_ROW.finditer(section_text)
        ]
