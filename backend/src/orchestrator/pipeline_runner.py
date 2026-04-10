"""인터랙티브 파이프라인 러너 — 게이트 승인 기반 단계별 실행."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from src.orchestrator.orchestrate import Orchestra
from src.orchestrator.phase import Phase
from src.orchestrator.runner import RunResult

# ---------------------------------------------------------------------------
# 게이트별 리뷰 에이전트 프롬프트
# ---------------------------------------------------------------------------

_REQUIREMENTS_REVIEW_PROMPT = """\
# 요구사항 검토 (office-hours 스타일)

아래 요구사항을 검토하고 다음 4가지를 분석해라:

1. **핵심 사용자 가치** — 이 제품이 없으면 사용자가 어떻게 해결하고 있는가? \
   만들 만한 가치가 있는가?
2. **MVP 범위** — 너무 넓지 않은가? Phase 1만으로 핵심 흐름이 완성되는가?
3. **기술적 리스크** — 구현 불가능하거나 과도하게 복잡한 요구사항이 있는가?
4. **누락된 요구사항** — 없으면 시스템이 불완전해지는 것이 빠진 게 있는가?

마지막에 **계속 진행 권장 여부**를 명확히 밝혀라.

💡 더 깊은 분석이 필요하면 Claude Code에서 /office-hours 를 실행하라.

<requirements>
{requirements}
</requirements>
"""

_ENGINEERING_REVIEW_PROMPT = """\
# 엔지니어링 리뷰 (plan-eng-review 스타일)

아래 skeleton 설계를 엔지니어링 관점에서 리뷰해라:

1. **아키텍처 결정** — DB/API 설계가 요구사항을 충족하는가? 빠진 테이블/엔드포인트가 있는가?
2. **기술 스택 적합성** — 선택된 기술이 요구사항 규모에 맞는가?
3. **데이터 흐름** — API ↔ DB ↔ 프론트엔드 흐름이 일관성 있는가?
4. **엣지케이스** — 인증, 에러 처리, 동시성 문제가 고려됐는가?
5. **구현 리스크** — 지금 이대로 구현하면 나중에 문제가 될 결정이 있는가?

마지막에 **구현 시작 가능 여부**를 명확히 밝혀라.

💡 더 깊은 리뷰가 필요하면 Claude Code에서 /plan-eng-review 를 실행하라.

