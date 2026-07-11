"""ToolCall API schema (read-only)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.agent import AgentRunStatus


class ToolCallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_run_id: int
    tool_name: str
    status: AgentRunStatus
    input_json: dict | None = None
    output_json: dict | None = None
    error_message: str | None = None
    latency_ms: int | None = None
    cache_hit: bool
    created_at: datetime
