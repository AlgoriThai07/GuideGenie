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

    # Google Places API key for resolving LLM-proposed locations (Sprint 3).
    # Empty default so the app starts without it; calls fail gracefully.
    GOOGLE_PLACES_API_KEY: str = ""

    # Google Distance Matrix API key for route optimization (Sprint 4).
    # Empty default so the app starts without it; calls fail gracefully.
    GOOGLE_ROUTES_API_KEY: str = ""


settings = Settings()
