"""프로젝트 상태 저장/로드 — .orchestra/ JSON 파일 기반."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.orchestrator.phase import Phase

logger = logging.getLogger(__name__)

_DEFAULT_STATE: dict[str, Any] = {
    "phase": "planning",
    "updated_at": None,
    "metadata": {},
}


class StateManager:
    """프로젝트 상태를 .orchestra/ 디렉토리에 JSON으로 저장/복구."""

    def __init__(self, project_dir: str | Path) -> None:
        self._project_dir = Path(project_dir)
        self._orchestra_dir = self._project_dir / ".orchestra"
        self._phases_dir = self._orchestra_dir / "phases"
        self._results_dir = self._orchestra_dir / "results"
        self._state_path = self._orchestra_dir / "state.json"

        self._orchestra_dir.mkdir(parents=True, exist_ok=True)
        self._phases_dir.mkdir(parents=True, exist_ok=True)
        self._results_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _atomic_write(path: Path, data: dict[str, Any]) -> None:
        """원자적 JSON 파일 쓰기 — temp 파일에 쓰고 rename."""
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(path))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def load(self) -> dict[str, Any]:
        """state.json을 로드. 없거나 손상되면 기본값(PLANNING) 반환."""
        if not self._state_path.exists():
            return dict(_DEFAULT_STATE)

        try:
            with open(self._state_path, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            logger.warning(
                "state.json 파싱 실패, 기본값으로 복구합니다: %s (오류: %s)",
                self._state_path,
                exc,
            )
            return dict(_DEFAULT_STATE)

        if not isinstance(data, dict):
            logger.warning(
                "state.json 형식 오류(dict 아님), 기본값으로 복구합니다: %s",
                self._state_path,
            )
            return dict(_DEFAULT_STATE)

        return data

    def save(self, phase: Phase, *, data: dict[str, Any] | None = None) -> None:
        """현재 phase와 선택적 메타데이터를 state.json에 저장."""
        state: dict[str, Any] = {
            "phase": str(phase),
            "updated_at": datetime.now(UTC).isoformat(),
            "metadata": data or {},
        }
        self._atomic_write(self._state_path, state)

    def save_phase_data(self, phase: Phase, data: dict[str, Any]) -> None:
        """phases/{phase}.json에 단계별 데이터 저장."""
        path = self._phases_dir / f"{phase}.json"
        self._atomic_write(path, data)

    def load_phase_data(self, phase: Phase) -> dict[str, Any] | None:
        """phases/{phase}.json 로드. 파일이 없으면 None 반환."""
        path = self._phases_dir / f"{phase}.json"
        if not path.exists():
            return None

        with open(path, encoding="utf-8") as f:
            return json.load(f)  # type: ignore[no-any-return]

    @staticmethod
    def _safe_filename(name: str) -> str:
        """파일명에 안전한 문자만 허용 — path traversal 방지."""
        sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
        if not sanitized:
            raise ValueError(f"유효하지 않은 ID: {name!r}")
        return sanitized

    def save_task_result(self, task_id: str, result: dict[str, Any]) -> None:
        """results/{task_id}.json에 태스크 결과 저장."""
        path = self._results_dir / f"{self._safe_filename(task_id)}.json"
        self._atomic_write(path, result)

    def load_task_result(self, task_id: str) -> dict[str, Any] | None:
        """results/{task_id}.json 로드. 없으면 None 반환."""
        path = self._results_dir / f"{self._safe_filename(task_id)}.json"
        if not path.exists():
            return None

        with open(path, encoding="utf-8") as f:
            return json.load(f)  # type: ignore[no-any-return]
