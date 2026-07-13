#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-accept` 백엔드 (수용 검증, advisory 게이트).

검증 사다리의 마지막 칸: test/lint/type(ha-verify) → 기동(ha-smoke) 다음에
"skeleton 의 GWT 수용 기준대로 실제로 동작하는가"를 확인한다.

파생(GWT 산문 → acceptance.yaml)은 LLM 몫, 실행은 결정론 — ha-plan 과 동일한
패턴이다 (acceptance-layer-design.md §1 D2):
    prepare  → skeleton 에서 GWT/확정기능/엔드포인트/프로파일 추출 → JSON
    (LLM)    → acceptance.yaml 작성 (SKILL.md 파생 규칙)
    validate → 스키마(BLOCK) + skeleton 교차검증(BLOCK) + 커버리지(advisory)
    run      → 프로파일별 시나리오 실행 (http: booted_server, cli: subprocess)
    record   → verify_history 기록 (step="accept", 상태 전이 없음)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from runtime import BootFailure, booted_server  # noqa: E402
from utils import (  # noqa: E402, I001
    assert_state,
    get_active_profiles,
    info,
    load_plan,
    record_verify,
    save_plan,
)

# backend src import — utils.py 가 backend/ 를 sys.path 에 추가 보장.
# _ENDPOINT_TOKEN_RE 는 consistency_checker 가 이미 정의한 것을 재사용한다
# (ha-plan 이 profile_loader._matches_detect 를 재사용하는 것과 동일한 이유 —
# 같은 토큰 문법을 두 곳에서 유지하면 drift 가 생긴다).
from src.orchestrator.consistency_checker import _ENDPOINT_TOKEN_RE  # noqa: E402
from src.orchestrator.context import split_sections_by_id  # noqa: E402

_HTTP_STEP_TIMEOUT_S = 5
_CLI_STEP_TIMEOUT_S = 30


# ── skeleton 추출 (prepare + validate 공유) ─────────────────────────────

_CONFIRMED_HEADING_RE = re.compile(r"^### 확정 기능\b.*$", re.MULTILINE)
_NEXT_SUBHEADING_RE = re.compile(r"^### ", re.MULTILINE)
_FEATURE_CHECKBOX_RE = re.compile(r"^-\s*\[[ xX]\]\s*(.+?)\s*$")
_GWT_LINE_RE = re.compile(r"\bGiven\b.*\bWhen\b.*\bThen\b", re.IGNORECASE)


def _extract_features(skel_text: str) -> tuple[list[dict], bool]:
    """requirements 섹션의 "확정 기능" 블록 → [{name, gwt: [...]}], legacy_skeleton.

    legacy_skeleton=True 는 GWT 라인이 단 하나도 없을 때 (구버전 skeleton —
    ha-design 의 Step D GWT 인터뷰 이전 산출물이거나 requirements 섹션 자체가
    비활성인 프로젝트).
    """
    sections = split_sections_by_id(skel_text)
    body = sections.get("requirements", "")
    m = _CONFIRMED_HEADING_RE.search(body)
    if not m:
        return [], True

    rest = body[m.end() :]
    next_m = _NEXT_SUBHEADING_RE.search(rest)
    block = rest[: next_m.start()] if next_m else rest

    features: list[dict] = []
    current: dict | None = None
    for line in block.splitlines():
        stripped = line.strip()
        cb = _FEATURE_CHECKBOX_RE.match(stripped)
        if cb:
            current = {"name": cb.group(1).strip(), "gwt": []}
            features.append(current)
            continue
        if current is not None and _GWT_LINE_RE.search(stripped):
            current["gwt"].append(stripped.lstrip("-").strip())

    legacy_skeleton = not any(f["gwt"] for f in features)
    return features, legacy_skeleton


