"""HarnessAI v0.10.0 마이그레이션 단위 테스트.

migrate_v10.migrate() 함수의 핵심 동작을 검증:
  1. legacy plan → frozen_status='drafting' 명시 박힘
  2. --auto-freeze + LOCKED 후보 있음 → frozen 박힘
  3. --auto-freeze + LOCKED 후보 없음 → WARN + drafting 유지
  4. 이미 migrated plan → SKIP (idempotent)
  5. --dry-run → 백업/변경 없음, 미리보기만

모든 픽스처는 tmp_path 기반 — 사용자 환경 비의존.
"""

from __future__ import annotations

# migrate_v10 는 ~/.claude/harness/bin/ 에 있으므로 직접 importlib 로 로드.
import importlib
import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest
import yaml


def _load_migrate_module():
    # migrate_v10.py 는 ~/.claude/harness/bin/ 에 설치됨.
    # 레포 내 harness/bin/ 도 fallback 으로 확인 (dev 레이아웃).
    repo_harness_bin = Path(__file__).resolve().parents[3] / "harness" / "bin"
    home_harness_bin = Path.home() / ".claude" / "harness" / "bin"
    for candidate in (repo_harness_bin, home_harness_bin):
        migrate_path = candidate / "migrate_v10.py"
        if migrate_path.exists():
            break
    else:
        pytest.fail(
            f"migrate_v10.py 를 찾을 수 없음. 확인한 경로:\n"
            f"  {repo_harness_bin / 'migrate_v10.py'}\n"
            f"  {home_harness_bin / 'migrate_v10.py'}"
        )
    loader = SourceFileLoader("_migrate_v10", str(migrate_path))
    spec = importlib.util.spec_from_loader("_migrate_v10", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_migrate_v10"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mmod():
    return _load_migrate_module()


# ── 픽스처 헬퍼 ──────────────────────────────────────────────────────────


def _write_legacy_plan(
    docs_dir: Path,
    *,
    included: list[str] | None = None,
    frozen_status: str | None = None,
    frozen_at: str | None = None,
) -> Path:
    """최소 harness-plan.md 작성. frozen_status/frozen_at 생략 시 legacy (없음)."""
    docs_dir.mkdir(parents=True, exist_ok=True)
    included = included or ["requirements", "user_journey"]
    fm: dict = {
        "harness_version": 2,
        "schema_version": 1,
        "project_name": "테스트 프로젝트",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "project_type": "web",
        "scale": "small",
        "scale_axes": {
            "user_scale": "small",
            "data_sensitivity": "none",
            "team_size": "solo",
            "availability": "standard",
            "monetization": "none",
            "lifecycle": "mvp",
        },
        "user_description_original": "테스트용",
        "profiles": [{"id": "fastapi", "path": ".", "status": "confirmed"}],
        "skeleton_sections": {
            "required": included,
            "optional": [],
            "included": included,
        },
        "pipeline": {
            "steps": ["ha-init", "ha-design", "ha-plan"],
            "current_step": "designed",
            "completed_steps": ["ha-init", "ha-design"],
            "skipped_steps": [],
            "gstack_mode": "manual",
        },
        "verify_history": [],
        "redesign_history": [],
        "backups": [],
        "last_activity": "2026-01-01T00:00:00+00:00",
    }
    # frozen_status/frozen_at 은 legacy plan 에서 없음 — 명시적으로 주어질 때만 포함
    if frozen_status is not None:
        fm["frozen_status"] = frozen_status
    if frozen_at is not None:
        fm["frozen_at"] = frozen_at

    text = "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) + "---\n\nBody.\n"
    plan_path = docs_dir / "harness-plan.md"
    plan_path.write_text(text, encoding="utf-8")
    return plan_path


# ── 테스트 1: legacy plan → drafting 명시 박힘 ───────────────────────────


def test_migrate_legacy_plan_default_drafting(tmp_path: Path, mmod) -> None:
    """frozen_status 키 없는 legacy frontmatter → 마이그레이션 후 frozen_status='drafting' 명시."""
    docs_dir = tmp_path / "project" / "docs"
    plan_path = _write_legacy_plan(docs_dir, included=["requirements", "user_journey"])

    # frozen_status 키가 없는 legacy 상태 확인
    raw = plan_path.read_text(encoding="utf-8")
    assert "frozen_status" not in raw

    rc = mmod.migrate(tmp_path / "project", auto_freeze=False, dry_run=False)
    assert rc == 0

    # 백업 생성 확인
    backup = plan_path.with_suffix(".md.v9.bak")
    assert backup.exists(), "백업 파일이 생성되어야 함"

    # 마이그레이션 후 frozen_status=drafting 이 frontmatter 에 박혀야 함.
    # plan_manager._plan_to_dict 는 frozen_status='drafting' 이면 생략하므로
    # 여기서는 파일을 reload 해서 plan 객체로 확인한다.
    from src.orchestrator.plan_manager import PlanManager

    pm = PlanManager()
    plan = pm.load(plan_path)
    assert plan.frozen_status == "drafting"
    assert plan.frozen_at == ""
    assert plan.locked_sections == []


# ── 테스트 2: --auto-freeze + LOCKED 후보 있음 → frozen ─────────────────


def test_migrate_auto_freeze_with_locked_candidates(tmp_path: Path, mmod) -> None:
    """--auto-freeze + included 에 requirements/user_journey 있음 → freeze() 호출, frozen 박힘."""
    docs_dir = tmp_path / "project" / "docs"
    plan_path = _write_legacy_plan(
        docs_dir, included=["requirements", "user_journey", "view.screens"]
    )

    rc = mmod.migrate(tmp_path / "project", auto_freeze=True, dry_run=False)
    assert rc == 0

    from src.orchestrator.plan_manager import PlanManager

    pm = PlanManager()
    plan = pm.load(plan_path)
    assert plan.frozen_status == "frozen"
    assert plan.frozen_at != ""
    # 3개 후보 모두 locked_sections 에 포함
    assert set(plan.locked_sections) == {"requirements", "user_journey", "view.screens"}


# ── 테스트 3: --auto-freeze + LOCKED 후보 없음 → WARN + drafting 유지 ───


def test_migrate_auto_freeze_without_candidates_warns(
    tmp_path: Path, mmod, capsys: pytest.CaptureFixture
) -> None:
    """--auto-freeze 박았지만 included 에 LOCKED 후보 없음 → WARN + drafting 유지."""
    docs_dir = tmp_path / "project" / "docs"
    # LOCKED 후보(requirements/user_journey/view.screens) 없는 섹션만 포함
    plan_path = _write_legacy_plan(docs_dir, included=["overview", "stack"])

    rc = mmod.migrate(tmp_path / "project", auto_freeze=True, dry_run=False)
    assert rc == 0

    # stderr 에 WARN 출력 확인
    captured = capsys.readouterr()
    assert "WARN" in captured.err
    assert "LOCKED 후보 없음" in captured.err

    # frozen_status 는 drafting 유지
    from src.orchestrator.plan_manager import PlanManager

    pm = PlanManager()
    plan = pm.load(plan_path)
    assert plan.frozen_status == "drafting"
    assert plan.locked_sections == []


# ── 테스트 4: 이미 migrated plan → SKIP ─────────────────────────────────


def test_migrate_skips_already_migrated(tmp_path: Path, mmod) -> None:
    """이미 frozen 된 plan → SKIP, 변경 X."""
    docs_dir = tmp_path / "project" / "docs"
    plan_path = _write_legacy_plan(
        docs_dir,
        included=["requirements"],
        frozen_status="frozen",
        frozen_at="2026-05-01T00:00:00+00:00",
    )
    original = plan_path.read_text(encoding="utf-8")

    rc = mmod.migrate(tmp_path / "project", auto_freeze=False, dry_run=False)
    assert rc == 0

    # 파일 변경 없어야 함
    assert plan_path.read_text(encoding="utf-8") == original
    # 백업 생성 없어야 함
    backup = plan_path.with_suffix(".md.v9.bak")
    assert not backup.exists()


# ── 테스트 5: --dry-run → 백업 X, 원본 변경 X ───────────────────────────


def test_migrate_dry_run_no_write(tmp_path: Path, mmod) -> None:
    """--dry-run → 백업 X, 원본 변경 X, 미리보기만 출력."""
    docs_dir = tmp_path / "project" / "docs"
    plan_path = _write_legacy_plan(docs_dir, included=["requirements", "user_journey"])
    original = plan_path.read_text(encoding="utf-8")

    rc = mmod.migrate(tmp_path / "project", auto_freeze=False, dry_run=True)
    assert rc == 0

    # 원본 변경 없어야 함
    assert plan_path.read_text(encoding="utf-8") == original
    # 백업 생성 없어야 함
    backup = plan_path.with_suffix(".md.v9.bak")
    assert not backup.exists()
