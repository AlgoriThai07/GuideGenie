"""User model.

Authentication is out of scope for Sprint 1. Every trip is owned by a single
seeded "default" user so the schema already carries a real ``user_id`` foreign
key. Real auth (and multiple users) lands in a later sprint without a migration
of the trip ownership shape.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.trip import Trip

# Stable id for the seeded placeholder user. Trips default to this owner until
# authentication exists.
DEFAULT_USER_ID = 1


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trips: Mapped[list["Trip"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
