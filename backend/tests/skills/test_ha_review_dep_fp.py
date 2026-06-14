"""FP #19 회귀 테스트: ha-review dependency-check 오탐 차단.

실전 결함 (Mendline dogfood, /ha-review prepare):
- node:fs/node:path 빌트인 36건 → 화이트리스트 외 WARN
- @shared/* 등 tsconfig paths 별칭 36건 → WARN
- dxf-parser/three 등 skeleton §3 승인 라이브러리 10건 → WARN
WARN 88건 중 82건 FP.

Fix: node: 무조건 제외(훅) + tsconfig 별칭 prefix + skeleton stack 병합(배선).
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
    loader = SourceFileLoader("ha_review_dep_fp", str(HA_REVIEW_RUN))
    spec = importlib.util.spec_from_loader("ha_review_dep_fp", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_review_dep_fp"] = mod
    loader.exec_module(mod)
    return mod


def _fe_profile() -> SimpleNamespace:
    """electron → frontend 모드 (FRONTEND_PROFILE_IDS)."""
    return SimpleNamespace(
        id="electron",
        whitelist=SimpleNamespace(runtime=["react"], dev=[], prefix_allowed=[]),
    )


def _ts_diff(import_line: str) -> str:
    return (
        "diff --git a/desktop/src/x.ts b/desktop/src/x.ts\n"
        "--- a/desktop/src/x.ts\n"
        "+++ b/desktop/src/x.ts\n"
        f"+{import_line}\n"
    )


def _dep_warns(result: dict) -> list[dict[str, str]]:
    return [f for f in result["security"] if f["hook"] == "dependency-check"]


def test_node_builtin_not_warned(ha_review: ModuleType, tmp_path: Path) -> None:
    """node: prefix 빌트인은 dependency-check WARN 없음 (훅 무조건 제외)."""
    diff = _ts_diff("import fs from 'node:fs'") + _ts_diff("import path from 'node:path'")
    result = ha_review._collect_findings(tmp_path, [_fe_profile()], diff)
    assert _dep_warns(result) == []


def test_tsconfig_alias_not_warned_with_tsconfig(ha_review: ModuleType, tmp_path: Path) -> None:
    """tsconfig paths 별칭(@shared/*)은 tsconfig 존재 시 WARN 없음."""
    (tmp_path / "tsconfig.json").write_text(
        '{\n  // 주석 (JSONC)\n  "compilerOptions": {\n'
        '    "paths": {\n      "@shared/*": ["./src/shared/*"],\n'
        '    },\n  },\n}\n',
        encoding="utf-8",
    )
    diff = _ts_diff("import { Entity } from '@shared/types/entity'")
    result = ha_review._collect_findings(tmp_path, [_fe_profile()], diff)
    assert _dep_warns(result) == []


def test_tsconfig_alias_warned_without_tsconfig(ha_review: ModuleType, tmp_path: Path) -> None:
    """대조군: tsconfig 없으면 @shared 별칭은 여전히 WARN (배선 효과 입증)."""
    diff = _ts_diff("import { Entity } from '@shared/types/entity'")
    result = ha_review._collect_findings(tmp_path, [_fe_profile()], diff)
    assert any("@shared/types/entity" in f["message"] for f in _dep_warns(result))


def test_skeleton_stack_lib_not_warned(ha_review: ModuleType, tmp_path: Path) -> None:
    """skeleton §3 허용 라이브러리(dxf-parser)는 WARN 없음."""
    skeleton = (
        "## 3. 기술 스택\n"
        "### 허용 라이브러리 화이트리스트\n"
        "**추가 허용 (프로파일 기본 + 이 목록)**:\n"
        "- dxf-parser: DXF 파싱\n"
        "- three: 3D 렌더링\n"
    )
    diff = _ts_diff("import DxfParser from 'dxf-parser'") + _ts_diff("import * as THREE from 'three'")
    result = ha_review._collect_findings(tmp_path, [_fe_profile()], diff, skeleton)
    assert _dep_warns(result) == []


def test_unknown_lib_still_warned(ha_review: ModuleType, tmp_path: Path) -> None:
    """TP 보존: 화이트리스트·별칭·스택 어디에도 없는 lodash 는 WARN 유지."""
    diff = _ts_diff("import _ from 'lodash'")
    result = ha_review._collect_findings(tmp_path, [_fe_profile()], diff)
    assert any("lodash" in f["message"] for f in _dep_warns(result))


def test_collect_tsconfig_prefixes_jsonc(ha_review: ModuleType, tmp_path: Path) -> None:
    """_collect_tsconfig_prefixes: JSONC(주석/trailing comma) + 서브앱 tsconfig 파싱."""
    (tmp_path / "desktop").mkdir()
    (tmp_path / "desktop" / "tsconfig.json").write_text(
        '{\n  /* block comment */\n  "compilerOptions": {\n'
        '    "paths": {\n'
        '      "@shared/*": ["x"],\n      "@/*": ["y"],\n      "@root": ["z"],\n'
        '    },\n  },\n}\n',
        encoding="utf-8",
    )
    prefixes = ha_review._collect_tsconfig_prefixes(tmp_path)
    assert prefixes == ("@/", "@root", "@shared/")
