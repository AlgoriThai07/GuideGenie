"""Agent run and step API schemas.

Read-only response bodies. ``AgentRunRead`` intentionally excludes nested
steps — steps are fetched via a separate endpoint, so the run schema only
carries its own fields.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.agent import AgentRunStatus, AgentStepName


class AgentStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_run_id: int
    step_name: AgentStepName
    status: AgentRunStatus
    input_json: dict | None = None
    output_json: dict | None = None
    error_message: str | None = None
    latency_ms: int | None = None
    created_at: datetime


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    status: AgentRunStatus
    model_used: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
