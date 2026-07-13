"""Profile loader — parse _registry.yaml, resolve local/global, merge inheritance, detect projects.

Phase 2-b-3 added: compute_active_sections() — 6축 답변 + profile components →
fragment.required_when 평가 → 활성 섹션 ID 결정 (skeleton 자동 맞춤).

Group 5 Step 1: SRP split — derive_axes_capabilities → capabilities.py,
ConsistencyViolation/find_consistency_violations → consistency.py,
UnknownLessonReference/extract_known_lessons/find_unknown_lesson_references → lessons.py.
Re-exports below preserve backward compatibility for all existing callers.

See design doc §3 (profile system spec) and §11 (migration plan).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.orchestrator.capabilities import derive_axes_capabilities
from src.orchestrator.plan_manager import ScaleAxes
from src.orchestrator.scale_expression import (
    EvalContext,
    ExpressionParseError,
)
from src.orchestrator.scale_expression import (
    evaluate as scale_evaluate,
)

DEFAULT_HARNESS_DIR = Path.home() / ".claude" / "harness"

_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---", re.DOTALL)

# user_scale → scale.X 토큰 (cumulative — small 은 small_or_larger 까지만,
# medium 은 small + medium, large 는 셋 다).
_USER_SCALE_TO_TOKENS: dict[str, frozenset[str]] = {
    "tiny": frozenset(),
    "small": frozenset({"small_or_larger"}),
    "medium": frozenset({"small_or_larger", "medium_or_larger"}),
    "large": frozenset({"small_or_larger", "medium_or_larger", "large"}),
}


# Data models


@dataclass(frozen=True)
class Toolchain:
    """Profile toolchain commands. None means the tool is not configured."""

    install: str | None
    test: str | None
    lint: str | None
    type: str | None
    format: str | None
    # /ha-smoke 런타임 기동 검증 명령 (exit 0 = PASS). 서버형 프로파일은
    # 포트가 프로젝트마다 달라 여기 고정하지 않고 SKILL.md 휴리스틱이 도출.
    smoke: str | None = None
    # T-000 결정론 스캐폴드 부트스트랩 명령 (비대화형, cwd(`.`) 대상 필수).
    # 공식 스캐폴더가 없는 프로파일(fastapi 등)은 None 유지 (scaffolding-design.md §1).
    scaffold: str | None = None


@dataclass(frozen=True)
class Whitelist:
    """Allowed dependency lists for a profile."""

    runtime: tuple[str, ...]
    dev: tuple[str, ...]
    prefix_allowed: tuple[str, ...]


@dataclass(frozen=True)
class Component:
    """Profile component type (e.g. persistence, interface.cli)."""

    id: str
    required: bool
    skeleton_section: str
    description: str = ""


@dataclass(frozen=True)
class SkeletonSections:
    """Skeleton section IDs used by a profile."""

    required: tuple[str, ...]
    optional: tuple[str, ...]
    order: tuple[str, ...]


@dataclass(frozen=True)
class Profile:
    """Fully parsed and inheritance-merged profile."""

    id: str
    name: str
    status: str  # "confirmed" | "draft"
    version: int
    extends: str | None
    paths: tuple[str, ...]
    detect: dict[str, Any]
    components: tuple[Component, ...]
    skeleton_sections: SkeletonSections
    toolchain: Toolchain
    whitelist: Whitelist
    file_structure: str
    gstack_mode: str  # "auto" | "manual" | "prompt"
    gstack_recommended: dict[str, list[str]]
    lessons_applied: tuple[str, ...]
    body: str  # markdown body (frontmatter stripped)
    raw: dict[str, Any] = field(default_factory=dict)
    # Capabilities the profile directly provides. Used by compute_has_keys
    # to drive fragment.required_when evaluation. Empty tuple means no
    # has.* atoms contributed (strict — legacy section-based fallback
    # was removed in Step 3). All profiles should declare this explicitly.
    provides_capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProfileMatch:
    """Detection result — profile + relative path from project root."""

    profile: Profile
    path: str


class ProfileNotFoundError(LookupError):
    """Profile file not found in either global or local locations."""


class CyclicInheritanceError(ValueError):
    """Cyclic inheritance detected in extends chain."""


# Loader


class ProfileLoader:
    """Profile loader with local override, inheritance merging, and caching.

    Local override (`{project}/.claude/harness/profiles/<id>.md`) takes
    precedence over global (`~/.claude/harness/profiles/<id>.md`).
    Follows extends chains with `_base` as the lowest ancestor.
    load() results are cached; detect() always scans the filesystem.
    """

    def __init__(
        self,
        harness_dir: Path | None = None,
        project_dir: Path | None = None,
    ) -> None:
        self.harness_dir = (harness_dir or DEFAULT_HARNESS_DIR).resolve()
        self.project_dir = project_dir.resolve() if project_dir else None
        self._cache: dict[str, Profile] = {}

    def load(self, profile_id: str) -> Profile:
        """Load a profile with local override and inheritance merging.

        Raises:
            ProfileNotFoundError: Not found in global or local.
            CyclicInheritanceError: Circular extends chain.
            ValueError: Frontmatter parse failure.
        """
        if profile_id == "_base":
            raise ValueError(
                "_base cannot be loaded directly (it is meant to be extended by other profiles)"
            )
        if profile_id in self._cache:
            return self._cache[profile_id]

        path = self._resolve_profile_path(profile_id)
        raw_data, body = self._parse_file(path)
        merged = self._apply_inheritance(raw_data)
        profile = self._dict_to_profile(merged, body)
        self._cache[profile_id] = profile
        return profile

    def detect(self, project_dir: Path | None = None) -> list[ProfileMatch]:
        """Return every matching profile for the project root (monorepo-aware).

        Each rule uses its first matching path. Multiple rules may match the
        same path independently.
        """
        root = (project_dir or self.project_dir or Path.cwd()).resolve()
        registry = self.load_registry()
        matches: list[ProfileMatch] = []
        for rule in registry.get("rules", []) or []:
            profile_id = rule.get("profile")
            if not profile_id:
                continue
            paths = rule.get("paths") or ["."]
            detect_block = rule.get("detect", {}) or {}
            for rel in paths:
                base = root if rel == "." else (root / rel)
                if _matches_detect(base, detect_block):
                    try:
                        profile = self.load(profile_id)
                    except (ProfileNotFoundError, ValueError):
                        continue
                    matches.append(ProfileMatch(profile=profile, path=rel))
                    break
        return matches

    def load_registry(self) -> dict[str, Any]:
        """Load _registry.yaml."""
        path = self.harness_dir / "profiles" / "_registry.yaml"
        if not path.exists():
            raise FileNotFoundError(f"_registry.yaml not found: {path}")
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _resolve_profile_path(self, profile_id: str) -> Path:
        """Resolve profile path — local override first, then global."""
        if self.project_dir:
            local = self.project_dir / ".claude" / "harness" / "profiles" / f"{profile_id}.md"
            if local.exists():
                return local
        global_path = self.harness_dir / "profiles" / f"{profile_id}.md"
        if global_path.exists():
            return global_path
        raise ProfileNotFoundError(f"profile '{profile_id}' file not found")

    def _parse_file(self, path: Path) -> tuple[dict[str, Any], str]:
        """Split file into frontmatter dict + body text."""
        text = path.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(text)
        if not m:
            raise ValueError(f"{path.name}: missing YAML frontmatter")
        try:
            data = yaml.safe_load(m.group(1))
        except yaml.YAMLError as exc:
            raise ValueError(f"{path.name}: YAML parse failed: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"{path.name}: frontmatter must be a dict")
        body = text[m.end() :].lstrip()
        return data, body

    def _read_base(self) -> dict[str, Any]:
        """Read _base.md raw frontmatter (empty dict if not found)."""
        candidates: list[Path] = []
        if self.project_dir:
            candidates.append(self.project_dir / ".claude" / "harness" / "profiles" / "_base.md")
        candidates.append(self.harness_dir / "profiles" / "_base.md")
        for p in candidates:
            if p.exists():
                data, _ = self._parse_file(p)
                return data
        return {}

    def _apply_inheritance(self, data: dict[str, Any]) -> dict[str, Any]:
        """Merge along the extends chain. _base is always the lowest ancestor."""
        chain: list[dict[str, Any]] = [data]
        seen: set[str] = {data.get("id", "")}
        cur = data
        while True:
            parent_id = cur.get("extends")
            if not parent_id or parent_id == "_base":
                break
            if parent_id in seen:
                raise CyclicInheritanceError(
                    f"cyclic inheritance: {' -> '.join([*seen, parent_id])}"
                )
            seen.add(parent_id)
            try:
                parent_path = self._resolve_profile_path(parent_id)
            except ProfileNotFoundError:
                # Parent not found — fall back to _base, but loudly: silently
                # dropping the parent strips its whitelist/toolchain and causes
                # false-negative security checks downstream (review H3).
                print(
                    f"[WARN] profile '{cur.get('id', '?')}' extends '{parent_id}' "
                    "— 부모 프로파일을 찾지 못해 _base 로 폴백합니다. "
                    "부모의 whitelist/toolchain 이 누락된 상태입니다.",
                    file=sys.stderr,
                )
                break
            parent_data, _ = self._parse_file(parent_path)
            chain.append(parent_data)
            cur = parent_data

        base = self._read_base()
        if base:
            chain.append(base)

        # Merge from base upward — child overrides parent
        merged: dict[str, Any] = {}
        for layer in reversed(chain):
            merged = _merge_layer(merged, layer)
        return merged

    # ── Phase 2-b-3: 6축 답변 → 활성 섹션 결정 ─────────────────────

    def compute_has_keys(
        self,
        profiles: list[Profile],
        axes: ScaleAxes | None = None,
        external_capabilities: frozenset[str] | None = None,
    ) -> frozenset[str]:
        """Compute has.* atoms from THREE sources (union):

        1. profile.provides_capabilities (explicit declaration)
        2. derive_axes_capabilities(axes) (user-intent inference from 6 axes)
        3. external_capabilities (Group 1-D: user-declared BaaS / external
           services. e.g. Firebase provides http_server + users + storage
           even without a backend profile in the profiles list.)

        All profiles MUST declare provides_capabilities (possibly empty list).
        Profile validation catches any profile that fails to declare it
        explicitly — silent legacy fallback removed in Step 3.

        axes is optional for backward compatibility — callers that haven't
        migrated still work, just without axes-derived atoms.
        external_capabilities is optional — None is treated as an empty set
        (backward-compatible; existing callers are unaffected).
        """
        keys: set[str] = set()

        for profile in profiles:
            keys.update(profile.provides_capabilities)

        if axes is not None:
            keys.update(derive_axes_capabilities(axes))

        if external_capabilities:
            keys.update(external_capabilities)

        return frozenset(keys)

    def compute_scale_tokens(self, axes: ScaleAxes) -> frozenset[str]:
        """6축의 user_scale → scale.X 토큰 set (cumulative)."""
        return _USER_SCALE_TO_TOKENS.get(axes.user_scale, frozenset())

    def load_fragments_metadata(self, fragments_dir: Path | None = None) -> dict[str, str]:
        """fragments dir 의 모든 *.md frontmatter 에서 id → required_when.

        본문은 무시 (SkeletonAssembler 의 책임). 파싱 실패 / 필수 필드 누락된
        fragment 는 silently skip — 정식 검증은 harness validate fragments 에서.
        """
        fragments_dir = fragments_dir or (self.harness_dir / "templates" / "skeleton")
        if not fragments_dir.exists():
            return {}
        out: dict[str, str] = {}
        for path in sorted(fragments_dir.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            m = _FRONTMATTER_RE.match(text)
            if not m:
                continue
            try:
                data = yaml.safe_load(m.group(1))
            except yaml.YAMLError:
                continue
            if not isinstance(data, dict):
                continue
            frag_id = data.get("id")
            required_when = data.get("required_when")
            if isinstance(frag_id, str) and isinstance(required_when, str):
                out[frag_id] = required_when
        return out

    def compute_active_sections(
        self,
        axes: ScaleAxes,
        profiles: list[Profile],
        fragments_dir: Path | None = None,
        external_capabilities: frozenset[str] | None = None,
    ) -> tuple[list[str], dict[str, str]]:
        """6축 + profiles → (활성 섹션 ID 리스트, activation trace dict).

        결정 흐름:
            profiles → has_keys (declared sections 매핑)
            axes.user_scale → scale_tokens (cumulative)
            fragments_dir → {id: required_when} 메타데이터
            scale_expression.evaluate(required_when, ctx) → bool
            True 인 fragment id 만 수집

        반환값:
            (active, trace) — active 는 정렬된 활성 섹션 ID 리스트,
            trace 는 {section_id: required_when_expression} dict.

        표현식 파싱 실패 시: ExpressionParseError 를 raise (fail-fast, frag_id 포함).
        보수적 활성화는 typo 를 silently 숨겨 폐기됨 (Group 5 Step 3 strictness) —
        invalid expression 은 harness validate 가 사전에 거부한다.

        external_capabilities: Group 1-D — user-declared BaaS / external service
        atoms unioned into has_keys so fragment required_when evaluation includes them.
        None is treated as an empty set (backward-compatible).
        """
        has_keys = self.compute_has_keys(profiles, axes, external_capabilities)
        scale_tokens = self.compute_scale_tokens(axes)
        fragments = self.load_fragments_metadata(fragments_dir)

        ctx = EvalContext(
            axes=axes,
            has_keys=has_keys,
            scale_tokens=scale_tokens,
        )

        active: list[str] = []
        trace: dict[str, str] = {}
        for frag_id, required_when in sorted(fragments.items()):
            try:
                if scale_evaluate(required_when, ctx):
                    active.append(frag_id)
                    trace[frag_id] = required_when
            except ExpressionParseError as exc:
                # Fail-fast: invalid required_when expression is a fragment
                # authoring bug. Silent conservative activation hid typos from
                # users — Group 5 Step 3 strictness. `harness validate` should
                # catch these before they reach runtime; surfacing frag_id here
                # gives actionable diagnostics if it slips through.
                raise ExpressionParseError(
                    f'fragment "{frag_id}" 의 required_when 파싱 실패 — '
                    f"harness validate 로 검증 후 수정: {exc}"
                ) from exc
        return active, trace

    # ── 기존 ────────────────────────────────────────────────────────────

    def _dict_to_profile(self, data: dict[str, Any], body: str) -> Profile:
        sec = data.get("skeleton_sections") or {}
        wl = data.get("whitelist") or {}
        tc = data.get("toolchain") or {}
        comps = data.get("components") or []

        # provides_capabilities: list in frontmatter → tuple; missing key → empty tuple (legacy).
        raw_caps = data.get("provides_capabilities")
        provides_capabilities: tuple[str, ...] = (
            tuple(str(c) for c in raw_caps) if isinstance(raw_caps, list) else ()
        )

        return Profile(
            id=data["id"],
            name=data.get("name", data["id"]),
            status=data.get("status", "confirmed"),
            version=int(data.get("version", 1)),
            extends=data.get("extends"),
            paths=tuple(data.get("paths") or []),
            detect=data.get("detect") or {},
            components=tuple(
                Component(
                    id=c["id"],
                    required=bool(c.get("required", False)),
                    skeleton_section=c.get("skeleton_section", ""),
                    description=c.get("description", ""),
                )
                for c in comps
                if isinstance(c, dict) and "id" in c
            ),
            skeleton_sections=SkeletonSections(
                required=tuple(sec.get("required") or []),
                optional=tuple(sec.get("optional") or []),
                order=tuple(sec.get("order") or []),
            ),
            toolchain=Toolchain(
                install=tc.get("install"),
                test=tc.get("test"),
                lint=tc.get("lint"),
                type=tc.get("type"),
                format=tc.get("format"),
                smoke=tc.get("smoke"),
                scaffold=tc.get("scaffold"),
            ),
            whitelist=Whitelist(
                runtime=tuple(wl.get("runtime") or []),
                dev=tuple(wl.get("dev") or []),
                prefix_allowed=tuple(wl.get("prefix_allowed") or []),
            ),
            file_structure=data.get("file_structure", ""),
            gstack_mode=data.get("gstack_mode", "manual"),
            gstack_recommended=data.get("gstack_recommended") or {},
            lessons_applied=tuple(data.get("lessons_applied") or []),
            body=body,
            raw=data,
            provides_capabilities=provides_capabilities,
        )


# Module-level helpers


def _matches_detect(base: Path, detect: dict[str, Any]) -> bool:
    """Evaluate a single detect block — files / files_any / contains / contains_any / not_contains.

    `files_any` 는 후보 중 **하나라도** 존재하면 매칭 (Android build.gradle.kts vs
    build.gradle 같은 OR 케이스). 빈 리스트는 vacuous match 가 아니라 fail —
    의도하지 않은 silent match 방어.
    """
    if "files" in detect:
        for f in detect["files"] or []:
            if not (base / f).exists():
                return False

    if "files_any" in detect:
        candidates = detect["files_any"] or []
        if not candidates or not any((base / f).exists() for f in candidates):
            return False

    for op in ("contains", "contains_any", "not_contains"):
        if op not in detect:
            continue
        for fname, subs in (detect[op] or {}).items():
            fp = base / fname
            if not fp.exists():
                return False
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return False
            if op == "contains":
                if not all(s in text for s in subs):
                    return False
            elif op == "contains_any":
                if not any(s in text for s in subs):
                    return False
            elif op == "not_contains" and any(s in text for s in subs):
                return False
    return True


def _merge_layer(base: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    """Child overrides base. Merge rules per design doc S3.4."""
    merged = dict(base)
    for key, value in child.items():
        if key == "whitelist" and isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_whitelist(merged[key], value)
        elif key == "components" and isinstance(value, list):
            base_comps = merged.get(key) or []
            child_ids = {c.get("id") for c in value if isinstance(c, dict)}
            kept = [c for c in base_comps if c.get("id") not in child_ids]
            merged[key] = [*kept, *value]
        elif (
            key == "skeleton_sections"
            and isinstance(value, dict)
            and isinstance(merged.get(key), dict)
        ):
            merged[key] = _merge_skeleton_sections(merged[key], value)
        else:
            merged[key] = value
    return merged


def _merge_whitelist(base: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    """Whitelist lists are unioned (base order first, child appended)."""
    out: dict[str, Any] = dict(base)
    for sub in ("runtime", "dev", "prefix_allowed"):
        seen: set[str] = set()
        combined: list[str] = []
        for item in [*(base.get(sub) or []), *(child.get(sub) or [])]:
            if item not in seen:
                seen.add(item)
                combined.append(item)
        out[sub] = combined
    return out


def _merge_skeleton_sections(
    base: dict[str, Any],
    child: dict[str, Any],
) -> dict[str, Any]:
    """skeleton_sections: required/optional are unioned, order is child-first."""
    out: dict[str, Any] = {}
    for sub in ("required", "optional"):
        seen: set[str] = set()
        combined: list[str] = []
        for item in [*(base.get(sub) or []), *(child.get(sub) or [])]:
            if item not in seen:
                seen.add(item)
                combined.append(item)
        out[sub] = combined
    out["order"] = child.get("order") or base.get("order") or []
    return out


# Re-exports for backward compatibility (Group 5 Step 1 SRP split).
# Prefer importing from the specialized modules directly in new code.
from src.orchestrator.consistency import (  # noqa: E402, F401, I001
    ConsistencyViolation,
    _HAS_KEY_PROVIDERS,
    find_consistency_violations,
)
from src.orchestrator.lessons import (  # noqa: E402, F401, I001
    UnknownLessonReference,
    extract_known_lessons,
    find_unknown_lesson_references,
)
