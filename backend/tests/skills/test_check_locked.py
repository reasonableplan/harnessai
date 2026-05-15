"""check_locked.py PreToolUse hook 단위 테스트 (5개).

대상: ~/.claude/harness/bin/check_locked.py
전략: subprocess 로 스크립트 호출 + stdin JSON 전달 + exit code / stderr 검증.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# check_locked.py 절대 경로
HOOK_SCRIPT = Path.home() / ".claude" / "harness" / "bin" / "check_locked.py"

# skeleton.md 를 담을 임시 경로 (tmp_path 로 교체)
_LOCKED_CONTENT = """\
# Skeleton

## Requirements

<!-- HUMAN-LOCKED:requirements — do not edit -->
This is the locked requirements section.
Bullet point 1.
<!-- /HUMAN-LOCKED:requirements -->

## Other Section

Free to edit content here.
"""

_UNLOCKED_CONTENT = """\
# Skeleton

## Requirements

No locked sections here.
"""


def _call_hook(
    payload: dict,
    *,
    skeleton_path: Path | None = None,
    env_override: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """hook 스크립트를 subprocess 로 호출하고 (exit_code, stdout, stderr) 반환."""
    env = os.environ.copy()
    env.pop("HARNESS_SKIP_LOCK_HOOK", None)
    if env_override:
        env.update(env_override)

    inp = json.dumps(payload)
    result = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=inp,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    return result.returncode, result.stdout, result.stderr


def test_non_skeleton_file_passes(tmp_path: Path) -> None:
    """다른 파일 (예: src/main.py) Edit → exit 0."""
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(tmp_path / "src" / "main.py"),
            "old_string": "some text",
            "new_string": "other text",
        },
    }
    rc, _, _ = _call_hook(payload)
    assert rc == 0


def test_skeleton_edit_outside_locked_passes(tmp_path: Path) -> None:
    """skeleton.md 안의 LOCKED 외 영역 Edit → exit 0."""
    skeleton = tmp_path / "docs" / "skeleton.md"
    skeleton.parent.mkdir(parents=True)
    skeleton.write_text(_LOCKED_CONTENT, encoding="utf-8")

    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(skeleton),
            "old_string": "Free to edit content here.",
            "new_string": "Updated free content.",
        },
    }
    rc, _, _ = _call_hook(payload)
    assert rc == 0


def test_skeleton_edit_inside_locked_blocks(tmp_path: Path) -> None:
    """LOCKED 섹션 안 텍스트를 old_string 으로 Edit → exit 2 + stderr 메시지."""
    skeleton = tmp_path / "docs" / "skeleton.md"
    skeleton.parent.mkdir(parents=True)
    skeleton.write_text(_LOCKED_CONTENT, encoding="utf-8")

    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(skeleton),
            "old_string": "This is the locked requirements section.",
            "new_string": "Replaced locked content.",
        },
    }
    rc, _, stderr = _call_hook(payload)
    assert rc == 2
    assert "HITL BLOCK" in stderr
    assert "requirements" in stderr


def test_skeleton_write_missing_marker_blocks(tmp_path: Path) -> None:
    """Write 로 전체 덮어쓰기 — LOCKED 마커 없는 content → exit 2."""
    skeleton = tmp_path / "docs" / "skeleton.md"
    skeleton.parent.mkdir(parents=True)
    skeleton.write_text(_LOCKED_CONTENT, encoding="utf-8")

    # LOCKED 마커가 없는 새 content 로 덮어쓰기 시도
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(skeleton),
            "content": "# New skeleton without locked markers\n\nAll new content.\n",
        },
    }
    rc, _, stderr = _call_hook(payload)
    assert rc == 2
    assert "HITL BLOCK" in stderr
    assert "requirements" in stderr


def test_skeleton_write_mutates_locked_body_blocks(tmp_path: Path) -> None:
    """Write 가 LOCKED 마커 유지하면서 body 만 변조 → silent HITL bypass 차단 (CRITICAL)."""
    skeleton = tmp_path / "docs" / "skeleton.md"
    skeleton.parent.mkdir(parents=True)
    skeleton.write_text(_LOCKED_CONTENT, encoding="utf-8")

    # 마커는 유지하면서 body 만 다른 텍스트로 변조 — silent HITL bypass 시나리오
    mutated = _LOCKED_CONTENT.replace(
        "This is the locked requirements section.",
        "Body silently swapped by AI.",
    )
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(skeleton),
            "content": mutated,
        },
    }
    rc, _, stderr = _call_hook(payload)
    assert rc == 2
    assert "HITL BLOCK" in stderr
    assert "body 변조" in stderr
    assert "requirements" in stderr


def test_env_skip_lock_hook_bypasses(tmp_path: Path) -> None:
    """HARNESS_SKIP_LOCK_HOOK=1 환경변수 → 항상 exit 0 (escape hatch)."""
    skeleton = tmp_path / "docs" / "skeleton.md"
    skeleton.parent.mkdir(parents=True)
    skeleton.write_text(_LOCKED_CONTENT, encoding="utf-8")

    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(skeleton),
            "old_string": "This is the locked requirements section.",
            "new_string": "Override via env.",
        },
    }
    rc, _, _ = _call_hook(payload, env_override={"HARNESS_SKIP_LOCK_HOOK": "1"})
    assert rc == 0
