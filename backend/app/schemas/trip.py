"""Trip and TripPreference API schemas.

Naming convention:
- ``*Base``   shared fields
- ``*Create`` request body for creation (no server-set fields)
- ``*Update`` request body for partial update (all fields optional)
- ``*Read``   response body (includes server-set fields like ids/timestamps)
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.trip import TripStatus


# --- TripPreference ---------------------------------------------------------


class TripPreferenceBase(BaseModel):
    travel_style: str | None = None
    max_walking_minutes_between_stops: int | None = Field(default=None, ge=0)
    max_total_walking_minutes_per_day: int | None = Field(default=None, ge=0)
    interests: list[str] = Field(default_factory=list)
    hotel_preferences: list[str] = Field(default_factory=list)
    food_preferences: list[str] = Field(default_factory=list)
    must_visit_places: list[str] = Field(default_factory=list)
    avoid_places: list[str] = Field(default_factory=list)


class TripPreferenceCreate(TripPreferenceBase):
    pass


class TripPreferenceRead(TripPreferenceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int


# --- Trip -------------------------------------------------------------------


class TripBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    destination: str = Field(min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    travelers: int = Field(default=1, ge=1)
    budget: Decimal | None = Field(default=None, ge=0)
    status: TripStatus = TripStatus.DRAFT


class TripCreate(TripBase):
    # Preferences may be supplied inline when creating a trip.
    preference: TripPreferenceCreate | None = None


class TripUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    destination: str | None = Field(default=None, min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    travelers: int | None = Field(default=None, ge=1)
    budget: Decimal | None = Field(default=None, ge=0)
    status: TripStatus | None = None
    preference: TripPreferenceCreate | None = None


class TripRead(TripBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    preference: TripPreferenceRead | None = None
