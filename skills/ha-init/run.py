#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-init` 백엔드 스크립트.

스킬(SKILL.md)이 호출하는 두 서브커맨드:
- detect <project_dir>          : 매칭 프로파일 JSON 출력
- write --project ... --profiles ... --included ... --description ...
                                : harness-plan.md + skeleton.md 작성

HARNESS_AI_HOME 탐지 로직은 `_ha_shared/utils.py` 에 일원화 (다른 6 스킬과 동일 경로).
env 우선 → 없으면 레포 루트 자동 탐지 (dev mode) → 실패 시 명확한 에러.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# UTF-8 stdout (Windows cp949 호환)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

# _ha_shared/utils.py 의 HARNESS_HOME 탐지 재사용 — 다른 스킬들과 일관성 유지.
# import 자체가 side effect (sys.path 에 backend 추가). cmd_write 가 직접 사용도 함.
sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from utils import HARNESS_HOME, info, resolve_guideline_paths  # noqa: E402, I001

from src.orchestrator.context import CANONICAL_SECTION_ORDER  # noqa: E402
from src.orchestrator.capabilities import KNOWN_CAPABILITY_ATOMS  # noqa: E402
from src.orchestrator.capability_inference import infer_capabilities_from_text  # noqa: E402
from src.orchestrator.profile_recommendation import recommend_profiles  # noqa: E402
from src.orchestrator.plan_manager import (  # noqa: E402
    PlanManager,
    ProfileRef,
    ScaleAxes,
    SkeletonSpec,
)
from src.orchestrator.profile_loader import (  # noqa: E402
    Profile,
    ProfileLoader,
    find_consistency_violations,
)
from src.orchestrator.skeleton_assembler import SkeletonAssembler  # noqa: E402


# ── 공통 유틸 ──────────────────────────────────────────────────────────


def _docs_dir(project: Path, profile_path: str) -> Path:
    """프로파일 매칭 경로 + 'docs/' 우선, 없으면 project/docs/."""
    base = project if profile_path == "." else (project / profile_path)
    return (base / "docs") if base.exists() else (project / "docs")


# ── mobile 프로파일 ID 집합 ────────────────────────────────────────────

_MOBILE_PROFILE_IDS: frozenset[str] = frozenset(
    {"react-native-expo", "flutter", "android-kotlin", "ios-swift"}
)

_MOBILE_AGENT_SUFFIX: dict[str, str] = {
    "react-native-expo": "rn",
    "flutter": "flutter",
    "android-kotlin": "android",
    "ios-swift": "ios",
}


# ── detect 서브커맨드 ─────────────────────────────────────────────────


def cmd_detect(args: argparse.Namespace) -> int:
    project = Path(args.project_dir).resolve()
    if not project.exists():
        print(json.dumps({"error": f"project not found: {project}"}), file=sys.stderr)
        return 1

    loader = ProfileLoader(project_dir=project)
    matches = loader.detect()

    output: dict = {"project": str(project), "matches": []}
    mobile_detected: list[str] = []
    for m in matches:
        p = m.profile
        is_mobile = p.id in _MOBILE_PROFILE_IDS
        if is_mobile:
            mobile_detected.append(p.id)
        output["matches"].append({
            "profile_id": p.id,
            "name": p.name,
            "path": m.path,
            "status": p.status,
            "is_mobile": is_mobile,
            "required_sections": list(p.skeleton_sections.required),
            "optional_sections": list(p.skeleton_sections.optional),
            "section_order": list(p.skeleton_sections.order),
            "toolchain": {
                "install": p.toolchain.install,
                "test": p.toolchain.test,
                "lint": p.toolchain.lint,
                "type": p.toolchain.type,
                "format": p.toolchain.format,
            },
            "whitelist_runtime": list(p.whitelist.runtime),
            "whitelist_dev": list(p.whitelist.dev),
            "gstack_mode": p.gstack_mode,
            "gstack_recommended": dict(p.gstack_recommended),
            "guideline_paths": [str(g) for g in resolve_guideline_paths(p.id)],
        })

    # 모바일 프로파일 감지 시 stderr 안내
    for profile_id in mobile_detected:
        agent_suffix = _MOBILE_AGENT_SUFFIX.get(profile_id, profile_id)
        info(f"[INFO] 모바일 프로젝트 감지: {profile_id}")
        info(f"→ 4개 가이드라인 (guideline_paths) 함께 읽으세요")
        info(f"→ mobile_coder_{agent_suffix} 에이전트 사용")
        info(f"→ HARNESS_AI_HOME 환경변수 설정 필수 (외부 사용자)")

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


