"""Itinerary day and item models.

A generated itinerary is a list of ``ItineraryDay`` rows for a trip, each
holding an ordered list of ``ItineraryItem`` rows. Enums are Python enums
stored as ``String`` columns, matching the Sprint 1 convention.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ItineraryItemType(str, Enum):
    """Kind of itinerary item."""

    ACTIVITY = "activity"
    MEAL = "meal"
    HOTEL = "hotel"
    TRANSPORT = "transport"
    REST = "rest"
    EVENT = "event"
    FREE_TIME = "free_time"


class WalkingIntensity(str, Enum):
    """Relative walking effort for an item."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ItineraryItemPriority(str, Enum):
    """How important an item is to the plan."""

    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


class ItineraryDay(Base):
    __tablename__ = "itinerary_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), index=True
    )

    day_number: Mapped[int] = mapped_column(Integer)
    date: Mapped[date | None] = mapped_column(Date(), default=None)
    theme: Mapped[str | None] = mapped_column(String(200), default=None)
    summary: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    trip: Mapped["Trip"] = relationship(back_populates="itinerary_days")  # noqa: F821
    items: Mapped[list["ItineraryItem"]] = relationship(
        back_populates="day",
        cascade="all, delete-orphan",
        order_by="ItineraryItem.order_index",
    )


class ItineraryItem(Base):
    __tablename__ = "itinerary_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    itinerary_day_id: Mapped[int] = mapped_column(
        ForeignKey("itinerary_days.id", ondelete="CASCADE"), index=True
    )

    start_time: Mapped[str] = mapped_column(String(5))  # "HH:MM"
    end_time: Mapped[str] = mapped_column(String(5))  # "HH:MM"
    title: Mapped[str] = mapped_column(String(200))
    type: Mapped[ItineraryItemType] = mapped_column(String(20))
    location_name: Mapped[str | None] = mapped_column(String(200), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    estimated_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), default=None
    )
    walking_intensity: Mapped[WalkingIntensity | None] = mapped_column(
        String(10), default=None
    )
    priority: Mapped[ItineraryItemPriority] = mapped_column(String(20))
    order_index: Mapped[int] = mapped_column(Integer)
    place_id: Mapped[int | None] = mapped_column(
        ForeignKey("places.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        default=None,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    day: Mapped["ItineraryDay"] = relationship(back_populates="items")
    place: Mapped["Place | None"] = relationship(  # noqa: F821
        back_populates="itinerary_items", passive_deletes=True
    )
