"""Agent capability matching — task → agent routing infrastructure.

Group 3 Step 1: pure matching logic, no ha-plan/run.py integration yet (Step 2).

Rules
-----
- Capability-agnostic agent (requires_capabilities=[], requires_profile_ids=[]):
  matches any task regardless of capabilities/profiles.
- Specific agent: ALL of requires_profile_ids must be in active_profile_ids,
  AND at least ONE of requires_capabilities must be in active_has_keys.
  If the task also specifies required_capabilities (non-empty), at least ONE of
  those must overlap with agent.requires_capabilities.
- find_best_agent_for_task returns the most specific match (highest
  len(caps)+len(profiles)). Agnostic agents lose to any specific match.
  Tie-break: alphabetical agent_id for determinism.
- Returns None when no agent matches — caller surfaces a violation.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.orchestrator.config import AgentConfig


@dataclass(frozen=True)
class AgentMatchResult:
    """Match status between a task's required capability set and an agent."""

    agent_id: str
    is_match: bool
    reason: str  # short rationale for logging / violation reporting


def match_task_to_agent(
    task_required_capabilities: frozenset[str],
    task_required_profile_ids: frozenset[str],
    agent_config: AgentConfig,
    active_has_keys: frozenset[str],
    active_profile_ids: frozenset[str],
    *,
    agent_id: str = "",
) -> AgentMatchResult:
    """Decide whether *agent_config* can handle a task.

    Parameters
    ----------
    task_required_capabilities:
        has.* atoms the task needs — may be empty (caller did not specify).
    task_required_profile_ids:
        Profile IDs the task requires — may be empty.
    agent_config:
        The candidate agent.
    active_has_keys:
        has.* atoms computed from active profiles + axes (compute_has_keys).
    active_profile_ids:
        IDs of profiles currently active in the plan.
    agent_id:
        Human-readable label for the AgentMatchResult (optional).
    """
    agent_caps = frozenset(agent_config.requires_capabilities)
    agent_profiles = frozenset(agent_config.requires_profile_ids)

    # Capability-agnostic agents always match.
    if not agent_caps and not agent_profiles:
        return AgentMatchResult(
            agent_id=agent_id,
            is_match=True,
            reason="capability-agnostic",
        )

    # Profile gate: all agent-required profiles must be active.
    missing_profiles = agent_profiles - active_profile_ids
    if missing_profiles:
        return AgentMatchResult(
            agent_id=agent_id,
            is_match=False,
            reason=f"missing required profiles: {sorted(missing_profiles)}",
        )

    # Capability gate: at least one agent capability must be in active has_keys.
    overlapping_caps = agent_caps & active_has_keys
    if not overlapping_caps:
        return AgentMatchResult(
            agent_id=agent_id,
            is_match=False,
            reason="no required capability active in current profile set",
        )

    # Task-side capability gate: if the task specifies required_capabilities,
    # at least one must overlap with the agent's declared capabilities.
    if task_required_capabilities:
        task_agent_overlap = task_required_capabilities & agent_caps
        if not task_agent_overlap:
            return AgentMatchResult(
                agent_id=agent_id,
                is_match=False,
                reason=(
                    f"task needs {sorted(task_required_capabilities)}, "
                    f"agent provides {sorted(agent_caps)} — no overlap"
                ),
            )

    matched_on = sorted(overlapping_caps)
    return AgentMatchResult(
        agent_id=agent_id,
        is_match=True,
        reason=f"matches {matched_on}",
    )


def _specificity(config: AgentConfig) -> int:
    """Higher = more specific.  Agnostic agents score 0."""
    return len(config.requires_capabilities) + len(config.requires_profile_ids)


def find_best_agent_for_task(
    task_required_capabilities: frozenset[str],
    task_required_profile_ids: frozenset[str],
    available_agents: dict[str, AgentConfig],
    active_has_keys: frozenset[str],
    active_profile_ids: frozenset[str],
) -> str | None:
    """Return the agent_id of the best matching agent, or None.

    Specificity = len(requires_capabilities) + len(requires_profile_ids).
    More specific wins over capability-agnostic. Ties broken alphabetically.
    """
    candidates: list[tuple[int, str]] = []  # (specificity, agent_id)

    for agent_id, config in available_agents.items():
        result = match_task_to_agent(
            task_required_capabilities=task_required_capabilities,
            task_required_profile_ids=task_required_profile_ids,
            agent_config=config,
            active_has_keys=active_has_keys,
            active_profile_ids=active_profile_ids,
            agent_id=agent_id,
        )
        if result.is_match:
            candidates.append((_specificity(config), agent_id))

    if not candidates:
        return None

    # Sort: descending specificity, then ascending agent_id (alphabetical tie-break).
    candidates.sort(key=lambda t: (-t[0], t[1]))
    return candidates[0][1]
