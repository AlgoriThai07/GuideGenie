"""Place model.

Caches resolved Google Places records so the same place is never looked up
twice across agent runs. Populated by the Sprint 3 places service, never
created directly via the API.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_place_id: Mapped[str] = mapped_column(
        String(300), unique=True, index=True
    )

    name: Mapped[str] = mapped_column(String(300))
    address: Mapped[str | None] = mapped_column(String(500), default=None)
    lat: Mapped[float | None] = mapped_column(Float, default=None)
    lng: Mapped[float | None] = mapped_column(Float, default=None)
    rating: Mapped[float | None] = mapped_column(Float, default=None)
    price_level: Mapped[int | None] = mapped_column(Integer, default=None)
    types: Mapped[list[str]] = mapped_column(JSON, default=list)
    opening_hours: Mapped[dict | None] = mapped_column(JSON, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    itinerary_items: Mapped[list["ItineraryItem"]] = relationship(  # noqa: F821
        back_populates="place",
        passive_deletes=True,
    )

    @property
    def maps_url(self) -> str:
        """Google Maps link for this place, built from its place_id."""
        return f"https://www.google.com/maps/place/?q=place_id:{self.google_place_id}"
