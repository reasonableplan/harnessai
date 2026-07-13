"""ha-deepinit validate: AGENTS.md citation-anchor gate.

2026-07-08 adoption (DeepWiki-style source citations): ha-deepinit was the only
skill without a machine gate — Agent-written AGENTS.md could carry hallucinated
paths unchecked. `validate` requires each AGENTS.md to carry >=1 backtick file
citation and verifies every cited path exists (resolved against the AGENTS.md
directory, then the project root) and cited line numbers fit the file.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_DEEPINIT_RUN = REPO_ROOT / "skills" / "ha-deepinit" / "run.py"


@pytest.fixture(scope="module")
def ha_deepinit() -> ModuleType:
    loader = SourceFileLoader("ha_deepinit_validate", str(HA_DEEPINIT_RUN))
    spec = importlib.util.spec_from_loader("ha_deepinit_validate", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_deepinit_validate"] = mod
    loader.exec_module(mod)
    return mod


def _run_validate(
    ha_deepinit: ModuleType, project: Path, min_citations: int = 1
) -> tuple[int, dict]:
    captured: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured.append(data)

    args = MagicMock()
    args.project = str(project)
    args.min_citations = min_citations

    with patch("builtins.print", side_effect=fake_print):
        result = ha_deepinit.cmd_validate(args)

    return result, json.loads(captured[-1])


def test_validate_passes_with_real_citations(ha_deepinit: ModuleType, tmp_path: Path) -> None:
    """실재 파일 인용만 있는 AGENTS.md → exit 0."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("line1\nline2\nline3\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "# Proj\n\n- 진입점: `src/main.py:2` 에서 부트스트랩\n", encoding="utf-8"
    )

    result, output = _run_validate(ha_deepinit, tmp_path)
    assert result == 0
    assert output["passed"] is True


def test_validate_fails_on_hallucinated_path(ha_deepinit: ModuleType, tmp_path: Path) -> None:
    """존재하지 않는 경로 인용 (주 실패 모드 = 환각 경로) → exit 1 + missing 목록."""
    (tmp_path / "AGENTS.md").write_text(
        "# Proj\n\n- 코어: `src/ghost_module.py` 참조\n", encoding="utf-8"
    )

    result, output = _run_validate(ha_deepinit, tmp_path)
    assert result == 1
    assert output["passed"] is False
    missing = [m for f in output["files"] for m in f["missing"]]
    assert any("ghost_module.py" in m for m in missing)


def test_validate_fails_on_zero_citations(ha_deepinit: ModuleType, tmp_path: Path) -> None:
    """인용 0개 = 검증 불가 주장 → exit 1."""
    (tmp_path / "AGENTS.md").write_text("# Proj\n\n근거 없는 요약만 있음.\n", encoding="utf-8")

    result, output = _run_validate(ha_deepinit, tmp_path)
    assert result == 1
    assert output["files"][0]["citation_count"] == 0


def test_validate_min_citations_zero_relaxes_gate(ha_deepinit: ModuleType, tmp_path: Path) -> None:
    """--min-citations 0 이면 인용 없는 파일도 통과 (완화 escape hatch)."""
    (tmp_path / "AGENTS.md").write_text("# Proj\n\n인용 없음.\n", encoding="utf-8")

    result, output = _run_validate(ha_deepinit, tmp_path, min_citations=0)
    assert result == 0
    assert output["passed"] is True


def test_validate_ignores_urls_and_code_identifiers(
    ha_deepinit: ModuleType, tmp_path: Path
) -> None:
    """URL / 점 표기 식별자 / 공백 포함 명령은 인용으로 세지 않는다 (오탐 방지)."""
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "# Proj\n\n"
        "- 참고: `https://ui.shadcn.com` 와 `plan.pipeline.current_step` 는 인용 아님\n"
        "- 명령: `uv run pytest tests/` 도 인용 아님\n"
        "- 실제 인용: `app.py`\n",
        encoding="utf-8",
    )

    result, output = _run_validate(ha_deepinit, tmp_path)
    assert result == 0, output
    assert output["files"][0]["citation_count"] == 1


def test_validate_resolves_relative_to_agents_md_dir(
    ha_deepinit: ModuleType, tmp_path: Path
) -> None:
    """서브디렉토리 AGENTS.md 의 인용은 그 디렉토리 기준으로도 해석."""
    sub = tmp_path / "backend"
    sub.mkdir()
    (sub / "service.py").write_text("x = 1\n", encoding="utf-8")
    (sub / "AGENTS.md").write_text("# backend\n\n- 서비스: `service.py`\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "# root\n\n- 백엔드: `backend/service.py`\n", encoding="utf-8"
    )

    result, output = _run_validate(ha_deepinit, tmp_path)
    assert result == 0, output
    assert len(output["files"]) == 2


def test_validate_fails_on_line_overflow(ha_deepinit: ModuleType, tmp_path: Path) -> None:
    """인용 라인이 파일 길이를 초과하면 위반 (stale/환각 라인 번호)."""
    (tmp_path / "tiny.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Proj\n\n- 참조: `tiny.py:99`\n", encoding="utf-8")

    result, output = _run_validate(ha_deepinit, tmp_path)
    assert result == 1
    overflow = [m for f in output["files"] for m in f["line_overflow"]]
    assert any("tiny.py:99" in m for m in overflow)


def test_validate_exit_3_when_no_agents_md(ha_deepinit: ModuleType, tmp_path: Path) -> None:
    """검증할 AGENTS.md 가 없으면 exit 3 (생성 단계 선행 필요)."""
    captured: list[str] = []
    args = MagicMock()
    args.project = str(tmp_path)
    args.min_citations = 1

    with patch("builtins.print", side_effect=lambda d, **k: captured.append(d)):
        result = ha_deepinit.cmd_validate(args)

    assert result == 3
