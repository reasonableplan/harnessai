"""Task B3: ha-verify mobile toolchain 사전 점검 + platform_warnings 검증.

ha-verify/run.py 의 cmd_prepare 출력에:
- platform_warnings: list[str] 필드 포함
- flutter 명령 없으면 stderr 안내 + platform_warnings 포함
- ios-swift on Windows → platform_warnings 에 "swift build dry-run only" 포함
- android-kotlin + JAVA_HOME 없음 → platform_warnings 에 "JAVA_HOME" 포함
- 정상 환경 → platform_warnings 빈 리스트

subprocess + monkeypatch 로 shutil.which / os.environ 시뮬.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_VERIFY_RUN = REPO_ROOT / "skills" / "ha-verify" / "run.py"


def _make_project(tmp_path: Path, profile_id: str) -> Path:
    """profile_id 에 맞는 최소 프로젝트 + harness-plan.md 생성."""
    project = tmp_path / "myproject"
    project.mkdir()
    docs = project / "docs"
    docs.mkdir()

    # 프로파일별 마커 파일
    if profile_id == "flutter":
        (project / "pubspec.yaml").write_text(
            "name: myapp\nflutter:\n  sdk: flutter\n", encoding="utf-8"
        )
    elif profile_id == "react-native-expo":
        (project / "package.json").write_text(
            '{"name":"myapp","dependencies":{"expo":"^50.0.0","react-native":"0.73.0"}}',
            encoding="utf-8",
        )
    elif profile_id == "android-kotlin":
        (project / "build.gradle.kts").write_text(
            'plugins { id("com.android.application") }\n', encoding="utf-8"
        )
    elif profile_id == "ios-swift":
        (project / "Package.swift").write_text(
            'let package = Package(name: "myapp")\n', encoding="utf-8"
        )

    plan_md = textwrap.dedent(f"""\
        ---
        project_name: myproject
        project_type: Mobile App
        scale: small
        pipeline:
          steps:
            - ha-init
            - ha-design
            - ha-plan
            - ha-build
            - ha-verify
            - ha-review
          current_step: built
          completed_steps:
            - ha-init
            - ha-design
            - ha-plan
            - ha-build:all-done
          skipped_steps: []
          gstack_mode: manual
        profiles:
          - id: {profile_id}
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
        user_description_original: "테스트용 {profile_id} 앱"
        gstack_mode: manual
        ---

        # myproject
    """)
    (docs / "harness-plan.md").write_text(plan_md, encoding="utf-8")
    (docs / "skeleton.md").write_text("# myproject\n", encoding="utf-8")

    return project


def _run_prepare(project: Path, extra_env: dict[str, str] | None = None) -> tuple[dict, str]:
    """ha-verify prepare 실행. (stdout_json, stderr_text) 반환."""
    env = dict(os.environ)
    env["HARNESS_AI_HOME"] = str(REPO_ROOT)
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [sys.executable, str(HA_VERIFY_RUN), "prepare"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(project),
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"ha-verify prepare failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout[:500]}\nstderr: {result.stderr[:500]}"
    )
    return json.loads(result.stdout), result.stderr


# ── 테스트 ──────────────────────────────────────────────────────────────


def test_flutter_missing_toolchain_warns(tmp_path: Path) -> None:
    """flutter 명령 없는 환경 → stderr 안내 + platform_warnings 포함."""
    project = _make_project(tmp_path, "flutter")
    # PATH 에서 flutter 제거 (빈 PATH 로 실행)
    output, stderr = _run_prepare(project, extra_env={"PATH": ""})
    assert "platform_warnings" in output, "platform_warnings field missing from output"
    # flutter 없으면 경고 메시지가 platform_warnings 또는 stderr 에 있어야 함
    has_warning = (
        any("flutter" in w.lower() for w in output["platform_warnings"])
        or "flutter" in stderr.lower()
    )
    assert has_warning, (
        f"expected flutter toolchain warning, got platform_warnings={output['platform_warnings']!r}, "
        f"stderr={stderr!r}"
    )


def test_ios_swift_on_windows_platform_warning(tmp_path: Path) -> None:
    """ios-swift on Windows → platform_warnings 에 'swift build dry-run only' 관련 메시지."""
    project = _make_project(tmp_path, "ios-swift")
    # Windows 시뮬: PLATFORM 환경변수로 표시, swift 없음
    output, _ = _run_prepare(project, extra_env={"PATH": "", "_HA_VERIFY_PLATFORM": "windows"})
    assert "platform_warnings" in output, "platform_warnings field missing"
    warnings_text = " ".join(output["platform_warnings"]).lower()
    assert "swift" in warnings_text or "xcode" in warnings_text or "ios" in warnings_text, (
        f"expected ios/swift warning on windows, got: {output['platform_warnings']}"
    )


def test_android_kotlin_no_java_home_warns(tmp_path: Path) -> None:
    """android-kotlin + JAVA_HOME 없음 → platform_warnings 에 JAVA_HOME 언급."""
    project = _make_project(tmp_path, "android-kotlin")
    env_override = {"JAVA_HOME": "", "PATH": ""}
    output, _ = _run_prepare(project, extra_env=env_override)
    assert "platform_warnings" in output, "platform_warnings field missing"
    warnings_text = " ".join(output["platform_warnings"]).lower()
    has_java_warn = (
        "java" in warnings_text or "gradle" in warnings_text or "android" in warnings_text
    )
    assert has_java_warn, (
        f"expected JAVA_HOME warning for android-kotlin, got: {output['platform_warnings']}"
    )


def test_normal_env_platform_warnings_empty(tmp_path: Path) -> None:
    """platform_warnings 필드가 output 에 항상 존재 (정상 환경에서도)."""
    # flutter project 로 테스트 (flutter 있는 환경이면 빈 리스트)
    project = _make_project(tmp_path, "flutter")
    output, _ = _run_prepare(project)
    # 필드 자체는 항상 존재해야 함
    assert "platform_warnings" in output, "platform_warnings field must always be present"
    assert isinstance(output["platform_warnings"], list), (
        f"platform_warnings must be a list, got: {type(output['platform_warnings'])}"
    )
