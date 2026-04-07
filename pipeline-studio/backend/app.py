"""Pipeline Studio — FastAPI application entry point."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.pipelines import router as pipelines_router
from .engine.templates import seed_templates


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    # Seed built-in templates on first run
    await seed_templates()
    yield


app = FastAPI(
    title="Pipeline Studio",
    description="Visual node-graph pipeline editor for audio LLM testing",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(pipelines_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "pipeline-studio"}
