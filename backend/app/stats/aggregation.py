"""Aggregation utilities for multi-dimensional sweep results."""

from __future__ import annotations

import pandas as pd
import numpy as np
from itertools import product


def build_results_dataframe(result_dicts: list[dict]) -> pd.DataFrame:
    """Convert raw result records to a DataFrame with proper types."""
    df = pd.DataFrame(result_dicts)

    # Ensure numeric types
    numeric_cols = ["eval_score", "total_latency_ms", "llm_latency_ms", "noise_level_db",
                    "delay_ms", "gain_db"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "eval_passed" in df.columns:
        df["eval_passed"] = df["eval_passed"].astype(bool)

    return df


def pivot_heatmap(
    df: pd.DataFrame,
    row_col: str,
    col_col: str,
    value_col: str = "eval_score",
    agg_func: str = "mean",
) -> pd.DataFrame:
    """Create a pivot table for heatmap visualization.

    Args:
        df: Results DataFrame.
        row_col: Column for heatmap rows (e.g., "noise_level_db").
        col_col: Column for heatmap columns (e.g., "delay_ms").
        value_col: Column to aggregate.
        agg_func: Aggregation function ("mean", "median", "count").
    """
    return pd.pivot_table(
        df,
        values=value_col,
        index=row_col,
        columns=col_col,
        aggfunc=agg_func,
    ).sort_index(ascending=True)


def sweep_summary(
    df: pd.DataFrame,
    sweep_dims: list[str],
    score_col: str = "eval_score",
    passed_col: str = "eval_passed",
) -> pd.DataFrame:
    """Aggregate results across all sweep dimensions.

    Returns one row per unique combination of sweep parameters with
    mean score, pass rate, count, and latency stats.
    """
    agg_dict = {
        score_col: ["mean", "std", "count"],
        passed_col: "mean",
    }
    if "total_latency_ms" in df.columns:
        agg_dict["total_latency_ms"] = ["mean", "median"]

    grouped = df.groupby(sweep_dims).agg(agg_dict)
    grouped.columns = ["_".join(col).strip("_") for col in grouped.columns]
    return grouped.reset_index()


def export_results(df: pd.DataFrame, path: str, format: str = "csv"):
    """Export results to file."""
    if format == "csv":
        df.to_csv(path, index=False)
    elif format == "parquet":
        df.to_parquet(path, index=False)
    elif format == "json":
        df.to_json(path, orient="records", indent=2)
    else:
        raise ValueError(f"Unsupported format: {format}")
