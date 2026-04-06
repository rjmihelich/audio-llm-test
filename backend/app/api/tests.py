"""Test suite configuration API endpoints."""

from __future__ import annotations

import hashlib
import json
import uuid
from itertools import product

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import get_session
from backend.app.models.speech import SpeechSample
from backend.app.models.test import SweepConfig, TestCase, TestSuite

router = APIRouter()


class FilterSpecConfig(BaseModel):
    filter_type: str  # lpf, hpf, peaking, lowshelf, highshelf
    frequency: float
    Q: float = 0.7071
    gain_db: float = 0.0


class EchoProfileConfig(BaseModel):
    delay_ms_values: list[float] = Field(default=[0, 50, 100, 200])
    gain_db_values: list[float] = Field(default=[-60, -40, -20])
    eq_chains: list[list[FilterSpecConfig]] = Field(default_factory=list)


class SweepConfigRequest(BaseModel):
    name: str
    description: str = ""
    snr_db_values: list[float] = Field(default=[-10, -5, 0, 5, 10, 20])
    noise_types: list[str] = Field(default=["pink_lpf"])
    echo: EchoProfileConfig = Field(default_factory=EchoProfileConfig)
    pipelines: list[str] = Field(default=["direct_audio", "asr_text"])
    llm_backends: list[str] = Field(default=[])
    voice_ids: list[str] | None = None
    corpus_categories: list[str] | None = None
    corpus_entry_ids: list[str] | None = None
    system_prompt: str = "You are a helpful in-car voice assistant."


class TestSuiteResponse(BaseModel):
    id: str
    name: str
    description: str
    status: str
    total_cases: int
    created_at: str


class SweepPreview(BaseModel):
    total_cases: int
    breakdown: dict  # e.g., {"snr_levels": 6, "echo_configs": 12, "backends": 3, ...}
    estimated_duration_minutes: float | None = None


@router.post("/suites", response_model=TestSuiteResponse)
async def create_test_suite(
    config: SweepConfigRequest,
    session: AsyncSession = Depends(get_session),
):
    """Create a new test suite from sweep configuration.

    Expands the cartesian product of all parameter ranges into
    individual test cases with deterministic IDs.
    """
    # Query ready speech samples
    sample_stmt = select(SpeechSample).where(SpeechSample.status == "ready")
    if config.voice_ids:
        sample_stmt = sample_stmt.where(
            SpeechSample.voice_id.in_([uuid.UUID(v) for v in config.voice_ids])
        )
    if config.corpus_entry_ids:
        sample_stmt = sample_stmt.where(
            SpeechSample.corpus_entry_id.in_([uuid.UUID(c) for c in config.corpus_entry_ids])
        )
    # Filter by corpus categories requires a join
    if config.corpus_categories:
        from backend.app.models.speech import CorpusEntry
        sample_stmt = sample_stmt.join(CorpusEntry).where(
            CorpusEntry.category.in_(config.corpus_categories)
        )

    sample_result = await session.execute(sample_stmt)
    samples = sample_result.scalars().all()

    if not samples:
        raise HTTPException(400, "No ready speech samples match the filters")

    # Create test suite
    suite = TestSuite(
        name=config.name,
        description=config.description or "",
        status="draft",
    )
    session.add(suite)
    await session.flush()  # get suite.id

    # Create sweep config
    backends = config.llm_backends if config.llm_backends else ["default"]
    eq_configs_data = [
        [f.model_dump() for f in chain] for chain in config.echo.eq_chains
    ] if config.echo.eq_chains else []

    sweep = SweepConfig(
        test_suite_id=suite.id,
        snr_db_values=config.snr_db_values,
        delay_ms_values=config.echo.delay_ms_values,
        gain_db_values=config.echo.gain_db_values,
        noise_types=config.noise_types,
        pipelines=config.pipelines,
        llm_backends=backends,
        eq_configs=eq_configs_data,
    )
    session.add(sweep)

    # Build cartesian product and create test cases
    total_cases = 0
    for sample, snr, noise, delay, gain, pipeline, backend in product(
        samples,
        config.snr_db_values,
        config.noise_types,
        config.echo.delay_ms_values,
        config.echo.gain_db_values,
        config.pipelines,
        backends,
    ):
        # Deterministic hash
        hash_input = json.dumps(
            {
                "speech_sample_id": str(sample.id),
                "snr_db": snr,
                "noise_type": noise,
                "delay_ms": delay,
                "gain_db": gain,
                "pipeline": pipeline,
                "llm_backend": backend,
            },
            sort_keys=True,
        )
        deterministic_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        test_case = TestCase(
            test_suite_id=suite.id,
            speech_sample_id=sample.id,
            snr_db=snr,
            delay_ms=delay,
            gain_db=gain,
            noise_type=noise,
            eq_config_json=None,
            pipeline=pipeline,
            llm_backend=backend,
            status="pending",
            deterministic_hash=deterministic_hash,
        )
        session.add(test_case)
        total_cases += 1

    # Update suite status
    suite.status = "ready"
    await session.commit()

    return TestSuiteResponse(
        id=str(suite.id),
        name=suite.name,
        description=suite.description or "",
        status=suite.status,
        total_cases=total_cases,
        created_at=suite.created_at.isoformat(),
    )


