"""SQLAlchemy ORM models.

Importing this package pulls in every model so that ``Base.metadata`` is fully
populated before table creation. New models should be re-exported here.
"""

from app.models.trip import Trip, TripPreference, TripStatus
from app.models.user import DEFAULT_USER_ID, User

__all__ = [
    "User",
    "Trip",
    "TripPreference",
    "TripStatus",
    "DEFAULT_USER_ID",
]