<skeleton>
{skeleton}
</skeleton>
"""


# ---------------------------------------------------------------------------
# 유틸리티
# ---------------------------------------------------------------------------

def _hr(title: str) -> None:
    width = 60
    print(f"\n{'='*width}")
    print(f"  {title}")
    print(f"{'='*width}")


async def _ask_approval(question: str) -> bool:
    """비동기 컨텍스트에서 stdin 블로킹 없이 사용자 승인을 받는다."""
    loop = asyncio.get_running_loop()
    while True:
        try:
            answer: str = await loop.run_in_executor(
                None, lambda: input(f"\n{question} (y/n): ").strip().lower()
            )
        except (EOFError, KeyboardInterrupt):
            return False
        if answer in ("y", "yes", "ㅇ", "ㅇㅇ", "예", "네"):
            return True
        if answer in ("n", "no", "아니", "아니오", "ㄴ"):
            return False
        print("y 또는 n으로 답해주세요.")


# ---------------------------------------------------------------------------
# 메인 러너
# ---------------------------------------------------------------------------

async def run(
    requirements: str,
    project_dir: Path,
    *,
    from_skeleton: bool = False,
    max_task_retries: int = 3,
    max_phase_retries: int = 2,
) -> bool:
    """인터랙티브 파이프라인 실행.

    각 주요 단계 전후에 사용자 승인을 받고 진행한다.

    Args:
        requirements: PM 요구사항 텍스트
        project_dir: 프로젝트 루트 디렉토리
        max_task_retries: 태스크당 최대 재시도 횟수
        max_phase_retries: Phase 리뷰 reject 시 최대 재시도 횟수

    Returns:
        True: 전체 파이프라인 성공, False: 중단 또는 실패
    """
    orchestra = Orchestra(project_dir=project_dir)
    # 이전 실행 잔여 state 초기화 — 항상 PLANNING에서 시작
    orchestra.state.save(Phase.PLANNING)
    orchestra.phase_manager._current = Phase.PLANNING

    # ── FROM SKELETON 모드: 설계 단계 건너뜀 ────────────────────────────────
    if from_skeleton:
        skeleton_path = project_dir / "docs" / "skeleton.md"
        if not skeleton_path.exists():
            print(f"\n❌ skeleton.md를 찾을 수 없습니다: {skeleton_path}")
            print("   /office-hours 등으로 skeleton.md를 먼저 작성하세요.")
            return False

        skeleton_text = skeleton_path.read_text(encoding="utf-8")
        _hr("FROM SKELETON 모드 — 설계 단계 건너뜀")
        print(f"✅ skeleton.md 로드: {skeleton_path}")
        print(f"   ({len(skeleton_text)}자)")

        # skeleton 내용을 architect/designer 출력으로 사용
        mock_result = RunResult(
            agent="skeleton",
            output=skeleton_text,
            success=True,
            duration_ms=0,
            attempts=1,
        )
        design_results: dict[str, RunResult] = {
            "architect": mock_result,
            "designer": mock_result,
        }

        approved = await _ask_approval("skeleton.md를 확인했습니다. 태스크 분해를 시작할까요?")
        if not approved:
            print("\n파이프라인 중단.")
            return False

        # PHASE 2로 바로 이동
        _hr("PHASE 2 — 태스크 분해")
        print("Orchestrator 에이전트가 태스크를 분해 중입니다...\n")

        phases, breakdown_dict = await orchestra.run_breakdown(requirements, design_results)

        if not phases:
            print("\n❌ 태스크 분해 실패 — Orchestrator 출력을 확인하세요.")
            print(breakdown_dict.get("output", "출력 없음"))
            return False

        total_tasks = sum(len(p) for p in phases)
        print(f"\n✅ {len(phases)}개 Phase, {total_tasks}개 태스크 분해 완료")
        for i, phase_tasks in enumerate(phases, start=1):
            print(f"  Phase {i}: {len(phase_tasks)}개 태스크 "
                  f"({', '.join(t.id for t in phase_tasks)})")

        approved = await _ask_approval("태스크 분해 결과를 확인했습니다. 구현을 시작할까요?")
        if not approved:
            print("\n파이프라인 중단.")
            return False

        _hr("PHASE 3 — 구현")
        print("구현을 시작합니다...\n")

        phase_results = await orchestra.run_phases(
            phases,
            max_task_retries=max_task_retries,
            max_phase_retries=max_phase_retries,
        )

        if phase_results["success"]:
            orchestra.phase_manager.transition(Phase.DEPLOYING)
            orchestra.phase_manager.transition(Phase.DONE)
            _hr("✅ 전체 파이프라인 완료")
            print(f"  성공한 Phase: {len(phase_results['phases'])}개")
            return True

        failed = [r for r in phase_results["phases"] if not r["passed"]]
        _hr("❌ 파이프라인 실패")
        print(f"  실패한 Phase: {[r['phase_num'] for r in failed]}")
        return False

    # ── GATE 1: 요구사항 검토 ─────────────────────────────────────────────────
    _hr("GATE 1 — 요구사항 검토")
    print("요구사항을 분석 중입니다...\n")

    req_result = await orchestra.runner.run(
        "architect",
        _REQUIREMENTS_REVIEW_PROMPT.format(requirements=requirements),
    )
    print(req_result.output)

    approved = await _ask_approval("설계를 시작할까요?")
    if not approved:
        print("\n파이프라인 중단 — 요구사항을 수정 후 다시 시작하세요.")
        return False

    # ── PHASE 1: 설계 (Architect + Designer) ─────────────────────────────────
    _hr("PHASE 1 — 설계")
    print("Architect + Designer 에이전트를 실행 중입니다...\n")

    design_results = await orchestra.design(requirements)

    if not design_results["architect"].success:
        print("\n❌ Architect 실패 — 설계를 진행할 수 없습니다.")
        print(design_results["architect"].error or "출력 없음")
        return False

    try:
        orchestra.materialize_skeleton(
            architect_output=design_results["architect"].output,
            designer_output=design_results["designer"].output,
        )
    except ValueError as exc:
        print(f"\n❌ skeleton 생성 실패 — Architect/Designer 출력에 유효한 섹션 없음: {exc}")
        return False

    skeleton_path = project_dir / "docs" / "skeleton.md"
    print(f"\n✅ skeleton.md 생성 완료: {skeleton_path}")

    # ── GATE 2: 엔지니어링 리뷰 ──────────────────────────────────────────────
    _hr("GATE 2 — 엔지니어링 리뷰")
    print("skeleton 설계를 리뷰 중입니다...\n")

    skeleton_text = (
        skeleton_path.read_text(encoding="utf-8") if skeleton_path.exists() else ""
    )
    eng_result = await orchestra.runner.run(
        "reviewer",
        _ENGINEERING_REVIEW_PROMPT.format(skeleton=skeleton_text),
    )
    print(eng_result.output)

    approved = await _ask_approval("구현을 시작할까요?")
    if not approved:
        print(
            "\n파이프라인 중단 — skeleton.md를 수정 후 "
            "pipeline_runner.run()으로 재시작하세요."
        )
        return False

    # ── PHASE 2: 태스크 분해 ─────────────────────────────────────────────────
    _hr("PHASE 2 — 태스크 분해")
    print("Orchestrator 에이전트가 태스크를 분해 중입니다...\n")

    phases, breakdown_dict = await orchestra.run_breakdown(requirements, design_results)

    if not phases:
        print("\n❌ 태스크 분해 실패 — Orchestrator 출력을 확인하세요.")
        print(breakdown_dict.get("output", "출력 없음"))
        return False

    total_tasks = sum(len(p) for p in phases)
    print(f"\n✅ {len(phases)}개 Phase, {total_tasks}개 태스크 분해 완료")
    for i, phase_tasks in enumerate(phases, start=1):
        print(f"  Phase {i}: {len(phase_tasks)}개 태스크 "
              f"({', '.join(t.id for t in phase_tasks)})")

    approved = await _ask_approval("태스크 분해 결과를 확인했습니다. 구현을 시작할까요?")
    if not approved:
        print("\n파이프라인 중단 — skeleton.md의 섹션 17을 수정 후 재시작하세요.")
        return False

    # ── PHASE 3: 구현 ────────────────────────────────────────────────────────
    _hr("PHASE 3 — 구현")
    print("구현을 시작합니다...\n")

    phase_results = await orchestra.run_phases(
        phases,
        max_task_retries=max_task_retries,
        max_phase_retries=max_phase_retries,
    )

    if phase_results["success"]:
        orchestra.phase_manager.transition(Phase.DEPLOYING)
        orchestra.phase_manager.transition(Phase.DONE)
        _hr("✅ 전체 파이프라인 완료")
        print(f"  성공한 Phase: {len(phase_results['phases'])}개")
        return True

    failed = [r for r in phase_results["phases"] if not r["passed"]]
    _hr("❌ 파이프라인 실패")
    print(f"  실패한 Phase: {[r['phase_num'] for r in failed]}")
    return False


def main() -> None:
    """CLI 진입점 — 요구사항을 stdin 또는 인자로 받는다."""
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]  # Windows cp949 대비

    parser = argparse.ArgumentParser(description="오케스트라 파이프라인 러너")
    parser.add_argument(
        "requirements",
        nargs="*",
        help="요구사항 텍스트 (생략 시 stdin에서 읽음)",
    )
    parser.add_argument(
        "--from-skeleton",
        action="store_true",
        help="skeleton.md가 이미 있으면 설계 단계를 건너뛰고 구현부터 시작",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help="프로젝트 루트 디렉토리 (기본: PROJECT_DIR 환경변수 또는 backend/)",
    )
    args = parser.parse_args()

    if args.requirements:
        requirements = " ".join(args.requirements)
    else:
        print("요구사항을 입력하세요 (여러 줄 가능, 빈 줄로 종료):")
        lines: list[str] = []
        try:
            while True:
                line = input()
                if not line:
                    break
                lines.append(line)
        except EOFError:
            pass
        requirements = "\n".join(lines)

    if not requirements.strip():
        print("요구사항이 비어 있습니다.")
        sys.exit(1)

    project_dir: Path = (
        args.project_dir
        or Path(os.environ.get("PROJECT_DIR", ""))
        or Path(__file__).parents[2]
    )
    success = asyncio.run(
        run(requirements, project_dir, from_skeleton=args.from_skeleton)
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
