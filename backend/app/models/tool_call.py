"""ToolCall model.

Logs every external tool invocation (e.g. Google Places lookups) made during
an agent run, mirroring the AgentStep logging pattern in ``app.models.agent``.
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.agent import AgentRunStatus


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )

    tool_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[AgentRunStatus] = mapped_column(String(20))
    input_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    output_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    latency_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    agent_run: Mapped["AgentRun"] = relationship(back_populates="tool_calls")  # noqa: F821
