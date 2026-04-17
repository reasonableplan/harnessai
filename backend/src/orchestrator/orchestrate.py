"""메인 오케스트레이터 — 전체 워크플로우를 조율하는 진입점."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.orchestrator.config import OrchestratorConfig, load_agents_config
from src.orchestrator.context import extract_section, fill_skeleton_template
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

# Phase별 에이전트 매핑 (순서가 있는 경우 tuple) — 파이프라인 내부용
_PHASE_AGENTS: dict[Phase, tuple[str, ...]] = {
    Phase.DESIGNING: ("architect", "designer"),
    Phase.TASK_BREAKDOWN: ("orchestrator",),
    Phase.VERIFYING: ("reviewer",),
}

# Phase → 단일 에이전트 매핑 — 대시보드 REST/WS 명령 디스패치용
# None이면 해당 Phase에서 에이전트 직접 실행 안 함
PHASE_AGENT_MAP: dict[str, str | None] = {
    "planning": None,
    "designing": "architect",
    "task_breakdown": "orchestrator",
    "implementing": "backend_coder",
    "verifying": "reviewer",
    "deploying": None,
    "done": None,
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
    # implement_with_retry per-task Lock — task_id별 직렬화, 병렬 태스크 간 간섭 방지
    _task_locks: dict[str, asyncio.Lock] = field(init=False)

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

    def _get_task_lock(self, task_id: str) -> asyncio.Lock:
        """task_id별 Lock을 반환한다. 없으면 새로 생성."""
        if task_id not in self._task_locks:
            self._task_locks[task_id] = asyncio.Lock()
        return self._task_locks[task_id]

    @classmethod
    def from_project_dir(cls, project_dir: str | Path) -> Orchestra:
        """팩토리 메서드 — project_dir로 Orchestra 인스턴스 생성."""
        return cls(project_dir=Path(project_dir))

    async def design(
        self,
        requirements: str,
        max_negotiation_rounds: int = 3,
    ) -> dict[str, RunResult]:
        """설계 Phase — Architect ↔ Designer 협의 루프 (최대 max_negotiation_rounds회).

        Designer가 ``## Design Verdict: CONFLICT``를 출력하면 API 요청사항을
        Architect에 전달해 재설계를 요청한다. ACCEPT 또는 마커 없음이면 합의로 처리.

        Args:
            requirements: PM 요구사항 프롬프트
            max_negotiation_rounds: 최대 협의 라운드 수 (기본 3)

        Returns:
            {"architect": RunResult, "designer": RunResult} — 마지막 라운드 결과
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
                        agent="designer", output="", success=False,
                        duration_ms=0, attempts=0,
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
                requests_text = "\n".join(f"- {r}" for r in verdict.api_requests) or "(세부 요청 없음)"
                architect_prompt = (
                    f"{requirements}\n\n"
                    f"<design_conflicts>\n"
                    f"Designer가 다음 API 추가를 요청했습니다 (라운드 {round_num}/{max_negotiation_rounds}):\n"
                    f"{requests_text}\n"
                    f"</design_conflicts>"
                )
                logger.warning(
                    "설계 충돌 — 재협의 라운드 %d/%d (API 요청 %d개)",
                    round_num, max_negotiation_rounds, len(verdict.api_requests),
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

        if not sections:
            raise ValueError(
                "skeleton 섹션 추출 실패 — Architect/Designer 출력에서 유효한 섹션을 찾을 수 없음"
            )

        if template_text:
            filled_text = fill_skeleton_template(template_text, sections)
        else:
            # 템플릿 없으면 추출된 섹션을 그대로 이어붙임
            filled_text = "\n\n".join(s["content"] for s in sections)

        skeleton_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            skeleton_path.write_text(filled_text, encoding="utf-8")
        except OSError as exc:
            logger.error("skeleton.md 쓰기 실패: %s", exc)
            raise

        logger.info("skeleton.md 생성 완료 — %d개 섹션 채움", len(sections))
        return skeleton_path

    def assemble_skeleton_for_profiles(
        self,
        profile_ids: list[str],
        *,
        title: str | None = None,
        harness_dir: Path | None = None,
        included_overrides: list[str] | None = None,
    ) -> Path:
        """프로파일 기반 빈 skeleton 생성 (Harness v2).

        - 각 profile_id 의 skeleton_sections.required 합집합을 included 로 사용
          (또는 included_overrides 우선)
        - 첫 프로파일의 skeleton_sections.order 를 따라 정렬
        - SkeletonAssembler 로 조각 → docs/skeleton.md 작성

        Args:
            profile_ids: 사용할 프로파일 ID 목록 (모노레포 가능)
            title: skeleton 최상위 제목. 기본값은 project_dir 이름.
            harness_dir: 글로벌 harness 디렉토리. 기본 ~/.claude/harness/
            included_overrides: required 합집합 대신 직접 지정 (ha-init 결과)

        Returns:
            생성된 skeleton.md 경로
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

        # 첫 프로파일의 order 우선 — 나머지 ID는 끝에 append
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

        assembler = SkeletonAssembler(
            harness_dir=harness_dir, project_dir=self.project_dir
        )
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
            profile_ids, len(ordered),
        )
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
        if self.phase_manager.current_phase != Phase.VERIFYING:
            try:
                self.phase_manager.transition(Phase.VERIFYING)
            except InvalidTransitionError:
                # 병렬 태스크에서 다른 태스크가 이미 VERIFYING으로 전이한 경우 — 무시
                logger.debug("VERIFYING 전이 생략 — 현재 Phase: %s", self.phase_manager.current_phase)

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
        *,
        is_frontend: bool = False,
        allowed_endpoints: list[str] | None = None,
    ) -> dict[str, Any]:
        """구현 + 검증을 Reviewer APPROVE까지 재시도한다.

        Args:
            task_id: 태스크 식별자
            agent: 실행할 에이전트 (backend_coder / frontend_coder)
            prompt: 태스크 프롬프트
            max_retries: 최대 재시도 횟수 (기본 3)
            is_frontend: 프론트엔드 코드면 True (의존성/스타일 규칙 적용)
            allowed_endpoints: skeleton 섹션 7에서 추출한 허용 엔드포인트 목록

        Returns:
            {"implement": RunResult, "verify": dict, "attempts": int, "passed": bool}
        """
        last_impl: RunResult | None = None
        last_verify: dict[str, Any] = {}
        original_prompt = prompt  # 원본 보존 — 재시도마다 중첩 방지

        # per-task-id Lock: 동일 태스크의 재시도 사이클을 직렬화.
        # 서로 다른 task_id는 병렬 실행 가능 — PhaseManager 전이는 각자 best-effort.
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
                    # 항상 원본 프롬프트 기준으로 피드백 추가 — 중첩 방지
                    prompt = (
                        f"{original_prompt}\n\n"
                        f"<review_feedback>\n"
                        f"이전 구현이 REJECT되었습니다 (시도 {attempt}/{max_retries}).\n"
                        f"수정 사항:\n" + "\n".join(f"- {v}" for v in violations) +
                        "\n</review_feedback>"
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

    async def qa_phase(
        self,
        phase_num: int,
        task_ids: list[str],
    ) -> QaResult | None:
        """Phase QA — 구현 코드의 API 계약·상태 흐름·문서 일치를 검증한다.

        review_phase() APPROVE 이후에 호출한다. QA 에이전트는 기능 코드를 수정하지 않고
        테스트만 작성하며, health score(0-10)와 이슈 목록을 반환한다.

        Args:
            phase_num: Phase 번호
            task_ids: 해당 Phase에 속한 태스크 ID 목록

        Returns:
            QaResult. 파싱 실패 시 None (통과로 처리).
        """
        task_summaries: list[str] = []
        for tid in task_ids:
            result = self.state.load_task_result(tid)
            if result:
                output = result.get("output", "")[:500]
                task_summaries.append(f"[{tid}]\n{output}")

        skeleton_path = self.project_dir / "docs" / "skeleton.md"
        skeleton_text = (
            skeleton_path.read_text(encoding="utf-8") if skeleton_path.exists() else ""
        )

        qa_prompt = (
            f"Phase {phase_num} QA를 수행하세요.\n\n"
            f"<skeleton>\n{skeleton_text}\n</skeleton>\n\n"
            f"<phase_tasks>\n" +
            "\n\n".join(task_summaries) +
            f"\n</phase_tasks>\n\n"
            f"QA Report 형식으로 결과를 출력하세요."
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
                phase_num, parsed.health_score, parsed.passed, len(parsed.issues),
            )
        return parsed

    async def run_breakdown(
        self,
        requirements: str,
        design_results: dict[str, RunResult],
    ) -> tuple[list[list[TaskItem]], dict[str, Any]]:
        """태스크 분해 단계 — Orchestrator 에이전트 실행 + parse_phases.

        Args:
            requirements: PM 요구사항
            design_results: design()의 반환값 (architect, designer RunResult)

        Returns:
            (phases, breakdown_dict)
            phases: Phase별 TaskItem 리스트 (파싱 실패 시 빈 리스트)
            breakdown_dict: Orchestrator RunResult의 dict 표현
        """
        self.phase_manager.transition(Phase.TASK_BREAKDOWN)
        breakdown_prompt = (
            f"{requirements}\n\n"
            f"<architect_output>\n{design_results['architect'].output}\n</architect_output>\n\n"
            f"<designer_output>\n{design_results['designer'].output}\n</designer_output>"
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
        """Phase별 태스크 실행 + Phase 리뷰.

        Args:
            phases: run_breakdown()이 반환한 Phase별 TaskItem 리스트
            max_task_retries: 태스크당 최대 재시도 횟수
            max_phase_retries: Phase 리뷰 reject 시 최대 재시도 횟수

        Returns:
            {
                "phases": [{"phase_num", "tasks", "review", "passed"}],
                "success": bool,
            }
        """
        results: list[dict[str, Any]] = []
        all_passed = True
        allowed_endpoints = self._extract_allowed_endpoints()

        for phase_num, phase_tasks in enumerate(phases, start=1):
            if not phase_tasks:
                logger.warning("Phase %d — 태스크 없음, 건너뜀", phase_num)
                results.append({"phase_num": phase_num, "tasks": {}, "review": None, "passed": True})
                continue

            phase_result: dict[str, Any] = {
                "phase_num": phase_num,
                "tasks": {},
                "review": None,
                "qa": None,
                "passed": False,
            }
            # Phase 재시도 시 이미 통과한 태스크는 재실행하지 않음
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
                        if isinstance(item, BaseException):
                            logger.error("병렬 태스크 예외 (gather): %s", item)
                            continue
                        tid, task_result = item
                        phase_result["tasks"][tid] = task_result
                        if task_result.get("passed", False):
                            passed_task_ids.add(tid)

                review = await self.review_phase(phase_num, task_ids)
                phase_result["review"] = review

                if review is not None and review.verdict == ReviewVerdict.APPROVE:
                    # Reviewer APPROVE → QA 검증 (API 계약·상태 흐름·문서 일치)
                    qa = await self.qa_phase(phase_num, task_ids)
                    phase_result["qa"] = qa
                    qa_passed = qa is None or qa.passed  # 파싱 실패 시 통과 처리
                    if qa_passed:
                        phase_result["passed"] = True
                        logger.info("Phase %d APPROVE + QA PASS (시도 %d/%d)", phase_num, phase_attempt, max_phase_retries)
                        break
                    logger.warning(
                        "Phase %d QA FAIL — health_score=%d/10 issues=%s",
                        phase_num,
                        qa.health_score if qa else 0,
                        [i[:80] for i in (qa.issues if qa else [])],
                    )

                if phase_attempt < max_phase_retries:
                    logger.warning("Phase %d REJECT — 재시도 %d/%d", phase_num, phase_attempt, max_phase_retries)
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
    ) -> dict[str, Any]:
        """Phase 분리 전체 파이프라인 (단일 호출 버전).

        인터랙티브 게이트가 필요하면 pipeline_runner.run()을 사용한다.

        Args:
            requirements: PM 요구사항
            max_task_retries: 태스크당 최대 재시도 횟수
            max_phase_retries: Phase 리뷰 reject 시 최대 재시도 횟수

        Returns:
            {"design", "breakdown", "phases", "success"}
        """
        # 1. 설계
        design_results = await self.design(requirements)
        if not design_results["architect"].success:
            logger.error("Architect 실패 — run_pipeline_with_phases() 중단")
            return {"design": design_results, "breakdown": {}, "phases": [], "success": False}
        try:
            self.materialize_skeleton(
                architect_output=design_results["architect"].output,
                designer_output=design_results["designer"].output,
            )
        except ValueError as exc:
            logger.error("skeleton 생성 실패 — run_pipeline_with_phases() 중단: %s", exc)
            return {"design": design_results, "breakdown": {}, "phases": [], "success": False}

        # 2. 태스크 분해
        phases, breakdown_dict = await self.run_breakdown(requirements, design_results)
        if not phases:
            return {"design": design_results, "breakdown": breakdown_dict, "phases": [], "success": False}

        # 3. Phase별 실행
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

    # skeleton 섹션 7 마크다운 테이블에서 엔드포인트 행 추출
    # | GET | /api/projects | ... |  → "GET /api/projects"
    _ENDPOINT_ROW = re.compile(
        r"^\|\s*(GET|POST|PUT|PATCH|DELETE)\s*\|\s*(/[^|\s]+)",
        re.MULTILINE | re.IGNORECASE,
    )

    def _extract_allowed_endpoints(self) -> list[str]:
        """skeleton.md 섹션 7(API 스키마)에서 허용된 엔드포인트 목록을 추출한다.

        Returns:
            ["GET /api/projects", "POST /api/issues", ...] 형태 리스트.
            skeleton.md 없으면 빈 리스트 (contract validator 비활성화됨).
        """
        skeleton_path = self.project_dir / "docs" / "skeleton.md"
        if not skeleton_path.exists():
            return []

        skeleton_text = skeleton_path.read_text(encoding="utf-8")
        section7 = extract_section(skeleton_text, 7)
        if not section7:
            return []

        return [
            f"{m.group(1).upper()} {m.group(2).rstrip()}"
            for m in self._ENDPOINT_ROW.finditer(section7)
        ]
