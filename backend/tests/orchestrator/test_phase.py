"""Phase 상태 머신 테스트."""

import pytest

from src.orchestrator.phase import (
    InvalidTransitionError,
    Phase,
    PhaseManager,
)
from src.orchestrator.state import StateManager


class TestPhaseEnum:
    def test_has_seven_values(self) -> None:
        assert len(Phase) == 7

    def test_values(self) -> None:
        assert Phase.PLANNING == "planning"
        assert Phase.DESIGNING == "designing"
        assert Phase.TASK_BREAKDOWN == "task_breakdown"
        assert Phase.IMPLEMENTING == "implementing"
        assert Phase.VERIFYING == "verifying"
        assert Phase.DEPLOYING == "deploying"
        assert Phase.DONE == "done"


class TestValidTransitions:
    @pytest.mark.parametrize(
        "from_phase,to_phase",
        [
            (Phase.PLANNING, Phase.DESIGNING),
            (Phase.DESIGNING, Phase.TASK_BREAKDOWN),
            (Phase.TASK_BREAKDOWN, Phase.IMPLEMENTING),
            (Phase.IMPLEMENTING, Phase.VERIFYING),
            (Phase.VERIFYING, Phase.IMPLEMENTING),
            (Phase.VERIFYING, Phase.DEPLOYING),
            (Phase.DEPLOYING, Phase.DONE),
        ],
    )
    def test_valid_transition(self, tmp_path, from_phase, to_phase) -> None:
        state = StateManager(tmp_path)
        state.save(from_phase)
        pm = PhaseManager(state)
        result = pm.transition(to_phase)
        assert result == to_phase
        assert pm.current_phase == to_phase

    @pytest.mark.parametrize(
        "from_phase,to_phase",
        [
            (Phase.PLANNING, Phase.IMPLEMENTING),
            (Phase.PLANNING, Phase.VERIFYING),
            (Phase.DESIGNING, Phase.IMPLEMENTING),
            (Phase.IMPLEMENTING, Phase.DEPLOYING),
            (Phase.DEPLOYING, Phase.PLANNING),
            (Phase.DONE, Phase.PLANNING),
        ],
    )
    def test_invalid_transition(self, tmp_path, from_phase, to_phase) -> None:
        state = StateManager(tmp_path)
        state.save(from_phase)
        pm = PhaseManager(state)
        with pytest.raises(InvalidTransitionError) as exc_info:
            pm.transition(to_phase)
        assert exc_info.value.from_phase == from_phase
        assert exc_info.value.to_phase == to_phase


class TestPhaseManager:
    def test_initial_phase_is_planning(self, tmp_path) -> None:
        state = StateManager(tmp_path)
        pm = PhaseManager(state)
        assert pm.current_phase == Phase.PLANNING

    def test_can_transition(self, tmp_path) -> None:
        state = StateManager(tmp_path)
        pm = PhaseManager(state)
        assert pm.can_transition(Phase.DESIGNING) is True
        assert pm.can_transition(Phase.IMPLEMENTING) is False

    def test_transition_saves_to_state(self, tmp_path) -> None:
        state = StateManager(tmp_path)
        pm = PhaseManager(state)
        pm.transition(Phase.DESIGNING)
        # 새 PhaseManager로 다시 로드해도 DESIGNING
        pm2 = PhaseManager(state)
        assert pm2.current_phase == Phase.DESIGNING

    def test_transition_with_data(self, tmp_path) -> None:
        state = StateManager(tmp_path)
        pm = PhaseManager(state)
        pm.transition(Phase.DESIGNING, data={"requirements": "이슈 관리"})
        loaded = state.load_phase_data(Phase.DESIGNING)
        assert loaded is not None
        assert loaded["requirements"] == "이슈 관리"

    def test_reject_loop(self, tmp_path) -> None:
        """VERIFYING → IMPLEMENTING → VERIFYING 루프."""
        state = StateManager(tmp_path)
        state.save(Phase.IMPLEMENTING)
        pm = PhaseManager(state)

        pm.transition(Phase.VERIFYING)
        assert pm.current_phase == Phase.VERIFYING

        pm.transition(Phase.IMPLEMENTING, data={"reason": "reject"})
        assert pm.current_phase == Phase.IMPLEMENTING

        pm.transition(Phase.VERIFYING)
        assert pm.current_phase == Phase.VERIFYING

        pm.transition(Phase.DEPLOYING)
        assert pm.current_phase == Phase.DEPLOYING

    def test_full_happy_path(self, tmp_path) -> None:
        """PLANNING → ... → DONE 전체 흐름."""
        state = StateManager(tmp_path)
        pm = PhaseManager(state)

        pm.transition(Phase.DESIGNING)
        pm.transition(Phase.TASK_BREAKDOWN)
        pm.transition(Phase.IMPLEMENTING)
        pm.transition(Phase.VERIFYING)
        pm.transition(Phase.DEPLOYING)
        pm.transition(Phase.DONE)
        assert pm.current_phase == Phase.DONE

    def test_done_has_no_transitions(self, tmp_path) -> None:
        state = StateManager(tmp_path)
        state.save(Phase.DONE)
        pm = PhaseManager(state)
        assert pm.can_transition(Phase.PLANNING) is False
        with pytest.raises(InvalidTransitionError):
            pm.transition(Phase.PLANNING)