def _extract_declared_endpoints(skel_text: str) -> frozenset[tuple[str, str]]:
    """interface.http 섹션의 백틱 `METHOD /path` 토큰 전부 (변경계 메서드 포함).

    ha-smoke 의 계층2 추출(_check_endpoints)은 GET 만 뽑는다 — ha-accept 는
    시나리오 스텝이 변경계 메서드도 참조하므로 method 무관하게 전부 뽑는다.
    """
    sections = split_sections_by_id(skel_text)
    http_body = sections.get("interface.http", "")
    return frozenset(_ENDPOINT_TOKEN_RE.findall(http_body))


_PARAM_SEGMENT_RE = re.compile(r"^(\{[^{}]+\}|:[^/]+)$")


def _normalize_segments(path: str) -> tuple[str, ...]:
    """경로 파라미터 세그먼트({id}, {todo_id}, :id)를 전부 "{*}" 로 정규화.

    시나리오가 쓰는 변수명({todo_id})과 skeleton 선언의 변수명({id})이 달라도
    세그먼트 위치만 같으면 동일 엔드포인트로 취급한다 (설계 §3).
    """
    return tuple("{*}" if _PARAM_SEGMENT_RE.match(seg) else seg for seg in path.split("/"))


# ── acceptance.yaml 스키마 검증 (BLOCK) ─────────────────────────────────


@dataclass(frozen=True)
class AcceptViolation:
    kind: str
    detail: str


_SCENARIO_ID_RE = re.compile(r"^A-\d{3}$")
_ALLOWED_KINDS = frozenset({"http", "cli"})
# kind 별 허용 expect 키 — http 스텝의 exit, cli 스텝의 status 같은 교차 키는
# 러너가 조용히 무시해 "검증된 줄 아는" 공허 단언이 되므로 스키마에서 차단한다.
_EXPECT_KEYS_BY_KIND: dict[str, frozenset[str]] = {
    "http": frozenset({"status", "json"}),
    "cli": frozenset({"exit", "stdout_contains"}),
}
# bad_kind 시나리오의 스텝 검사용 폴백 (kind 위반은 이미 별도 보고됨)
_ALLOWED_EXPECT_KEYS = frozenset().union(*_EXPECT_KEYS_BY_KIND.values())


