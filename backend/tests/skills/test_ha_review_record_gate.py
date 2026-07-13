"""R2/R5/R6 회귀 테스트: ha-review 보안 훅 자동 실행 + record gate.

결함 요약:
  R2: cmd_prepare 가 ai-slop 만 실행하고 SecurityHooks 7개 훅과 mobile 룰을 호출 안 함.
  R5: record reject + violations 빈 string 도 통과 (가드레일 미강제).
  R6: record approve + BLOCK 발견 상태에서 통과 가능 (BLOCK 검증 없음).

Fix:
  - _collect_findings() 헬퍼: SecurityHooks.from_profile().run_all() + mobile 룰 모두 실행.
  - cmd_prepare: _collect_findings() 결과를 security_findings + security_summary 로 출력.
  - cmd_record: approve + BLOCK → exit 1. reject + violations 없음 → exit 1.
  - --allow-block flag: 의도적 BLOCK 우회.
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
HA_REVIEW_RUN = REPO_ROOT / "skills" / "ha-review" / "run.py"


@pytest.fixture(scope="module")
def ha_review() -> ModuleType:
    """ha-review/run.py (repo mirror) 를 모듈로 로드."""
    loader = SourceFileLoader("ha_review_record_gate", str(HA_REVIEW_RUN))
    spec = importlib.util.spec_from_loader("ha_review_record_gate", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_review_record_gate"] = mod
    loader.exec_module(mod)
    return mod


# ── R2: prepare 가 security_findings 키 포함 ──────────────────────────


def test_prepare_output_has_security_findings_key(ha_review: ModuleType, tmp_path: Path) -> None:
    """cmd_prepare 출력에 security_findings + security_summary 키가 존재."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"
    mock_plan.profiles = []
    mock_plan.skeleton_hash = ""

    captured_output: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured_output.append(data)

    with (
        patch.object(
            ha_review, "load_plan", return_value=(mock_plan, tmp_path / "harness-plan.md", tmp_path)
        ),
        patch.object(ha_review, "assert_state"),
        patch.object(ha_review, "_check_git_repo"),
        patch.object(ha_review, "get_active_profiles", return_value=[]),
        patch.object(ha_review, "_extract_diff", return_value=("", "test-scope")),
        patch.object(
            ha_review,
            "_collect_findings",
            return_value={
                "ai_slop": [],
                "security": [],
                "block_count": 0,
                "warn_count": 0,
            },
        ),
        patch.object(
            ha_review,
            "check_skeleton_hash",
            return_value=MagicMock(
                skeleton_missing=True,
                is_legacy=False,
                is_match=True,
            ),
        ),
        patch("builtins.print", side_effect=fake_print),
    ):
        args = MagicMock()
        result = ha_review.cmd_prepare(args)

    assert result == 0
    # #8 가드 추가로 빈 diff 시 [WARN] stderr 출력이 생겨 captured_output 길이 >= 1
    # JSON 출력은 마지막 원소 (info() 는 stderr 로 출력하나 builtins.print 패치로 포함됨)
    assert len(captured_output) >= 1
    output = json.loads(captured_output[-1])
    assert "security_findings" in output, f"security_findings missing: {list(output.keys())}"
    assert "security_summary" in output, f"security_summary missing: {list(output.keys())}"
    assert "block_count" in output["security_summary"]
    assert "warn_count" in output["security_summary"]
    # backward compat
    assert "ai_slop_findings_in_diff" in output


