"""Itinerary API and AI-output schemas.

Two families live here:

- ``*Read`` schemas mirror the persisted ORM models for API responses.
- ``*AI`` schemas validate the raw JSON returned by the LLM before it is
  mapped to DB rows. They use camelCase aliases so they match the exact JSON
  shape the model is prompted to return, while exposing snake_case fields to
  Python code (``populate_by_name=True``).
"""

# Imported as a module (not ``from datetime import date``) because the itinerary
# schemas expose a field literally named ``date``, which would otherwise shadow
# the type at class-body evaluation time.
import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.itinerary import (
    ItineraryItemPriority,
    ItineraryItemType,
    WalkingIntensity,
)
from app.schemas.place import PlaceRead


# --- Read schemas (mirror ORM models) ---------------------------------------


class ItineraryItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    itinerary_day_id: int
    start_time: str
    end_time: str
    title: str
    type: ItineraryItemType
    location_name: str | None = None
    description: str | None = None
    estimated_cost: Decimal | None = None
    verified_cost: Decimal | None = None
    price_source: str | None = None
    walking_intensity: WalkingIntensity | None = None
    priority: ItineraryItemPriority
    order_index: int
    place: PlaceRead | None = None
    travel_time_to_next_minutes: int | None = None
    distance_to_next_meters: int | None = None
    travel_mode_to_next: str | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class ItineraryDayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    day_number: int
    date: datetime.date | None = None
    theme: str | None = None
    summary: str | None = None
    total_walking_minutes: int | None = None
    total_transit_minutes: int | None = None
    total_distance_meters: int | None = None
    route_optimized: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime
    items: list[ItineraryItemRead] = Field(default_factory=list)


# --- AI-output schemas (validate raw LLM JSON, not persisted) ---------------


class ItineraryItemAI(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    start_time: str = Field(alias="startTime")
    end_time: str = Field(alias="endTime")
    title: str
    type: ItineraryItemType
    location_name: str | None = Field(default=None, alias="locationName")
    description: str | None = None
    estimated_cost: Decimal | None = Field(default=None, alias="estimatedCost")
    walking_intensity: WalkingIntensity | None = Field(
        default=None, alias="walkingIntensity"
    )
    priority: ItineraryItemPriority


class ItineraryDayAI(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    day_number: int = Field(alias="dayNumber")
    date: datetime.date | None = None
    theme: str | None = None
    summary: str | None = None
    items: list[ItineraryItemAI] = Field(default_factory=list)


class ItineraryAIResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    trip_title: str = Field(alias="tripTitle")
    overview: str
    days: list[ItineraryDayAI] = Field(default_factory=list)
