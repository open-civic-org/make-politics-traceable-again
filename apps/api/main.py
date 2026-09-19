from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from packages.shared.config import get_settings
from packages.shared.logging import configure_logging, get_logger

from apps.api.routes import constituencies, health, parties, people, sources

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info("API starting", extra={"version": "0.1.0"})
    yield


app = FastAPI(
    title="Make Politics Traceable Again API",
    description=(
        "Evidence-based REST API for elected representatives in India. "
        "Every material claim includes provenance. No political scoring."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(people.router, prefix="/api/v1")
app.include_router(constituencies.router, prefix="/api/v1")
app.include_router(parties.router, prefix="/api/v1")
app.include_router(sources.router, prefix="/api/v1")
