"""Test results query and analysis API endpoints."""

from __future__ import annotations

import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd

from backend.app.config import settings
from backend.app.models.base import get_session
from backend.app.models.run import TestResult, TestRun
from backend.app.models.test import TestCase
from backend.app.models.speech import SpeechSample, CorpusEntry
from backend.app.stats.analysis import (
    accuracy_by_group,
    pairwise_backend_comparison,
    parameter_effects_anova,
    summary_statistics,
)
from backend.app.stats.aggregation import pivot_heatmap

router = APIRouter()


class ResultResponse(BaseModel):
    test_case_id: str
    pipeline_type: str
    llm_backend: str
    snr_db: float
    speech_level_db: float
    delay_ms: float
    gain_db: float
    noise_type: str
    original_text: str | None = None
    expected_intent: str | None = None
    expected_action: str | None = None
    llm_response_text: str | None = None
    asr_transcript: str | None = None
    eval_score: float | None = None
    eval_passed: bool | None = None
    evaluator_type: str | None = None
    total_latency_ms: float | None = None
    error: str | None = None
    error_stage: str | None = None


class StatsResponse(BaseModel):
    total_tests: int
    completed: int
    errors: int
    overall_pass_rate: float | None
    overall_mean_score: float | None
    mean_latency_ms: float | None
    accuracy_by_snr: list[dict] | None = None
    accuracy_by_backend: list[dict] | None = None
    backend_comparison: list[dict] | None = None
    parameter_effects: dict | None = None


class HeatmapResponse(BaseModel):
    row_labels: list[float]
    col_labels: list[float]
    values: list[list[float | None]]
    row_name: str
    col_name: str


async def _load_results_for_run(
    session: AsyncSession, run_id: uuid.UUID
) -> list[dict]:
    """Load all results for a run joined with test case params, returned as dicts."""
    stmt = (
        select(TestResult, TestCase, CorpusEntry)
        .join(TestCase, TestResult.test_case_id == TestCase.id)
        .outerjoin(SpeechSample, TestCase.speech_sample_id == SpeechSample.id)
        .outerjoin(CorpusEntry, SpeechSample.corpus_entry_id == CorpusEntry.id)
        .where(TestResult.test_run_id == run_id)
    )
    result = await session.execute(stmt)
    rows = result.all()

    records = []
    for tr, tc, ce in rows:
        records.append({
            "test_case_id": str(tc.id),
            "pipeline_type": tc.pipeline,
            "llm_backend": tc.llm_backend,
            "snr_db": tc.snr_db,
            "speech_level_db": getattr(tc, "speech_level_db", None) or 0.0,
            "delay_ms": tc.delay_ms,
            "gain_db": tc.gain_db,
            "noise_type": tc.noise_type,
            "original_text": ce.text if ce else None,
            "expected_intent": ce.expected_intent if ce else None,
            "expected_action": ce.expected_action if ce else None,
            "llm_response_text": tr.llm_response_text,
            "asr_transcript": tr.asr_transcript,
            "eval_score": tr.evaluation_score,
            "eval_passed": tr.evaluation_passed,
            "evaluator_type": tr.evaluator_type,
            "total_latency_ms": tr.llm_latency_ms,
            "error": getattr(tr, "error", None) or ((tr.evaluation_details_json or {}).get("error") if tr.evaluation_details_json else None),
            "error_stage": getattr(tr, "error_stage", None),
        })
    return records


