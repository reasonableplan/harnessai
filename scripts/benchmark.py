#!/usr/bin/env python3
"""HarnessAI 벤치마크 — LLM 호출 없이 측정 가능한 부분만.

측정 대상:
  1. 프로파일 감지 (profile_loader.detect) — 샘플 프로젝트
  2. skeleton 조립 (SkeletonAssembler.assemble) — 20 섹션
  3. harness validate — 27 파일 스키마 검증
  4. harness integrity — clean skeleton 대상
  5. find_placeholders 스케일링 — 소/중/대 텍스트

사용:
  python scripts/benchmark.py               # stdout + docs/benchmarks/ 갱신
  python scripts/benchmark.py --json        # JSON 만 stdout
  python scripts/benchmark.py --iterations 10  # 각 측정 10회 반복
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

# 레포 루트 자동 감지 — 이 스크립트는 HarnessAI 레포 내에서만 동작.
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = REPO_ROOT / "backend"
HARNESS_BIN = REPO_ROOT / "harness" / "bin" / "harness"
if not BACKEND_SRC.exists() or not HARNESS_BIN.exists():
    sys.stderr.write(
        f"[FAIL] 레포 루트 구조 확인 필요 — 기대:\n"
        f"  {BACKEND_SRC}\n  {HARNESS_BIN}\n"
        "레포 루트에서 `uv run python scripts/benchmark.py` 로 실행하세요.\n"
    )
    sys.exit(3)
sys.path.insert(0, str(BACKEND_SRC))

from src.orchestrator.profile_loader import ProfileLoader  # noqa: E402
from src.orchestrator.skeleton_assembler import (  # noqa: E402
    SkeletonAssembler,
    find_placeholders,
)


def time_it(fn: Callable[[], Any], iterations: int) -> dict[str, float]:
    """함수를 N회 실행하고 통계 반환 (초 단위)."""
    times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return {
        "iterations": iterations,
        "mean_ms": statistics.mean(times) * 1000,
        "median_ms": statistics.median(times) * 1000,
        "stdev_ms": (statistics.stdev(times) * 1000) if len(times) > 1 else 0.0,
        "min_ms": min(times) * 1000,
        "max_ms": max(times) * 1000,
    }


# ── 측정 함수 ──────────────────────────────────────────────────────


def bench_profile_detect(iterations: int) -> dict[str, Any]:
    """프로파일 감지 — 레포 자체를 대상으로 (fastapi 감지 예상)."""
    loader = ProfileLoader()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "backend").mkdir()
        (root / "backend" / "pyproject.toml").write_text(
            '[project]\nname="test"\ndependencies=["fastapi>=0.100"]\n',
            encoding="utf-8",
        )
        stats = time_it(lambda: loader.detect(root), iterations)
    stats["target"] = "fastapi 프로파일 감지 (샘플 pyproject.toml)"
    return stats


def bench_skeleton_assemble(iterations: int) -> dict[str, Any]:
    """20 섹션 전체 조립."""
    assembler = SkeletonAssembler()
    all_sections = [
        "overview", "requirements", "stack", "configuration", "errors",
        "auth", "persistence", "integrations",
        "interface.http", "interface.cli", "interface.ipc", "interface.sdk",
        "view.screens", "view.components", "state.flow", "core.logic",
        "observability", "deployment", "tasks", "notes",
    ]
    stats = time_it(lambda: assembler.assemble(all_sections), iterations)
    stats["target"] = f"{len(all_sections)} 섹션 전체 조립"
    return stats


def bench_harness_validate(iterations: int) -> dict[str, Any]:
    """harness validate — 27 파일 스키마 검증 (subprocess)."""
    stats = time_it(
        lambda: subprocess.run(
            [sys.executable, str(HARNESS_BIN), "validate"],
            capture_output=True, check=True,
        ),
        iterations,
    )
    stats["target"] = "27 파일 스키마 검증 (subprocess)"
    return stats


def bench_harness_integrity(iterations: int) -> dict[str, Any]:
    """harness integrity — clean sample project 대상."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        docs = root / "docs"
        docs.mkdir()
        (root / "pyproject.toml").touch()
        (root / "src").mkdir()
        (root / "src" / "cli.py").touch()
        (docs / "harness-plan.md").write_text(
            "---\nharness_version: 2\nschema_version: 1\nproject_name: t\n"
            "profiles: []\npipeline:\n  steps: [init]\n  current_step: built\n"
            "  completed_steps: []\n  skipped_steps: []\n  gstack_mode: manual\n"
            "skeleton_sections: {included: [overview]}\nverify_history: []\n---\n",
            encoding="utf-8",
        )
        (docs / "skeleton.md").write_text(
            "# Test\n\n```filesystem\npyproject.toml\nsrc/\n  cli.py\n```\n",
            encoding="utf-8",
        )
        stats = time_it(
            lambda: subprocess.run(
                [sys.executable, str(HARNESS_BIN), "integrity",
                 "--project", str(root)],
                capture_output=True, check=True,
            ),
            iterations,
        )
    stats["target"] = "clean skeleton (5 파일) 대상 integrity"
    return stats


def bench_find_placeholders_scaling(iterations: int) -> dict[str, Any]:
    """find_placeholders 스케일링 — 크기 다른 텍스트 3종."""
    texts = {
        "small_100B": "# X\n<pkg> placeholder.\n",
        "medium_10KB": ("# X\n<pkg>\n" + "Lorem ipsum dolor sit amet. " * 400),
        "large_100KB": ("# X\n<pkg>\n" + "Lorem ipsum dolor sit amet. " * 4000),
    }
    result: dict[str, Any] = {"target": "find_placeholders 스케일링", "sizes": {}}
    for name, text in texts.items():
        stats = time_it(lambda t=text: find_placeholders(t), iterations)
        stats["size_bytes"] = len(text)
        result["sizes"][name] = stats
    return result


