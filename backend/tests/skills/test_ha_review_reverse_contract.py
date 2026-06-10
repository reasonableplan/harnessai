"""ha-review 역방향 contract 검증 회귀 테스트 (architecture review F7-1).

contract-validator 훅은 "skeleton 에 없는 endpoint 구현" 만 잡는다 — 역방향
(skeleton 에 선언됐는데 소스에 없음) 은 `_check_missing_declared_endpoints` 가 잡는다.
"""

from __future__ import annotations

from pathlib import Path

# conftest.py 의 ha_review_module fixture 사용 (repo skills/ha-review/run.py 로드)


def _skel(endpoints: str) -> str:
    return f"## 9. HTTP API\n\n### 엔드포인트\n\n{endpoints}\n"


def test_missing_declared_endpoint_flagged(ha_review_module, tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text('@router.get("/api/users")\n', encoding="utf-8")

    skel = _skel("**`GET /api/users`**\n**`POST /api/posts`**\n")
    findings = ha_review_module._check_missing_declared_endpoints(tmp_path, skel)

    assert [(f["method"], f["path"]) for f in findings] == [("POST", "/api/posts")]


def test_param_path_matches_via_static_prefix(ha_review_module, tmp_path: Path) -> None:
    """router prefix 조합 케이스: 정적 prefix 가 소스에 있으면 미구현으로 안 잡는다."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "router.py").write_text(
        'router = APIRouter(prefix="/api/users")\n', encoding="utf-8"
    )

    skel = _skel("**`GET /api/users/{id}`**\n")
    assert ha_review_module._check_missing_declared_endpoints(tmp_path, skel) == []


def test_docs_dir_excluded_from_search(ha_review_module, tmp_path: Path) -> None:
    """docs/ 의 skeleton.md 자기 자신은 '구현' 으로 치지 않는다."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "skeleton.md").write_text("/api/orphans 언급\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("# no endpoints\n", encoding="utf-8")

    skel = _skel("**`GET /api/orphans`**\n")
    findings = ha_review_module._check_missing_declared_endpoints(tmp_path, skel)
    assert [(f["method"], f["path"]) for f in findings] == [("GET", "/api/orphans")]


def test_no_http_section_returns_empty(ha_review_module, tmp_path: Path) -> None:
    skel = "## 1. 프로젝트 개요\nCLI 도구\n"
    assert ha_review_module._check_missing_declared_endpoints(tmp_path, skel) == []
