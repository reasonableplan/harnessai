"""StateManager JSON 파일 기반 상태 저장/로드 테스트."""

from pathlib import Path

import pytest

from src.orchestrator.phase import Phase
from src.orchestrator.state import StateManager


class TestStateManagerInit:
    def test_creates_orchestra_dirs(self, tmp_path: Path) -> None:
        StateManager(tmp_path)
        assert (tmp_path / ".orchestra").is_dir()
        assert (tmp_path / ".orchestra" / "phases").is_dir()
        assert (tmp_path / ".orchestra" / "results").is_dir()


class TestStateLoad:
    def test_no_file_returns_default(self, tmp_path: Path) -> None:
        sm = StateManager(tmp_path)
        data = sm.load()
        assert data["phase"] == "planning"
        assert data["metadata"] == {}

    def test_corrupted_json_returns_default(self, tmp_path: Path) -> None:
        sm = StateManager(tmp_path)
        state_path = tmp_path / ".orchestra" / "state.json"
        state_path.write_text("{invalid json", encoding="utf-8")

        data = sm.load()
        assert data["phase"] == "planning"

    def test_non_dict_json_returns_default(self, tmp_path: Path) -> None:
        sm = StateManager(tmp_path)
        state_path = tmp_path / ".orchestra" / "state.json"
        state_path.write_text('"just a string"', encoding="utf-8")

        data = sm.load()
        assert data["phase"] == "planning"


class TestStateSaveLoad:
    def test_roundtrip(self, tmp_path: Path) -> None:
        sm = StateManager(tmp_path)
        sm.save(Phase.DESIGNING, data={"key": "value"})

        loaded = sm.load()
        assert loaded["phase"] == "designing"
        assert loaded["metadata"]["key"] == "value"
        assert loaded["updated_at"] is not None


class TestPhaseData:
    def test_save_and_load(self, tmp_path: Path) -> None:
        sm = StateManager(tmp_path)
        sm.save_phase_data(Phase.PLANNING, {"requirements": "이슈 관리 시스템"})

        loaded = sm.load_phase_data(Phase.PLANNING)
        assert loaded is not None
        assert loaded["requirements"] == "이슈 관리 시스템"

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        sm = StateManager(tmp_path)
        assert sm.load_phase_data(Phase.DESIGNING) is None


class TestPathTraversal:
    def test_task_id_with_path_traversal(self, tmp_path: Path) -> None:
        sm = StateManager(tmp_path)
        sm.save_task_result("../../etc/passwd", {"data": "hack"})
        # 경로 탈출 안 되고 안전한 파일명으로 저장됨
        safe_path = tmp_path / ".orchestra" / "results" / "______etc_passwd.json"
        assert safe_path.exists()

    def test_task_id_special_chars_sanitized(self, tmp_path: Path) -> None:
        sm = StateManager(tmp_path)
        sm.save_task_result("task@#$%", {"data": "test"})
        safe_path = tmp_path / ".orchestra" / "results" / "task____.json"
        assert safe_path.exists()


class TestTaskResult:
    def test_save_and_load(self, tmp_path: Path) -> None:
        sm = StateManager(tmp_path)
        sm.save_task_result("task-001", {"status": "success", "output": "done"})

        loaded = sm.load_task_result("task-001")
        assert loaded is not None
        assert loaded["status"] == "success"

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        sm = StateManager(tmp_path)
        assert sm.load_task_result("nonexistent") is None
