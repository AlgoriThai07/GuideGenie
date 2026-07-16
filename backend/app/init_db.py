"""Create database tables and seed the default user.

Sprint 1 uses ``Base.metadata.create_all`` for simplicity instead of Alembic
migrations. Importing ``app.models`` registers every model on ``Base.metadata``
before the tables are created.

``create_all`` never alters existing tables, so a model change (new/renamed
column) requires dropping tables first. Use ``--drop`` to do that in one step.

Run from ``backend/`` with the venv active::

    python -m app.init_db
    python -m app.init_db --drop
"""

import sys

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import DEFAULT_USER_ID, User


def drop_tables() -> None:
    """Drop all tables so create_tables() can rebuild them from current models."""
    Base.metadata.drop_all(bind=engine)


def create_tables() -> None:
    """Create all tables that do not already exist."""
    Base.metadata.create_all(bind=engine)


def seed_default_user() -> None:
    """Insert the placeholder user that owns every trip until auth exists."""
    with SessionLocal() as session:
        existing = session.scalar(select(User).where(User.id == DEFAULT_USER_ID))
        if existing is None:
            session.add(
                User(
                    id=DEFAULT_USER_ID,
                    email="default@guidegenie.local",
                    display_name="Default User",
                )
            )
            session.commit()


def main() -> None:
    if "--drop" in sys.argv:
        drop_tables()
        print("Tables dropped.")
    create_tables()
    seed_default_user()
    print("Tables created and default user seeded.")


if __name__ == "__main__":
    main()
