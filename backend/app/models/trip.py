"""Trip and TripPreference models.

A ``Trip`` is the core Sprint 1 record. Each trip optionally carries one
``TripPreference`` row (one-to-one) holding the planning constraints used by
later sprints (routing, AI itinerary generation). List-valued preferences are
stored as JSON to keep the schema portable and easy to read.
"""

from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.user import DEFAULT_USER_ID

if TYPE_CHECKING:
    from app.models.agent import AgentRun
    from app.models.itinerary import ItineraryDay
    from app.models.user import User


class TripStatus(str, Enum):
    """Lifecycle of a trip. Kept minimal for Sprint 1."""

    DRAFT = "draft"
    PLANNED = "planned"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        default=DEFAULT_USER_ID,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(200))
    destination: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date(), default=None)
    end_date: Mapped[date | None] = mapped_column(Date(), default=None)
    travelers: Mapped[int] = mapped_column(Integer, default=1)
    # Stored as fixed-precision money; ``None`` means "no budget set".
    budget: Mapped[float | None] = mapped_column(Numeric(10, 2), default=None)
    status: Mapped[TripStatus] = mapped_column(
        String(20), default=TripStatus.DRAFT
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="trips")  # noqa: F821
    preference: Mapped["TripPreference | None"] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        uselist=False,
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(  # noqa: F821
        back_populates="trip", cascade="all, delete-orphan"
    )
    itinerary_days: Mapped[list["ItineraryDay"]] = relationship(  # noqa: F821
        back_populates="trip", cascade="all, delete-orphan"
    )


class TripPreference(Base):
    __tablename__ = "trip_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), unique=True, index=True
    )

    travel_style: Mapped[str | None] = mapped_column(String(100), default=None)
    max_walking_minutes_between_stops: Mapped[int | None] = mapped_column(
        Integer, default=None
    )
    max_total_walking_minutes_per_day: Mapped[int | None] = mapped_column(
        Integer, default=None
    )

    # List-valued free-form preferences, stored as JSON arrays of strings.
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)
    hotel_preferences: Mapped[list[str]] = mapped_column(JSON, default=list)
    food_preferences: Mapped[list[str]] = mapped_column(JSON, default=list)
    must_visit_places: Mapped[list[str]] = mapped_column(JSON, default=list)
    avoid_places: Mapped[list[str]] = mapped_column(JSON, default=list)

    trip: Mapped["Trip"] = relationship(back_populates="preference")
