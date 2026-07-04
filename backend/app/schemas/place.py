"""Place API schema.

Places are only created internally by the places service (Task 2), never via
the API, so only a ``PlaceRead`` response schema is needed.
"""

import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    google_place_id: str
    name: str
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    rating: float | None = None
    price_level: int | None = None
    types: list[str] = Field(default_factory=list)
    opening_hours: dict | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
