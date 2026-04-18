"""ha-review 의 테스트 분포 체크 (`_check_test_distribution`) 단위 테스트.

대상:
- `_scan_source_modules` — src/ 아래 구현 모듈 수집 (테스트/빌드 디렉토리 제외)
- `_find_python_test_files` / `_find_js_test_files` — 테스트 파일 탐색
- `_python_test_file_counts` — AST 로 def test_* 카운트
- `_js_test_file_counts` — describe/it/test 정규식 카운트
- `_check_test_distribution` — 통합 게이트

모든 픽스처는 tmp_path 기반.
"""

from __future__ import annotations

from pathlib import Path

# fixture: ha_review_module (from conftest)


def _mk_python_project(root: Path, src_modules: dict[str, str], test_modules: dict[str, str]) -> None:
    """src/ 와 tests/ 레이아웃으로 Python 프로젝트 구조 작성."""
    src = root / "src"
    tests = root / "tests"
    src.mkdir(parents=True, exist_ok=True)
    tests.mkdir(parents=True, exist_ok=True)
    (src / "__init__.py").touch()
    for rel, body in src_modules.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    for rel, body in test_modules.items():
        p = tests / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def _mk_js_project(root: Path, src_modules: dict[str, str], test_modules: dict[str, str]) -> None:
    """src/ + src/__tests__ or src/*.test.* 레이아웃으로 JS 프로젝트."""
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    for rel, body in src_modules.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    for rel, body in test_modules.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


# ── _check_test_distribution ──────────────────────────────────────────


def test_distribution_even_coverage_no_findings(ha_review_module, tmp_path: Path) -> None:
    _mk_python_project(
        tmp_path,
        src_modules={"a.py": "def a(): pass\n", "b.py": "def b(): pass\n"},
        test_modules={
            "test_a.py": "def test_a1(): pass\ndef test_a2(): pass\n",
            "test_b.py": "def test_b1(): pass\ndef test_b2(): pass\n",
        },
    )
    findings = ha_review_module._check_test_distribution(
        tmp_path, "python-cli", ".", "uv run pytest tests/"
    )
    assert findings == []


def test_distribution_blocks_when_src_exists_but_no_tests(
    ha_review_module, tmp_path: Path
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").touch()
    (src / "a.py").write_text("def a(): pass\n", encoding="utf-8")
    # tests/ 디렉토리 자체가 없음

    findings = ha_review_module._check_test_distribution(
        tmp_path, "python-cli", ".", "uv run pytest tests/"
    )
    assert len(findings) == 1
    assert findings[0]["severity"] == "BLOCK"
    assert findings[0]["hook"] == "test-distribution"


def test_distribution_warns_on_large_skew(ha_review_module, tmp_path: Path) -> None:
    # 편중: 한 파일에 20 테스트, 다른 파일에 1 테스트
    many = "\n".join(f"def test_big_{i}(): pass" for i in range(20))
    _mk_python_project(
        tmp_path,
        src_modules={"big.py": "def big(): pass\n", "small.py": "def small(): pass\n"},
        test_modules={
            "test_big.py": many,
            "test_small.py": "def test_small(): pass\n",
        },
    )
    findings = ha_review_module._check_test_distribution(
        tmp_path, "python-cli", ".", "uv run pytest tests/"
    )
    assert any(f["severity"] == "WARN" for f in findings)
    assert any("편차" in f["message"] for f in findings)


def test_distribution_skips_when_no_src_dir(ha_review_module, tmp_path: Path) -> None:
    # src/ 없음 — 라이브러리 루트 구조 등
    findings = ha_review_module._check_test_distribution(
        tmp_path, "python-cli", ".", "uv run pytest tests/"
    )
    assert findings == []


def test_distribution_skips_unknown_language(ha_review_module, tmp_path: Path) -> None:
    # profile id / toolchain.test 어느 쪽에서도 언어 감지 실패
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.go").write_text("package main\n", encoding="utf-8")
    findings = ha_review_module._check_test_distribution(
        tmp_path, "go-service", ".", "go test ./..."
    )
    assert findings == []


def test_distribution_finds_tests_at_project_root(ha_review_module, tmp_path: Path) -> None:
    """src/ 가 backend/src/, tests/ 가 프로젝트 루트 (code-hijack 레이아웃)."""
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "src").mkdir()
    (backend / "src" / "__init__.py").touch()
    (backend / "src" / "a.py").write_text("def a(): pass\n", encoding="utf-8")

    # 테스트는 프로젝트 루트 tests/ 에
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(
        "def test_a(): pass\ndef test_a2(): pass\n", encoding="utf-8"
    )
    findings = ha_review_module._check_test_distribution(
        tmp_path, "python-cli", "backend", "uv run pytest tests/"
    )
    # 테스트 찾음 → BLOCK 없음, 편차도 없음
    assert findings == []


