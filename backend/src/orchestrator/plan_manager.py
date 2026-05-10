"""Plan manager — read/write harness-plan.md frontmatter and validate state transitions.

See design doc §6 (pipeline state tracking).

State machine (§6.2):
    init → designed → planned → building → built → verified → reviewed → shipped

Transition rules:
- Forward only (rollback requires explicit backup)
- One step at a time (no skipping)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)

# State machine — forward progression only
STATE_ORDER: tuple[str, ...] = (
    "init",
    "designed",
    "planned",
    "building",
    "built",
    "verified",
    "reviewed",
    "shipped",
)
ALLOWED_GSTACK_MODES = {"auto", "manual", "prompt"}

# 6-axis project scaling — drives profile-matrix section activation downstream
ALLOWED_USER_SCALES = {"tiny", "small", "medium", "large"}
ALLOWED_DATA_SENSITIVITY = {"none", "pii", "payment"}
ALLOWED_TEAM_SIZES = {"solo", "small", "multi"}
ALLOWED_AVAILABILITY = {"casual", "standard", "high"}
ALLOWED_MONETIZATION = {"none", "ads", "subscription", "payment"}
ALLOWED_LIFECYCLE = {"poc", "mvp", "ga"}

# Redesign lifecycle — see /ha-redesign skill (mutation propagation feature).
#   proposed: ha-redesign prepare identified the affected scope, awaiting approval.
#   approved: user accepted the proposed re-derivation; skeleton/tasks edits pending.
#   applied:  skeleton.md and (when relevant) tasks.md have been updated.
#   rejected: user declined the proposal — kept for audit trail.
ALLOWED_REDESIGN_STATUS = {"proposed", "approved", "applied", "rejected"}


# Data models


@dataclass(frozen=True)
class ProfileRef:
    """Profile reference in harness-plan (id + applied path)."""

    id: str
    path: str
    status: str = "confirmed"


@dataclass(frozen=True)
class VerifyRecord:
    """Single /ha-verify execution record."""

    step: str
    at: str  # ISO 8601 UTC
    passed: bool
    summary: str


@dataclass(frozen=True)
class RedesignEntry:
    """A single mutation-propagation event recorded by /ha-redesign.

    Captures a decision change (e.g. CEO pivot, eng review correction) along with
    the sections/tasks it affects so that re-derivation is auditable and reversible.
    The skill itself drives the lifecycle (proposed → approved → applied or rejected);
    this record is the source of truth for what changed and why.
    """

    at: str  # ISO 8601 UTC
    decision: str  # short human-readable label (e.g. "CEO pivot: PTT only")
    rationale: str  # source/reason (e.g. "/plan-ceo-review 결과 — D7 retention 우선")
    affected_sections: tuple[str, ...]  # skeleton section identifiers (e.g. "§13")
    affected_tasks: tuple[str, ...]  # task IDs whose status/spec changed (e.g. "T-200")
    status: str  # one of ALLOWED_REDESIGN_STATUS

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_REDESIGN_STATUS:
            raise PlanSchemaError(
                f"redesign status must be one of {sorted(ALLOWED_REDESIGN_STATUS)}, "
                f"got '{self.status}'"
            )


@dataclass(frozen=True)
class SkeletonSpec:
    """Skeleton section decisions from harness-plan."""

    required: tuple[str, ...]
    optional: tuple[str, ...]
    included: tuple[str, ...]


@dataclass(frozen=True)
class Pipeline:
    """Pipeline progress state."""

    steps: tuple[str, ...]  # order proposed by ha-init (gstack steps included)
    current_step: str  # abstract state (one of STATE_ORDER)
    completed_steps: tuple[str, ...]  # step names that actually ran
    skipped_steps: tuple[str, ...] = ()
    gstack_mode: str = "manual"

    def __post_init__(self) -> None:
        # Validate at construction so a hand-edited frontmatter with bogus values
        # surfaces as PlanSchemaError instead of a confusing ValueError later
        # from STATE_ORDER.index() during transition().
        if self.current_step not in STATE_ORDER:
            raise PlanSchemaError(
                f"pipeline.current_step must be one of {STATE_ORDER}, got '{self.current_step}'"
            )
        if self.gstack_mode not in ALLOWED_GSTACK_MODES:
            raise PlanSchemaError(
                f"pipeline.gstack_mode must be one of {sorted(ALLOWED_GSTACK_MODES)}, "
                f"got '{self.gstack_mode}'"
            )


@dataclass(frozen=True)
class ScaleAxes:
    """Six-axis project scaling profile collected during /ha-init.

    Each axis is independent. Captured here so the downstream profile-matrix
    can decide which skeleton sections to activate (Phase 2 work).
    Defaults are the most conservative / common option for each axis so that
    legacy plans without this block load cleanly.
    """

    user_scale: str = "small"  # tiny | small | medium | large
    data_sensitivity: str = "none"  # none | pii | payment
    team_size: str = "solo"  # solo | small | multi
    availability: str = "standard"  # casual | standard | high
    monetization: str = "none"  # none | ads | subscription | payment
    lifecycle: str = "mvp"  # poc | mvp | ga

    def __post_init__(self) -> None:
        for name, val, allowed in (
            ("user_scale", self.user_scale, ALLOWED_USER_SCALES),
            ("data_sensitivity", self.data_sensitivity, ALLOWED_DATA_SENSITIVITY),
            ("team_size", self.team_size, ALLOWED_TEAM_SIZES),
            ("availability", self.availability, ALLOWED_AVAILABILITY),
            ("monetization", self.monetization, ALLOWED_MONETIZATION),
            ("lifecycle", self.lifecycle, ALLOWED_LIFECYCLE),
        ):
            if val not in allowed:
                raise PlanSchemaError(
                    f"scale_axes.{name} must be one of {sorted(allowed)}, got '{val}'"
                )


@dataclass
class HarnessPlan:
    """Parsed harness-plan.md contents."""

    project_name: str
    project_type: str
    scale: str
    user_description_original: str
    profiles: list[ProfileRef]
    skeleton_sections: SkeletonSpec
    pipeline: Pipeline
    scale_axes: ScaleAxes = field(default_factory=ScaleAxes)
    verify_history: list[VerifyRecord] = field(default_factory=list)
    redesign_history: list[RedesignEntry] = field(default_factory=list)
    backups: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    last_activity: str = ""
    harness_version: int = 2
    schema_version: int = 1
    body: str = ""  # markdown body outside the frontmatter


# Exceptions


class PlanNotFoundError(FileNotFoundError):
    """harness-plan.md file does not exist."""


class InvalidStateTransitionError(ValueError):
    """Invalid state transition attempt (backward, skip, or unknown state)."""


class PlanSchemaError(ValueError):
    """harness-plan.md frontmatter schema violation."""


# Manager


class PlanManager:
    """Read/write harness-plan.md with state transition validation."""

    def load(self, path: Path) -> HarnessPlan:
        """Load harness-plan.md.

        Raises:
            PlanNotFoundError: File does not exist.
            PlanSchemaError: Frontmatter schema violation.
        """
        if not path.exists():
            raise PlanNotFoundError(f"harness-plan.md not found: {path}")

        text = path.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(text)
        if not m:
            raise PlanSchemaError(f"{path.name}: missing YAML frontmatter")
        try:
            data = yaml.safe_load(m.group(1))
        except yaml.YAMLError as exc:
            raise PlanSchemaError(f"{path.name}: YAML parse failed: {exc}") from exc
        if not isinstance(data, dict):
            raise PlanSchemaError(f"{path.name}: frontmatter must be a dict")

        body = text[m.end() :].lstrip()
        return _dict_to_plan(data, body)

    def save(self, plan: HarnessPlan, path: Path) -> None:
        """Serialize HarnessPlan to file (frontmatter + body).

        Mutates ``plan.updated_at`` / ``plan.last_activity`` only after the write
        succeeds — a failed disk write must not leave the in-memory plan with a
        phantom timestamp that disagrees with the file. Per CLAUDE.md rule 5,
        OSError is caught, logged, and re-raised so callers see a real failure.
        """
        prev_updated = plan.updated_at
        prev_activity = plan.last_activity
        plan.updated_at = _now_iso()
        plan.last_activity = plan.updated_at
        data = _plan_to_dict(plan)
        text = (
            "---\n"
            + yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
            + "---\n\n"
            + plan.body
        )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError:
            # Roll back the timestamp so the in-memory plan stays consistent
            # with whatever is still on disk.
            plan.updated_at = prev_updated
            plan.last_activity = prev_activity
            raise

    def create(
        self,
        *,
        project_name: str,
        project_type: str,
        scale: str,
        user_description_original: str,
        profiles: list[ProfileRef],
        skeleton_sections: SkeletonSpec,
        pipeline_steps: list[str],
        gstack_mode: str = "manual",
        scale_axes: ScaleAxes | None = None,
        body: str = "",
    ) -> HarnessPlan:
        """Create a new plan. Starts at current_step="init"."""
        if gstack_mode not in ALLOWED_GSTACK_MODES:
            raise PlanSchemaError(
                f"gstack_mode must be one of {sorted(ALLOWED_GSTACK_MODES)}, got '{gstack_mode}'"
            )
        if scale not in ALLOWED_USER_SCALES:
            raise PlanSchemaError(
                f"scale must be one of {sorted(ALLOWED_USER_SCALES)}, got '{scale}'"
            )

        now = _now_iso()
        return HarnessPlan(
            project_name=project_name,
            project_type=project_type,
            scale=scale,
            user_description_original=user_description_original,
            profiles=list(profiles),
            skeleton_sections=skeleton_sections,
            pipeline=Pipeline(
                steps=tuple(pipeline_steps),
                current_step="init",
                completed_steps=(),
                skipped_steps=(),
                gstack_mode=gstack_mode,
            ),
            scale_axes=scale_axes or ScaleAxes(),
            created_at=now,
            updated_at=now,
            last_activity=now,
            body=body,
        )

    def transition(
        self,
        plan: HarnessPlan,
        target_state: str,
        *,
        completed_step: str | None = None,
    ) -> HarnessPlan:
        """Transition current_step to target_state.

        Raises:
            InvalidStateTransitionError: Backward, skip, or unknown state.
        """
        if target_state not in STATE_ORDER:
            raise InvalidStateTransitionError(
                f"unknown state '{target_state}'. allowed: {STATE_ORDER}"
            )

        current_idx = STATE_ORDER.index(plan.pipeline.current_step)
        target_idx = STATE_ORDER.index(target_state)

        if target_idx == current_idx:
            # Same state (idempotent) — only append the new step if given
            pass
        elif target_idx < current_idx:
            raise InvalidStateTransitionError(
                f"cannot move backward: {plan.pipeline.current_step} -> {target_state}. "
                "use explicit backup() for rollback."
            )
        elif target_idx - current_idx > 1:
            # e.g. 'building' → 'verified' (skips 'built')
            raise InvalidStateTransitionError(
                f"cannot skip states: {plan.pipeline.current_step} -> {target_state}. "
                f"missing intermediate {STATE_ORDER[current_idx + 1 : target_idx]}."
            )

        completed = list(plan.pipeline.completed_steps)
        if completed_step and completed_step not in completed:
            completed.append(completed_step)

        plan.pipeline = Pipeline(
            steps=plan.pipeline.steps,
            current_step=target_state,
            completed_steps=tuple(completed),
            skipped_steps=plan.pipeline.skipped_steps,
            gstack_mode=plan.pipeline.gstack_mode,
        )
        plan.last_activity = _now_iso()
        return plan

    def regress(self, plan: HarnessPlan, target_state: str) -> HarnessPlan:
        """Regress current_step backward to target_state (explicit rollback).

        Unlike transition(), regress() is the sanctioned backward-movement path
        used by verify/review failure gates. Any backward jump to a known state
        is allowed — the caller is explicitly choosing the recovery point.

        Raises:
            InvalidStateTransitionError: target is unknown or not behind current.
        """
        if target_state not in STATE_ORDER:
            raise InvalidStateTransitionError(
                f"unknown state '{target_state}'. allowed: {STATE_ORDER}"
            )
        current_idx = STATE_ORDER.index(plan.pipeline.current_step)
        target_idx = STATE_ORDER.index(target_state)
        if target_idx >= current_idx:
            raise InvalidStateTransitionError(
                f"regress() requires a backward target: "
                f"'{plan.pipeline.current_step}' -> '{target_state}' is not backward."
            )
        plan.pipeline = Pipeline(
            steps=plan.pipeline.steps,
            current_step=target_state,
            completed_steps=plan.pipeline.completed_steps,
            skipped_steps=plan.pipeline.skipped_steps,
            gstack_mode=plan.pipeline.gstack_mode,
        )
        plan.last_activity = _now_iso()
        return plan

    def record_verify(
        self,
        plan: HarnessPlan,
        *,
        step: str,
        passed: bool,
        summary: str,
    ) -> HarnessPlan:
        """Append a verification result to verify_history."""
        plan.verify_history.append(
            VerifyRecord(step=step, at=_now_iso(), passed=passed, summary=summary)
        )
        plan.last_activity = _now_iso()
        return plan

    def record_redesign(
        self,
        plan: HarnessPlan,
        *,
        decision: str,
        rationale: str,
        affected_sections: tuple[str, ...] | list[str] = (),
        affected_tasks: tuple[str, ...] | list[str] = (),
        status: str = "proposed",
    ) -> HarnessPlan:
        """Append a redesign entry — used by /ha-redesign across its lifecycle.

        Typical flow:
            record_redesign(..., status="proposed")  # ha-redesign prepare
            record_redesign(..., status="approved")  # user accepts the diff
            record_redesign(..., status="applied")   # skeleton/tasks updated
        Each call appends a new entry rather than mutating prior ones, so the
        full audit trail is preserved (including rejected proposals).
        """
        plan.redesign_history.append(
            RedesignEntry(
                at=_now_iso(),
                decision=decision,
                rationale=rationale,
                affected_sections=tuple(affected_sections),
                affected_tasks=tuple(affected_tasks),
                status=status,
            )
        )
        plan.last_activity = _now_iso()
        return plan

    def mark_skipped(self, plan: HarnessPlan, step: str) -> HarnessPlan:
        """Add step to skipped_steps."""
        if step in plan.pipeline.skipped_steps:
            return plan
        plan.pipeline = Pipeline(
            steps=plan.pipeline.steps,
            current_step=plan.pipeline.current_step,
            completed_steps=plan.pipeline.completed_steps,
            skipped_steps=(*plan.pipeline.skipped_steps, step),
            gstack_mode=plan.pipeline.gstack_mode,
        )
        plan.last_activity = _now_iso()
        return plan

    def add_backup(
        self,
        plan: HarnessPlan,
        *,
        path: str,
        reason: str,
    ) -> HarnessPlan:
        """Record a rollback backup entry (actual file copy is caller's responsibility)."""
        plan.backups.append({"path": path, "at": _now_iso(), "reason": reason})
        plan.last_activity = _now_iso()
        return plan


# Serialization helpers


def _now_iso() -> str:
    """Current UTC time as ISO 8601 (microseconds truncated)."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _parse_redesign_history(raw: list[Any]) -> list[RedesignEntry]:
    """Parse redesign_history list. Audit trail integrity matters here so
    malformed entries raise PlanSchemaError instead of being silently dropped —
    a vanished proposal would defeat the whole purpose of the lifecycle log.
    """
    out: list[RedesignEntry] = []
    for i, r in enumerate(raw):
        if not isinstance(r, dict):
            raise PlanSchemaError(
                f"redesign_history[{i}] must be a mapping, got {type(r).__name__}"
            )
        if "decision" not in r:
            raise PlanSchemaError(
                f"redesign_history[{i}] missing required field 'decision'"
            )
        out.append(
            RedesignEntry(
                at=r.get("at", ""),
                decision=r["decision"],
                rationale=r.get("rationale", ""),
                affected_sections=tuple(r.get("affected_sections") or []),
                affected_tasks=tuple(r.get("affected_tasks") or []),
                status=r.get("status", "proposed"),
            )
        )
    return out


def _dict_to_plan(data: dict[str, Any], body: str) -> HarnessPlan:
    """Convert frontmatter dict to HarnessPlan."""
    try:
        pipeline_raw = data.get("pipeline") or {}
        skeleton_raw = data.get("skeleton_sections") or {}
        profiles_raw = data.get("profiles") or []
        verify_raw = data.get("verify_history") or []
        redesign_raw = data.get("redesign_history") or []
        scale_axes_raw = data.get("scale_axes") or {}

        return HarnessPlan(
            project_name=data["project_name"],
            project_type=data.get("project_type", ""),
            scale=data.get("scale", "small"),
            user_description_original=data.get("user_description_original", ""),
            profiles=[
                ProfileRef(
                    id=p["id"],
                    path=p.get("path", "."),
                    status=p.get("status", "confirmed"),
                )
                for p in profiles_raw
                if isinstance(p, dict) and "id" in p
            ],
            skeleton_sections=SkeletonSpec(
                required=tuple(skeleton_raw.get("required") or []),
                optional=tuple(skeleton_raw.get("optional") or []),
                included=tuple(skeleton_raw.get("included") or []),
            ),
            pipeline=Pipeline(
                steps=tuple(pipeline_raw.get("steps") or []),
                current_step=pipeline_raw.get("current_step", "init"),
                completed_steps=tuple(pipeline_raw.get("completed_steps") or []),
                skipped_steps=tuple(pipeline_raw.get("skipped_steps") or []),
                gstack_mode=pipeline_raw.get("gstack_mode", "manual"),
            ),
            scale_axes=ScaleAxes(
                user_scale=scale_axes_raw.get("user_scale", "small"),
                data_sensitivity=scale_axes_raw.get("data_sensitivity", "none"),
                team_size=scale_axes_raw.get("team_size", "solo"),
                availability=scale_axes_raw.get("availability", "standard"),
                monetization=scale_axes_raw.get("monetization", "none"),
                lifecycle=scale_axes_raw.get("lifecycle", "mvp"),
            ),
            verify_history=[
                VerifyRecord(
                    step=v["step"],
                    at=v.get("at", ""),
                    passed=bool(v.get("passed", False)),
                    summary=v.get("summary", ""),
                )
                for v in verify_raw
                if isinstance(v, dict) and "step" in v
            ],
            redesign_history=_parse_redesign_history(redesign_raw),
            backups=list(data.get("backups") or []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            last_activity=data.get("last_activity", ""),
            harness_version=int(data.get("harness_version", 2)),
            schema_version=int(data.get("schema_version", 1)),
            body=body,
        )
    except KeyError as exc:
        raise PlanSchemaError(f"missing required field: {exc}") from exc


def _plan_to_dict(plan: HarnessPlan) -> dict[str, Any]:
    """Convert HarnessPlan to frontmatter dict (preserves key order)."""
    return {
        "harness_version": plan.harness_version,
        "schema_version": plan.schema_version,
        "project_name": plan.project_name,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
        "project_type": plan.project_type,
        "scale": plan.scale,
        "scale_axes": {
            "user_scale": plan.scale_axes.user_scale,
            "data_sensitivity": plan.scale_axes.data_sensitivity,
            "team_size": plan.scale_axes.team_size,
            "availability": plan.scale_axes.availability,
            "monetization": plan.scale_axes.monetization,
            "lifecycle": plan.scale_axes.lifecycle,
        },
        "user_description_original": plan.user_description_original,
        "profiles": [{"id": p.id, "path": p.path, "status": p.status} for p in plan.profiles],
        "skeleton_sections": {
            "required": list(plan.skeleton_sections.required),
            "optional": list(plan.skeleton_sections.optional),
            "included": list(plan.skeleton_sections.included),
        },
        "pipeline": {
            "steps": list(plan.pipeline.steps),
            "current_step": plan.pipeline.current_step,
            "completed_steps": list(plan.pipeline.completed_steps),
            "skipped_steps": list(plan.pipeline.skipped_steps),
            "gstack_mode": plan.pipeline.gstack_mode,
        },
        "verify_history": [
            {"step": v.step, "at": v.at, "passed": v.passed, "summary": v.summary}
            for v in plan.verify_history
        ],
        "redesign_history": [
            {
                "at": r.at,
                "decision": r.decision,
                "rationale": r.rationale,
                "affected_sections": list(r.affected_sections),
                "affected_tasks": list(r.affected_tasks),
                "status": r.status,
            }
            for r in plan.redesign_history
        ],
        "backups": plan.backups,
        "last_activity": plan.last_activity,
    }