def _validate_schema(data: dict) -> list[AcceptViolation]:
    """acceptance.yaml 의 구조적 정합성 (버전/ID/필수필드/kind/steps/expect/capture).

    Pure — I/O 없음. 시나리오/스텝이 통째로 잘못된 타입이면 그 항목만 스킵하고
    계속 진행해 나머지 위반도 한 번에 보고한다 (best-effort collection).
    """
    violations: list[AcceptViolation] = []

    if data.get("version") != 1:
        violations.append(
            AcceptViolation("bad_version", f"version 은 1 이어야 함 (실제: {data.get('version')!r})")
        )

    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list):
        violations.append(AcceptViolation("bad_scenarios", "scenarios 는 리스트여야 함"))
        scenarios = []

    seen_ids: set[str] = set()
    for idx, sc in enumerate(scenarios):
        if not isinstance(sc, dict):
            violations.append(AcceptViolation("bad_scenario", f"scenarios[{idx}] 은 dict 여야 함"))
            continue

        sid = sc.get("id")
        label = sid if isinstance(sid, str) and sid else f"scenarios[{idx}]"
        if not isinstance(sid, str) or not _SCENARIO_ID_RE.match(sid):
            violations.append(AcceptViolation("bad_id", f"{label}.id 형식 위반 (^A-\\d{{3}}$): {sid!r}"))
        elif sid in seen_ids:
            violations.append(AcceptViolation("duplicate_id", f"scenario id 중복: {sid}"))
        if isinstance(sid, str) and sid:
            seen_ids.add(sid)

        for field in ("feature", "gwt", "profile"):
            if not sc.get(field) or not isinstance(sc.get(field), str):
                violations.append(AcceptViolation("missing_field", f"{label}.{field} 필수 (비어있지 않은 문자열)"))

        kind = sc.get("kind")
        if kind not in _ALLOWED_KINDS:
            violations.append(AcceptViolation("bad_kind", f"{label}.kind 는 http|cli 여야 함 (실제: {kind!r})"))

        steps = sc.get("steps")
        if not isinstance(steps, list) or not steps:
            violations.append(AcceptViolation("missing_steps", f"{label}.steps 는 비어있지 않은 리스트여야 함"))
            steps = []

        for step_idx, step in enumerate(steps, start=1):
            step_label = f"{label}.steps[{step_idx}]"
            if not isinstance(step, dict):
                violations.append(AcceptViolation("bad_step", f"{step_label} 은 dict 여야 함"))
                continue

            if kind == "http":
                if not step.get("method"):
                    violations.append(AcceptViolation("missing_field", f"{step_label}.method 필수"))
                if not step.get("path"):
                    violations.append(AcceptViolation("missing_field", f"{step_label}.path 필수"))
            elif kind == "cli":
                if not step.get("run"):
                    violations.append(AcceptViolation("missing_field", f"{step_label}.run 필수"))

            expect = step.get("expect") or {}
            if not isinstance(expect, dict):
                violations.append(AcceptViolation("bad_expect", f"{step_label}.expect 는 dict 여야 함"))
            else:
                allowed_keys = _EXPECT_KEYS_BY_KIND.get(kind, _ALLOWED_EXPECT_KEYS)
                for key in expect:
                    if key not in allowed_keys:
                        violations.append(
                            AcceptViolation(
                                "bad_expect_key",
                                f"{step_label}.expect 허용되지 않은 키 (kind={kind}): {key}",
                            )
                        )

            capture = step.get("capture") or {}
            if not isinstance(capture, dict):
                violations.append(AcceptViolation("bad_capture", f"{step_label}.capture 는 dict 여야 함"))
            else:
                for var, dotted in capture.items():
                    if not isinstance(dotted, str):
                        violations.append(
                            AcceptViolation(
                                "bad_capture_value",
                                f"{step_label}.capture.{var} 는 dotted path 문자열이어야 함 (실제: {dotted!r})",
                            )
                        )

    underivable = data.get("underivable")
    if underivable is not None and not isinstance(underivable, list):
        violations.append(AcceptViolation("bad_underivable", "underivable 은 리스트여야 함"))

    return violations


def _validate_cross(
    data: dict,
    declared_endpoints: frozenset[tuple[str, str]],
    active_profile_ids: frozenset[str],
) -> list[AcceptViolation]:
    """skeleton 대조 (BLOCK): 미선언 엔드포인트 참조 / 비활성 프로파일 참조.

    스키마가 이미 깨진 시나리오(잘못된 타입 등)는 _validate_schema 가 먼저
    잡으므로, 호출측은 스키마 위반이 없을 때만 이 함수를 부른다.
    """
    violations: list[AcceptViolation] = []

    declared_by_method: dict[str, list[tuple[str, ...]]] = {}
    for method, path in declared_endpoints:
        declared_by_method.setdefault(method, []).append(_normalize_segments(path))

    for sc in data.get("scenarios", []):
        sid = sc.get("id", "?")
        profile = sc.get("profile")
        if profile not in active_profile_ids:
            violations.append(
                AcceptViolation("unknown_profile", f"{sid}.profile '{profile}' 은 활성 프로파일에 없음")
            )

        if sc.get("kind") != "http":
            continue
        for step_idx, step in enumerate(sc.get("steps", []), start=1):
            method = step.get("method")
            path = step.get("path")
            if not method or not path:
                continue
            candidates = declared_by_method.get(method, [])
            segments = _normalize_segments(path)
            if segments not in candidates:
                violations.append(
                    AcceptViolation(
                        "endpoint_not_declared",
                        f"{sid} step {step_idx}: {method} {path} 가 skeleton interface.http 에 선언되지 않음",
                    )
                )

    return violations


