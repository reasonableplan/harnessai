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

# Task status produced by redesign propagation — distinct from ha-build statuses
# (done | blocked | in-progress) so that ha-verify / ha-build --skip-done cannot
# silently pass stale code. Only mark_for_rebuild() may set this value; general
# task status updates go through ha-build complete.
TASK_STATUS_NEEDS_REBUILD = "needs_rebuild"

# Eng-review audit trail — captures external engineering review events (e.g. /plan-eng-review).
# Distinct from redesign_history (purpose: mutation propagation) — eng_review_history records
# what an external review tool examined and changed, without driving a redesign lifecycle.
ALLOWED_ENG_REVIEW_SCOPES = {"tasks", "skeleton", "both"}

# HITL freeze lifecycle — /ha-design completion gate.
#   drafting: /ha-design 채움 진행 중. frontmatter 에서 생략 (legacy backward-compat).
#   frozen:   /ha-build 진입 허용. HITL-required sections 모두 확인 완료.
ALLOWED_FROZEN_STATUS = {"drafting", "frozen"}

# Sections that require a human-in-the-loop interview before /ha-build. A plan
# only needs the frozen gate when at least one of these is active — CLI tools,
# libraries, and other projects without persona/screen sections have nothing to
# freeze, so the gate is a vacuous pass for them (see requires_hitl_freeze).
# Single source of truth: /ha-design, /ha-build, and pipeline_advisor all read this.
HITL_LOCKABLE_SECTIONS: frozenset[str] = frozenset({"requirements", "user_journey", "view.screens"})


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
class EngReviewEntry:
    """A single external engineering review event (e.g. /plan-eng-review).

    Captures *what was reviewed* + *what changed* + *who/when* so that
    skeleton.md / tasks.md mutations performed by external tools have an
    audit trail in the plan frontmatter. The plan body remains the
    source of truth for content; this entry is metadata only.
    """

    at: str  # ISO 8601 UTC
    reviewer: str  # tool/agent label (e.g. "plan-eng-review", "manual")
    scope: str  # one of ALLOWED_ENG_REVIEW_SCOPES
    summary: str  # one-line human-readable summary
    affected_sections: tuple[str, ...]  # skeleton section IDs (e.g. "§13") or fragment IDs
    affected_tasks: tuple[str, ...]  # task IDs (e.g. "T-024")

    def __post_init__(self) -> None:
        if self.scope not in ALLOWED_ENG_REVIEW_SCOPES:
            raise PlanSchemaError(
                f"eng_review scope must be one of {sorted(ALLOWED_ENG_REVIEW_SCOPES)}, "
                f"got '{self.scope}'"
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
    # eng_review_history: audit trail for external engineering review events (e.g. /plan-eng-review).
    # Records what a review tool examined and changed in skeleton.md / tasks.md — distinct from
    # redesign_history (ha-redesign mutation propagation lifecycle). Empty list = no external
    # reviews recorded (legacy or fresh plan). Omitted from frontmatter when empty (backward-compat).
    eng_review_history: list[EngReviewEntry] = field(default_factory=list)
    backups: list[dict[str, Any]] = field(default_factory=list)
    # activation_trace: {section_id: required_when_expression} — why each section
    # was activated. Empty dict when --included override was used (no auto-derivation).
    # Omitted from frontmatter when empty (backward-compatible with legacy plans).
    activation_trace: dict[str, str] = field(default_factory=dict)
    # SHA-256 hash of skeleton.md as of the last ha-design commit (or
    # ha-redesign apply). Used by downstream skills to detect external
    # modifications (e.g., /plan-eng-review writing to skeleton.md without
    # /ha-redesign audit). Empty string for legacy plans (no comparison).
    # Omitted from frontmatter when empty (backward-compatible with legacy plans).
    skeleton_hash: str = ""
    # Per-section SHA-256 snapshot {section_id: hash}, written at the same
    # moments as skeleton_hash (ha-design commit / ha-redesign apply). Lets
    # ha-redesign diff sections and derive stale done-tasks deterministically.
    # Empty dict for legacy plans; omitted from frontmatter when empty.
    section_hashes: dict[str, str] = field(default_factory=dict)
    # external_capabilities: user-declared has.* atoms provided by external services
    # (e.g. Firebase / Supabase / managed backend) that are NOT covered by any
    # profile in the active profile set.  compute_has_keys() unions these in so
    # fragment required_when evaluation and find_consistency_violations() treat them
    # as satisfied — preventing false-positive violation reports for BaaS cases.
    # Empty list = no external services declared (default).
    # Omitted from frontmatter when empty (legacy backward-compat).
    # Values must be members of KNOWN_CAPABILITY_ATOMS; validated at the CLI layer
    # (ha-init write --external-capabilities) before being written here.
    external_capabilities: list[str] = field(default_factory=list)
    # === Optional fields below — must come BEFORE created_at/updated_at/last_activity. ===
    # _plan_to_dict 의 omitted-when-empty 패턴이 이 순서를 가정한다 (frontmatter 직렬화
    # 시 timestamps 가 항상 마지막 그룹으로 묶이도록). 새 optional 필드는 여기에 추가.
    #
    # HITL freeze 상태 (v0.10.0). drafting → /ha-design 채움 진행 / frozen → /ha-build 진입 허용.
    # frozen_status="drafting" 이면 frontmatter 에서 생략 (legacy backward-compat).
    frozen_status: str = "drafting"
    # frozen_at: frozen 진입 시점 ISO 8601 UTC. drafting 상태면 빈 문자열.
    # 빈 문자열이면 frontmatter 에서 생략.
    frozen_at: str = ""
    # locked_sections: HITL gate 적용된 섹션 ID 목록 (e.g. ["requirements", "user_journey", "view.screens"]).
    # 빈 리스트면 frontmatter 에서 생략.
    locked_sections: list[str] = field(default_factory=list)
    # ai_drafted_sections: 사용자가 인터뷰 회피 시 --ai-draft 옵트인으로 AI 가 채운 섹션.
    # 사용자 promotion (검토 + 승인) 전까지 추적. 빈 리스트면 frontmatter 에서 생략.
    ai_drafted_sections: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    last_activity: str = ""
    harness_version: int = 2
    schema_version: int = 1
    body: str = ""  # markdown body outside the frontmatter


def requires_hitl_freeze(plan: HarnessPlan) -> bool:
    """Whether this plan must pass the HITL freeze gate before /ha-build.

    True iff at least one HITL-lockable section (persona/requirements/screens)
    is active. Projects without any of them — CLI tools, libraries, batch jobs —
    have nothing to interview-lock, so the frozen gate is a vacuous pass and
    /ha-build proceeds directly (prevents the designed→design driver loop).
    """
    return bool(set(plan.skeleton_sections.included) & HITL_LOCKABLE_SECTIONS)


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
        activation_trace: dict[str, str] | None = None,
        external_capabilities: list[str] | None = None,
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
            activation_trace=dict(activation_trace) if activation_trace else {},
            external_capabilities=list(external_capabilities) if external_capabilities else [],
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

    def record_eng_review(
        self,
        plan: HarnessPlan,
        *,
        reviewer: str,
        scope: str,
        summary: str,
        affected_sections: tuple[str, ...] | list[str] = (),
        affected_tasks: tuple[str, ...] | list[str] = (),
    ) -> HarnessPlan:
        """Append an eng-review entry — used by /plan-eng-review and similar tools.

        Each call appends a new entry preserving the full audit trail. Entries are
        never mutated or removed after creation (audit trail integrity).
        """
        plan.eng_review_history.append(
            EngReviewEntry(
                at=_now_iso(),
                reviewer=reviewer,
                scope=scope,
                summary=summary,
                affected_sections=tuple(affected_sections),
                affected_tasks=tuple(affected_tasks),
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

    def mark_for_rebuild(
        self,
        tasks_path: Path,
        task_ids: list[str],
    ) -> list[str]:
        """Rewrite status of done tasks to needs_rebuild in tasks.md.

        Called exclusively by ha-redesign commit --status applied when affected_tasks
        contain tasks whose status is already "done". This prevents ha-verify /
        ha-build --skip-done from silently validating stale code.

        Only tasks with status "done" (case-insensitive, including "완료"/"completed")
        are transitioned; tasks with any other status are left unchanged. This is an
        intentional special path — mark_for_rebuild() is the only caller that may set
        TASK_STATUS_NEEDS_REBUILD on a task. General status updates go through
        ha-build complete.

        Args:
            tasks_path: Absolute path to tasks.md.
            task_ids: Task IDs to inspect and potentially rewrite.

        Returns:
            List of task IDs that were actually transitioned (status was "done").

        Raises:
            OSError: tasks_path read or write failed.
        """
        text = tasks_path.read_text(encoding="utf-8")
        transitioned: list[str] = []

        for task_id in task_ids:
            # Locate the row and extract the current status column (5th pipe segment).
            # Pattern mirrors ha-build/run.py cmd_complete for consistency.
            # Note: regex is compiled per iteration because task_id is interpolated
            # into the pattern; task_ids is typically small (≤ tens) so the cost
            # is negligible. lru_cache 도 가능하지만 함수 호출 빈도가 낮아 over-engineering.
            row_re = re.compile(
                rf"(\|\s*{re.escape(task_id)}\s*\|.*?\|.*?\|.*?\|\s*)([^|]+)(\|\s*$)",
                re.MULTILINE,
            )
            m = row_re.search(text)
            if m is None:
                # Task ID not found — caller already validated existence; skip silently.
                continue
            current_status = m.group(2).strip().lower()
            if current_status in ("done", "완료", "completed"):
                text = row_re.sub(
                    lambda match: (
                        f"{match.group(1)}{TASK_STATUS_NEEDS_REBUILD:<10}{match.group(3)}"
                    ),
                    text,
                    count=1,
                )
                transitioned.append(task_id)

        if transitioned:
            tasks_path.write_text(text, encoding="utf-8")

        return transitioned

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

    def freeze(
        self,
        plan: HarnessPlan,
        *,
        locked_sections: list[str],
        ai_drafted_sections: list[str] | None = None,
    ) -> HarnessPlan:
        """Transition plan to frozen status — /ha-design completion gate.

        Sets frozen_status="frozen" + frozen_at=now + locked_sections.
        Called by /ha-design after user confirms all HITL-required sections are filled.
        Idempotent — freezing an already-frozen plan updates locked_sections + frozen_at.
        No unfreeze() — frozen is a one-way gate by design (any rollback goes through
        /ha-redesign which records an audit entry, not a silent state revert).

        Args:
            plan: HarnessPlan to transition.
            locked_sections: Section IDs to lock (HITL gate). Must be non-empty.
            ai_drafted_sections: Optional. None = preserve existing list (re-freeze with
                no draft change). [] = explicitly clear (e.g. user promoted all drafts to
                reviewed). list = replace.

        Returns:
            Mutated plan (also mutates in place).

        Raises:
            PlanSchemaError: locked_sections is empty (no point freezing nothing).
        """
        if not locked_sections:
            raise PlanSchemaError("freeze() requires at least one locked section")
        plan.frozen_status = "frozen"
        plan.frozen_at = _now_iso()
        plan.locked_sections = list(locked_sections)
        # Distinguish None (preserve) from [] (clear) — clearing is the path for
        # post-promotion: user reviewed an --ai-draft section and approved it, so it
        # should leave ai_drafted_sections.
        if ai_drafted_sections is not None:
            plan.ai_drafted_sections = list(ai_drafted_sections)
        plan.last_activity = plan.frozen_at
        return plan


# Serialization helpers


def _now_iso() -> str:
    """Current UTC time as ISO 8601 (microseconds truncated)."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _parse_eng_review_history(raw: list[Any]) -> list[EngReviewEntry]:
    """Parse eng_review_history list. Audit trail integrity matters here so
    malformed entries raise PlanSchemaError instead of being silently dropped —
    a vanished review entry would defeat the purpose of the audit trail.
    """
    out: list[EngReviewEntry] = []
    for i, r in enumerate(raw):
        if not isinstance(r, dict):
            raise PlanSchemaError(
                f"eng_review_history[{i}] must be a mapping, got {type(r).__name__}"
            )
        if "summary" not in r:
            raise PlanSchemaError(f"eng_review_history[{i}] missing required field 'summary'")
        out.append(
            EngReviewEntry(
                at=r.get("at", ""),
                reviewer=r.get("reviewer", ""),
                scope=r.get("scope", "tasks"),
                summary=r["summary"],
                affected_sections=tuple(r.get("affected_sections") or []),
                affected_tasks=tuple(r.get("affected_tasks") or []),
            )
        )
    return out


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
            raise PlanSchemaError(f"redesign_history[{i}] missing required field 'decision'")
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
        eng_review_raw = data.get("eng_review_history") or []
        scale_axes_raw = data.get("scale_axes") or {}
        # activation_trace: legacy plans without this key load as empty dict (backward-compat).
        activation_trace_raw = data.get("activation_trace") or {}
        activation_trace = (
            {str(k): str(v) for k, v in activation_trace_raw.items()}
            if isinstance(activation_trace_raw, dict)
            else {}
        )
        # skeleton_hash: legacy plans without this key load as empty string (backward-compat).
        skeleton_hash = str(data.get("skeleton_hash") or "")
        # section_hashes: legacy plans without this key load as empty dict (backward-compat).
        section_hashes_raw = data.get("section_hashes") or {}
        section_hashes = (
            {str(k): str(v) for k, v in section_hashes_raw.items()}
            if isinstance(section_hashes_raw, dict)
            else {}
        )
        # external_capabilities: legacy plans without this key load as empty list (backward-compat).
        external_caps_raw = data.get("external_capabilities") or []
        external_capabilities = (
            [str(c) for c in external_caps_raw] if isinstance(external_caps_raw, list) else []
        )
        # frozen_status: legacy plans without this key load as "drafting" (backward-compat).
        frozen_status = str(data.get("frozen_status") or "drafting")
        if frozen_status not in ALLOWED_FROZEN_STATUS:
            raise PlanSchemaError(
                f"frozen_status must be one of {sorted(ALLOWED_FROZEN_STATUS)}, got '{frozen_status}'"
            )
        # frozen_at: legacy plans without this key load as "" (backward-compat).
        frozen_at = str(data.get("frozen_at") or "")
        # locked_sections: legacy plans without this key load as [] (backward-compat).
        locked_raw = data.get("locked_sections") or []
        locked_sections = [str(s) for s in locked_raw] if isinstance(locked_raw, list) else []
        # ai_drafted_sections: legacy plans without this key load as [] (backward-compat).
        ai_drafted_raw = data.get("ai_drafted_sections") or []
        ai_drafted_sections = (
            [str(s) for s in ai_drafted_raw] if isinstance(ai_drafted_raw, list) else []
        )

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
            eng_review_history=_parse_eng_review_history(eng_review_raw),
            backups=list(data.get("backups") or []),
            activation_trace=activation_trace,
            skeleton_hash=skeleton_hash,
            section_hashes=section_hashes,
            external_capabilities=external_capabilities,
            frozen_status=frozen_status,
            frozen_at=frozen_at,
            locked_sections=locked_sections,
            ai_drafted_sections=ai_drafted_sections,
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
    d: dict[str, Any] = {
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
    # eng_review_history: only written when non-empty — omitting it keeps legacy plans
    # clean and avoids a meaningless empty list in frontmatter.
    if plan.eng_review_history:
        d["eng_review_history"] = [
            {
                "at": e.at,
                "reviewer": e.reviewer,
                "scope": e.scope,
                "summary": e.summary,
                "affected_sections": list(e.affected_sections),
                "affected_tasks": list(e.affected_tasks),
            }
            for e in plan.eng_review_history
        ]
    # activation_trace: only written when non-empty — omitting it keeps legacy plans
    # clean and avoids a meaningless empty mapping in frontmatter.
    # Keys are sorted for deterministic output (regression-test stability).
    if plan.activation_trace:
        d["activation_trace"] = dict(sorted(plan.activation_trace.items()))
    # skeleton_hash: only written when non-empty — omitting it keeps legacy plans
    # clean. Set by ha-design commit and ha-redesign apply; empty for fresh plans.
    if plan.skeleton_hash:
        d["skeleton_hash"] = plan.skeleton_hash
    # section_hashes: only written when non-empty. Keys sorted for deterministic
    # output (regression-test stability), same as activation_trace.
    if plan.section_hashes:
        d["section_hashes"] = dict(sorted(plan.section_hashes.items()))
    # external_capabilities: only written when non-empty — omitting it keeps legacy
    # plans clean. Values are sorted for deterministic output (regression-test stability).
    if plan.external_capabilities:
        d["external_capabilities"] = sorted(plan.external_capabilities)
    # frozen_status: "drafting" default 면 frontmatter 생략 (legacy 호환).
    # frozen 인 경우만 박음. 직접 plan.frozen_status = "..." 로 corruption 했을
    # 때 한 save/load 사이클이 지나서야 _dict_to_plan 이 잡으므로, 직렬화 시점에
    # 한 번 더 검증해서 corruption 이 디스크에 못 쓰이게 차단.
    if plan.frozen_status not in ALLOWED_FROZEN_STATUS:
        raise PlanSchemaError(
            f"frozen_status must be one of {sorted(ALLOWED_FROZEN_STATUS)}, "
            f"got '{plan.frozen_status}'"
        )
    if plan.frozen_status != "drafting":
        d["frozen_status"] = plan.frozen_status
    # frozen_at: 빈 문자열이면 생략.
    if plan.frozen_at:
        d["frozen_at"] = plan.frozen_at
    # locked_sections: 빈 리스트면 생략. 정렬해서 deterministic 출력.
    if plan.locked_sections:
        d["locked_sections"] = sorted(plan.locked_sections)
    # ai_drafted_sections: 빈 리스트면 생략. 정렬해서 deterministic 출력.
    if plan.ai_drafted_sections:
        d["ai_drafted_sections"] = sorted(plan.ai_drafted_sections)
    return d
