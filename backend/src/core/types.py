from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ===== Enums =====

class TaskStatus(str, Enum):
    BACKLOG = "backlog"
    READY = "ready"
    IN_PROGRESS = "in-progress"
    REVIEW = "review"
    FAILED = "failed"
    DONE = "done"


class TaskComplexity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AgentLevel(int, Enum):
    DIRECTOR = 0
    MANAGER = 1
    WORKER = 2


class AgentStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    PAUSED = "paused"
    ERROR = "error"


class BoardColumn(str, Enum):
    BACKLOG = "Backlog"
    READY = "Ready"
    IN_PROGRESS = "In Progress"
    REVIEW = "Review"
    FAILED = "Failed"
    DONE = "Done"


class FollowUpType(str, Enum):
    COMMIT = "commit"
    API_HOOK = "api-hook"
    TEST = "test"
    DOCS = "docs"
    REVIEW = "review"


class FileAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class HookEvent(str, Enum):
    TASK_COMPLETED = "hook.task.completed"
    TASK_FAILED = "hook.task.failed"
    AGENT_ERROR = "hook.agent.error"
    EPIC_COMPLETED = "hook.epic.completed"


# ===== Message Types =====

class MessageType:
    BOARD_MOVE = "board.move"
    BOARD_REMOVE = "board.remove"
    REVIEW_REQUEST = "review.request"
    REVIEW_FEEDBACK = "review.feedback"
    EPIC_PROGRESS = "epic.progress"
    AGENT_STATUS = "agent.status"
    TOKEN_USAGE = "token.usage"
    USER_INPUT = "user.input"
    SYSTEM_COMMAND = "system.command"
    AGENT_CONFIG_UPDATED = "agent.config.updated"


# ===== Domain Models =====

class Task(BaseModel):
    id: str
    epic_id: str | None = None
    title: str
    description: str = ""
    assigned_agent: str | None = None
    status: TaskStatus = TaskStatus.BACKLOG
    github_issue_number: int | None = None
    board_column: str = "Backlog"
    dependencies: list[str] = Field(default_factory=list)
    priority: int = 3  # 1(highest) ~ 5(lowest)
    complexity: TaskComplexity = TaskComplexity.MEDIUM
    retry_count: int = 0
    artifacts: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    review_note: str | None = None


class TaskResult(BaseModel):
    success: bool
    data: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    artifacts: list[str] = Field(default_factory=list)


class Message(BaseModel):
    id: str
    type: str
    from_agent: str
    to_agent: str | None = None
    payload: Any = None
    trace_id: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BoardIssue(BaseModel):
    issue_number: int
    title: str
    body: str
    labels: list[str] = Field(default_factory=list)
    column: str
    dependencies: list[int] = Field(default_factory=list)
    assignee: str | None = None
    generated_by: str = ""
    epic_id: str | None = None


class FollowUp(BaseModel):
    title: str
    target_agent: str
    type: FollowUpType
    description: str
    dependencies: list[int] = Field(default_factory=list)
    additional_context: str | None = None


class GeneratedFile(BaseModel):
    path: str
    content: str
    action: FileAction
    language: str


class GeneratedCode(BaseModel):
    files: list[GeneratedFile]
    summary: str


class IssueSpec(BaseModel):
    title: str
    body: str
    labels: list[str] = Field(default_factory=list)
    milestone: int | None = None
    dependencies: list[int] = Field(default_factory=list)


# ===== Agent Config =====

class AgentConfig(BaseModel):
    id: str
    domain: str
    level: AgentLevel = AgentLevel.WORKER
    claude_model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    temperature: float = 0.7
    token_budget: int = 10_000_000
    task_timeout_ms: int = 300_000
    poll_interval_ms: int = 10_000


# ===== Stats & History =====

class AgentStats(BaseModel):
    agent_id: str
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    in_progress_tasks: int = 0
    completion_rate: float = 0.0
    avg_duration_ms: float | None = None
    total_retries: int = 0


class TaskHistoryEntry(BaseModel):
    timestamp: datetime
    type: str
    from_agent: str
    detail: str


# ===== Config Row (DB) =====

class AgentConfigRow(BaseModel):
    agent_id: str
    claude_model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    temperature: float = 0.7
    token_budget: int = 10_000_000
    task_timeout_ms: int = 300_000
    poll_interval_ms: int = 10_000
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HookRow(BaseModel):
    id: str
    event: str
    name: str
    description: str | None = None
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ===== User Input =====

class UserInput(BaseModel):
    source: Literal["cli", "dashboard"]
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ===== API Spec =====

class TypeDefinition(BaseModel):
    type: str
    example: Any = None


class ApiSpec(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    request: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)
    auth: Literal["none", "bearer", "api-key"] = "none"
    description: str = ""