def _load_acceptance_yaml(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        info(f"[FAIL] acceptance.yaml 읽기 실패: {e}")
        return None
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        info(f"[FAIL] acceptance.yaml YAML 파싱 실패: {e}")
        return None
    if not isinstance(data, dict):
        info("[FAIL] acceptance.yaml 최상위가 dict 가 아님")
        return None
    return data


# ── dotted path 게터 + {var} 치환 (run 전용) ────────────────────────────


def _get_dotted(obj: object, dotted: str) -> object:
    """dotted path (예: "data.items.0.id") 로 obj 를 순회해 값을 반환.

    dict 는 키로, list 는 정수 인덱스 문자열로 진입. 경로가 없으면
    KeyError/IndexError/ValueError/TypeError 중 하나를 raise (호출측이 처리).
    """
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur[part]
        else:
            raise TypeError(f"'{dotted}' 경로 진입 불가 — {part} 지점이 dict/list 아님")
    return cur


_VAR_RE = re.compile(r"\{(\w+)\}")


def _substitute(value: object, variables: dict[str, object]) -> object:
    """문자열의 {var} 를 variables 로 치환 (dict/list 는 재귀). 미정의 변수는 KeyError."""
    if isinstance(value, str):

        def repl(m: re.Match[str]) -> str:
            name = m.group(1)
            if name not in variables:
                raise KeyError(name)
            return str(variables[name])

        return _VAR_RE.sub(repl, value)
    if isinstance(value, dict):
        return {k: _substitute(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, variables) for v in value]
    return value


def _fail(scenario: dict, step_idx: int | None, detail: str) -> dict:
    return {
        "id": scenario.get("id"),
        "feature": scenario.get("feature"),
        "passed": False,
        "failed_step": step_idx,
        "detail": detail,
    }


def _pass(scenario: dict) -> dict:
    return {
        "id": scenario.get("id"),
        "feature": scenario.get("feature"),
        "passed": True,
        "failed_step": None,
        "detail": "PASS",
    }


def _run_http_scenario(scenario: dict, origin: str) -> dict:
    """http kind 시나리오 실행 — 스텝 순차, 캡처/치환, 부분 일치 단언."""
    variables: dict[str, object] = {}
    for step_idx, step in enumerate(scenario.get("steps", []), start=1):
        try:
            path = _substitute(step["path"], variables)
            json_body = _substitute(step.get("json"), variables) if "json" in step else None
        except KeyError as e:
            return _fail(scenario, step_idx, f"미정의 변수 참조: {e}")

        method = step["method"]
        headers: dict[str, str] = {}
        data: bytes | None = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(origin + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=_HTTP_STEP_TIMEOUT_S) as resp:
                status = resp.status
                raw_body = resp.read()
        except urllib.error.HTTPError as e:
            status = e.code
            raw_body = e.read()
        except (urllib.error.URLError, OSError) as e:
            return _fail(scenario, step_idx, f"요청 실패: {e}")

        try:
            resp_json = json.loads(raw_body) if raw_body else None
        except json.JSONDecodeError:
            resp_json = None

        expect = step.get("expect") or {}
        if "status" in expect and status != expect["status"]:
            return _fail(scenario, step_idx, f"status 기대 {expect['status']} 실제 {status}")

        if "json" in expect:
            for dotted, want in expect["json"].items():
                try:
                    got = _get_dotted(resp_json, dotted)
                except (KeyError, IndexError, TypeError, ValueError):
                    return _fail(scenario, step_idx, f"응답에 json.{dotted} 경로 없음")
                if got != want:
                    return _fail(scenario, step_idx, f"json.{dotted} 기대 {want!r} 실제 {got!r}")

        for var, dotted in (step.get("capture") or {}).items():
            try:
                variables[var] = _get_dotted(resp_json, dotted)
            except (KeyError, IndexError, TypeError, ValueError):
                return _fail(scenario, step_idx, f"capture 대상 json.{dotted} 경로 없음")

    return _pass(scenario)


def _run_cli_scenario(scenario: dict, cwd: Path) -> dict:
    """cli kind 시나리오 실행 — 스텝 순차, exit/stdout_contains 단언."""
    variables: dict[str, object] = {}
    for step_idx, step in enumerate(scenario.get("steps", []), start=1):
        try:
            cmd = _substitute(step["run"], variables)
        except KeyError as e:
            return _fail(scenario, step_idx, f"미정의 변수 참조: {e}")

        try:
            r = subprocess.run(
                cmd,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_CLI_STEP_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return _fail(scenario, step_idx, f"타임아웃 {_CLI_STEP_TIMEOUT_S}s 초과")

        expect = step.get("expect") or {}
        if "exit" in expect and r.returncode != expect["exit"]:
            return _fail(scenario, step_idx, f"exit 기대 {expect['exit']} 실제 {r.returncode}")
        if "stdout_contains" in expect:
            output = r.stdout or ""
            for needle in expect["stdout_contains"]:
                if needle not in output:
                    return _fail(scenario, step_idx, f"stdout 에 '{needle}' 없음")

    return _pass(scenario)


# ── 서브커맨드 ───────────────────────────────────────────────────────────


def cmd_prepare(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["verified", "reviewed"], "/ha-accept")

    skel_path = plan_path.parent / "skeleton.md"
    if not skel_path.exists():
        # verified/reviewed 상태에서 skeleton 부재는 비정상 — silent legacy 폴백이
        # 아니라 명시 FAIL (ha-init/ha-design 산출물 확인 유도).
        info(f"[FAIL] skeleton.md 없음: {skel_path} — /ha-init·/ha-design 산출물을 확인하세요")
        return 1
    skel_text = skel_path.read_text(encoding="utf-8")

    features, legacy_skeleton = _extract_features(skel_text)
    declared = sorted(_extract_declared_endpoints(skel_text))
    acc_path = plan_path.parent / "acceptance.yaml"

    profiles = get_active_profiles(plan, project)
    output = {
        "project": str(project),
        "state": plan.pipeline.current_step,
        "features": features,
        "legacy_skeleton": legacy_skeleton,
        "declared_endpoints": [{"method": m, "path": p} for m, p in declared],
        "profiles": [
            {
                "id": p.id,
                "path": plan.profiles[i].path if i < len(plan.profiles) else ".",
                "toolchain": {"smoke": p.toolchain.smoke},
            }
            for i, p in enumerate(profiles)
        ],
        "acceptance_yaml_exists": acc_path.exists(),
        "acceptance_yaml_path": str(acc_path),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    skel_path = plan_path.parent / "skeleton.md"
    acc_path = plan_path.parent / "acceptance.yaml"

    data = _load_acceptance_yaml(acc_path)
    if data is None:
        info(f"[BLOCK] acceptance.yaml 로드 실패 또는 없음: {acc_path}")
        return 1

    schema_violations = _validate_schema(data)

    if not skel_path.exists():
        # 교차 검증의 기준이 없으면 모든 엔드포인트가 "미선언" 으로 오진된다 —
        # 명시 FAIL 로 근본 원인(skeleton 부재)을 바로 보여준다.
        info(f"[FAIL] skeleton.md 없음: {skel_path} — 교차 검증 불가")
        return 1
    skel_text = skel_path.read_text(encoding="utf-8")
    declared_endpoints = _extract_declared_endpoints(skel_text)
    features, _legacy = _extract_features(skel_text)
    active_profile_ids = frozenset(ref.id for ref in plan.profiles)

    cross_violations: list[AcceptViolation] = []
    if not schema_violations:
        cross_violations = _validate_cross(data, declared_endpoints, active_profile_ids)

    feature_names = {f["name"] for f in features}
    referenced = {sc.get("feature") for sc in data.get("scenarios", []) if isinstance(sc, dict)}
    features_without_scenarios = sorted(feature_names - referenced)
    underivable = data.get("underivable")
    underivable_count = len(underivable) if isinstance(underivable, list) else 0

    all_violations = [*schema_violations, *cross_violations]
    output = {
        "schema_violations": [v.__dict__ for v in schema_violations],
        "cross_violations": [v.__dict__ for v in cross_violations],
        "coverage": {
            "features_without_scenarios": features_without_scenarios,
            "underivable_count": underivable_count,
        },
        "passed": not all_violations,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not all_violations else 1


def cmd_run(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    acc_path = plan_path.parent / "acceptance.yaml"

    data = _load_acceptance_yaml(acc_path)
    if data is None:
        info(f"[FAIL] acceptance.yaml 로드 실패 또는 없음: {acc_path}")
        return 2

    scenarios = [sc for sc in data.get("scenarios", []) if sc.get("profile") == args.profile]
    if not scenarios:
        # 매칭 0개가 exit 0 이 되면 --profile 오타가 공허 통과로 둔갑한다.
        available = sorted({sc.get("profile") for sc in data.get("scenarios", [])})
        info(
            f"[FAIL] acceptance.yaml 에 profile '{args.profile}' 시나리오 없음 "
            f"(존재: {', '.join(str(p) for p in available) or '없음'})"
        )
        return 2
    profile_ref = next((ref for ref in plan.profiles if ref.id == args.profile), None)
    cwd = project if profile_ref is None or profile_ref.path == "." else project / profile_ref.path

    needs_http = any(sc.get("kind") == "http" for sc in scenarios)
    results: list[dict] = []

    if needs_http:
        if not args.command or not args.url:
            info("[FAIL] http kind 시나리오가 있으나 --command/--url 미지정")
            return 2
        try:
            with booted_server(args.command, cwd, args.url, args.ready_timeout) as origin:
                for sc in scenarios:
                    if sc.get("kind") == "http":
                        results.append(_run_http_scenario(sc, origin))
                    else:
                        results.append(_run_cli_scenario(sc, cwd))
        except BootFailure as e:
            if e.result.exited:
                reason = f"프로세스가 ready 전에 종료 (exit code {e.result.exit_code})"
            elif e.result.status is not None:
                reason = f"HTTP {e.result.status} — 서버는 떴으나 ready 아님"
            else:
                reason = "ready 타임아웃 초과"
            for sc in scenarios:
                results.append(
                    _fail(sc, None, f"프로파일 '{args.profile}' 부팅 실패 — 시나리오 실행 불가 ({reason})")
                )
    else:
        for sc in scenarios:
            results.append(_run_cli_scenario(sc, cwd))

    output = {"profile": args.profile, "scenarios": results}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if all(r["passed"] for r in results) else 1


def cmd_record(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["verified", "reviewed"], "/ha-accept record")

    passed = args.passed.lower() in ("true", "1", "yes", "y")
    record_verify(plan, step="accept", passed=passed, summary=args.summary)
    # advisory 게이트 — 상태 전이 없음 (ha-smoke 와 동일 시맨틱)
    save_plan(plan, plan_path)

    output = {
        "passed": passed,
        "summary": args.summary,
        "current_step": plan.pipeline.current_step,
        "verify_history_count": len(plan.verify_history),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-accept")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    sub.add_parser("validate")
    r = sub.add_parser("run")
    r.add_argument("--profile", required=True, help="실행 대상 프로파일 id")
    r.add_argument("--command", default="", help="http kind: 기동 명령 (shell)")
    r.add_argument("--url", default="", help="http kind: readiness 폴링 URL")
    r.add_argument("--ready-timeout", type=int, default=60, help="http kind: ready 타임아웃 (초)")
    rec = sub.add_parser("record")
    rec.add_argument("--passed", required=True)
    rec.add_argument("--summary", required=True)
    args = parser.parse_args()
    if args.cmd == "prepare":
        return cmd_prepare(args)
    if args.cmd == "validate":
        return cmd_validate(args)
    if args.cmd == "run":
        return cmd_run(args)
    return cmd_record(args)


if __name__ == "__main__":
    sys.exit(main())