def test_prepare_security_summary_reflects_block_count(
    ha_review: ModuleType, tmp_path: Path
) -> None:
    """_collect_findings 가 BLOCK 1건 반환 시 security_summary.block_count == 1."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"
    mock_plan.profiles = []
    mock_plan.skeleton_hash = ""

    captured_output: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured_output.append(data)

    block_finding = {
        "hook": "secret-filter",
        "severity": "BLOCK",
        "message": "하드코딩 시크릿",
        "snippet": "",
    }
    with (
        patch.object(
            ha_review, "load_plan", return_value=(mock_plan, tmp_path / "harness-plan.md", tmp_path)
        ),
        patch.object(ha_review, "assert_state"),
        patch.object(ha_review, "_check_git_repo"),
        patch.object(ha_review, "get_active_profiles", return_value=[]),
        patch.object(ha_review, "_extract_diff", return_value=("", "test-scope")),
        patch.object(
            ha_review,
            "_collect_findings",
            return_value={
                "ai_slop": [],
                "security": [block_finding],
                "block_count": 1,
                "warn_count": 0,
            },
        ),
        patch.object(
            ha_review,
            "check_skeleton_hash",
            return_value=MagicMock(
                skeleton_missing=True,
                is_legacy=False,
                is_match=True,
            ),
        ),
        patch("builtins.print", side_effect=fake_print),
    ):
        args = MagicMock()
        result = ha_review.cmd_prepare(args)

    assert result == 0  # prepare 는 advisory — BLOCK 있어도 exit 0
    # #8 가드 추가로 빈 diff 시 [WARN] 출력이 포함될 수 있어 마지막 원소에서 JSON 파싱
    output = json.loads(captured_output[-1])
    assert output["security_summary"]["block_count"] == 1
    assert len(output["security_findings"]) == 1


# ── R2: _collect_findings 가 SecurityHooks 를 호출 ────────────────────


def test_collect_findings_calls_security_hooks(ha_review: ModuleType, tmp_path: Path) -> None:
    """_collect_findings 가 SecurityHooks.from_profile().run_all() 을 호출."""
    mock_profile = MagicMock()
    mock_profile.id = "fastapi"

    mock_result = MagicMock()
    mock_result.findings = []

    mock_hooks_instance = MagicMock()
    mock_hooks_instance.run_all.return_value = mock_result

    with patch.object(ha_review, "SecurityHooks") as mock_hooks_cls:
        mock_hooks_cls.from_profile.return_value = mock_hooks_instance
        result = ha_review._collect_findings(tmp_path, [mock_profile], "some diff text")

    # extra_python_allowed: tmp_path 에 로컬 패키지 없음 → 빈 frozenset (LESSON-030).
    # backend 모드라 frontend FP #19 채널(extra_frontend_*)은 None.
    mock_hooks_cls.from_profile.assert_called_once_with(
        mock_profile,
        extra_python_allowed=frozenset(),
        extra_frontend_allowed=None,
        extra_frontend_prefixes=None,
    )
    mock_hooks_instance.run_all.assert_called_once()
    assert "security" in result
    assert "ai_slop" in result
    assert "block_count" in result


def test_collect_findings_mobile_profile_runs_mobile_rules(
    ha_review: ModuleType, tmp_path: Path
) -> None:
    """_collect_findings — mobile profile 이면 mobile 룰도 실행."""
    mock_profile = MagicMock()
    mock_profile.id = "react-native-expo"

    mock_result = MagicMock()
    mock_result.findings = []

    mock_hooks_instance = MagicMock()
    mock_hooks_instance.run_all.return_value = mock_result

    diff = "+  await AsyncStorage.setItem('auth_token', token);\n"

    with patch.object(ha_review, "SecurityHooks") as mock_hooks_cls:
        mock_hooks_cls.from_profile.return_value = mock_hooks_instance
        result = ha_review._collect_findings(tmp_path, [mock_profile], diff)

    # mobile 룰(_check_mobile_secret_storage)이 BLOCK 을 추가해야 함
    block_items = [f for f in result["security"] if f.get("severity") == "BLOCK"]
    assert len(block_items) >= 1, (
        f"mobile secret storage BLOCK 기대, got security={result['security']}"
    )
    assert result["block_count"] >= 1


# ── R5: record reject + violations 없음 → exit 1 ──────────────────────


def test_record_reject_without_violations_exits_1(ha_review: ModuleType) -> None:
    """record reject + --violations '' → exit 1."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"

    with (
        patch.object(
            ha_review,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_review, "assert_state"),
    ):
        args = MagicMock()
        args.verdict = "reject"
        args.violations = ""
        args.summary = "some summary"
        args.allow_block = False
        result = ha_review.cmd_record(args)

    assert result == 1


