"""LESSON-030 회귀 테스트: ha-review _collect_findings 문서 diff FP 차단.

실전 결함 (code-hijack Phase 3~4):
- harness-plan.md rationale 산문 'external eval (' → command-guard BLOCK 3건
- SKILL.md 인라인 예시 print/import → code-quality·dependency-check WARN 다발
- 자기 패키지 (hijack) import → dependency-check WARN 25건

Fix: SecurityHooks/mobile 룰 입력을 strip_doc_files_from_diff 로 코드 블록만,
dependency-check 에 detect_local_packages + stdlib 허용.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_REVIEW_RUN = REPO_ROOT / "skills" / "ha-review" / "run.py"


@pytest.fixture(scope="module")
def ha_review() -> ModuleType:
    loader = SourceFileLoader("ha_review_doc_diff_fp", str(HA_REVIEW_RUN))
    spec = importlib.util.spec_from_loader("ha_review_doc_diff_fp", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_review_doc_diff_fp"] = mod
    loader.exec_module(mod)
    return mod


def _profile(pid: str = "python-cli") -> SimpleNamespace:
    return SimpleNamespace(
        id=pid,
        whitelist=SimpleNamespace(runtime=["pytest"], dev=[], prefix_allowed=[]),
    )


_MD_EVAL_DIFF = (
    "diff --git a/backend/docs/harness-plan.md b/backend/docs/harness-plan.md\n"
    "--- a/backend/docs/harness-plan.md\n"
    "+++ b/backend/docs/harness-plan.md\n"
    "+  rationale: external eval (matching rate 50%) remains manual\n"
    "+  print('SKILL.md inline example')\n"
    "+  import some_unlisted_pkg\n"
)

_PY_EVAL_DIFF = (
    "diff --git a/backend/src/app.py b/backend/src/app.py\n"
    "--- a/backend/src/app.py\n"
    "+++ b/backend/src/app.py\n"
    "+result = eval(user_input)\n"
)


def test_md_prose_produces_zero_security_findings(ha_review: ModuleType, tmp_path: Path) -> None:
    """실전 FP 재현: 문서 diff 만 있으면 security findings 0 / BLOCK 0."""
    result = ha_review._collect_findings(tmp_path, [_profile()], _MD_EVAL_DIFF)
    assert result["security"] == []
    assert result["block_count"] == 0


def test_py_eval_still_blocked(ha_review: ModuleType, tmp_path: Path) -> None:
    """문서 제외가 코드 검사를 무력화하지 않음 — .py eval() 은 BLOCK 유지."""
    result = ha_review._collect_findings(tmp_path, [_profile()], _MD_EVAL_DIFF + _PY_EVAL_DIFF)
    assert any(
        f["hook"] == "command-guard" and f["severity"] == "BLOCK" for f in result["security"]
    )


def test_self_package_import_not_warned(ha_review: ModuleType, tmp_path: Path) -> None:
    """자기 패키지 (backend/src/hijack) import → dependency-check WARN 0."""
    pkg = tmp_path / "backend" / "src" / "hijack"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    diff = (
        "diff --git a/backend/tests/test_x.py b/backend/tests/test_x.py\n"
        "--- a/backend/tests/test_x.py\n"
        "+++ b/backend/tests/test_x.py\n"
        "+from hijack import analyzer\n"
        "+import tomllib\n"
    )
    result = ha_review._collect_findings(tmp_path, [_profile()], diff)
    assert [f for f in result["security"] if f["hook"] == "dependency-check"] == []
