"""Database connection and session management.

Sets up the SQLAlchemy engine and a session factory backed by the
``DATABASE_URL`` setting. No models or CRUD yet — those land in a later task.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# ``pool_pre_ping`` checks a connection is alive before handing it out, which
# avoids errors from connections dropped by the database between requests.
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class for ORM models defined in later tasks."""


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and closes it after use."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