@router.get("", response_model=list[ResultResponse])
async def query_results(
    run_id: str | None = None,
    suite_id: str | None = None,
    llm_backend: str | None = None,
    pipeline: str | None = None,
    snr_db: float | None = None,
    passed: bool | None = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """Query test results with filtering and pagination."""
    stmt = (
        select(TestResult, TestCase, CorpusEntry)
        .join(TestCase, TestResult.test_case_id == TestCase.id)
        .outerjoin(SpeechSample, TestCase.speech_sample_id == SpeechSample.id)
        .outerjoin(CorpusEntry, SpeechSample.corpus_entry_id == CorpusEntry.id)
    )

    if run_id is not None:
        stmt = stmt.where(TestResult.test_run_id == uuid.UUID(run_id))
    if suite_id is not None:
        stmt = stmt.where(TestCase.test_suite_id == uuid.UUID(suite_id))
    if llm_backend is not None:
        stmt = stmt.where(TestCase.llm_backend == llm_backend)
    if pipeline is not None:
        stmt = stmt.where(TestCase.pipeline == pipeline)
    if snr_db is not None:
        stmt = stmt.where(TestCase.snr_db == snr_db)
    if passed is not None:
        stmt = stmt.where(TestResult.evaluation_passed == passed)

    stmt = stmt.offset(offset).limit(limit)

    result = await session.execute(stmt)
    rows = result.all()

    return [
        ResultResponse(
            test_case_id=str(tc.id),
            pipeline_type=tc.pipeline,
            llm_backend=tc.llm_backend,
            snr_db=tc.snr_db or 0.0,
            speech_level_db=getattr(tc, "speech_level_db", None) or 0.0,
            delay_ms=tc.delay_ms or 0.0,
            gain_db=tc.gain_db or 0.0,
            noise_type=tc.noise_type or "",
            original_text=ce.text if ce else None,
            expected_intent=ce.expected_intent if ce else None,
            expected_action=ce.expected_action if ce else None,
            llm_response_text=tr.llm_response_text,
            asr_transcript=tr.asr_transcript,
            eval_score=tr.evaluation_score,
            eval_passed=tr.evaluation_passed,
            evaluator_type=tr.evaluator_type,
            total_latency_ms=tr.llm_latency_ms,
            error=getattr(tr, "error", None) or ((tr.evaluation_details_json or {}).get("error") if tr.evaluation_details_json else None),
            error_stage=getattr(tr, "error_stage", None),
        )
        for tr, tc, ce in rows
    ]


class DashboardResponse(BaseModel):
    """Aggregated dashboard data across all completed runs."""
    total_runs: int
    total_cases: int
    overall_pass_rate: float | None
    overall_mean_score: float | None
    mean_latency_ms: float | None
    accuracy_by_snr: list[dict] | None = None
    accuracy_by_speech_level: list[dict] | None = None
    accuracy_by_noise: list[dict] | None = None
    accuracy_by_backend: list[dict] | None = None
    echo_heatmap: dict | None = None
    speech_level_heatmap: dict | None = None
    latency_by_backend: list[dict] | None = None
    parameter_effects: dict | None = None
    run_history: list[dict] | None = None


@router.get("/dashboard/aggregate", response_model=DashboardResponse)
async def get_dashboard_aggregate(
    session: AsyncSession = Depends(get_session),
):
    """Get aggregated dashboard metrics across all completed runs."""
    # Find all completed runs
    run_stmt = select(TestRun).where(TestRun.status == "completed")
    run_result = await session.execute(run_stmt)
    completed_runs = run_result.scalars().all()

    if not completed_runs:
        return DashboardResponse(
            total_runs=0,
            total_cases=0,
            overall_pass_rate=None,
            overall_mean_score=None,
            mean_latency_ms=None,
        )

    # Load results from all completed runs
    all_records = []
    for run in completed_runs:
        records = await _load_results_for_run(session, run.id)
        for r in records:
            r["run_id"] = str(run.id)
            r["run_started_at"] = run.started_at.isoformat() if run.started_at else None
        all_records.extend(records)

    if not all_records:
        return DashboardResponse(
            total_runs=len(completed_runs),
            total_cases=0,
            overall_pass_rate=None,
            overall_mean_score=None,
            mean_latency_ms=None,
        )

    df = pd.DataFrame(all_records)

    # Summary
    summary = summary_statistics(df)

    # Accuracy by SNR
    snr_acc = accuracy_by_group(df, "snr_db") if "snr_db" in df.columns and df["snr_db"].nunique() > 1 else pd.DataFrame()

    # Accuracy by speech level
    speech_level_acc = accuracy_by_group(df, "speech_level_db") if "speech_level_db" in df.columns and df["speech_level_db"].nunique() > 1 else pd.DataFrame()

    # Accuracy by noise type
    noise_acc = accuracy_by_group(df, "noise_type") if "noise_type" in df.columns and df["noise_type"].nunique() > 1 else pd.DataFrame()

    # Accuracy by backend
    backend_acc = accuracy_by_group(df, "llm_backend") if "llm_backend" in df.columns and df["llm_backend"].nunique() > 1 else pd.DataFrame()

    # Echo heatmap (delay_ms vs gain_db)
    echo_heatmap = None
    if "delay_ms" in df.columns and "gain_db" in df.columns:
        if df["delay_ms"].nunique() > 1 and df["gain_db"].nunique() > 1:
            pivot = pivot_heatmap(df, "delay_ms", "gain_db", value_col="eval_score")
            echo_heatmap = {
                "row_labels": [float(x) for x in pivot.index.tolist()],
                "col_labels": [float(x) for x in pivot.columns.tolist()],
                "values": [
                    [None if pd.isna(v) else float(v) for v in row]
                    for row in pivot.values.tolist()
                ],
                "row_name": "delay_ms",
                "col_name": "gain_db",
            }

    # Speech level heatmap (snr_db vs speech_level_db)
    speech_level_heatmap = None
    if "speech_level_db" in df.columns and "snr_db" in df.columns:
        if df["speech_level_db"].nunique() > 1 and df["snr_db"].nunique() > 1:
            pivot_sl = pivot_heatmap(df, "speech_level_db", "snr_db", value_col="eval_score")
            speech_level_heatmap = {
                "row_labels": [float(x) for x in pivot_sl.index.tolist()],
                "col_labels": [float(x) for x in pivot_sl.columns.tolist()],
                "values": [
                    [None if pd.isna(v) else float(v) for v in row]
                    for row in pivot_sl.values.tolist()
                ],
                "row_name": "speech_level_db",
                "col_name": "snr_db",
            }

    # Latency by backend
    latency_data = None
    if "total_latency_ms" in df.columns and "llm_backend" in df.columns:
        lat_groups = df.groupby("llm_backend")["total_latency_ms"].agg(
            ["mean", "median", "std", "count"]
        ).reset_index()
        lat_groups.columns = ["backend", "mean_ms", "median_ms", "std_ms", "count"]
        latency_data = lat_groups.to_dict("records")

    # Parameter effects
    factors = [c for c in ["snr_db", "speech_level_db", "delay_ms", "gain_db", "noise_type", "llm_backend", "pipeline_type"] if c in df.columns]
    param_effects = parameter_effects_anova(df, factors) if factors else None

    # Run history: per-run pass rate over time
    run_history = []
    for run in completed_runs:
        run_df = df[df["run_id"] == str(run.id)]
        if not run_df.empty and "eval_passed" in run_df.columns:
            run_history.append({
                "run_id": str(run.id)[:8],
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "total_cases": len(run_df),
                "pass_rate": float(run_df["eval_passed"].mean()),
                "mean_score": float(run_df["eval_score"].mean()) if "eval_score" in run_df.columns else None,
                "mean_latency_ms": float(run_df["total_latency_ms"].mean()) if "total_latency_ms" in run_df.columns and run_df["total_latency_ms"].notna().any() else None,
            })

    return DashboardResponse(
        total_runs=len(completed_runs),
        total_cases=len(all_records),
        overall_pass_rate=summary.get("overall_pass_rate"),
        overall_mean_score=summary.get("overall_mean_score"),
        mean_latency_ms=summary.get("mean_latency_ms"),
        accuracy_by_snr=snr_acc.to_dict("records") if not snr_acc.empty else None,
        accuracy_by_speech_level=speech_level_acc.to_dict("records") if not speech_level_acc.empty else None,
        accuracy_by_noise=noise_acc.to_dict("records") if not noise_acc.empty else None,
        accuracy_by_backend=backend_acc.to_dict("records") if not backend_acc.empty else None,
        echo_heatmap=echo_heatmap,
        speech_level_heatmap=speech_level_heatmap,
        latency_by_backend=latency_data,
        parameter_effects=param_effects,
        run_history=run_history if run_history else None,
    )


@router.get("/{run_id}/stats", response_model=StatsResponse)
async def get_run_stats(
    run_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get statistical analysis for a test run."""
    run_uuid = uuid.UUID(run_id)

    # Verify run exists
    run_stmt = select(TestRun).where(TestRun.id == run_uuid)
    run_result = await session.execute(run_stmt)
    run = run_result.scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Run not found")

    records = await _load_results_for_run(session, run_uuid)
    if not records:
        return StatsResponse(
            total_tests=0,
            completed=0,
            errors=0,
            overall_pass_rate=None,
            overall_mean_score=None,
            mean_latency_ms=None,
        )

    df = pd.DataFrame(records)

    # Summary statistics
    summary = summary_statistics(df)

    # Accuracy by SNR
    snr_df = accuracy_by_group(df, "snr_db")
    accuracy_by_snr = snr_df.to_dict("records") if not snr_df.empty else None

    # Accuracy by backend
    backend_df = accuracy_by_group(df, "llm_backend")
    accuracy_by_backend = backend_df.to_dict("records") if not backend_df.empty else None

    # Pairwise backend comparison
    comparison_df = pairwise_backend_comparison(df)
    backend_comparison = comparison_df.to_dict("records") if not comparison_df.empty else None

    # Parameter effects ANOVA
    factors = [c for c in ["snr_db", "speech_level_db", "delay_ms", "gain_db", "noise_type", "llm_backend", "pipeline_type"] if c in df.columns]
    param_effects = parameter_effects_anova(df, factors) if factors else None

    return StatsResponse(
        total_tests=summary["total_tests"],
        completed=int(summary["completed"]),
        errors=int(summary["errors"]),
        overall_pass_rate=summary.get("overall_pass_rate"),
        overall_mean_score=summary.get("overall_mean_score"),
        mean_latency_ms=summary.get("mean_latency_ms"),
        accuracy_by_snr=accuracy_by_snr,
        accuracy_by_backend=accuracy_by_backend,
        backend_comparison=backend_comparison,
        parameter_effects=param_effects,
    )


@router.get("/{run_id}/heatmap", response_model=HeatmapResponse)
async def get_heatmap(
    run_id: str,
    row_param: str = Query(default="snr_db"),
    col_param: str = Query(default="delay_ms"),
    llm_backend: str | None = None,
    pipeline: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Get heatmap data for two-parameter sweep visualization."""
    run_uuid = uuid.UUID(run_id)

    # Verify run exists
    run_stmt = select(TestRun).where(TestRun.id == run_uuid)
    run_result = await session.execute(run_stmt)
    run = run_result.scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Run not found")

    records = await _load_results_for_run(session, run_uuid)
    if not records:
        raise HTTPException(404, "No results found for this run")

    df = pd.DataFrame(records)

    # Apply optional filters
    if llm_backend is not None:
        df = df[df["llm_backend"] == llm_backend]
    if pipeline is not None:
        df = df[df["pipeline_type"] == pipeline]

    if df.empty:
        raise HTTPException(404, "No results match the filters")

    pivot = pivot_heatmap(df, row_param, col_param, value_col="eval_score")

    row_labels = [float(x) for x in pivot.index.tolist()]
    col_labels = [float(x) for x in pivot.columns.tolist()]
    values = [
        [None if pd.isna(v) else float(v) for v in row]
        for row in pivot.values.tolist()
    ]

    return HeatmapResponse(
        row_labels=row_labels,
        col_labels=col_labels,
        values=values,
        row_name=row_param,
        col_name=col_param,
    )


@router.get("/{run_id}/export")
async def export_results(
    run_id: str,
    format: str = Query(default="csv", pattern="^(csv|parquet|json)$"),
    session: AsyncSession = Depends(get_session),
):
    """Export all results for a run as CSV, Parquet, or JSON."""
    run_uuid = uuid.UUID(run_id)

    # Verify run exists
    run_stmt = select(TestRun).where(TestRun.id == run_uuid)
    run_result = await session.execute(run_stmt)
    run = run_result.scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Run not found")

    records = await _load_results_for_run(session, run_uuid)
    if not records:
        raise HTTPException(404, "No results found for this run")

    df = pd.DataFrame(records)
    buf = io.BytesIO()

    if format == "csv":
        csv_str = df.to_csv(index=False)
        buf.write(csv_str.encode("utf-8"))
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=run_{run_id}.csv"},
        )
    elif format == "json":
        json_str = df.to_json(orient="records", indent=2)
        buf.write(json_str.encode("utf-8"))
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=run_{run_id}.json"},
        )
    elif format == "parquet":
        df.to_parquet(buf, index=False)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename=run_{run_id}.parquet"},
        )


