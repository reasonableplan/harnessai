"""T-000 결정론 스캐폴드 부트스트랩 회귀 테스트 (scaffolding-design.md Phase A).

대상:
  - skills/ha-plan/run.py :: _compute_t000_row / _inject_t000_row /
    _validate_agent_mappings (scaffold agent 예외)
  - skills/ha-build/run.py :: cmd_prepare (scaffold 분기 + 선행 게이트) /
    cmd_scaffold / _merge_no_overwrite

로딩 패턴: test_ha_deepinit_validate.py 의 SourceFileLoader. 모듈 어트리뷰트 patch 는
test_ha_build_run.py / test_ha_build_drift_gate.py 의 SimpleNamespace + monkeypatch 패턴을 따른다.
스캐폴드/install 명령은 네트워크 없이 `sys.executable -c "..."` 페이크로 대체한다.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from subprocess import CompletedProcess
from types import ModuleType, SimpleNamespace

import pytest

from src.orchestrator.tasks_schema import validate_tasks_md

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_PLAN_RUN = REPO_ROOT / "skills" / "ha-plan" / "run.py"
HA_BUILD_RUN = REPO_ROOT / "skills" / "ha-build" / "run.py"


def _load_module(name: str, path: Path) -> ModuleType:
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None, f"spec load failed: {path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ha_plan() -> ModuleType:
    return _load_module("ha_plan_scaffold_bootstrap", HA_PLAN_RUN)


@pytest.fixture(scope="module")
def ha_build() -> ModuleType:
    return _load_module("ha_build_scaffold_bootstrap", HA_BUILD_RUN)


def _py(code: str) -> str:
    """현재 인터프리터로 한 줄 파이썬을 실행하는 셸 명령 (네트워크 없는 스캐폴드 페이크)."""
    return f'"{sys.executable}" -c "{code}"'


def _profile(
    id_: str,
    *,
    scaffold: str | None,
    detect: dict,
    install: str | None = None,
) -> SimpleNamespace:
    """_matches_detect / cmd_scaffold / cmd_prepare 출력이 필요로 하는 속성을 갖춘 duck-typed Profile."""
    return SimpleNamespace(
        id=id_,
        detect=detect,
        toolchain=SimpleNamespace(scaffold=scaffold, install=install, test=None),
        whitelist=SimpleNamespace(runtime=()),
    )


_TASKS_HEADER = (
    "### Phase 1 — MVP\n"
    "| ID | 에이전트 | 의존성 | 설명 | 상태 |\n"
    "|----|---------|--------|------|------|\n"
)


# ── ha-plan: _compute_t000_row — 조건 3개 ────────────────────────────────────


def test_compute_t000_row_injects_when_unbootstrapped(ha_plan, tmp_path: Path) -> None:
    """조건 1+2 충족 (scaffold 프로파일 존재 + detect 불일치) → 주입 행 반환."""
    profile = _profile(
        "nextjs", scaffold="pnpm create next-app@16 .", detect={"files": ["package.json"]}
    )
    tasks_content = _TASKS_HEADER + "| T-001 | backend_coder | - | 태스크 | 대기 |\n"

    row = ha_plan._compute_t000_row([profile], ["."], tmp_path, tasks_content)

    assert row is not None
    assert row.startswith("| T-000 | scaffold | - |")
    assert "nextjs" in row
    assert row.rstrip().endswith("| 대기 |")


def test_compute_t000_row_none_when_already_bootstrapped(ha_plan, tmp_path: Path) -> None:
    """조건 2 불충족 — detect 가 이미 만족(부트스트랩 완료) → 미주입."""
    (tmp_path / "package.json").write_text('{"name": "x"}', encoding="utf-8")
    profile = _profile(
        "nextjs", scaffold="pnpm create next-app@16 .", detect={"files": ["package.json"]}
    )
    tasks_content = _TASKS_HEADER + "| T-001 | backend_coder | - | 태스크 | 대기 |\n"

    row = ha_plan._compute_t000_row([profile], ["."], tmp_path, tasks_content)

    assert row is None


def test_compute_t000_row_none_when_t000_already_present(ha_plan, tmp_path: Path) -> None:
    """조건 3 불충족 — T-000 행이 이미 있음 (LLM 이 직접 작성) → 중복 주입 안 함."""
    profile = _profile(
        "nextjs", scaffold="pnpm create next-app@16 .", detect={"files": ["package.json"]}
    )
    tasks_content = (
        _TASKS_HEADER
        + "| T-000 | scaffold | - | 수동 작성 | 대기 |\n"
        + "| T-001 | backend_coder | T-000 | 태스크 | 대기 |\n"
    )

    row = ha_plan._compute_t000_row([profile], ["."], tmp_path, tasks_content)

    assert row is None


def test_compute_t000_row_none_when_no_scaffold_profile(ha_plan, tmp_path: Path) -> None:
    """조건 1 불충족 — toolchain.scaffold 가 없는 프로파일(예: fastapi)만 있으면 미주입."""
    profile = _profile("fastapi", scaffold=None, detect={"files": ["pyproject.toml"]})
    tasks_content = _TASKS_HEADER + "| T-001 | backend_coder | - | 태스크 | 대기 |\n"

    row = ha_plan._compute_t000_row([profile], ["."], tmp_path, tasks_content)

    assert row is None


# ── ha-plan: _inject_t000_row — 주입 위치 ────────────────────────────────────


def test_inject_t000_row_right_after_header_separator(ha_plan) -> None:
    """주입 위치 — 첫 태스크 표의 헤더 구분행(|---|...) 직후."""
    tasks_content = _TASKS_HEADER + "| T-001 | backend_coder | - | 태스크 | 대기 |\n"
    row = "| T-000 | scaffold | - | 결정론 스캐폴드 부트스트랩 (nextjs) | 대기 |"

    result = ha_plan._inject_t000_row(tasks_content, row)

    lines = result.splitlines()
    sep_idx = next(i for i, line in enumerate(lines) if line.startswith("|----"))
    assert lines[sep_idx + 1] == row
    assert "T-001" in result  # 기존 태스크는 보존


def test_injected_content_passes_schema_validation(ha_plan) -> None:
    """주입 후에도 validate_tasks_md 통과 (T-000 행 자체가 well-formed)."""
    tasks_content = _TASKS_HEADER + "| T-001 | backend_coder | - | 태스크 | 대기 |\n"
    row = "| T-000 | scaffold | - | 결정론 스캐폴드 부트스트랩 (nextjs) | 대기 |"

    injected = ha_plan._inject_t000_row(tasks_content, row)

    assert validate_tasks_md(injected) == []


# ── ha-plan: _validate_agent_mappings — scaffold agent 예외 ─────────────────


def test_validate_agent_mappings_exempts_scaffold_agent(ha_plan) -> None:
    """agent_id == 'scaffold' 는 agents.yaml 대조 없이 항상 통과 (예약 의사 에이전트)."""
    agents_yaml_path = REPO_ROOT / "backend" / "agents.yaml"
    tasks_content = (
        _TASKS_HEADER + "| T-000 | scaffold | - | 결정론 스캐폴드 부트스트랩 (nextjs) | 대기 |\n"
    )

    mismatches = ha_plan._validate_agent_mappings(
        tasks_content, agents_yaml_path, frozenset(), frozenset()
    )

    assert mismatches == []


# ── ha-build: cmd_prepare — scaffold 분기 출력 ───────────────────────────────


_TASKS_TABLE_SCAFFOLD_ONLY = (
    "| ID    | Agent    | Depends On | Description | Status |\n"
    "|-------|----------|------------|-------------|--------|\n"
    "| T-000 | scaffold | -          | 결정론 스캐폴드 부트스트랩 (nextjs) | 대기 |\n"
)

_TASKS_TABLE_WITH_SCAFFOLD_AND_NEXT = (
    "| ID    | Agent         | Depends On | Description | Status |\n"
    "|-------|---------------|------------|-------------|--------|\n"
    "| T-000 | scaffold      | -          | 결정론 스캐폴드 부트스트랩 (nextjs) | 대기 |\n"
    "| T-001 | backend_coder | -          | 태스크       | 대기    |\n"
)


def _make_build_plan() -> SimpleNamespace:
    return SimpleNamespace(
        pipeline=SimpleNamespace(
            current_step="planned",
            completed_steps=(),
            skipped_steps=(),
            steps=("planned", "building", "built"),
            gstack_mode="manual",
        ),
        profiles=[SimpleNamespace(id="nextjs", path=".")],
        skeleton_hash=None,
        frozen_status="frozen",
    )


def _patch_build_prepare(ha_build, monkeypatch, plan, tmp_path: Path, tasks_text: str) -> Path:
    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(tasks_text, encoding="utf-8")
    plan_path = tmp_path / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(ha_build, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_build, "save_plan", lambda p, pp: None)
    return tasks_path


def test_prepare_scaffold_task_output_shape(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """agent=scaffold 태스크 prepare 출력: scaffold=true + scaffold_commands, agent_prompt 없음."""
    plan = _make_build_plan()
    _patch_build_prepare(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_SCAFFOLD_ONLY)
    nextjs = _profile(
        "nextjs", scaffold="pnpm create next-app@16 .", detect={"files": ["package.json"]}
    )
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda plan, project: [nextjs])

    rc = ha_build.cmd_prepare(SimpleNamespace(task="T-000", skip_frozen_gate=False))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    task = out["tasks"][0]
    assert task["scaffold"] is True
    assert task["scaffold_commands"] == [
        {"profile": "nextjs", "path": ".", "command": "pnpm create next-app@16 ."}
    ]
    assert "agent_prompt" not in task
    assert task["guideline_paths"] == []


# ── ha-build: cmd_prepare — scaffold 선행 게이트 ────────────────────────────


def test_prepare_blocks_when_scaffold_unresolved_and_not_targeted(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    """미해결 T-000 이 있는데 다른 태스크를 타겟하면 BLOCK."""
    plan = _make_build_plan()
    _patch_build_prepare(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_WITH_SCAFFOLD_AND_NEXT)
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda plan, project: [])

    rc = ha_build.cmd_prepare(SimpleNamespace(task="T-001", skip_frozen_gate=False))

    assert rc == 1
    err = capsys.readouterr().err
    assert "[BLOCK]" in err
    assert "T-000" in err


def test_prepare_allows_targeting_scaffold_task_itself(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    """--task 로 scaffold 태스크 자신을 지정하면 선행 게이트가 막지 않는다."""
    plan = _make_build_plan()
    _patch_build_prepare(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_WITH_SCAFFOLD_AND_NEXT)
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda plan, project: [])

    rc = ha_build.cmd_prepare(SimpleNamespace(task="T-000", skip_frozen_gate=False))

    assert rc == 0
    err = capsys.readouterr().err
    assert "부트스트랩 선행 필요" not in err


def test_prepare_skip_scaffold_gate_bypasses_block(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """--skip-scaffold-gate 로 의도적 우회."""
    plan = _make_build_plan()
    _patch_build_prepare(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_WITH_SCAFFOLD_AND_NEXT)
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda plan, project: [])

    rc = ha_build.cmd_prepare(
        SimpleNamespace(task="T-001", skip_frozen_gate=False, skip_scaffold_gate=True)
    )

    assert rc == 0
    err = capsys.readouterr().err
    assert "부트스트랩 선행 필요" not in err


# ── ha-build: _merge_no_overwrite ───────────────────────────────────────────


def test_merge_no_overwrite_moves_new_files(ha_build, tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dst"
    (src / "a.txt").write_text("A", encoding="utf-8")

    moved, skipped = ha_build._merge_no_overwrite(src, dst)

    assert moved == 1
    assert skipped == []
    assert (dst / "a.txt").read_text(encoding="utf-8") == "A"
    assert not (src / "a.txt").exists()  # move, not copy


def test_merge_no_overwrite_preserves_existing_files(ha_build, tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dst"
    dst.mkdir()
    (src / "a.txt").write_text("NEW", encoding="utf-8")
    (dst / "a.txt").write_text("EXISTING", encoding="utf-8")

    moved, skipped = ha_build._merge_no_overwrite(src, dst)

    assert moved == 0
    assert skipped == ["a.txt"]
    assert (dst / "a.txt").read_text(encoding="utf-8") == "EXISTING"


def test_merge_no_overwrite_recurses_into_directories(ha_build, tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "app").mkdir(parents=True)
    (src / "app" / "page.tsx").write_text("x", encoding="utf-8")
    dst = tmp_path / "dst"

    moved, skipped = ha_build._merge_no_overwrite(src, dst)

    assert moved == 1
    assert skipped == []
    assert (dst / "app" / "page.tsx").read_text(encoding="utf-8") == "x"


def test_merge_no_overwrite_excludes_git_and_node_modules(ha_build, tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / ".git").mkdir(parents=True)
    (src / ".git" / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")
    (src / "node_modules").mkdir()
    (src / "node_modules" / "pkg.js").write_text("x", encoding="utf-8")
    (src / "app.py").write_text("x", encoding="utf-8")
    dst = tmp_path / "dst"

    moved, skipped = ha_build._merge_no_overwrite(src, dst)

    assert moved == 1  # app.py 만
    assert not (dst / ".git").exists()
    assert not (dst / "node_modules").exists()
    assert (dst / "app.py").exists()


# ── ha-build: cmd_scaffold — E2E (네트워크 없는 페이크 명령) ────────────────


def test_scaffold_subcommand_rejects_non_scaffold_task(ha_build, tmp_path, monkeypatch) -> None:
    """agent 가 scaffold 가 아닌 태스크를 지정하면 FAIL (exit 2)."""
    plan = SimpleNamespace(profiles=[])
    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(_TASKS_TABLE_WITH_SCAFFOLD_AND_NEXT, encoding="utf-8")
    plan_path = tmp_path / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(ha_build, "load_plan", lambda: (plan, plan_path, tmp_path))

    rc = ha_build.cmd_scaffold(SimpleNamespace(task="T-001"))

    assert rc == 2


def test_scaffold_subcommand_bootstraps_then_is_idempotent(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    """스캐폴드 실행(미부트스트랩 경로) → 재실행 시 이미 부트스트랩됨(멱등 skip)."""
    plan = SimpleNamespace(profiles=[SimpleNamespace(id="fakeprofile", path=".")])
    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(_TASKS_TABLE_SCAFFOLD_ONLY, encoding="utf-8")
    plan_path = tmp_path / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(ha_build, "load_plan", lambda: (plan, plan_path, tmp_path))

    fake_profile = _profile(
        "fakeprofile",
        scaffold=_py("open('package.json', 'w').write('{}')"),
        install=_py("open('installed.marker', 'w').write('ok')"),
        detect={"files": ["package.json"]},
    )
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda plan, project: [fake_profile])

    # 1차: detect 불일치 (package.json 없음) → 스캐폴드 실행 경로
    rc1 = ha_build.cmd_scaffold(SimpleNamespace(task="T-000"))
    assert rc1 == 0
    out1 = json.loads(capsys.readouterr().out)
    entry1 = out1["profiles"][0]
    assert entry1["id"] == "fakeprofile"
    assert entry1["scaffolded"] is True
    assert entry1["moved"] == 1
    assert entry1["skipped"] == []
    assert entry1["install_ok"] is True
    assert out1["next"] == "complete --task T-000 --status done --skip-toolchain"
    assert (tmp_path / "package.json").exists()
    assert (tmp_path / "installed.marker").exists()

    # 2차: detect 만족 (package.json 이미 있음) → 멱등 skip 경로
    rc2 = ha_build.cmd_scaffold(SimpleNamespace(task="T-000"))
    assert rc2 == 0
    out2 = json.loads(capsys.readouterr().out)
    entry2 = out2["profiles"][0]
    assert entry2["scaffolded"] is False
    assert entry2["moved"] == 0
    assert entry2["skipped"] == []
    assert entry2["install_ok"] is True


def _patch_scaffold_run(ha_build, monkeypatch, tmp_path: Path, tasks_text: str) -> None:
    """cmd_scaffold 테스트 공통 픽스처 — plan/tasks.md/load_plan 배선."""
    plan = SimpleNamespace(profiles=[SimpleNamespace(id="fakeprofile", path=".")])
    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(tasks_text, encoding="utf-8")
    plan_path = tmp_path / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(ha_build, "load_plan", lambda: (plan, plan_path, tmp_path))


def test_scaffold_subcommand_reports_failed_profile_in_results(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    """scaffold 명령 rc≠0 → exit 1 + 실패 프로파일도 results 에 포함 (JSON 완전성)."""
    _patch_scaffold_run(ha_build, monkeypatch, tmp_path, _TASKS_TABLE_SCAFFOLD_ONLY)
    fake_profile = _profile(
        "fakeprofile",
        scaffold=_py("import sys; sys.exit(1)"),
        detect={"files": ["package.json"]},
    )
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda plan, project: [fake_profile])

    rc = ha_build.cmd_scaffold(SimpleNamespace(task="T-000"))

    assert rc == 1
    cap = capsys.readouterr()
    assert "[FAIL]" in cap.err
    out = json.loads(cap.out)
    assert out["profiles"] == [
        {
            "id": "fakeprofile",
            "path": ".",
            "scaffolded": False,
            "moved": 0,
            "skipped": [],
            "install_ok": False,
        }
    ]


def test_scaffold_subcommand_handles_scaffold_timeout(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    """scaffold 명령 타임아웃 → traceback 크래시 없이 FAIL 메시지 + exit 1 + results 포함."""
    _patch_scaffold_run(ha_build, monkeypatch, tmp_path, _TASKS_TABLE_SCAFFOLD_ONLY)
    fake_profile = _profile(
        "fakeprofile", scaffold="slow-scaffold-cmd", detect={"files": ["package.json"]}
    )
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda plan, project: [fake_profile])

    def _raise_timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr("subprocess.run", _raise_timeout)

    rc = ha_build.cmd_scaffold(SimpleNamespace(task="T-000"))

    assert rc == 1
    cap = capsys.readouterr()
    assert "타임아웃" in cap.err
    out = json.loads(cap.out)
    assert out["profiles"] == [
        {
            "id": "fakeprofile",
            "path": ".",
            "scaffolded": False,
            "moved": 0,
            "skipped": [],
            "install_ok": False,
        }
    ]


def test_scaffold_subcommand_handles_install_timeout(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    """install 타임아웃 → 크래시 없이 install_ok=False + exit 1 (scaffold 산출물은 병합됨)."""
    _patch_scaffold_run(ha_build, monkeypatch, tmp_path, _TASKS_TABLE_SCAFFOLD_ONLY)
    fake_profile = _profile(
        "fakeprofile",
        scaffold="fake-scaffold-cmd",
        install="slow-install-cmd",
        detect={"files": ["package.json"]},
    )
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda plan, project: [fake_profile])

    def _fake_run(cmd, **kwargs):
        if cmd == "slow-install-cmd":
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 0))
        # scaffold command: emit the detect file into the sandbox cwd
        (Path(kwargs["cwd"]) / "package.json").write_text("{}", encoding="utf-8")
        return CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", _fake_run)

    rc = ha_build.cmd_scaffold(SimpleNamespace(task="T-000"))

    assert rc == 1
    cap = capsys.readouterr()
    assert "타임아웃" in cap.err
    out = json.loads(cap.out)
    entry = out["profiles"][0]
    assert entry["scaffolded"] is True
    assert entry["moved"] == 1
    assert entry["install_ok"] is False


# ── 스캐폴드 산출물 후처리 + 실패 관측성 (subtrack dogfood D-1~D-4) ─────────────


def test_fix_scaffold_package_name_rewrites_sandbox_leak(ha_build, tmp_path: Path) -> None:
    """D-1: package.json name 의 샌드박스 임시명(ha-scaffold-*)을 프로젝트 디렉토리명으로 재작성."""
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "ha-scaffold-_abc123", "private": True}), encoding="utf-8"
    )

    ha_build._fix_scaffold_package_name(tmp_path)

    pkg = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    assert not pkg["name"].startswith("ha-scaffold-")
    assert pkg["name"] == ha_build._npm_safe_name(tmp_path.name)
    assert pkg["private"] is True  # 다른 필드 보존


def test_fix_scaffold_package_name_keeps_real_name(ha_build, tmp_path: Path) -> None:
    """샌드박스 임시명이 아니면 무변경."""
    (tmp_path / "package.json").write_text(json.dumps({"name": "myapp"}), encoding="utf-8")

    ha_build._fix_scaffold_package_name(tmp_path)

    pkg = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    assert pkg["name"] == "myapp"


def test_fix_scaffold_package_name_noop_without_package_json(ha_build, tmp_path: Path) -> None:
    """package.json 부재 시 크래시 없이 무동작."""
    ha_build._fix_scaffold_package_name(tmp_path)


_CNA_WORKSPACE_TEMPLATE = (
    "allowBuilds:\n"
    "  sharp: set this to true or false\n"
    "  unrs-resolver: set this to true or false\n"
    "ignoredBuiltDependencies:\n"
    "  - sharp\n"
    "  - unrs-resolver\n"
)


def test_approve_scaffold_builds_replaces_placeholder(ha_build, tmp_path: Path) -> None:
    """D-2: create-next-app 템플릿의 allowBuilds 플레이스홀더 → true 승인 + 중복 ignored 블록 제거."""
    ws = tmp_path / "pnpm-workspace.yaml"
    ws.write_text(_CNA_WORKSPACE_TEMPLATE, encoding="utf-8")

    ha_build._approve_scaffold_builds(tmp_path)

    text = ws.read_text(encoding="utf-8")
    assert "set this to true or false" not in text
    assert "sharp: true" in text
    assert "unrs-resolver: true" in text
    assert "ignoredBuiltDependencies" not in text


def test_approve_scaffold_builds_noop_without_placeholder(ha_build, tmp_path: Path) -> None:
    """플레이스홀더 없는(이미 사용자가 관리하는) 파일은 그대로 둔다."""
    ws = tmp_path / "pnpm-workspace.yaml"
    original = "allowBuilds:\n  esbuild: true\n"
    ws.write_text(original, encoding="utf-8")

    ha_build._approve_scaffold_builds(tmp_path)

    assert ws.read_text(encoding="utf-8") == original


def test_approve_scaffold_builds_noop_without_file(ha_build, tmp_path: Path) -> None:
    """pnpm-workspace.yaml 부재 시 크래시 없이 무동작."""
    ha_build._approve_scaffold_builds(tmp_path)


def test_scaffold_postprocess_wired_into_pipeline(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """D-1/D-2 후처리가 cmd_scaffold 병합 직후에 실제로 수행되는지 (배선 검증)."""
    _patch_scaffold_run(ha_build, monkeypatch, tmp_path, _TASKS_TABLE_SCAFFOLD_ONLY)
    scaffold_cmd = _py(
        "import json, pathlib; "
        "pathlib.Path('package.json').write_text(json.dumps({'name': pathlib.Path.cwd().name})); "
        "pathlib.Path('pnpm-workspace.yaml').write_text('allowBuilds:\\n  sharp: set this to true or false\\n')"
    )
    fake_profile = _profile(
        "fakeprofile", scaffold=scaffold_cmd, detect={"files": ["package.json"]}
    )
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda plan, project: [fake_profile])

    rc = ha_build.cmd_scaffold(SimpleNamespace(task="T-000"))

    assert rc == 0
    pkg = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    assert not pkg["name"].startswith("ha-scaffold-")
    ws_text = (tmp_path / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    assert "set this to true or false" not in ws_text


def test_install_failure_surfaces_stdout(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """D-3: 실패 원인이 stdout 에만 있어도 FAIL 메시지에 포함 (pnpm 은 stdout 에 에러를 쓴다)."""
    _patch_scaffold_run(ha_build, monkeypatch, tmp_path, _TASKS_TABLE_SCAFFOLD_ONLY)
    fake_profile = _profile(
        "fakeprofile",
        scaffold=_py("open('package.json', 'w').write('{}')"),
        # 마커를 런타임 조합으로 생성 — 명령 문자열 echo 만으로 통과하는 공허 테스트 방지
        install=_py(
            "import sys; print('ERR_PNPM_' + 'IGNORED_BUILDS: approve needed'); sys.exit(1)"
        ),
        detect={"files": ["package.json"]},
    )
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda plan, project: [fake_profile])

    rc = ha_build.cmd_scaffold(SimpleNamespace(task="T-000"))

    assert rc == 1
    cap = capsys.readouterr()
    assert "ERR_PNPM_IGNORED_BUILDS" in cap.err


def test_scaffold_failure_next_hint_is_not_done(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """D-4: 실패(rc=1) 시 next 힌트가 done 마킹을 유도하면 안 됨."""
    _patch_scaffold_run(ha_build, monkeypatch, tmp_path, _TASKS_TABLE_SCAFFOLD_ONLY)
    fake_profile = _profile(
        "fakeprofile", scaffold=_py("import sys; sys.exit(1)"), detect={"files": ["package.json"]}
    )
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda plan, project: [fake_profile])

    rc = ha_build.cmd_scaffold(SimpleNamespace(task="T-000"))

    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert "--status done" not in out["next"]