# ── recommend 서브커맨드 ──────────────────────────────────────────────


def cmd_recommend(args: argparse.Namespace) -> int:
    """설명 텍스트 → 후보 프로파일 점수순 (blueprint 흡수 B — unsure 진입장벽 완화).

    결정론 스코어링만 — 이유/트레이드오프 서술은 SKILL(LLM)이 프로파일 본문으로 담당.
    """
    description = args.description.strip()
    candidate_ids = (
        [c.strip() for c in args.candidates.split(",") if c.strip()]
        if args.candidates
        else None
    )
    recs = recommend_profiles(description, candidate_ids)
    out = [
        {
            "profile_id": r.profile_id,
            "score": r.score,
            "signals": list(r.signals),
            "guideline_paths": [str(g) for g in resolve_guideline_paths(r.profile_id)],
        }
        for r in recs[: args.top]
    ]
    print(json.dumps({"recommendations": out}, ensure_ascii=False, indent=2))
    return 0


# ── write 서브커맨드 ──────────────────────────────────────────────────


def _order_included_sections(
    included: list[str], profile_order: list[str]
) -> list[str]:
    """활성 섹션 배치 (S-1) — 프로파일 order 우선 + canonical 삽입.

    프로파일 `order` 를 1차 기준으로 유지하되, order 에 없는 활성 섹션
    (6축 자동 활성 신형 — user_journey/threat_model 등) 은 끝에 append 하지
    않고 CANONICAL_SECTION_ORDER 위치에 **삽입**한다. 기존 동작은 HITL
    페르소나 섹션이 notes 뒤에 dangling 하는 결함이 있었다.
    tasks/notes 는 항상 마지막.
    """
    canon_idx = {sid: i for i, sid in enumerate(CANONICAL_SECTION_ORDER)}
    included_set = set(included)
    terminal = [sid for sid in ("tasks", "notes") if sid in included_set]

    seen: set[str] = set()
    primary: list[str] = []
    for sid in profile_order:
        if sid in included_set and sid not in terminal and sid not in seen:
            primary.append(sid)
            seen.add(sid)

    rest = sorted(
        (sid for sid in included if sid not in seen and sid not in terminal),
        key=lambda s: canon_idx.get(s, len(canon_idx)),
    )
    ordered = list(primary)
    for sid in rest:
        ci = canon_idx.get(sid, len(canon_idx))
        pos = len(ordered)
        for j, existing in enumerate(ordered):
            if canon_idx.get(existing, -1) > ci:
                pos = j
                break
        ordered.insert(pos, sid)
    return ordered + terminal


def _axis_warnings(axes) -> list[str]:
    """6축 답변 간 모순 감지 (design backlog D) — advisory.

    모순 조합이 그대로 통과하면 보안 섹션(threat_model/audit_log)이 비활성된 채
    결제 앱이 설계되는 식의 구멍이 생긴다. 차단하지 않고 경고 — SKILL 이
    사용자에게 재질문하도록 안내한다.
    """
    warnings: list[str] = []
    if axes.monetization in ("payment", "subscription") and axes.data_sensitivity == "none":
        warnings.append(
            f"monetization={axes.monetization} 인데 data_sensitivity=none — "
            "결제/구독 정보는 최소 pii 취급 권장. 그대로 두면 threat_model/audit_log "
            "등 보안 섹션이 비활성될 수 있습니다."
        )
    if axes.availability == "high" and axes.lifecycle == "poc":
        warnings.append(
            "availability=high 인데 lifecycle=poc — PoC 에 99.9%+ 가용성 요구는 "
            "모순일 수 있습니다 (runbook/slo 섹션 과활성)."
        )
    return warnings