def test_distribution_detects_js_test_patterns(ha_review_module, tmp_path: Path) -> None:
    """JS/TS: describe/it/test 호출 정규식 카운트."""
    # 20 tests in one file, 1 in another — 편차 20x 기대
    big = "\n".join(f"test('case {i}', () => {{}})" for i in range(20))
    _mk_js_project(
        tmp_path,
        src_modules={
            "Big.tsx": "export const Big = () => null;\n",
            "Small.tsx": "export const Small = () => null;\n",
        },
        test_modules={
            "__tests__/Big.test.tsx": f"describe('Big', () => {{\n{big}\n}});\n",
            "__tests__/Small.test.tsx": "test('renders', () => {});\n",
        },
    )
    findings = ha_review_module._check_test_distribution(
        tmp_path, "react-vite", ".", "vitest run"
    )
    assert any(f["severity"] == "WARN" for f in findings)


def test_distribution_ignores_tests_folder_in_source_scan(
    ha_review_module, tmp_path: Path
) -> None:
    """src/__tests__/ 안의 파일은 source 모듈로 카운트 안 됨."""
    _mk_js_project(
        tmp_path,
        src_modules={"App.tsx": "export default null;\n"},
        test_modules={
            "__tests__/helper.tsx": "export const helper = () => null;\n",
            "__tests__/App.test.tsx": "test('a', () => {});\n",
        },
    )
    # helper.tsx 는 __tests__/ 안이라 source 로 카운트되면 안 됨.
    # App.tsx 만 source 로 인식되고, test 파일 1개 존재 → no BLOCK, no skew.
    findings = ha_review_module._check_test_distribution(
        tmp_path, "react-vite", ".", "vitest run"
    )
    assert findings == []


def test_distribution_blocks_empty_tests_dir(ha_review_module, tmp_path: Path) -> None:
    """tests/ 는 있으나 실제 테스트 함수 0개."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").touch()
    (src / "a.py").write_text("def a(): pass\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "conftest.py").write_text("# fixtures only\n", encoding="utf-8")

    findings = ha_review_module._check_test_distribution(
        tmp_path, "python-cli", ".", "uv run pytest tests/"
    )
    assert len(findings) == 1
    assert findings[0]["severity"] == "BLOCK"


# ── 언어 판정 ────────────────────────────────────────────────────────


def test_language_from_profile_pytest_toolchain(ha_review_module) -> None:
    assert ha_review_module._language_from_profile("custom", "uv run pytest") == "python"


def test_language_from_profile_vitest_toolchain(ha_review_module) -> None:
    assert ha_review_module._language_from_profile("custom", "pnpm vitest") == "javascript"


def test_language_from_profile_unknown_returns_unknown(ha_review_module) -> None:
    assert ha_review_module._language_from_profile("go-service", "go test") == "unknown"


def test_language_from_profile_id_fallback_when_toolchain_empty(ha_review_module) -> None:
    assert ha_review_module._language_from_profile("fastapi", None) == "python"
    assert ha_review_module._language_from_profile("react-vite", "") == "javascript"
