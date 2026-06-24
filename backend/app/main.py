"""GuideGenie FastAPI application entrypoint."""

from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(title=settings.APP_NAME)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok", "service": settings.SERVICE_NAME}
