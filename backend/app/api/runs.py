"""Test run management API endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import get_session
from backend.app.models.test import TestCase, TestSuite
from backend.app.models.run import TestRun

router = APIRouter()


class LaunchRunRequest(BaseModel):
    test_suite_id: str
    resume: bool = False  # If True, skip already-completed test cases
    sample_size: int | None = None  # If set, pick N random cases for a quick test


class RunResponse(BaseModel):
    id: str
    test_suite_id: str
    status: str  # pending, running, completed, cancelled, failed
    total_cases: int
    completed_cases: int
    failed_cases: int
    skipped_cases: int = 0
    progress_pct: float
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    error_details: dict | None = None


def _run_to_response(run: TestRun) -> RunResponse:
    return RunResponse(
        id=str(run.id),
        test_suite_id=str(run.test_suite_id),
        status=run.status,
        total_cases=run.total_cases,
        completed_cases=run.completed_cases,
        failed_cases=run.failed_cases,
        skipped_cases=getattr(run, "skipped_cases", 0),
        progress_pct=run.progress_pct,
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        error_message=getattr(run, "error_message", None),
        error_details=getattr(run, "error_details", None),
    )


@router.post("", response_model=RunResponse)
async def launch_run(
    request: LaunchRunRequest,
    session: AsyncSession = Depends(get_session),
):
    """Launch a new test run for a test suite.

    Creates a TestRun record and enqueues it for execution via the arq worker.
    """
    suite_uuid = uuid.UUID(request.test_suite_id)

    # Verify suite exists
    suite_stmt = select(TestSuite).where(TestSuite.id == suite_uuid)
    suite_result = await session.execute(suite_stmt)
    suite = suite_result.scalar_one_or_none()
    if suite is None:
        raise HTTPException(404, "Test suite not found")

    # Count test cases
    count_stmt = select(func.count()).select_from(TestCase).where(
        TestCase.test_suite_id == suite_uuid
    )
    count_result = await session.execute(count_stmt)
    total_cases = count_result.scalar() or 0

    if total_cases == 0:
        raise HTTPException(400, "Test suite has no test cases")

    # If sample_size is set, we'll only run a random subset
    run_cases = total_cases
    if request.sample_size and request.sample_size < total_cases:
        run_cases = request.sample_size

    run = TestRun(
        test_suite_id=suite_uuid,
        status="pending",
        total_cases=run_cases,
        completed_cases=0,
        failed_cases=0,
        progress_pct=0.0,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    # Enqueue the job in Redis for the arq worker
    try:
        import asyncio as _aio
        from arq.connections import create_pool, RedisSettings
        from backend.app.config import settings as app_settings
        redis = await _aio.wait_for(
            create_pool(RedisSettings.from_dsn(app_settings.redis_url)),
            timeout=5.0,
        )
        await redis.enqueue_job("run_test_suite", str(run.id), request.sample_size)
        await redis.close()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to enqueue run job: {e}")
        # Run was created, worker can still pick it up manually

    return _run_to_response(run)


@router.get("", response_model=list[RunResponse])
async def list_runs(session: AsyncSession = Depends(get_session)):
    """List all test runs."""
    stmt = select(TestRun).order_by(TestRun.created_at.desc())
    result = await session.execute(stmt)
    runs = result.scalars().all()
    return [_run_to_response(r) for r in runs]


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get test run status and progress."""
    stmt = select(TestRun).where(TestRun.id == uuid.UUID(run_id))
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()

    if run is None:
        raise HTTPException(404, "Run not found")

    return _run_to_response(run)


@router.delete("/{run_id}")
async def cancel_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Cancel a running test run."""
    stmt = select(TestRun).where(TestRun.id == uuid.UUID(run_id))
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()

    if run is None:
        raise HTTPException(404, "Run not found")

    if run.status in ("completed", "cancelled"):
        raise HTTPException(400, f"Cannot cancel run with status={run.status}")

    run.status = "cancelled"
    await session.commit()

    return {"status": "cancelled", "id": run_id}