def test_record_reject_with_empty_json_array_exits_1(ha_review: ModuleType) -> None:
    """record reject + --violations '[]' (빈 배열) → exit 1."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"

    with (
        patch.object(
            ha_review,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_review, "assert_state"),
    ):
        args = MagicMock()
        args.verdict = "reject"
        args.violations = "[]"
        args.summary = "some summary"
        args.allow_block = False
        result = ha_review.cmd_record(args)

    assert result == 1


def test_record_reject_with_violations_passes(ha_review: ModuleType) -> None:
    """record reject + violations 있는 JSON → 통과 (exit 0)."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"
    mock_plan.verify_history = []

    captured: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured.append(data)

    with (
        patch.object(
            ha_review,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_review, "assert_state"),
        patch.object(ha_review, "record_verify"),
        patch.object(ha_review, "regress"),
        patch.object(ha_review, "save_plan"),
        patch("builtins.print", side_effect=fake_print),
    ):
        args = MagicMock()
        args.verdict = "reject"
        args.violations = '["[auth-guard:BLOCK] src/foo.py:42 — JWT type claim 누락 → T-003"]'
        args.summary = "auth guard violation"
        args.allow_block = False
        result = ha_review.cmd_record(args)

    assert result == 0
    output = json.loads(captured[0])
    assert output["verdict"] == "reject"
    assert len(output["violations"]) == 1


# ── R6: record approve + BLOCK → exit 1 ──────────────────────────────


def test_record_approve_with_block_exits_1(ha_review: ModuleType) -> None:
    """record approve + BLOCK 1건 → exit 1."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"

    block_finding = {
        "hook": "secret-filter",
        "severity": "BLOCK",
        "message": "하드코딩 시크릿",
        "snippet": "",
    }
    findings_result = {
        "ai_slop": [],
        "security": [block_finding],
        "block_count": 1,
        "warn_count": 0,
    }

    with (
        patch.object(
            ha_review,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_review, "assert_state"),
        patch.object(ha_review, "get_active_profiles", return_value=[]),
        patch.object(ha_review, "_extract_diff", return_value=("", "test-scope")),
        patch.object(ha_review, "_collect_findings", return_value=findings_result),
    ):
        args = MagicMock()
        args.verdict = "approve"
        args.violations = ""
        args.summary = ""
        args.allow_block = False
        result = ha_review.cmd_record(args)

    assert result == 1


def test_record_approve_with_block_and_allow_block_passes(ha_review: ModuleType) -> None:
    """record approve + BLOCK 1건 + --allow-block → 통과 (exit 0)."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"
    mock_plan.verify_history = []

    captured: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured.append(data)

    with (
        patch.object(
            ha_review,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_review, "assert_state"),
        # #8 가드: approve 분기에서 _extract_diff 가 호출되므로 mock 필요
        patch.object(ha_review, "_extract_diff", return_value=("some diff", "test-scope")),
        patch.object(ha_review, "record_verify"),
        patch.object(ha_review, "transition"),
        patch.object(ha_review, "save_plan"),
        patch("builtins.print", side_effect=fake_print),
    ):
        args = MagicMock()
        args.verdict = "approve"
        args.violations = ""
        args.summary = "override approved"
        args.allow_block = True
        # allow_empty 는 MagicMock 자동 속성으로 truthy → #8 가드 통과
        result = ha_review.cmd_record(args)

    assert result == 0
    output = json.loads(captured[0])
    assert output["verdict"] == "approve"


