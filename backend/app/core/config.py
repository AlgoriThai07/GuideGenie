"""Application configuration.

Settings load from environment variables (and a local ``.env`` file if present)
via pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings sourced from the environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "GuideGenie Backend"
    SERVICE_NAME: str = "guidegenie-backend"

    # SQLAlchemy connection string. Defaults to the local Docker Compose Postgres.
    DATABASE_URL: str = (
        "postgresql+psycopg://guidegenie:guidegenie@localhost:5433/guidegenie"
    )

    # Gemini credentials for AI itinerary generation. ``GEMINI_API_KEY`` has no
    # default (must be set in the environment); ``AI_MODEL`` picks the model.
    GEMINI_API_KEY: str = ""
    AI_MODEL: str = "gemini-2.5-flash"


settings = Settings()