def bench_install_script(iterations: int) -> dict[str, Any] | None:
    """install.sh 전체 시나리오 — fresh install 만 측정 (3회 권장)."""
    install_sh = REPO_ROOT / "install.sh"
    if not install_sh.exists():
        return None

    def _fresh():
        with tempfile.TemporaryDirectory() as tmp:
            # 기존 env 상속 + CLAUDE_HOME 오버라이드 (PATH 등 유지 — sha256sum, find 필요)
            env = os.environ.copy()
            env["CLAUDE_HOME"] = f"{tmp}/.claude"
            subprocess.run(
                ["bash", str(install_sh), "--force"],
                capture_output=True, check=True, env=env,
            )

    # install 은 비싸서 iteration 은 최대 5회로 제한
    n = min(iterations, 5)
    stats = time_it(_fresh, n)
    stats["target"] = "install.sh fresh install (44 파일 + manifest)"
    return stats


# ── 메인 ──────────────────────────────────────────────────────────


def run_all(iterations: int) -> dict[str, Any]:
    results: dict[str, Any] = {
        "repo": str(REPO_ROOT),
        "python": sys.version.split()[0],
        "iterations": iterations,
        "benchmarks": {},
    }
    print("[1/6] profile detect …", file=sys.stderr, flush=True)
    results["benchmarks"]["profile_detect"] = bench_profile_detect(iterations)
    print("[2/6] skeleton assemble …", file=sys.stderr, flush=True)
    results["benchmarks"]["skeleton_assemble"] = bench_skeleton_assemble(iterations)
    print("[3/6] harness validate …", file=sys.stderr, flush=True)
    results["benchmarks"]["harness_validate"] = bench_harness_validate(iterations)
    print("[4/6] harness integrity …", file=sys.stderr, flush=True)
    results["benchmarks"]["harness_integrity"] = bench_harness_integrity(iterations)
    print("[5/6] find_placeholders scaling …", file=sys.stderr, flush=True)
    results["benchmarks"]["find_placeholders"] = bench_find_placeholders_scaling(iterations)
    # install.sh 측정은 shell environment 차이로 플랫폼별 불안정.
    # --with-install 플래그 있을 때만 실행.
    if os.environ.get("HARNESS_BENCH_INSTALL") == "1":
        print("[6/6] install.sh fresh (최대 5회) …", file=sys.stderr, flush=True)
        try:
            install_result = bench_install_script(iterations)
            if install_result:
                results["benchmarks"]["install_fresh"] = install_result
        except subprocess.CalledProcessError as exc:
            print(f"  [SKIP] install.sh 실행 실패: rc={exc.returncode}", flush=True)
    return results


def render_markdown(results: dict[str, Any]) -> str:
    """결과를 마크다운 테이블로."""
    lines: list[str] = []
    lines.append("# HarnessAI 벤치마크 결과")
    lines.append("")
    lines.append(f"- Python: {results['python']}")
    lines.append(f"- Iterations: {results['iterations']}")
    lines.append("- 측정 항목: LLM 호출 없이 측정 가능한 부분만")
    lines.append("")
    lines.append("## 요약")
    lines.append("")
    lines.append("| 측정 | mean | median | p_min | p_max |")
    lines.append("|---|---|---|---|---|")
    for name, bench in results["benchmarks"].items():
        if "sizes" in bench:
            for size_name, size_stats in bench["sizes"].items():
                label = f"{name} ({size_name})"
                lines.append(
                    f"| {label} | {size_stats['mean_ms']:.2f} ms | "
                    f"{size_stats['median_ms']:.2f} ms | "
                    f"{size_stats['min_ms']:.2f} ms | "
                    f"{size_stats['max_ms']:.2f} ms |"
                )
        else:
            lines.append(
                f"| {name} | {bench['mean_ms']:.2f} ms | "
                f"{bench['median_ms']:.2f} ms | "
                f"{bench['min_ms']:.2f} ms | "
                f"{bench['max_ms']:.2f} ms |"
            )
    lines.append("")
    lines.append("## 상세")
    lines.append("")
    for name, bench in results["benchmarks"].items():
        lines.append(f"### {name}")
        lines.append(f"- **대상**: {bench.get('target', '(n/a)')}")
        if "sizes" in bench:
            for size_name, size_stats in bench["sizes"].items():
                lines.append(
                    f"- `{size_name}` ({size_stats['size_bytes']}B): "
                    f"mean {size_stats['mean_ms']:.2f} ms "
                    f"(±{size_stats['stdev_ms']:.2f})"
                )
        else:
            lines.append(
                f"- mean **{bench['mean_ms']:.2f} ms** "
                f"(±{bench['stdev_ms']:.2f}), "
                f"median {bench['median_ms']:.2f} ms, "
                f"range [{bench['min_ms']:.2f}, {bench['max_ms']:.2f}]"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--iterations", type=int, default=20, help="각 측정 반복 수 (default: 20)")
    parser.add_argument("--json", action="store_true", help="JSON 만 stdout")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "docs" / "benchmarks", help="마크다운 출력 디렉토리")
    args = parser.parse_args()

    results = run_all(args.iterations)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0

    # 마크다운 생성
    args.out_dir.mkdir(parents=True, exist_ok=True)
    md = render_markdown(results)
    out = args.out_dir / "results.md"
    out.write_text(md, encoding="utf-8")
    raw = args.out_dir / "results.json"
    raw.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(md)
    print()
    print(f"[OK] 결과: {out}")
    print(f"     원본: {raw}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
