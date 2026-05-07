"""Task 2: 6 skill cmd_prepare 출력에 guideline_paths 필드 존재 확인.

전략:
- tmp_path 에 가짜 flutter 프로젝트 (pubspec.yaml + harness-plan.md + skeleton.md + tasks.md) 생성
- 각 skill 의 run.py 를 subprocess 로 실행해 stdout JSON 파싱
- guideline_paths 필드 존재 + flutter 프로젝트 시 4개 경로 포함 확인
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = REPO_ROOT / "skills"

# 각 run.py 경로
HA_INIT_RUN = SKILLS_DIR / "ha-init" / "run.py"
HA_DESIGN_RUN = SKILLS_DIR / "ha-design" / "run.py"
HA_PLAN_RUN = SKILLS_DIR / "ha-plan" / "run.py"
HA_BUILD_RUN = SKILLS_DIR / "ha-build" / "run.py"
HA_VERIFY_RUN = SKILLS_DIR / "ha-verify" / "run.py"
HA_REVIEW_RUN = SKILLS_DIR / "ha-review" / "run.py"


def _run_skill(script: Path, args: list[str], cwd: Path) -> dict:
    """skill run.py 를 subprocess 실행해 stdout JSON 반환."""
    import os
    env = dict(os.environ)
    env["HARNESS_AI_HOME"] = str(REPO_ROOT)
    result = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd),
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"{script.name} failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout[:500]}\n"
        f"stderr: {result.stderr[:500]}"
    )
    return json.loads(result.stdout)


def _make_flutter_project(tmp_path: Path) -> Path:
    """가짜 flutter 프로젝트 생성 — harness-plan.md 포함."""
    project = tmp_path / "myapp"
    project.mkdir()

    # flutter 마커 파일
    (project / "pubspec.yaml").write_text(
        "name: myapp\nflutter:\n  sdk: flutter\n",
        encoding="utf-8",
    )

    docs = project / "docs"
    docs.mkdir()

    # harness-plan.md — flutter 프로파일 포함
    plan_md = textwrap.dedent("""\
        ---
        project_name: myapp
        project_type: Flutter 모바일 앱
        scale: small
        pipeline:
          steps:
            - ha-init
            - ha-design
            - ha-plan
            - ha-build
            - ha-verify
            - ha-review
          current_step: init
          completed_steps: []
          skipped_steps: []
          gstack_mode: manual
        profiles:
          - id: flutter
            path: "."
            status: confirmed
        skeleton_sections:
          required:
            - overview
            - stack
          optional: []
          included:
            - overview
            - stack
        scale_axes:
          user_scale: small
          data_sensitivity: none
          team_size: solo
          availability: standard
          monetization: none
          lifecycle: mvp
        last_activity: "2026-05-07T00:00:00"
        verify_history: []
        user_description_original: "테스트용 flutter 앱"
        gstack_mode: manual
        ---

        # myapp

        ## 원본 설명
        테스트용 flutter 앱
    """)
    (docs / "harness-plan.md").write_text(plan_md, encoding="utf-8")

    # skeleton.md
    (docs / "skeleton.md").write_text(
        "# myapp Skeleton\n\n## 1. 개요\n테스트 skeleton.\n",
        encoding="utf-8",
    )

    # tasks.md (ha-build/ha-verify 용)
    tasks_md = textwrap.dedent("""\
        # Tasks — myapp

        ### Phase 1 — MVP
        | ID | 에이전트 | 의존성 | 설명 | 상태 |
        |----|---------|--------|------|------|
        | T-001 | mobile_coder_flutter | - | 기본 화면 구현 | 대기 |
    """)
    (docs / "tasks.md").write_text(tasks_md, encoding="utf-8")

    return project


# ── ha-init detect ─────────────────────────────────────────────────────


def test_ha_init_detect_has_guideline_paths(tmp_path: Path) -> None:
    """ha-init detect 출력의 matches 에 guideline_paths 필드 포함."""
    project = _make_flutter_project(tmp_path)
    output = _run_skill(HA_INIT_RUN, ["detect", str(project)], cwd=project)
    assert "matches" in output
    assert len(output["matches"]) >= 1
    flutter_match = next(
        (m for m in output["matches"] if m["profile_id"] == "flutter"), None
    )
    assert flutter_match is not None, "flutter profile not detected"
    assert "guideline_paths" in flutter_match, "guideline_paths missing from detect output"
    assert len(flutter_match["guideline_paths"]) == 4, (
        f"expected 4 guideline paths, got {flutter_match['guideline_paths']}"
    )


# ── ha-design prepare ──────────────────────────────────────────────────


def test_ha_design_prepare_has_guideline_paths(tmp_path: Path) -> None:
    """ha-design prepare 출력의 profiles 에 guideline_paths 필드 포함."""
    project = _make_flutter_project(tmp_path)
    output = _run_skill(HA_DESIGN_RUN, ["prepare"], cwd=project)
    assert "profiles" in output
    assert len(output["profiles"]) >= 1
    profile = output["profiles"][0]
    assert "guideline_paths" in profile, "guideline_paths missing from ha-design prepare output"
    assert len(profile["guideline_paths"]) == 4


# ── ha-plan prepare ────────────────────────────────────────────────────


def test_ha_plan_prepare_has_guideline_paths(tmp_path: Path) -> None:
    """ha-plan prepare 출력의 profiles 에 guideline_paths 필드 포함."""
    project = _make_flutter_project(tmp_path)
    # ha-plan 은 designed 상태 필요 → plan 을 designed 로 변경
    _advance_plan_to(project / "docs" / "harness-plan.md", "designed", ["ha-init", "ha-design"])
    output = _run_skill(HA_PLAN_RUN, ["prepare"], cwd=project)
    assert "profiles" in output
    profile = output["profiles"][0]
    assert "guideline_paths" in profile, "guideline_paths missing from ha-plan prepare output"
    assert len(profile["guideline_paths"]) == 4


# ── ha-build prepare ───────────────────────────────────────────────────


def test_ha_build_prepare_has_guideline_paths(tmp_path: Path) -> None:
    """ha-build prepare 출력의 tasks 에 guideline_paths 필드 포함."""
    project = _make_flutter_project(tmp_path)
    _advance_plan_to(
        project / "docs" / "harness-plan.md", "planned", ["ha-init", "ha-design", "ha-plan"]
    )
    output = _run_skill(HA_BUILD_RUN, ["prepare", "--task", "T-001"], cwd=project)
    assert "tasks" in output
    assert len(output["tasks"]) >= 1
    task = output["tasks"][0]
    assert "guideline_paths" in task, "guideline_paths missing from ha-build prepare task output"
    assert len(task["guideline_paths"]) == 4, (
        f"expected 4 flutter guideline paths, got {task['guideline_paths']}"
    )


# ── ha-verify prepare ──────────────────────────────────────────────────


def test_ha_verify_prepare_has_guideline_paths(tmp_path: Path) -> None:
    """ha-verify prepare 출력의 profiles 에 guideline_paths 필드 포함."""
    project = _make_flutter_project(tmp_path)
    _advance_plan_to(
        project / "docs" / "harness-plan.md",
        "built",
        ["ha-init", "ha-design", "ha-plan", "ha-build:all-done"],
    )
    output = _run_skill(HA_VERIFY_RUN, ["prepare"], cwd=project)
    assert "profiles" in output
    profile = output["profiles"][0]
    assert "guideline_paths" in profile, "guideline_paths missing from ha-verify prepare output"
    assert len(profile["guideline_paths"]) == 4


# ── ha-review prepare ──────────────────────────────────────────────────


def test_ha_review_prepare_has_guideline_paths(tmp_path: Path) -> None:
    """ha-review prepare 출력의 profiles 에 guideline_paths 필드 포함."""
    project = _make_flutter_project(tmp_path)
    _advance_plan_to(
        project / "docs" / "harness-plan.md",
        "verified",
        ["ha-init", "ha-design", "ha-plan", "ha-build:all-done", "ha-verify"],
    )
    output = _run_skill(HA_REVIEW_RUN, ["prepare"], cwd=project)
    assert "profiles" in output
    profile = output["profiles"][0]
    assert "guideline_paths" in profile, "guideline_paths missing from ha-review prepare output"
    assert len(profile["guideline_paths"]) == 4


# ── helper ─────────────────────────────────────────────────────────────


def _advance_plan_to(plan_path: Path, target_step: str, completed: list[str]) -> None:
    """harness-plan.md 의 current_step / completed_steps 를 직접 패치 (상태 강제 이동)."""
    text = plan_path.read_text(encoding="utf-8")

    # current_step 교체
    import re
    text = re.sub(r"current_step: \w+", f"current_step: {target_step}", text)

    # completed_steps 교체
    completed_yaml = "\n".join(f"    - {s}" for s in completed)
    text = re.sub(
        r"completed_steps: \[\]",
        f"completed_steps:\n{completed_yaml}",
        text,
    )
    plan_path.write_text(text, encoding="utf-8")
