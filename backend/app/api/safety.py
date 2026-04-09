"""Safety testing API endpoints.

Provides CRUD for safety test runs, corpus browsing, and result querying.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import get_session
from backend.app.models.safety import (
    SafetyTestRun,
    SafetyTestCaseResult,
    SafetyAgentVerdict,
    SafetyRunStatusEnum,
)
from backend.app.safety.corpus import (
    AdversarialCategory,
    SeverityLevel,
    get_all_utterances,
    get_by_category,
    get_by_severity,
    get_by_agent,
    get_categories,
    corpus_stats,
    sample_corpus,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class CorpusUtteranceResponse(BaseModel):
    id: str
    text: str
    category: str
    subcategory: str
    severity: str
    expected_behavior: str
    description: str
    relevant_agents: list[str]
    language: str


class LaunchSafetyRunRequest(BaseModel):
    name: str
    description: str | None = None
    llm_backend: str
    system_prompt: str = "You are a helpful in-car voice assistant."
    categories: list[str] | None = None  # Filter to specific categories
    min_severity: str | None = None  # Minimum severity level
    agents: list[str] | None = None  # Which agents to use (null = all)
    max_concurrent: int = 6
    sample_size: int | None = None  # If set, sample N utterances


class SafetyRunResponse(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    llm_backend: str
    total_cases: int
    completed_cases: int
    passed_cases: int
    failed_cases: int
    warning_cases: int
    error_cases: int
    progress_pct: float
    started_at: str | None
    completed_at: str | None
    created_at: str | None


class SafetyCaseResultResponse(BaseModel):
    id: str
    utterance_id: str
    utterance_text: str
    category: str
    subcategory: str
    severity: str
    expected_behavior: str
    model_response: str | None
    model_latency_ms: float | None
    composite_verdict: str
    composite_score: float
    passed: bool
    error: str | None
    agent_verdicts: list[dict]


class AgentSummary(BaseModel):
    agent_name: str
    total_evaluated: int
    passed: int
    warnings: int
    failed: int
    avg_score: float


class SafetyRunStatsResponse(BaseModel):
    run_id: str
    total_cases: int
    passed: int
    failed: int
    warnings: int
    errors: int
    pass_rate: float
    avg_score: float
    by_category: dict
    by_severity: dict
    by_agent: list[AgentSummary]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_to_response(run: SafetyTestRun) -> SafetyRunResponse:
    return SafetyRunResponse(
        id=str(run.id),
        name=run.name,
        description=run.description,
        status=run.status,
        llm_backend=run.llm_backend,
        total_cases=run.total_cases,
        completed_cases=run.completed_cases,
        passed_cases=run.passed_cases,
        failed_cases=run.failed_cases,
        warning_cases=run.warning_cases,
        error_cases=run.error_cases,
        progress_pct=run.progress_pct,
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        created_at=run.created_at.isoformat() if run.created_at else None,
    )


def _case_to_response(case: SafetyTestCaseResult) -> SafetyCaseResultResponse:
    return SafetyCaseResultResponse(
        id=str(case.id),
        utterance_id=case.utterance_id,
        utterance_text=case.utterance_text,
        category=case.category,
        subcategory=case.subcategory,
        severity=case.severity,
        expected_behavior=case.expected_behavior,
        model_response=case.model_response,
        model_latency_ms=case.model_latency_ms,
        composite_verdict=case.composite_verdict,
        composite_score=case.composite_score,
        passed=case.passed,
        error=case.error,
        agent_verdicts=[
            {
                "agent_name": v.agent_name,
                "verdict": v.verdict,
                "severity": v.severity,
                "score": v.score,
                "reasoning": v.reasoning,
                "flags": v.flags,
                "recommendations": v.recommendations,
            }
            for v in (case.agent_verdicts or [])
        ],
    )


# ---------------------------------------------------------------------------
# Corpus endpoints
# ---------------------------------------------------------------------------

@router.get("/corpus", response_model=list[CorpusUtteranceResponse])
async def list_corpus(
    category: str | None = None,
    min_severity: str | None = None,
    agent: str | None = None,
):
    """Browse the adversarial utterance corpus with optional filters."""
    if category:
        try:
            cat = AdversarialCategory(category)
        except ValueError:
            raise HTTPException(400, f"Invalid category: {category}")
        utterances = get_by_category(cat)
    elif min_severity:
        try:
            sev = SeverityLevel(min_severity)
        except ValueError:
            raise HTTPException(400, f"Invalid severity: {min_severity}")
        utterances = get_by_severity(sev)
    elif agent:
        utterances = get_by_agent(agent)
    else:
        utterances = get_all_utterances()

    return [
        CorpusUtteranceResponse(
            id=u.id,
            text=u.text,
            category=u.category.value,
            subcategory=u.subcategory,
            severity=u.severity.value,
            expected_behavior=u.expected_behavior.value,
            description=u.description,
            relevant_agents=list(u.relevant_agents),
            language=u.language,
        )
        for u in utterances
    ]


@router.get("/corpus/stats")
async def get_corpus_stats():
    """Get corpus statistics: counts by category, severity, agent."""
    return corpus_stats()


@router.get("/corpus/categories")
async def list_categories():
    """List all adversarial categories with counts."""
    return get_categories()


# ---------------------------------------------------------------------------
# Safety run endpoints
# ---------------------------------------------------------------------------

@router.post("/runs", response_model=SafetyRunResponse)
async def launch_safety_run(
    request: LaunchSafetyRunRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Launch a new safety test run.

    Selects utterances from the corpus based on filters, creates a run record,
    and starts the batch pipeline in the background.
    """
    # Resolve utterances
    categories = None
    if request.categories:
        try:
            categories = [AdversarialCategory(c) for c in request.categories]
        except ValueError as e:
            raise HTTPException(400, f"Invalid category: {e}")

    min_severity = None
    if request.min_severity:
        try:
            min_severity = SeverityLevel(request.min_severity)
        except ValueError:
            raise HTTPException(400, f"Invalid severity: {request.min_severity}")

    if request.sample_size:
        utterances = sample_corpus(request.sample_size, categories, min_severity)
    else:
        utterances = get_all_utterances()
        if categories:
            utterances = [u for u in utterances if u.category in categories]
        if min_severity:
            levels = [SeverityLevel.low, SeverityLevel.medium, SeverityLevel.high, SeverityLevel.critical]
            min_idx = levels.index(min_severity)
            target = set(levels[min_idx:])
            utterances = [u for u in utterances if u.severity in target]

    if not utterances:
        raise HTTPException(400, "No utterances match the given filters")

    run = SafetyTestRun(
        name=request.name,
        description=request.description,
        status=SafetyRunStatusEnum.pending,
        llm_backend=request.llm_backend,
        system_prompt=request.system_prompt,
        categories_filter=request.categories,
        min_severity_filter=request.min_severity,
        agents_filter=request.agents,
        max_concurrent=request.max_concurrent,
        total_cases=len(utterances),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    # Schedule background execution
    background_tasks.add_task(
        _execute_safety_run,
        str(run.id),
        utterances,
        request.llm_backend,
        request.system_prompt,
        request.agents,
        request.max_concurrent,
    )

    return _run_to_response(run)


@router.get("/runs", response_model=list[SafetyRunResponse])
async def list_safety_runs(session: AsyncSession = Depends(get_session)):
    """List all safety test runs."""
    stmt = select(SafetyTestRun).order_by(SafetyTestRun.created_at.desc())
    result = await session.execute(stmt)
    runs = result.scalars().all()
    return [_run_to_response(r) for r in runs]


@router.get("/runs/{run_id}", response_model=SafetyRunResponse)
async def get_safety_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get safety test run status."""
    stmt = select(SafetyTestRun).where(SafetyTestRun.id == uuid.UUID(run_id))
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Safety run not found")
    return _run_to_response(run)


@router.delete("/runs/{run_id}")
async def cancel_safety_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Cancel a running safety test."""
    stmt = select(SafetyTestRun).where(SafetyTestRun.id == uuid.UUID(run_id))
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Safety run not found")
    if run.status in ("completed", "cancelled"):
        raise HTTPException(400, f"Cannot cancel run with status={run.status}")
    run.status = SafetyRunStatusEnum.cancelled
    await session.commit()
    return {"status": "cancelled", "id": run_id}


# ---------------------------------------------------------------------------
# Results endpoints
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}/results", response_model=list[SafetyCaseResultResponse])
async def get_safety_results(
    run_id: str,
    category: str | None = None,
    verdict: str | None = None,
    agent: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Get results for a safety test run with optional filters."""
    stmt = select(SafetyTestCaseResult).where(
        SafetyTestCaseResult.safety_run_id == uuid.UUID(run_id)
    )
    if category:
        stmt = stmt.where(SafetyTestCaseResult.category == category)
    if verdict:
        stmt = stmt.where(SafetyTestCaseResult.composite_verdict == verdict)

    stmt = stmt.order_by(SafetyTestCaseResult.composite_score.asc())
    result = await session.execute(stmt)
    cases = result.scalars().all()

    responses = [_case_to_response(c) for c in cases]

    # Filter by agent if requested (post-query since it's in a child relation)
    if agent:
        responses = [
            r for r in responses
            if any(v["agent_name"] == agent for v in r.agent_verdicts)
        ]

    return responses


@router.get("/runs/{run_id}/stats", response_model=SafetyRunStatsResponse)
async def get_safety_stats(
    run_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get aggregate statistics for a safety test run."""
    run_uuid = uuid.UUID(run_id)

    # Verify run exists
    run_stmt = select(SafetyTestRun).where(SafetyTestRun.id == run_uuid)
    run_result = await session.execute(run_stmt)
    run = run_result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Safety run not found")

    # Load all results
    stmt = select(SafetyTestCaseResult).where(
        SafetyTestCaseResult.safety_run_id == run_uuid
    )
    result = await session.execute(stmt)
    cases = result.scalars().all()

    total = len(cases)
    passed = sum(1 for c in cases if c.passed)
    failed = sum(1 for c in cases if c.composite_verdict == "failed")
    warnings = sum(1 for c in cases if c.composite_verdict == "warning")
    errors = sum(1 for c in cases if c.error)
    scores = [c.composite_score for c in cases if not c.error]

    # By category
    by_cat: dict[str, dict] = {}
    for c in cases:
        if c.category not in by_cat:
            by_cat[c.category] = {"total": 0, "passed": 0, "failed": 0, "avg_score": 0.0, "scores": []}
        by_cat[c.category]["total"] += 1
        if c.passed:
            by_cat[c.category]["passed"] += 1
        if c.composite_verdict == "failed":
            by_cat[c.category]["failed"] += 1
        if not c.error:
            by_cat[c.category]["scores"].append(c.composite_score)
    for cat_data in by_cat.values():
        cat_scores = cat_data.pop("scores")
        cat_data["avg_score"] = sum(cat_scores) / len(cat_scores) if cat_scores else 0.0

    # By severity
    by_sev: dict[str, dict] = {}
    for c in cases:
        if c.severity not in by_sev:
            by_sev[c.severity] = {"total": 0, "passed": 0, "failed": 0}
        by_sev[c.severity]["total"] += 1
        if c.passed:
            by_sev[c.severity]["passed"] += 1
        if c.composite_verdict == "failed":
            by_sev[c.severity]["failed"] += 1

    # By agent
    agent_data: dict[str, dict] = {}
    for c in cases:
        for v in (c.agent_verdicts or []):
            if v.agent_name not in agent_data:
                agent_data[v.agent_name] = {
                    "total_evaluated": 0, "passed": 0, "warnings": 0,
                    "failed": 0, "scores": [],
                }
            ad = agent_data[v.agent_name]
            ad["total_evaluated"] += 1
            if v.verdict == "passed":
                ad["passed"] += 1
            elif v.verdict == "warning":
                ad["warnings"] += 1
            elif v.verdict == "failed":
                ad["failed"] += 1
            ad["scores"].append(v.score)

    agent_summaries = []
    for name, data in sorted(agent_data.items()):
        agent_scores = data.pop("scores")
        agent_summaries.append(AgentSummary(
            agent_name=name,
            total_evaluated=data["total_evaluated"],
            passed=data["passed"],
            warnings=data["warnings"],
            failed=data["failed"],
            avg_score=sum(agent_scores) / len(agent_scores) if agent_scores else 0.0,
        ))

    return SafetyRunStatsResponse(
        run_id=run_id,
        total_cases=total,
        passed=passed,
        failed=failed,
        warnings=warnings,
        errors=errors,
        pass_rate=passed / total if total else 0.0,
        avg_score=sum(scores) / len(scores) if scores else 0.0,
        by_category=by_cat,
        by_severity=by_sev,
        by_agent=agent_summaries,
    )


# ---------------------------------------------------------------------------
# Background execution
# ---------------------------------------------------------------------------

async def _execute_safety_run(
    run_id: str,
    utterances: list,
    llm_backend_name: str,
    system_prompt: str,
    agent_names: list[str] | None,
    max_concurrent: int,
):
    """Execute a safety test run in the background.

    This function initializes the LLM backend and monitoring agents, runs
    the pipeline, and persists results to the database.
    """
    import logging
    from datetime import datetime
    from backend.app.models.base import async_session
    from backend.app.safety.agents import ALL_AGENTS

    log = logging.getLogger(__name__)

    async with async_session() as session:
        # Load run
        stmt = select(SafetyTestRun).where(SafetyTestRun.id == uuid.UUID(run_id))
        result = await session.execute(stmt)
        run = result.scalar_one_or_none()
        if not run:
            log.error(f"Safety run {run_id} not found")
            return

        run.status = SafetyRunStatusEnum.running
        run.started_at = datetime.utcnow()
        await session.commit()

    # Initialize LLM backend
    try:
        target = _resolve_llm_backend(llm_backend_name)
    except Exception as e:
        log.error(f"Failed to resolve backend {llm_backend_name}: {e}")
        async with async_session() as session:
            stmt = select(SafetyTestRun).where(SafetyTestRun.id == uuid.UUID(run_id))
            result = await session.execute(stmt)
            run = result.scalar_one()
            run.status = SafetyRunStatusEnum.failed
            run.error_message = f"Failed to resolve backend: {e}"
            run.completed_at = datetime.utcnow()
            await session.commit()
        return

    # Initialize judge backend (use the same or a separate LLM for judging)
    try:
        judge = _resolve_judge_backend()
    except Exception as e:
        log.error(f"Failed to resolve judge backend: {e}")
        async with async_session() as session:
            stmt = select(SafetyTestRun).where(SafetyTestRun.id == uuid.UUID(run_id))
            result = await session.execute(stmt)
            run = result.scalar_one()
            run.status = SafetyRunStatusEnum.failed
            run.error_message = f"Failed to resolve judge backend: {e}"
            run.completed_at = datetime.utcnow()
            await session.commit()
        return

    # Initialize agents
    selected_agents = []
    for name, agent_cls in ALL_AGENTS.items():
        if agent_names is None or name in agent_names:
            selected_agents.append(agent_cls(judge_backend=judge))

    if not selected_agents:
        log.error("No agents selected for safety run")
        return

    # Build pipeline
    from backend.app.safety.pipeline import SafetyTestPipeline

    completed_count = 0
    passed_count = 0
    failed_count = 0
    warning_count = 0
    error_count = 0

    async def on_result(result):
        nonlocal completed_count, passed_count, failed_count, warning_count, error_count
        completed_count += 1
        if result.error:
            error_count += 1
        elif result.passed:
            passed_count += 1
        elif result.composite_verdict.value == "failed":
            failed_count += 1
        else:
            warning_count += 1

        # Persist result to DB
        async with async_session() as s:
            case_result = SafetyTestCaseResult(
                safety_run_id=uuid.UUID(run_id),
                utterance_id=result.utterance_id,
                utterance_text=result.utterance_text,
                category=result.category,
                subcategory=result.subcategory,
                severity=result.severity,
                expected_behavior=result.expected_behavior,
                model_response=result.model_response or None,
                model_latency_ms=result.model_latency_ms,
                model_backend=result.model_backend,
                composite_verdict=result.composite_verdict.value,
                composite_score=result.composite_score,
                passed=result.passed,
                error=result.error,
            )
            s.add(case_result)
            await s.flush()

            # Persist agent verdicts
            for v in result.agent_verdicts:
                agent_verdict = SafetyAgentVerdict(
                    case_result_id=case_result.id,
                    agent_name=v.agent_name,
                    verdict=v.verdict.value,
                    severity=v.severity.value,
                    score=v.score,
                    reasoning=v.reasoning,
                    flags=v.flags,
                    recommendations=v.recommendations,
                )
                s.add(agent_verdict)

            await s.commit()

        # Update run progress
        async with async_session() as s:
            stmt = select(SafetyTestRun).where(SafetyTestRun.id == uuid.UUID(run_id))
            res = await s.execute(stmt)
            run = res.scalar_one()
            run.completed_cases = completed_count
            run.passed_cases = passed_count
            run.failed_cases = failed_count
            run.warning_cases = warning_count
            run.error_cases = error_count
            run.progress_pct = (completed_count / run.total_cases * 100) if run.total_cases else 0
            await s.commit()

    pipeline = SafetyTestPipeline(
        target_backend=target,
        agents=selected_agents,
        system_prompt=system_prompt,
        max_concurrent_inference=max_concurrent,
        on_result=on_result,
    )

    try:
        await pipeline.run(utterances)
    except Exception as e:
        log.error(f"Safety pipeline failed: {e}", exc_info=True)
        async with async_session() as session:
            stmt = select(SafetyTestRun).where(SafetyTestRun.id == uuid.UUID(run_id))
            result = await session.execute(stmt)
            run = result.scalar_one()
            run.status = SafetyRunStatusEnum.failed
            run.error_message = str(e)
            run.completed_at = datetime.utcnow()
            await session.commit()
        return

    # Mark complete
    async with async_session() as session:
        stmt = select(SafetyTestRun).where(SafetyTestRun.id == uuid.UUID(run_id))
        result = await session.execute(stmt)
        run = result.scalar_one()
        run.status = SafetyRunStatusEnum.completed
        run.completed_at = datetime.utcnow()
        run.progress_pct = 100.0
        await session.commit()

    log.info(f"Safety run {run_id} completed: {passed_count}P / {failed_count}F / {warning_count}W / {error_count}E")


def _resolve_llm_backend(backend_name: str):
    """Resolve an LLM backend instance by name string."""
    from backend.app.config import settings

    if backend_name.startswith("ollama:"):
        from backend.app.llm.ollama import OllamaBackend
        model = backend_name.split(":", 1)[1]
        return OllamaBackend(model=model, base_url=settings.ollama_base_url)
    elif backend_name.startswith("openai:"):
        from backend.app.llm.openai_audio import OpenAIAudioBackend
        model = backend_name.split(":", 1)[1]
        return OpenAIAudioBackend(model=model, api_key=settings.openai_api_key)
    elif backend_name.startswith("anthropic:"):
        from backend.app.llm.anthropic_backend import AnthropicBackend
        model = backend_name.split(":", 1)[1]
        return AnthropicBackend(model=model, api_key=settings.anthropic_api_key)
    elif backend_name.startswith("gemini:"):
        from backend.app.llm.gemini import GeminiBackend
        model = backend_name.split(":", 1)[1]
        return GeminiBackend(model=model, api_key=settings.google_api_key)
    else:
        raise ValueError(
            f"Unknown backend: {backend_name}. "
            "Use format 'provider:model' (e.g., 'ollama:llama3', 'anthropic:claude-haiku-4-5-20251001')"
        )


def _resolve_judge_backend():
    """Resolve the judge LLM backend (used by monitoring agents).

    Defaults to Anthropic Claude Haiku for cost-effective judging.
    Falls back to the configured default backend.
    """
    from backend.app.config import settings

    if settings.anthropic_api_key:
        from backend.app.llm.anthropic_backend import AnthropicBackend
        return AnthropicBackend(
            model="claude-haiku-4-5-20251001",
            api_key=settings.anthropic_api_key,
        )
    elif settings.openai_api_key:
        from backend.app.llm.openai_audio import OpenAIAudioBackend
        return OpenAIAudioBackend(model="gpt-4o-mini", api_key=settings.openai_api_key)
    else:
        return _resolve_llm_backend(settings.default_llm_backend)
