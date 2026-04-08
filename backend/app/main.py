"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .config import settings
from .api import speech, tests, runs, results, ws, health, cars
from .api import settings as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure storage directories exist
    settings.audio_storage_path.mkdir(parents=True, exist_ok=True)
    settings.results_storage_path.mkdir(parents=True, exist_ok=True)

    # Create database tables if they don't exist
    from backend.app.models.base import engine, Base
    import backend.app.models.speech  # noqa: F401
    import backend.app.models.test  # noqa: F401
    import backend.app.models.run  # noqa: F401
    import backend.app.models.car  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield
    # Shutdown: cleanup


app = FastAPI(
    title="Audio LLM Test Platform",
    description="Test platform for evaluating LLM speech understanding in automotive cabin conditions",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(speech.router, prefix="/api/speech", tags=["Speech"])
app.include_router(tests.router, prefix="/api/tests", tags=["Tests"])
app.include_router(runs.router, prefix="/api/runs", tags=["Runs"])
app.include_router(results.router, prefix="/api/results", tags=["Results"])
app.include_router(ws.router, prefix="/api/ws", tags=["WebSocket"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["Settings"])
app.include_router(health.router, prefix="/api/health", tags=["Health"])
app.include_router(cars.router, prefix="/api/cars", tags=["Cars"])


@app.get("/api/ping")
async def ping():
    return {"status": "ok"}