def cmd_write(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    if not project.exists():
        print(f"[FAIL] project not found: {project}", file=sys.stderr)
        return 1

    profile_ids = [p.strip() for p in args.profiles.split(",") if p.strip()]
    if not profile_ids:
        print("[FAIL] --profiles 비어 있음", file=sys.stderr)
        return 2

    loader = ProfileLoader(project_dir=project)

    # 프로파일 로드 + match 정보 (path 결정용)
    matches = {m.profile.id: m for m in loader.detect()}
    profiles_for_plan: list[ProfileRef] = []
    profile_objs: list[Profile] = []  # for compute_active_sections
    for pid in profile_ids:
        if pid not in matches:
            # detect 안 된 프로파일도 로드 시도 (사용자가 수동 선택한 경우)
            try:
                p = loader.load(pid)
                profiles_for_plan.append(ProfileRef(id=p.id, path=".", status=p.status))
                profile_objs.append(p)
            except Exception as exc:
                print(f"[FAIL] 프로파일 '{pid}' 로드 실패: {exc}", file=sys.stderr)
                return 1
        else:
            m = matches[pid]
            profiles_for_plan.append(
                ProfileRef(id=m.profile.id, path=m.path, status=m.profile.status)
            )
            profile_objs.append(m.profile)

    primary_id = profile_ids[0]
    primary = (
        matches[primary_id].profile if primary_id in matches else loader.load(primary_id)
    )
    primary_path = profiles_for_plan[0].path

    # external_capabilities — BaaS / 외부 backend escape hatch (Group 1-D)
    external_caps_raw = args.external_capabilities.strip()
    external_capabilities: frozenset[str] = frozenset(
        a.strip() for a in external_caps_raw.split(",") if a.strip()
    )
    if external_capabilities:
        unknown_external = external_capabilities - KNOWN_CAPABILITY_ATOMS
        if unknown_external:
            print(
                f"[FAIL] --external-capabilities 의 unknown atom: {sorted(unknown_external)}. "
                f"허용 셋: {sorted(KNOWN_CAPABILITY_ATOMS)}",
                file=sys.stderr,
            )
            return 1

    # 6축 — auto-determine 보다 위로 (axes 가 입력 중 하나라서)
    args.scale = args.user_scale  # legacy `scale` 강제 동기화
    axes = ScaleAxes(
        user_scale=args.user_scale,
        data_sensitivity=args.data_sensitivity,
        team_size=args.team_size,
        availability=args.availability,
        monetization=args.monetization,
        lifecycle=args.lifecycle,
    )

    axis_warnings = _axis_warnings(axes)
    for w in axis_warnings:
        print(f"[WARN] 6축 모순: {w}", file=sys.stderr)

    # included 결정 — 명시 vs auto (Phase 2-b-4)
    included_raw = args.included.strip()
    if included_raw in ("", "auto"):
        # auto: 6축 + profile.skeleton_sections → fragment.required_when 평가
        # utils.py 가 import 시점에 HARNESS_HOME None 이면 sys.exit(3) 하므로 정상
        # 도달 경로엔 None 이 아님. 이중 가드는 type 안전성 + utils 거동 변경 대비.
        fragments_dir_hint: Path | None = None
        if HARNESS_HOME is not None:
            candidate = HARNESS_HOME / "harness" / "templates" / "skeleton"
            if candidate.exists():
                fragments_dir_hint = candidate
        included, activation_trace = loader.compute_active_sections(
            axes, profile_objs, fragments_dir_hint,
            external_capabilities=external_capabilities or None,
        )
        if not included:
            print(
                "[FAIL] auto-determine 결과 활성 섹션 0 — 6축 답변 또는 profile 확인 필요",
                file=sys.stderr,
            )
            return 1

        # Cross-section consistency check — deterministic, not advisory-only.
        # violations 는 차단하지 않음 (write 진행). 차단은 SKILL.md 의 LLM 인터뷰가 담당.
        consistency_violations = find_consistency_violations(
            activation_trace, profile_objs,
            external_capabilities=external_capabilities or None,
        )
        if consistency_violations:
            print(
                f"[WARN] 활성 섹션 중 {len(consistency_violations)}개가 profile 셋과 정합하지 않습니다:",
                file=sys.stderr,
            )
            for v in consistency_violations:
                providers_str = ", ".join(v.expected_providers) if v.expected_providers else "(없음)"
                print(
                    f"  - {v.section_id}: {v.trigger_expression}"
                    f"  (필요: has.{v.missing_atom}, 제공 가능 프로파일: {providers_str})",
                    file=sys.stderr,
                )
            print("SKILL.md 의 명시 승인 흐름을 따르세요.", file=sys.stderr)
    else:
        included = [s.strip() for s in included_raw.split(",") if s.strip()]
        # Override path — no auto-derivation, so no trace to record.
        activation_trace: dict[str, str] = {}
        consistency_violations: list = []
        if not included:
            print("[FAIL] --included 빈 결과", file=sys.stderr)
            return 2

    # skeleton 조립 — 모든 프로파일 order 병합 (tasks/notes 는 항상 맨 끝)
    # paired 모드에서 secondary 프로파일(mobile.* 등)이 tasks/notes 뒤로 밀리는 문제 방지
    _TERMINAL = {"tasks", "notes"}
    seen_order: set[str] = set()
    merged_order: list[str] = []
    for prof in profile_objs:
        for sid in prof.skeleton_sections.order:
            if sid not in _TERMINAL and sid not in seen_order:
                merged_order.append(sid)
                seen_order.add(sid)
    # S-1: order 에 없는 활성 섹션은 canonical 위치에 삽입 (append 금지).
    # terminal(tasks/notes) 강제 후미 배치는 helper 가 담당.
    ordered_included = _order_included_sections(included, merged_order)

    docs_dir = _docs_dir(project, primary_path)
    docs_dir.mkdir(parents=True, exist_ok=True)

    # SkeletonAssembler 의 harness_dir 을 HARNESS_HOME/harness 로 명시 — ProfileLoader
    # 가 본 fragments_dir 과 일치시켜 신규 fragment (Phase 2-a) 도 dev 모드에서 로드.
    assembler_harness_dir = (HARNESS_HOME / "harness") if HARNESS_HOME else None
    assembler = SkeletonAssembler(
        harness_dir=assembler_harness_dir, project_dir=project
    )
    title = f"Project Skeleton — {project.name}"
    try:
        skeleton_text = assembler.assemble(ordered_included, title=title)
    except Exception as exc:
        print(f"[FAIL] skeleton 조립 실패: {exc}", file=sys.stderr)
        return 1

    out_skeleton = docs_dir / "skeleton.md"
    try:
        if out_skeleton.exists() and not args.overwrite:
            backup = docs_dir / f".backup-skeleton-{_now_tag()}.md"
            backup.write_text(out_skeleton.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"[backup] 기존 skeleton.md → {backup.name}", file=sys.stderr)
        out_skeleton.write_text(skeleton_text, encoding="utf-8")
    except OSError as e:
        # Abort before plan creation — a plan must never reference a skeleton
        # that was not actually written (review H2).
        print(f"[FAIL] skeleton.md 쓰기 실패 — plan 생성 중단: {e}", file=sys.stderr)
        return 1

    # plan 작성 (axes 는 위에서 이미 만들어짐)
    pm = PlanManager()
    plan = pm.create(
        project_name=project.name,
        project_type=args.project_type or "(미지정)",
        scale=args.scale,
        user_description_original=args.description or "",
        profiles=profiles_for_plan,
        skeleton_sections=SkeletonSpec(
            required=tuple(primary.skeleton_sections.required),
            optional=tuple(primary.skeleton_sections.optional),
            included=tuple(ordered_included),
        ),
        pipeline_steps=(
            args.pipeline.split(",")
            if args.pipeline
            else [
                "ha-init",
                "ha-design",
                "ha-plan",
                "ha-build",
                "ha-verify",
                "ha-review",
            ]
        ),
        gstack_mode=args.gstack_mode,
        scale_axes=axes,
        activation_trace=activation_trace,
        external_capabilities=sorted(external_capabilities) if external_capabilities else None,
    )
    plan.body = (
        f"# {project.name}\n\n"
        f"## 원본 설명\n{args.description or '(미입력)'}\n\n"
        f"## 판단 근거\n"
        f"- 타입: {args.project_type or '(미지정)'}\n"
        f"- 규모(legacy): {args.scale}\n"
        f"- 6축:\n"
        f"  - user_scale: {axes.user_scale}\n"
        f"  - data_sensitivity: {axes.data_sensitivity}\n"
        f"  - team_size: {axes.team_size}\n"
        f"  - availability: {axes.availability}\n"
        f"  - monetization: {axes.monetization}\n"
        f"  - lifecycle: {axes.lifecycle}\n"
        f"- 활성 프로파일: {', '.join(p.id + '@' + p.path for p in profiles_for_plan)}\n\n"
        f"## 다음 단계\n- /ha-design — skeleton 채우기\n"
    )

    out_plan = docs_dir / "harness-plan.md"
    try:
        if out_plan.exists() and not args.overwrite:
            backup = docs_dir / f".backup-harness-plan-{_now_tag()}.md"
            backup.write_text(out_plan.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"[backup] 기존 harness-plan.md → {backup.name}", file=sys.stderr)
    except OSError as e:
        print(f"[FAIL] harness-plan.md 백업 실패 — plan 저장 중단: {e}", file=sys.stderr)
        return 1
    pm.save(plan, out_plan)

    # capability 추론 제안 (P5 #11) — 설명에서 감지됐지만 아직 활성 안 된 has.* atom.
    # 자동 활성화 아님 — SKILL.md 가 사용자에게 확인 후 --external-capabilities 로 재작성.
    # auto 모드에서만 (override 는 사용자가 섹션을 명시 선택한 상태).
    capability_suggestions: dict[str, list[str]] = {}
    if included_raw in ("", "auto"):
        inferred = infer_capabilities_from_text(args.description or "")
        if inferred:
            active_has = loader.compute_has_keys(
                profile_objs, axes, external_capabilities or None
            )
            capability_suggestions = {
                atom: kws for atom, kws in inferred.items()
                if atom not in active_has and atom not in external_capabilities
            }

    print(json.dumps({
        "project": str(project),
        "skeleton_path": str(out_skeleton),
        "plan_path": str(out_plan),
        "axis_warnings": axis_warnings,
        "included_sections": ordered_included,
        "capability_suggestions": capability_suggestions,
        "profiles": [
            {
                "id": p.id,
                "path": p.path,
                "guideline_paths": [str(g) for g in resolve_guideline_paths(p.id)],
            }
            for p in profiles_for_plan
        ],
        "consistency_violations": [
            {
                "section_id": v.section_id,
                "trigger_expression": v.trigger_expression,
                "missing_atom": v.missing_atom,
                "expected_providers": list(v.expected_providers),
            }
            for v in consistency_violations
        ],
    }, ensure_ascii=False, indent=2))
    return 0


def _now_tag() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d-%H%M%S")


# ── CLI ───────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-init")
    sub = parser.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("detect", help="프로젝트 디렉토리에서 매칭 프로파일 JSON 출력")
    d.add_argument("project_dir", help="프로젝트 루트 경로")

    r = sub.add_parser("recommend", help="설명 텍스트 → 후보 프로파일 점수순 JSON")
    r.add_argument("--description", required=True, help="사용자 자연어 설명")
    r.add_argument("--candidates", default="", help="콤마 구분 후보 프로파일 ID 제한 (선택)")
    r.add_argument("--top", type=int, default=3, help="반환할 최대 후보 수 (기본: 3)")

    w = sub.add_parser("write", help="harness-plan.md + skeleton.md 작성")
    w.add_argument("--project", required=True, help="프로젝트 루트")
    w.add_argument("--profiles", required=True, help="콤마 구분 프로파일 ID")
    w.add_argument(
        "--included",
        default="",
        help=(
            "콤마 구분 섹션 ID (포함할 것). 빈 값 또는 'auto' 면 6축 + profile components "
            "로부터 ProfileLoader.compute_active_sections 가 자동 결정 (Phase 2-b-4)."
        ),
    )
    w.add_argument("--description", default="", help="사용자 설명 원문")
    w.add_argument("--project-type", default="", help="프로젝트 타입 한 줄 요약")
    w.add_argument(
        "--scale",
        choices=["tiny", "small", "medium", "large"],
        default="small",
        help="overall project complexity (legacy axis — keep for compatibility)",
    )
    # 6-axis scaling — fed into plan.scale_axes (see ScaleAxes in plan_manager.py)
    w.add_argument(
        "--user-scale",
        choices=["tiny", "small", "medium", "large"],
        default="small",
        help="expected DAU bucket",
    )
    w.add_argument(
        "--data-sensitivity",
        choices=["none", "pii", "payment"],
        default="none",
    )
    w.add_argument(
        "--team-size",
        choices=["solo", "small", "multi"],
        default="solo",
    )
    w.add_argument(
        "--availability",
        choices=["casual", "standard", "high"],
        default="standard",
    )
    w.add_argument(
        "--monetization",
        choices=["none", "ads", "subscription", "payment"],
        default="none",
    )
    w.add_argument(
        "--lifecycle",
        choices=["poc", "mvp", "ga"],
        default="mvp",
    )
    w.add_argument(
        "--gstack-mode",
        choices=["auto", "manual", "prompt"],
        default="manual",
    )
    w.add_argument("--pipeline", default="", help="콤마 구분 파이프라인 step (선택)")
    w.add_argument(
        "--overwrite",
        action="store_true",
        help="기존 파일 백업 없이 덮어쓰기",
    )
    w.add_argument(
        "--external-capabilities",
        default="",
        help=(
            "콤마 구분 has.* atom (예: 'http_server,users,storage'). "
            "사용자가 명시한 외부 서비스 (BaaS / Firebase / Supabase 등) 가 제공하는 capability. "
            "compute_active_sections + find_consistency_violations 가 이 atom 들을 만족된 것으로 간주 — "
            "backend profile 없이도 BaaS 가 제공하는 섹션의 false-positive violation 방지. "
            "KNOWN_CAPABILITY_ATOMS 안의 atom 만 허용 (typo 차단)."
        ),
    )

    args = parser.parse_args()

    if args.cmd == "detect":
        return cmd_detect(args)
    if args.cmd == "recommend":
        return cmd_recommend(args)
    if args.cmd == "write":
        return cmd_write(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
