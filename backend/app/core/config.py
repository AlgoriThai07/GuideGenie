"""Application configuration.

Minimal for now. Database and environment loading land in a later task.
"""


class Settings:
    """Static application settings."""

    APP_NAME: str = "GuideGenie Backend"
    SERVICE_NAME: str = "guidegenie-backend"


settings = Settings()
