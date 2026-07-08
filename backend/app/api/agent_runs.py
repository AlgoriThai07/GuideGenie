"""Agent run read endpoints (Sprint 2, read-only)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models.agent import AgentRun, AgentStep
from app.models.tool_call import ToolCall
from app.schemas.agent import AgentRunRead, AgentStepRead
from app.schemas.tool_call import ToolCallRead

router = APIRouter(prefix="/api/agent-runs", tags=["agent-runs"])


def _get_run_or_404(session: Session, run_id: int) -> AgentRun:
    """Fetch an agent run by id or raise 404."""
    run = session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent run {run_id} not found",
        )
    return run


@router.get("/{run_id}", response_model=AgentRunRead)
def get_agent_run(
    run_id: int, session: Session = Depends(get_session)
) -> AgentRun:
    """Fetch a single agent run by id."""
    return _get_run_or_404(session, run_id)


@router.get("/{run_id}/steps", response_model=list[AgentStepRead])
def get_agent_run_steps(
    run_id: int, session: Session = Depends(get_session)
) -> list[AgentStep]:
    """Return the run's steps ordered by created_at. Empty list if none."""
    _get_run_or_404(session, run_id)
    stmt = (
        select(AgentStep)
        .where(AgentStep.agent_run_id == run_id)
        .order_by(AgentStep.created_at)
    )
    return list(session.scalars(stmt).all())


@router.get("/{run_id}/tool-calls", response_model=list[ToolCallRead])
def get_agent_run_tool_calls(
    run_id: int, session: Session = Depends(get_session)
) -> list[ToolCall]:
    """Return the run's tool calls ordered by created_at. Empty list if none."""
    _get_run_or_404(session, run_id)
    stmt = (
        select(ToolCall)
        .where(ToolCall.agent_run_id == run_id)
        .order_by(ToolCall.created_at)
    )
    return list(session.scalars(stmt).all())