@router.get("/suites", response_model=list[TestSuiteResponse])
async def list_test_suites(session: AsyncSession = Depends(get_session)):
    """List all test suites."""
    stmt = select(TestSuite)
    result = await session.execute(stmt)
    suites = result.scalars().all()

    responses = []
    for suite in suites:
        # Count test cases
        count_stmt = select(func.count()).select_from(TestCase).where(
            TestCase.test_suite_id == suite.id
        )
        count_result = await session.execute(count_stmt)
        case_count = count_result.scalar() or 0

        responses.append(
            TestSuiteResponse(
                id=str(suite.id),
                name=suite.name,
                description=suite.description or "",
                status=suite.status,
                total_cases=case_count,
                created_at=suite.created_at.isoformat(),
            )
        )

    return responses


@router.get("/suites/{suite_id}", response_model=TestSuiteResponse)
async def get_test_suite(
    suite_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get test suite details."""
    stmt = select(TestSuite).where(TestSuite.id == uuid.UUID(suite_id))
    result = await session.execute(stmt)
    suite = result.scalar_one_or_none()

    if suite is None:
        raise HTTPException(404, "Suite not found")

    count_stmt = select(func.count()).select_from(TestCase).where(
        TestCase.test_suite_id == suite.id
    )
    count_result = await session.execute(count_stmt)
    case_count = count_result.scalar() or 0

    return TestSuiteResponse(
        id=str(suite.id),
        name=suite.name,
        description=suite.description or "",
        status=suite.status,
        total_cases=case_count,
        created_at=suite.created_at.isoformat(),
    )


@router.post("/suites/preview", response_model=SweepPreview)
async def preview_sweep(
    config: SweepConfigRequest,
    session: AsyncSession = Depends(get_session),
):
    """Preview the number of test cases a sweep configuration would generate.

    Does not create anything -- just returns the count and breakdown.
    """
    n_snr = len(config.snr_db_values)
    n_noise = len(config.noise_types)
    n_delay = len(config.echo.delay_ms_values)
    n_gain = len(config.echo.gain_db_values)
    n_pipelines = len(config.pipelines)
    n_backends = len(config.llm_backends) or 1

    # Count ready speech samples matching filters
    sample_stmt = select(func.count()).select_from(SpeechSample).where(
        SpeechSample.status == "ready"
    )
    if config.voice_ids:
        sample_stmt = sample_stmt.where(
            SpeechSample.voice_id.in_([uuid.UUID(v) for v in config.voice_ids])
        )
    if config.corpus_entry_ids:
        sample_stmt = sample_stmt.where(
            SpeechSample.corpus_entry_id.in_([uuid.UUID(c) for c in config.corpus_entry_ids])
        )
    if config.corpus_categories:
        from backend.app.models.speech import CorpusEntry
        sample_stmt = sample_stmt.join(CorpusEntry).where(
            CorpusEntry.category.in_(config.corpus_categories)
        )

    count_result = await session.execute(sample_stmt)
    n_speech = count_result.scalar() or 0

    total = n_speech * n_snr * n_noise * n_delay * n_gain * n_pipelines * n_backends

    return SweepPreview(
        total_cases=total,
        breakdown={
            "snr_levels": n_snr,
            "noise_types": n_noise,
            "echo_delays": n_delay,
            "echo_gains": n_gain,
            "pipelines": n_pipelines,
            "backends": n_backends,
            "speech_samples": n_speech,
        },
    )


@router.delete("/suites/{suite_id}")
async def delete_test_suite(
    suite_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete a test suite and all its test cases."""
    suite_uuid = uuid.UUID(suite_id)

    stmt = select(TestSuite).where(TestSuite.id == suite_uuid)
    result = await session.execute(stmt)
    suite = result.scalar_one_or_none()

    if suite is None:
        raise HTTPException(404, "Suite not found")

    # Delete test cases first (cascade)
    await session.execute(
        delete(TestCase).where(TestCase.test_suite_id == suite_uuid)
    )
    # Delete sweep configs
    await session.execute(
        delete(SweepConfig).where(SweepConfig.test_suite_id == suite_uuid)
    )
    # Delete the suite itself
    await session.delete(suite)
    await session.commit()

    return {"status": "deleted", "id": suite_id}
