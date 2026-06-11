"""ha-log/run.py 단위 테스트 (4개).

대상: skills/ha-log/run.py::append_entry
전략: tmp_path 기반 파일 I/O — 실제 worklog.md 미접촉.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_LOG_RUN = REPO_ROOT / "skills" / "ha-log" / "run.py"


def _load_ha_log() -> ModuleType:
    loader = SourceFileLoader("ha_log_run", str(HA_LOG_RUN))
    spec = importlib.util.spec_from_loader("ha_log_run", loader)
    assert spec is not None, f"spec load failed: {HA_LOG_RUN}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_log_run"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ha_log() -> ModuleType:
    return _load_ha_log()


def test_append_creates_worklog_if_missing(ha_log, tmp_path: Path) -> None:
    """worklog.md 없을 때 호출하면 자동 생성 + Title + 오늘 섹션 + bullet 박힘."""
    worklog = tmp_path / "docs" / "worklog.md"
    assert not worklog.exists()

    ha_log.append_entry(worklog, "discussion", "첫 번째 항목")

    assert worklog.exists()
    text = worklog.read_text(encoding="utf-8")
    assert "# 작업 일지" in text
    assert "### 논의 / 합의" in text
    assert "- 첫 번째 항목" in text
    # 오늘 날짜 섹션 존재
    today = ha_log._today()
    assert f"## {today}" in text


def test_append_existing_today_section(ha_log, tmp_path: Path) -> None:
    """오늘 섹션 + sub_header 이미 있으면 그 안에 bullet 추가."""
    worklog = tmp_path / "worklog.md"
    today = ha_log._today()
    initial = f"# 작업 일지\n\n## {today}\n\n### 논의 / 합의\n- 기존 항목\n"
    worklog.write_text(initial, encoding="utf-8")

    ha_log.append_entry(worklog, "discussion", "두 번째 항목")

    text = worklog.read_text(encoding="utf-8")
    assert "- 기존 항목" in text
    assert "- 두 번째 항목" in text
    # 섹션 헤더 중복 없음
    assert text.count("### 논의 / 합의") == 1


def test_append_new_today_section_above_old(ha_log, tmp_path: Path) -> None:
    """기존 어제 섹션만 있을 때 오늘 섹션 신규 + 어제 섹션 위에 삽입."""
    worklog = tmp_path / "worklog.md"
    yesterday = "2020-01-01"
    today = ha_log._today()
    initial = f"# 작업 일지\n\n## {yesterday}\n\n### 변경\n- 어제 항목\n"
    worklog.write_text(initial, encoding="utf-8")

    ha_log.append_entry(worklog, "next", "다음 할 일")

    text = worklog.read_text(encoding="utf-8")
    # 오늘 섹션이 어제 섹션보다 앞에 위치
    today_pos = text.index(f"## {today}")
    yesterday_pos = text.index(f"## {yesterday}")
    assert today_pos < yesterday_pos
    assert "- 다음 할 일" in text
    assert "- 어제 항목" in text


def test_append_invalid_category_raises(ha_log, tmp_path: Path) -> None:
    """잘못된 category 는 ValueError 발생."""
    worklog = tmp_path / "worklog.md"
    with pytest.raises(ValueError, match="category must be one of"):
        ha_log.append_entry(worklog, "invalid_cat", "메시지")
