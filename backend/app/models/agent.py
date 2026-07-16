"""Agent run and step models.

Tracks each AI itinerary-generation run against a trip and the individual
steps within it. Statuses and step names are Python enums stored as ``String``
columns (no native Postgres enum types), matching the Sprint 1 convention.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.tool_call import ToolCall
    from app.models.trip import Trip


class AgentRunStatus(str, Enum):
    """Lifecycle of an agent run (and of an individual step)."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentStepName(str, Enum):
    """Named steps within an itinerary-generation run."""

    LOAD_TRIP_PREFERENCES = "load_trip_preferences"
    BUILD_PROMPT = "build_prompt"
    CALL_LLM = "call_llm"
    PARSE_RESPONSE = "parse_response"
    RESOLVE_PLACES = "resolve_places"
    RESOLVE_PRICES = "resolve_prices"
    OPTIMIZE_ROUTE = "optimize_route"
    SAVE_ITINERARY = "save_itinerary"


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )

    status: Mapped[AgentRunStatus] = mapped_column(
        String(20), default=AgentRunStatus.PENDING
    )
    model_used: Mapped[str | None] = mapped_column(String(100), default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trip: Mapped["Trip"] = relationship(back_populates="agent_runs")  # noqa: F821
    steps: Mapped[list["AgentStep"]] = relationship(
        back_populates="agent_run",
        cascade="all, delete-orphan",
        order_by="AgentStep.created_at",
    )
    tool_calls: Mapped[list["ToolCall"]] = relationship(  # noqa: F821
        back_populates="agent_run",
        cascade="all, delete-orphan",
        order_by="ToolCall.created_at",
    )


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )

    step_name: Mapped[AgentStepName] = mapped_column(String(50))
    status: Mapped[AgentRunStatus] = mapped_column(String(20))
    input_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    output_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    latency_ms: Mapped[int | None] = mapped_column(Integer, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    agent_run: Mapped["AgentRun"] = relationship(back_populates="steps")
