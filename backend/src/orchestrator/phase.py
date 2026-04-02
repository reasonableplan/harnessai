"""Phase 상태 머신 — 프로젝트 워크플로우 Phase 전이 관리."""

from __future__ import annotations

from enum import StrEnum

from src.orchestrator.state import StateManager


class Phase(StrEnum):
    PLANNING = "planning"
    DESIGNING = "designing"
    TASK_BREAKDOWN = "task_breakdown"
    IMPLEMENTING = "implementing"
    VERIFYING = "verifying"
    DEPLOYING = "deploying"
    DONE = "done"


# 허용된 전이만 정의. 이 외에는 전부 InvalidTransitionError.
VALID_TRANSITIONS: dict[Phase, set[Phase]] = {
    Phase.PLANNING: {Phase.DESIGNING},
    Phase.DESIGNING: {Phase.TASK_BREAKDOWN},
    Phase.TASK_BREAKDOWN: {Phase.IMPLEMENTING},
    Phase.IMPLEMENTING: {Phase.VERIFYING},
    Phase.VERIFYING: {Phase.IMPLEMENTING, Phase.DEPLOYING},  # reject 루프 포함
    Phase.DEPLOYING: {Phase.DONE},
    Phase.DONE: set(),
}


class InvalidTransitionError(Exception):
    """허용되지 않은 Phase 전이 시도."""

    def __init__(self, from_phase: Phase, to_phase: Phase) -> None:
        self.from_phase = from_phase
        self.to_phase = to_phase
        super().__init__(
            f"전이 불가: {from_phase} → {to_phase}. "
            f"허용: {VALID_TRANSITIONS.get(from_phase, set())}"
        )


class PhaseManager:
    """Phase 전이를 관리하고 StateManager와 연동."""

    def __init__(self, state: StateManager) -> None:
        self._state = state
        self._current: Phase | None = None

    @property
    def current_phase(self) -> Phase:
        """현재 Phase. 최초 호출 시 state.json에서 로드."""
        if self._current is None:
            loaded = self._state.load()
            self._current = Phase(loaded.get("phase", "planning"))
        return self._current

    def can_transition(self, to: Phase) -> bool:
        """전이 가능 여부 확인."""
        allowed = VALID_TRANSITIONS.get(self.current_phase, set())
        return to in allowed

    def transition(self, to: Phase, *, data: dict | None = None) -> Phase:
        """Phase를 전이한다.

        Args:
            to: 전이할 Phase
            data: Phase에 저장할 데이터 (선택)

        Returns:
            전이된 Phase

        Raises:
            InvalidTransitionError: 허용되지 않은 전이
        """
        if not self.can_transition(to):
            raise InvalidTransitionError(self.current_phase, to)

        # phase data 먼저 (덜 중요한 파일), 그 다음 state (source of truth)
        # self._current는 양쪽 다 성공한 후에만 변경 — 실패 시 in-memory 상태 일관성 유지
        if data is not None:
            self._state.save_phase_data(to, data)
        self._state.save(to, data=data)
        self._current = to

        return to
