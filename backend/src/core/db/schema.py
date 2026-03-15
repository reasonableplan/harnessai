from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AgentModel(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    status: Mapped[str] = mapped_column(String, nullable=False, default="idle")
    parent_id: Mapped[str | None] = mapped_column(String, ForeignKey("agents.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tasks: Mapped[list["TaskModel"]] = relationship("TaskModel", back_populates="agent", lazy="noload")
    config: Mapped["AgentConfigModel | None"] = relationship("AgentConfigModel", back_populates="agent", lazy="noload", uselist=False)


class EpicModel(Base):
    __tablename__ = "epics"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    github_milestone_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tasks: Mapped[list["TaskModel"]] = relationship("TaskModel", back_populates="epic", lazy="noload")


class TaskModel(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("idx_tasks_board_column", "board_column"),
        Index("idx_tasks_assigned_agent", "assigned_agent"),
        Index("idx_tasks_epic_id", "epic_id"),
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_github_issue", "github_issue_number"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    epic_id: Mapped[str | None] = mapped_column(String, ForeignKey("epics.id"), nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_agent: Mapped[str | None] = mapped_column(String, ForeignKey("agents.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="backlog")
    github_issue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    board_column: Mapped[str] = mapped_column(String, nullable=False, default="Backlog")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    complexity: Mapped[str | None] = mapped_column(String, nullable=True, default="medium")
    dependencies: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    labels: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    epic: Mapped["EpicModel | None"] = relationship("EpicModel", back_populates="tasks", lazy="noload")
    agent: Mapped["AgentModel | None"] = relationship("AgentModel", back_populates="tasks", lazy="noload")
    artifacts: Mapped[list["ArtifactModel"]] = relationship("ArtifactModel", back_populates="task", lazy="noload")


class MessageModel(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("idx_messages_type", "type"),
        Index("idx_messages_trace_id", "trace_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    from_agent: Mapped[str] = mapped_column(String, nullable=False)
    to_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    acked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentConfigModel(Base):
    __tablename__ = "agent_config"

    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id"), primary_key=True)
    claude_model: Mapped[str] = mapped_column(String, nullable=False, default="claude-sonnet-4-20250514")
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    token_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=10_000_000)
    task_timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=300_000)
    poll_interval_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=10_000)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    agent: Mapped["AgentModel"] = relationship("AgentModel", back_populates="config", lazy="noload")


class HookModel(Base):
    __tablename__ = "hooks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    event: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())


class ArtifactModel(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, ForeignKey("tasks.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("agents.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    task: Mapped["TaskModel"] = relationship("TaskModel", back_populates="artifacts", lazy="noload")
