"""GuideGenie FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.trips import router as trips_router
from app.core.config import settings

app = FastAPI(title=settings.APP_NAME)

app.include_router(trips_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok", "service": settings.SERVICE_NAME}