@router.get("/{run_id}/cases/{case_id}/audio")
async def get_test_case_audio(
    run_id: str,
    case_id: str,
    type: str = Query(default="degraded", pattern="^(clean|degraded|echo)$"),
    session: AsyncSession = Depends(get_session),
):
    """Stream the audio for a specific test case result.

    type: "clean" = original speech, "degraded" = with noise/echo, "echo" = just echo component
    """
    case_uuid = uuid.UUID(case_id)

    # Load test case with speech sample
    stmt = select(TestCase).where(TestCase.id == case_uuid)
    result = await session.execute(stmt)
    test_case = result.scalar_one_or_none()

    if test_case is None:
        raise HTTPException(404, "Test case not found")

    from backend.app.models.speech import SpeechSample
    from pathlib import Path

    sample_stmt = select(SpeechSample).where(SpeechSample.id == test_case.speech_sample_id)
    sample_result = await session.execute(sample_stmt)
    sample = sample_result.scalar_one_or_none()

    if sample is None:
        raise HTTPException(404, "Speech sample not found")

    # Determine file path based on type
    if type == "clean":
        file_path = Path(sample.file_path)
    else:
        # degraded/echo audio stored alongside the clean sample
        base_path = Path(sample.file_path)
        file_path = base_path.parent / f"{base_path.stem}_{type}_{case_id}{base_path.suffix}"

    if not file_path.exists():
        raise HTTPException(404, "Audio file not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type="audio/wav",
        filename=f"{case_id}_{type}.wav",
    )
