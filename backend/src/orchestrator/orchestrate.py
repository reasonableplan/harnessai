"""메인 오케스트레이터 — 전체 워크플로우를 조율하는 진입점."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.orchestrator.config import OrchestratorConfig, load_agents_config
from src.orchestrator.context import build_context
from src.orchestrator.logger import AgentLogger
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

    async def verify(self, task_id: str) -> dict[str, Any]:
        """검증 Phase — ValidationPipeline + Reviewer 에이전트 실행.

        Args:
            task_id: 검증할 태스크 식별자

        Returns:
            {"pipeline": ValidationResult, "reviewer": RunResult}
            pipeline 실패 또는 reviewer reject → IMPLEMENTING으로 전이 (reject 루프)
            둘 다 pass → DEPLOYING 준비
        """
        self.phase_manager.transition(Phase.VERIFYING)

        pipeline_result: ValidationResult = await self.pipeline.run_all()

        task_result = self.state.load_task_result(task_id)
        reviewer_prompt = (
            f"태스크 ID: {task_id}\n\n"
            f"<validation_summary>\n{pipeline_result.summary}\n</validation_summary>\n\n"
            f"<task_output>\n{task_result or '결과 없음'}\n</task_output>"
        )
        reviewer_result = await self.runner.run("reviewer", reviewer_prompt)
        self._log_result("reviewer", reviewer_result)

        pipeline_passed = pipeline_result.passed
        reviewer_passed = reviewer_result.success and not reviewer_result.escalated

        if not pipeline_passed or not reviewer_passed:
            logger.warning(
                "검증 실패 — task_id=%s pipeline=%s reviewer=%s. IMPLEMENTING으로 전이.",
                task_id,
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

        outcome = {
            "pipeline": pipeline_result,
            "reviewer": reviewer_result,
            "passed": pipeline_passed and reviewer_passed,
        }
        self.state.save_task_result(
            f"verify_{task_id}",
            {
                "pipeline_summary": pipeline_result.summary,
                "pipeline_passed": pipeline_passed,
                "reviewer": self._result_to_dict(reviewer_result),
                "passed": outcome["passed"],
            },
        )
        return outcome

    async def run_full_pipeline(
        self,
        requirements: str,
        tasks: list[dict[str, str]],
    ) -> dict[str, Any]:
        """전체 파이프라인을 한 번에 실행한다.

        Args:
            requirements: PM 요구사항
            tasks: [{"id": "task-001", "agent": "backend_coder", "prompt": "..."}, ...]

        Returns:
            {
                "design": {"architect": RunResult, "designer": RunResult},
                "tasks": {task_id: {"implement": RunResult, "verify": dict}},
                "success": bool,
            }
        """
        pipeline_results: dict[str, Any] = {
            "design": {},
            "tasks": {},
            "success": False,
        }

        # 1. 설계
        design_results = await self.design(requirements)
        pipeline_results["design"] = design_results

        # 2. 태스크 분류 (TASK_BREAKDOWN)
        self.phase_manager.transition(Phase.TASK_BREAKDOWN)
        breakdown_prompt = (
            f"{requirements}\n\n"
            f"<architect_output>\n{design_results['architect'].output}\n</architect_output>\n\n"
            f"<designer_output>\n{design_results['designer'].output}\n</designer_output>"
        )
        breakdown_result = await self.runner.run("orchestrator", breakdown_prompt)
        self._log_result("orchestrator", breakdown_result)
        self.state.save_task_result("task_breakdown", self._result_to_dict(breakdown_result))

        # 3. 각 태스크 구현 + 검증
        all_passed = True
        for task in tasks:
            task_id: str = task["id"]
            agent: str = task["agent"]
            prompt: str = task["prompt"]

            impl_result = await self.implement(task_id, agent, prompt)
            verify_result = await self.verify(task_id)

            pipeline_results["tasks"][task_id] = {
                "implement": impl_result,
                "verify": verify_result,
            }

            if not verify_result.get("passed", False):
                all_passed = False
                logger.warning("태스크 %s 검증 실패 — 파이프라인 계속 진행.", task_id)

        pipeline_results["success"] = all_passed
        return pipeline_results

    # ── 내부 헬퍼 ──────────────────────────────────────────────────────────────

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
