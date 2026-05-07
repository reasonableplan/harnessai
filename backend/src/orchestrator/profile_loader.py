"""Profile loader — parse _registry.yaml, resolve local/global, merge inheritance, detect projects.

Phase 2-b-3 added: compute_active_sections() — 6축 답변 + profile components →
fragment.required_when 평가 → 활성 섹션 ID 결정 (skeleton 자동 맞춤).

See design doc §3 (profile system spec) and §11 (migration plan).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

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


# 섹션 ID → has 키 매핑. profile.skeleton_sections.{required, optional} 에
# declared 된 섹션이 있으면 그 섹션의 has 키가 활성. fragment 의 required_when
# 표현식이 has.<key> atom 으로 참조.
#
# KEEP IN SYNC with harness/templates/skeleton/<id>.md frontmatter 의
# required_when. 새 섹션 추가 시 이 매핑도 갱신 — 그렇지 않으면 활성 결정에서
# 빠짐 (silent miss).
_SECTION_TO_HAS_KEY: dict[str, str] = {
    "auth": "users",
    "authorization_matrix": "users",
    "user_journey": "users",
    "persistence": "storage",
    "data_model": "storage",
    "configuration": "env_config",
    "external_deps": "external_deps",
    "integrations": "external_deps",
    "interface.http": "http_server",
    "interface.cli": "cli_entrypoint",
    "interface.ipc": "ipc",
    "interface.sdk": "sdk_surface",
    "view.screens": "ui",
    "view.components": "ui",
    "state.flow": "complex_state",
    "observability": "production_concerns",
    "deployment": "production_concerns",
    "ci_cd": "production_concerns",
    "runbook": "production_concerns",
    # Mobile — profile 이 mobile.* 를 declared sections 에 포함하면
    # has.navigation / has.build_config / has.lifecycle atom 활성.
    # Web/CLI/Lib 프로파일은 이 섹션을 선언 안 하므로 자동 비활성 (호환성 유지).
    "mobile.navigation": "navigation",
    "mobile.build_config": "build_config",
    "mobile.lifecycle": "lifecycle",
}

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
                # Parent not found — break to _base
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

    def compute_has_keys(self, profiles: list[Profile]) -> frozenset[str]:
        """Profiles 의 declared sections (required ∪ optional) 에서 has 키 추출.

        반환된 frozenset 은 fragment 의 required_when 표현식 평가 시 ctx.has_keys
        로 사용. 표준 has 토큰 (users / storage / env_config / external_deps /
        http_server / cli_entrypoint / ipc / sdk_surface / ui / complex_state /
        production_concerns) 만 포함 — `_SECTION_TO_HAS_KEY` 매핑에 없는 섹션은
        무시.
        """
        keys: set[str] = set()
        for profile in profiles:
            for section_id in (
                *profile.skeleton_sections.required,
                *profile.skeleton_sections.optional,
            ):
                mapped = _SECTION_TO_HAS_KEY.get(section_id)
                if mapped:
                    keys.add(mapped)
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
    ) -> list[str]:
        """6축 + profiles → 활성 fragment 섹션 ID 리스트 (정렬 보장).

        결정 흐름:
            profiles → has_keys (declared sections 매핑)
            axes.user_scale → scale_tokens (cumulative)
            fragments_dir → {id: required_when} 메타데이터
            scale_expression.evaluate(required_when, ctx) → bool
            True 인 fragment id 만 수집

        표현식 파싱 실패 시: 보수적으로 활성화 (False positive 가 False negative
        보다 안전 — 사용자가 만든 fragment 는 일반적으로 더 포함되는 게 안전).
        invalid expression 은 harness validate 가 사전에 거부.
        """
        has_keys = self.compute_has_keys(profiles)
        scale_tokens = self.compute_scale_tokens(axes)
        fragments = self.load_fragments_metadata(fragments_dir)

        ctx = EvalContext(
            axes=axes,
            has_keys=has_keys,
            scale_tokens=scale_tokens,
        )

        active: list[str] = []
        for frag_id, required_when in sorted(fragments.items()):
            try:
                if scale_evaluate(required_when, ctx):
                    active.append(frag_id)
            except ExpressionParseError:
                # 보수적 활성화 — Phase 2-b-2 의 harness validate 가 사전에
                # invalid expression 을 거부하므로 정상 경로에서는 도달 안 함.
                active.append(frag_id)
        return active

    # ── 기존 ────────────────────────────────────────────────────────────

    def _dict_to_profile(self, data: dict[str, Any], body: str) -> Profile:
        sec = data.get("skeleton_sections") or {}
        wl = data.get("whitelist") or {}
        tc = data.get("toolchain") or {}
        comps = data.get("components") or []

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