def test_record_approve_no_block_passes(ha_review: ModuleType) -> None:
    """record approve + BLOCK 0건 → 정상 통과 (exit 0)."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"
    mock_plan.verify_history = []

    captured: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured.append(data)

    findings_result = {"ai_slop": [], "security": [], "block_count": 0, "warn_count": 0}

    with (
        patch.object(
            ha_review,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_review, "assert_state"),
        patch.object(ha_review, "get_active_profiles", return_value=[]),
        patch.object(ha_review, "_extract_diff", return_value=("", "test-scope")),
        patch.object(ha_review, "_collect_findings", return_value=findings_result),
        patch.object(ha_review, "record_verify"),
        patch.object(ha_review, "transition"),
        patch.object(ha_review, "save_plan"),
        patch("builtins.print", side_effect=fake_print),
    ):
        args = MagicMock()
        args.verdict = "approve"
        args.violations = ""
        args.summary = "all clean"
        args.allow_block = False
        result = ha_review.cmd_record(args)

    assert result == 0


def test_record_approve_error_message_mentions_block(
    ha_review: ModuleType, capsys: pytest.CaptureFixture
) -> None:
    """approve + BLOCK 시 에러 메시지에 'BLOCK 위반' 포함."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"

    block_finding = {
        "hook": "command-guard",
        "severity": "BLOCK",
        "message": "eval() 사용",
        "snippet": "eval(x)",
    }
    findings_result = {
        "ai_slop": [],
        "security": [block_finding],
        "block_count": 1,
        "warn_count": 0,
    }

    with (
        patch.object(
            ha_review,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_review, "assert_state"),
        patch.object(ha_review, "get_active_profiles", return_value=[]),
        patch.object(ha_review, "_extract_diff", return_value=("", "test-scope")),
        patch.object(ha_review, "_collect_findings", return_value=findings_result),
    ):
        args = MagicMock()
        args.verdict = "approve"
        args.violations = ""
        args.summary = ""
        args.allow_block = False
        ha_review.cmd_record(args)

    captured = capsys.readouterr()
    assert "BLOCK 위반" in captured.err or "BLOCK 위반" in captured.out


# ── D-8 (dogfood subtrack): REJECT → 위반 태스크 needs_rebuild 전이 ──────────
#
# REJECT 는 pipeline 을 building 으로 회귀시키지만 태스크는 done 그대로였다.
# → /ha-build --resume 이 "빌드할 태스크 없음" 으로 dead-end (rework 루프 단절).
# ha-verify record --passed false --rework-tasks 와 동일한 계약으로 맞춘다.

_TASKS_MD = (
    "| ID    | Agent         | Depends On | Description | Status     |\n"
    "|-------|---------------|------------|-------------|------------|\n"
    "| T-003 | backend_coder | -          | auth 서비스 | done       |\n"
    "| T-004 | backend_coder | -          | 대시보드    | done       |\n"
)


def _reject_args(violations: str, *, rework_tasks: str | None = None, no_rework: bool = False):
    args = MagicMock()
    args.verdict = "reject"
    args.violations = violations
    args.summary = "review reject"
    args.allow_block = False
    args.rework_tasks = rework_tasks
    args.no_rework = no_rework
    return args


