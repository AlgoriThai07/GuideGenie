"""GuideGenie FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent_runs import router as agent_runs_router
from app.api.trips import router as trips_router
from app.core.config import settings

app = FastAPI(title=settings.APP_NAME)

# Allow the Next.js dev server (localhost:3000) to call the API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trips_router)
app.include_router(agent_runs_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok", "service": settings.SERVICE_NAME}
