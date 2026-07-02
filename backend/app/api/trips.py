"""Trip CRUD endpoints.

Sprint 1: no authentication. Every trip is owned by the seeded default user
(``DEFAULT_USER_ID``). A trip may carry one inline ``TripPreference`` supplied
on create or update.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models.agent import AgentRun, AgentRunStatus
from app.models.itinerary import ItineraryDay
from app.models.trip import Trip, TripPreference
from app.models.user import DEFAULT_USER_ID
from app.schemas.agent import AgentRunRead
from app.schemas.itinerary import ItineraryDayRead
from app.schemas.trip import TripCreate, TripRead, TripUpdate
from app.services.ai_itinerary_service import TripNotFoundError, generate_itinerary

router = APIRouter(prefix="/api/trips", tags=["trips"])


def _get_trip_or_404(session: Session, trip_id: int) -> Trip:
    """Fetch a trip by id or raise 404."""
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip {trip_id} not found",
        )
    return trip


@router.post("", response_model=TripRead, status_code=status.HTTP_201_CREATED)
def create_trip(
    payload: TripCreate, session: Session = Depends(get_session)
) -> Trip:
    """Create a trip (owned by the default user) and its optional preference."""
    data = payload.model_dump(exclude={"preference"})
    trip = Trip(user_id=DEFAULT_USER_ID, **data)

    if payload.preference is not None:
        trip.preference = TripPreference(**payload.preference.model_dump())

    session.add(trip)
    session.commit()
    session.refresh(trip)
    return trip


@router.get("", response_model=list[TripRead])
def list_trips(session: Session = Depends(get_session)) -> list[Trip]:
    """List all trips for the default user, newest first."""
    stmt = (
        select(Trip)
        .where(Trip.user_id == DEFAULT_USER_ID)
        .order_by(Trip.created_at.desc())
    )
    return list(session.scalars(stmt).all())


@router.get("/{trip_id}", response_model=TripRead)
def get_trip(trip_id: int, session: Session = Depends(get_session)) -> Trip:
    """Fetch a single trip by id."""
    return _get_trip_or_404(session, trip_id)


@router.get("/{trip_id}/itinerary", response_model=list[ItineraryDayRead])
def get_trip_itinerary(
    trip_id: int, session: Session = Depends(get_session)
) -> list[ItineraryDay]:
    """Return the trip's itinerary days (with items). Empty list if none."""
    _get_trip_or_404(session, trip_id)
    stmt = (
        select(ItineraryDay)
        .where(ItineraryDay.trip_id == trip_id)
        .order_by(ItineraryDay.day_number)
    )
    return list(session.scalars(stmt).all())


@router.post("/{trip_id}/generate-itinerary", response_model=AgentRunRead)
def generate_trip_itinerary(
    trip_id: int, session: Session = Depends(get_session)
) -> AgentRun:
    """Generate and save a day-by-day itinerary for the trip (sync)."""
    _get_trip_or_404(session, trip_id)
    try:
        run = generate_itinerary(session, trip_id)
    except TripNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from e

    if run.status == AgentRunStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=run.error_message or "Itinerary generation failed",
        )
    return run


@router.put("/{trip_id}", response_model=TripRead)
def update_trip(
    trip_id: int,
    payload: TripUpdate,
    session: Session = Depends(get_session),
) -> Trip:
    """Partially update a trip. Only provided fields change."""
    trip = _get_trip_or_404(session, trip_id)
    data = payload.model_dump(exclude={"preference"}, exclude_unset=True)
    for field, value in data.items():
        setattr(trip, field, value)

    # ``preference`` is only touched when explicitly present in the request.
    if "preference" in payload.model_fields_set:
        if payload.preference is None:
            trip.preference = None
        elif trip.preference is None:
            trip.preference = TripPreference(**payload.preference.model_dump())
        else:
            for field, value in payload.preference.model_dump().items():
                setattr(trip.preference, field, value)

    session.commit()
    session.refresh(trip)
    return trip


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(trip_id: int, session: Session = Depends(get_session)) -> None:
    """Delete a trip and its preference (cascade)."""
    trip = _get_trip_or_404(session, trip_id)
    session.delete(trip)
    session.commit()