def _run_reject(ha_review: ModuleType, tmp_path: Path, args) -> tuple[int, list[str]]:
    plan_path = tmp_path / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")
    (tmp_path / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")

    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"
    mock_plan.verify_history = []

    captured: list[str] = []

    with (
        patch.object(ha_review, "load_plan", return_value=(mock_plan, plan_path, tmp_path)),
        patch.object(ha_review, "assert_state"),
        patch.object(ha_review, "record_verify"),
        patch.object(ha_review, "regress"),
        patch.object(ha_review, "save_plan"),
        patch("builtins.print", side_effect=lambda data, **kw: captured.append(data)),
    ):
        code = ha_review.cmd_record(args)
    return code, captured


def test_reject_marks_violation_tasks_for_rebuild(ha_review: ModuleType, tmp_path: Path) -> None:
    """violations 의 T-ID → tasks.md 가 needs_rebuild 로 전이 + 출력에 보고."""
    args = _reject_args(
        '["[code-quality:WARN] app/loading.tsx:20 — inline style → T-003"]',
        rework_tasks=None,
    )
    code, captured = _run_reject(ha_review, tmp_path, args)

    assert code == 0
    text = (tmp_path / "tasks.md").read_text(encoding="utf-8")
    assert "needs_rebuild" in text
    rows = {
        line.split("|")[1].strip(): line.split("|")[5].strip()
        for line in text.splitlines()
        if line.startswith("| T-")
    }
    assert rows["T-003"] == "needs_rebuild"
    assert rows["T-004"] == "done"  # 지목되지 않은 태스크는 불변

    payload = json.loads(captured[-1])
    assert payload["rebuild_required_tasks"] == ["T-003"]


def test_reject_rework_tasks_flag_overrides_violation_parsing(
    ha_review: ModuleType, tmp_path: Path
) -> None:
    """--rework-tasks CSV 가 있으면 그것이 재작업 대상 (ha-verify 와 동일 계약)."""
    args = _reject_args('["[hook] 파일 설명 (T-ID 없음)"]', rework_tasks="T-003,T-004")
    code, _ = _run_reject(ha_review, tmp_path, args)

    assert code == 0
    text = (tmp_path / "tasks.md").read_text(encoding="utf-8")
    assert text.count("needs_rebuild") == 2


def test_reject_without_any_task_id_exits_1(ha_review: ModuleType, tmp_path: Path) -> None:
    """violations 에 T-ID 도 없고 --rework-tasks/--no-rework 도 없으면 차단."""
    args = _reject_args('["[hook:BLOCK] src/foo.py:1 — 설명만 있고 재작업 대상 미지정"]')
    code, _ = _run_reject(ha_review, tmp_path, args)

    assert code == 1
    assert "needs_rebuild" not in (tmp_path / "tasks.md").read_text(encoding="utf-8")


def test_reject_no_rework_flag_allows_missing_task_id(
    ha_review: ModuleType, tmp_path: Path
) -> None:
    """환경 문제 등 태스크 재작업이 아닌 REJECT → --no-rework 로 통과, 태스크 불변."""
    args = _reject_args('["[env] 설명"]', no_rework=True)
    code, _ = _run_reject(ha_review, tmp_path, args)

    assert code == 0
    assert "needs_rebuild" not in (tmp_path / "tasks.md").read_text(encoding="utf-8")


def test_reject_summary_carries_rework_marker(ha_review: ModuleType, tmp_path: Path) -> None:
    """summary 에 [rework: T-003] 마킹 — pipeline_advisor 가 회귀 사유를 읽는 경로."""
    args = _reject_args('["[hook] app/x.tsx:1 — 위반 → T-003"]')
    recorded: list[str] = []

    plan_path = tmp_path / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")
    (tmp_path / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")

    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"

    with (
        patch.object(ha_review, "load_plan", return_value=(mock_plan, plan_path, tmp_path)),
        patch.object(ha_review, "assert_state"),
        patch.object(
            ha_review,
            "record_verify",
            side_effect=lambda plan, step, passed, summary: recorded.append(summary),
        ),
        patch.object(ha_review, "regress"),
        patch.object(ha_review, "save_plan"),
        patch("builtins.print"),
    ):
        assert ha_review.cmd_record(args) == 0

    assert "[rework: T-003]" in recorded[0]


def test_reject_warns_when_task_id_not_transitioned(ha_review: ModuleType, tmp_path: Path) -> None:
    """지목한 T-ID 가 tasks.md 에 없으면(오타 등) 조용히 넘어가지 말고 경고.

    mark_for_rebuild 는 done 태스크만 전이시킨다 — 미매칭이면 needs_rebuild 가 하나도
    안 생겨 /ha-build --resume 이 다시 dead-end 가 된다.
    """
    args = _reject_args('["[hook] src/x.py:1 — 위반 → T-999"]')
    code, captured = _run_reject(ha_review, tmp_path, args)

    assert code == 0
    assert any("needs_rebuild 미전이" in line and "T-999" in line for line in captured)
    payload = json.loads(captured[-1])
    assert payload["rebuild_required_tasks"] == []
