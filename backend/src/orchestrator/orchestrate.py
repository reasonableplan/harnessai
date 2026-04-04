"""메인 오케스트레이터 — 전체 워크플로우를 조율하는 진입점."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.orchestrator.config import OrchestratorConfig, load_agents_config
from src.orchestrator.context import build_context, fill_skeleton_template
from src.orchestrator.logger import AgentLogger
from src.orchestrator.output_parser import (
    PhaseReviewResult,
    ReviewVerdict,
    extract_filled_sections,
    parse_phase_review,
    parse_pr_review,
)
from src.orchestrator.security_hooks import SecurityHooks, SecurityResult
from src.orchestrator.phase import InvalidTransitionError, Phase, PhaseManager
from src.orchestrator.pipeline import ValidationPipeline, ValidationResult
from src.orchestrator.runner import AgentRunner, RunResult
from src.orchestrator.state import StateManager

logger = logging.getLogger(__name__)

# Phase별 에이전트 매핑 (순서가 있는 경우 tuple)
_PHASE_AGENTS: dict[Phase, tuple[str, ...]] = {
    Phase.DESIGNING: ("architect", "designer"),
    Phase.TASK_BREAKDOWN: ("orchestrator",),
    Phase.VERIFYING: ("reviewer",),
}


@dataclass
class Orchestra:
    """전체 에이전트 워크플로우를 조율하는 오케스트레이터."""

    project_dir: Path
    config: OrchestratorConfig = field(init=False)
    state: StateManager = field(init=False)
    phase_manager: PhaseManager = field(init=False)
    runner: AgentRunner = field(init=False)
    pipeline: ValidationPipeline = field(init=False)
    agent_logger: AgentLogger = field(init=False)

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

    @classmethod
    def from_project_dir(cls, project_dir: str | Path) -> Orchestra:
        """팩토리 메서드 — project_dir로 Orchestra 인스턴스 생성."""
        return cls(project_dir=Path(project_dir))

    async def run_phase(
        self,
        phase: Phase,
        prompt: str,
        **kwargs: Any,
    ) -> RunResult | None:
        """현재 Phase에 맞는 에이전트를 실행하고 결과를 state에 저장한다.

        Args:
            phase: 실행할 Phase
            prompt: 에이전트에 전달할 프롬프트
            **kwargs: IMPLEMENTING Phase에서 agent 이름을 받을 때 사용 (agent="backend_coder")

        Returns:
            실행 결과. PLANNING/DEPLOYING/DONE은 에이전트 없이 None 반환.
        """
        if phase in (Phase.PLANNING, Phase.DEPLOYING, Phase.DONE):
            return None

        if phase == Phase.IMPLEMENTING:
            agent_name: str = kwargs.get("agent", "backend_coder")
            result = await self.runner.run(agent_name, prompt)
            self._log_result(agent_name, result)
            task_id: str = kwargs.get("task_id", agent_name)
            self.state.save_task_result(task_id, self._result_to_dict(result))
            return result

        agents = _PHASE_AGENTS.get(phase, ())
        last_result: RunResult | None = None
        for agent_name in agents:
            last_result = await self.runner.run(agent_name, prompt)
            self._log_result(agent_name, last_result)
            self.state.save_task_result(f"{phase}_{agent_name}", self._result_to_dict(last_result))

        return last_result

    async def design(self, requirements: str) -> dict[str, RunResult]:
        """설계 Phase — Architect → Designer 순서로 실행.

        Args:
            requirements: PM 요구사항 프롬프트

        Returns:
            {"architect": RunResult, "designer": RunResult}
        """
        self.phase_manager.transition(Phase.DESIGNING)

        architect_result = await self.runner.run("architect", requirements)
        self._log_result("architect", architect_result)

        # Architect 출력을 Designer의 컨텍스트로 활용
        designer_prompt = (
            f"{requirements}\n\n"
            f"<architect_output>\n{architect_result.output}\n</architect_output>"
        )
        designer_result = await self.runner.run("designer", designer_prompt)
        self._log_result("designer", designer_result)

        results = {"architect": architect_result, "designer": designer_result}
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
        """Architect + Designer 출력을 파싱해 docs/skeleton.md에 기록한다.

        runner.py가 에이전트 실행 시 docs/skeleton.md를 자동으로 읽으므로,
        이 파일이 생성되면 이후 모든 에이전트가 채워진 계약서를 받는다.

        Args:
            architect_output: Architect 에이전트 출력 텍스트
            designer_output: Designer 에이전트 출력 텍스트

        Returns:
            생성된 skeleton.md 경로
        """
        template_path = self.project_dir / "docs" / "skeleton_template.md"
        skeleton_path = self.project_dir / "docs" / "skeleton.md"

        template_text = (
            template_path.read_text(encoding="utf-8") if template_path.exists() else ""
        )

        # 두 에이전트 출력에서 섹션 추출 (Designer가 Architect를 덮어쓸 수 있음)
        raw_sections = extract_filled_sections(architect_output)
        raw_sections += extract_filled_sections(designer_output)
        sections = [{"section_num": s.section_num, "content": s.content} for s in raw_sections]

        if template_text:
            filled_text = fill_skeleton_template(template_text, sections)
        else:
            # 템플릿 없으면 추출된 섹션을 그대로 이어붙임
            filled_text = "\n\n".join(s["content"] for s in sections)

        skeleton_path.parent.mkdir(parents=True, exist_ok=True)
        skeleton_path.write_text(filled_text, encoding="utf-8")

        logger.info("skeleton.md 생성 완료 — %d개 섹션 채움", len(sections))
        if not sections:
            logger.warning("skeleton 섹션 추출 실패 — 빈 skeleton.md 생성됨")

        return skeleton_path

    async def implement(self, task_id: str, agent: str, prompt: str) -> RunResult:
        """구현 Phase — 지정된 에이전트로 태스크를 실행한다.

        Args:
            task_id: 태스크 식별자 (결과 저장 키)
            agent: 실행할 에이전트 (backend_coder / frontend_coder)
            prompt: 태스크 프롬프트

        Returns:
            RunResult
        """
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
        """검증 Phase — SecurityHooks + ValidationPipeline + Reviewer 에이전트 실행.

        Args:
            task_id: 검증할 태스크 식별자
            is_frontend: 프론트엔드 코드면 True (의존성/스타일 규칙 적용)
            allowed_endpoints: skeleton에서 추출한 허용 엔드포인트 목록

        Returns:
            {"security": SecurityResult, "pipeline": ValidationResult, "reviewer": RunResult, "passed": bool}
            security BLOCK 또는 pipeline 실패 또는 reviewer reject → IMPLEMENTING으로 전이
        """
        self.phase_manager.transition(Phase.VERIFYING)

        # 1. 보안 훅 — 에이전트 출력 코드 분석
        task_result = self.state.load_task_result(task_id)
        agent_output = (task_result or {}).get("output", "") if isinstance(task_result, dict) else ""
        security_result: SecurityResult = SecurityHooks().run_all(
            agent_output,
            is_frontend=is_frontend,
            allowed_endpoints=allowed_endpoints,
        )
        if security_result.blocked:
            block_msgs = [f.message for f in security_result.findings if f.severity.value == "BLOCK"]
            logger.error(
                "보안 훅 BLOCK — task_id=%s findings=%s",
                task_id,
                block_msgs,
            )

        # 2. 린트/타입체크/테스트 파이프라인
        pipeline_result: ValidationResult = await self.pipeline.run_all()

        # 3. Reviewer 에이전트
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
    ) -> dict[str, Any]:
        """구현 + 검증을 Reviewer APPROVE까지 재시도한다.

        Args:
            task_id: 태스크 식별자
            agent: 실행할 에이전트 (backend_coder / frontend_coder)
            prompt: 태스크 프롬프트
            max_retries: 최대 재시도 횟수 (기본 3)

        Returns:
            {"implement": RunResult, "verify": dict, "attempts": int, "passed": bool}
        """
        last_impl: RunResult | None = None
        last_verify: dict[str, Any] = {}
        original_prompt = prompt  # 원본 보존 — 재시도마다 중첩 방지

        for attempt in range(1, max_retries + 1):
            impl_result = await self.implement(task_id, agent, prompt)
            verify_result = await self.verify(task_id)
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
                # 항상 원본 프롬프트 기준으로 피드백 추가 — 중첩 방지
                prompt = (
                    f"{original_prompt}\n\n"
                    f"<review_feedback>\n"
                    f"이전 구현이 REJECT되었습니다 (시도 {attempt}/{max_retries}).\n"
                    f"수정 사항:\n" + "\n".join(f"- {v}" for v in violations) +
                    f"\n</review_feedback>"
                )
                logger.warning(
                    "태스크 %s REJECT — 재시도 %d/%d", task_id, attempt, max_retries
                )
            else:
                logger.error(
                    "태스크 %s — 최대 재시도 %d회 초과. 에스컬레이션 필요.", task_id, max_retries
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
        """Phase 전체 리뷰 — 해당 Phase의 모든 태스크 완료 후 호출한다.

        Args:
            phase_num: Phase 번호 (1, 2, ...)
            task_ids: 해당 Phase에 속한 태스크 ID 목록

        Returns:
            PhaseReviewResult. 파싱 실패 시 None.
        """
        task_summaries: list[str] = []
        for tid in task_ids:
            result = self.state.load_task_result(tid)
            if result:
                output = result.get("output", "")[:500]  # 요약본만
                task_summaries.append(f"[{tid}]\n{output}")

        phase_prompt = (
            f"Phase {phase_num} 리뷰를 수행하세요.\n\n"
            f"<phase_tasks>\n" +
            "\n\n".join(task_summaries) +
            f"\n</phase_tasks>\n\n"
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

    async def run_pipeline_with_phases(
        self,
        requirements: str,
        phases: list[list[dict[str, str]]],
        max_task_retries: int = 3,
        max_phase_retries: int = 2,
    ) -> dict[str, Any]:
        """Phase 분리 전체 파이프라인.

        Args:
            requirements: PM 요구사항
            phases: Phase별 태스크 목록.
                예: [
                    [{"id": "T-001", "agent": "backend_coder", "prompt": "..."}],  # Phase 1
                    [{"id": "T-010", "agent": "frontend_coder", "prompt": "..."}], # Phase 2
                ]
            max_task_retries: 태스크당 최대 재시도 횟수
            max_phase_retries: Phase 리뷰 reject 시 최대 재시도 횟수

        Returns:
            {
                "design": dict,
                "phases": [{
                    "phase_num": int,
                    "tasks": dict,
                    "review": PhaseReviewResult | None,
                    "passed": bool,
                }],
                "success": bool,
            }
        """
        pipeline_results: dict[str, Any] = {
            "design": {},
            "phases": [],
            "success": False,
        }

        # 1. 설계
        design_results = await self.design(requirements)
        pipeline_results["design"] = design_results

        # 1-1. Architect + Designer 출력 → docs/skeleton.md 기록
        self.materialize_skeleton(
            architect_output=design_results["architect"].output,
            designer_output=design_results["designer"].output,
        )

        # 2. 태스크 분해
        self.phase_manager.transition(Phase.TASK_BREAKDOWN)
        breakdown_prompt = (
            f"{requirements}\n\n"
            f"<architect_output>\n{design_results['architect'].output}\n</architect_output>\n\n"
            f"<designer_output>\n{design_results['designer'].output}\n</designer_output>"
        )
        breakdown_result = await self.runner.run("orchestrator", breakdown_prompt)
        self._log_result("orchestrator", breakdown_result)
        self.state.save_task_result("task_breakdown", self._result_to_dict(breakdown_result))

        # 3. Phase별 실행
        all_phases_passed = True

        for phase_num, phase_tasks in enumerate(phases, start=1):
            phase_result: dict[str, Any] = {
                "phase_num": phase_num,
                "tasks": {},
                "review": None,
                "passed": False,
            }

            for phase_attempt in range(1, max_phase_retries + 1):
                # 태스크 실행
                task_ids: list[str] = []
                for task in phase_tasks:
                    task_id: str = task["id"]
                    agent: str = task["agent"]
                    task_prompt: str = task["prompt"]
                    ref_files: list[str] = task.get("ref_files", [])
                    task_ids.append(task_id)

                    # 참조 파일 내용을 프롬프트에 주입 (Golden Principle #8 Preserve Style)
                    if ref_files:
                        ref_contents: list[str] = []
                        for ref_path in ref_files:
                            full_path = self.project_dir / ref_path
                            if full_path.exists():
                                content = full_path.read_text(encoding="utf-8")
                                ref_contents.append(f"# {ref_path}\n```\n{content}\n```")
                            else:
                                logger.warning("참조 파일 없음: %s", ref_path)
                        if ref_contents:
                            task_prompt = (
                                f"{task_prompt}\n\n"
                                f"<reference_files>\n"
                                f"아래 파일들의 기존 패턴을 따라라.\n\n"
                                + "\n\n".join(ref_contents)
                                + "\n</reference_files>"
                            )

                    try:
                        task_result = await self.implement_with_retry(
                            task_id, agent, task_prompt, max_retries=max_task_retries
                        )
                    except Exception as e:
                        logger.error("태스크 %s 실행 중 예외: %s", task_id, e)
                        task_result = {"error": str(e), "passed": False}
                    phase_result["tasks"][task_id] = task_result

                # Phase 리뷰
                review = await self.review_phase(phase_num, task_ids)
                phase_result["review"] = review

                if review is not None and review.verdict == ReviewVerdict.APPROVE:
                    phase_result["passed"] = True
                    logger.info("Phase %d APPROVE (시도 %d/%d)", phase_num, phase_attempt, max_phase_retries)
                    break

                if phase_attempt < max_phase_retries:
                    logger.warning(
                        "Phase %d REJECT — 재시도 %d/%d",
                        phase_num, phase_attempt, max_phase_retries,
                    )
                else:
                    logger.error("Phase %d — 최대 재시도 초과.", phase_num)
                    all_phases_passed = False

            pipeline_results["phases"].append(phase_result)

            if not phase_result["passed"]:
                all_phases_passed = False
                logger.error("Phase %d 실패 — 이후 Phase 중단.", phase_num)
                break  # Phase 실패 시 다음 Phase 진행 안 함

        pipeline_results["success"] = all_phases_passed

        if all_phases_passed:
            self.phase_manager.transition(Phase.DEPLOYING)
            self.phase_manager.transition(Phase.DONE)
            logger.info("전체 파이프라인 완료 — Phase.DONE")

        return pipeline_results

    # ── 내부 헬퍼 ──────────────────────────────────────────────────────────────

    def _is_reviewer_approved(self, result: RunResult) -> bool:
        """Reviewer 출력에서 APPROVE/REJECT를 파싱한다.

        APPROVE/REJECT 마커가 없으면 subprocess 성공 여부로 폴백.
        """
        parsed = parse_pr_review(result.output)
        if parsed is not None:
            return parsed.verdict == ReviewVerdict.APPROVE
        # 파싱 실패 폴백 — subprocess 성공 여부 사용
        return result.success and not result.escalated

    def _log_result(self, agent: str, result: RunResult) -> None:
        """실행 결과에 따라 적절한 로그를 남긴다."""
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
        """RunResult를 JSON 직렬화 가능한 dict로 변환."""
        return {
            "agent": result.agent,
            "output": result.output,
            "success": result.success,
            "duration_ms": result.duration_ms,
            "attempts": result.attempts,
            "error": result.error,
            "escalated": result.escalated,
        }
