"""Tests for statistical analysis and aggregation modules."""

import numpy as np
import pandas as pd
import pytest
import tempfile
import os

from backend.app.stats.analysis import (
    accuracy_by_group,
    pairwise_backend_comparison,
    parameter_effects_anova,
    summary_statistics,
    _wilson_ci,
    _bootstrap_ci,
)
from backend.app.stats.aggregation import (
    build_results_dataframe,
    pivot_heatmap,
    sweep_summary,
    export_results,
)


def _make_results_df(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Generate a synthetic results DataFrame for testing."""
    rng = np.random.default_rng(seed)
    backends = ["openai:gpt-4o", "gemini:flash", "anthropic:claude"]
    snr_values = [-5.0, 0.0, 5.0, 10.0, 20.0]
    delay_values = [0.0, 50.0, 100.0, 200.0]

    rows = []
    for i in range(n):
        snr = rng.choice(snr_values)
        backend = rng.choice(backends)
        delay = rng.choice(delay_values)

        # Score correlates with SNR (higher SNR = better score)
        base_score = 0.3 + (snr + 10) / 40.0
        noise = rng.normal(0, 0.15)
        score = np.clip(base_score + noise, 0.0, 1.0)
        passed = score >= 0.6

        rows.append({
            "test_case_id": f"tc_{i:04d}",
            "pipeline_type": rng.choice(["direct_audio", "asr_text"]),
            "llm_backend": backend,
            "snr_db": snr,
            "delay_ms": delay,
            "gain_db": rng.choice([-60.0, -40.0, -20.0]),
            "noise_type": rng.choice(["pink_lpf", "babble"]),
            "eval_score": score,
            "eval_passed": passed,
            "total_latency_ms": 200 + rng.exponential(100),
            "error": None,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Wilson CI
# ---------------------------------------------------------------------------

class TestWilsonCI:
    def test_all_success(self):
        lo, hi = _wilson_ci(100, 100)
        assert lo > 0.95
        assert hi == 1.0 or hi == pytest.approx(1.0, abs=0.01)

    def test_all_failure(self):
        lo, hi = _wilson_ci(0, 100)
        assert lo == pytest.approx(0.0, abs=0.01)
        assert hi < 0.05

    def test_half(self):
        lo, hi = _wilson_ci(50, 100)
        assert lo < 0.5
        assert hi > 0.5

    def test_empty(self):
        lo, hi = _wilson_ci(0, 0)
        assert lo == 0.0
        assert hi == 1.0

    def test_bounds(self):
        lo, hi = _wilson_ci(7, 10)
        assert 0.0 <= lo <= hi <= 1.0


# ---------------------------------------------------------------------------
# Bootstrap CI
# ---------------------------------------------------------------------------

class TestBootstrapCI:
    def test_narrow_for_large_sample(self):
        data = np.random.default_rng(42).normal(0.5, 0.01, size=1000)
        lo, hi = _bootstrap_ci(data, np.mean)
        assert hi - lo < 0.01

    def test_contains_mean(self):
        data = np.random.default_rng(42).normal(0.7, 0.1, size=50)
        lo, hi = _bootstrap_ci(data, np.mean)
        assert lo < 0.7 < hi

    def test_reproducible(self):
        data = np.array([0.1, 0.5, 0.9])
        ci1 = _bootstrap_ci(data, np.mean)
        ci2 = _bootstrap_ci(data, np.mean)
        assert ci1 == ci2  # Same seed (42) → same result


# ---------------------------------------------------------------------------
# Accuracy by group
# ---------------------------------------------------------------------------

class TestAccuracyByGroup:
    def test_basic_grouping(self):
        df = _make_results_df()
        result = accuracy_by_group(df, "snr_db")
        assert len(result) == 5  # 5 SNR values
        assert "mean_score" in result.columns
        assert "pass_rate" in result.columns
        assert "score_ci_low" in result.columns
        assert "pass_ci_low" in result.columns

    def test_higher_snr_higher_score(self):
        df = _make_results_df(n=500)
        result = accuracy_by_group(df, "snr_db")
        result = result.sort_values("group")
        # Generally, higher SNR should mean higher scores
        scores = result["mean_score"].values
        assert scores[-1] > scores[0]

    def test_ci_bounds_valid(self):
        df = _make_results_df()
        result = accuracy_by_group(df, "llm_backend")
        for _, row in result.iterrows():
            assert row["score_ci_low"] <= row["mean_score"] <= row["score_ci_high"]
            assert row["pass_ci_low"] <= row["pass_rate"] <= row["pass_ci_high"]

    def test_by_backend(self):
        df = _make_results_df()
        result = accuracy_by_group(df, "llm_backend")
        assert len(result) == 3  # 3 backends

    def test_empty_group(self):
        df = pd.DataFrame({
            "group_col": [],
            "eval_score": [],
            "eval_passed": [],
        })
        result = accuracy_by_group(df, "group_col")
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Pairwise comparison
# ---------------------------------------------------------------------------

class TestPairwiseComparison:
    def _make_paired_df(self, n_cases: int = 50) -> pd.DataFrame:
        """Make a DataFrame where each test case has results for all backends."""
        rng = np.random.default_rng(42)
        backends = ["openai:gpt-4o", "gemini:flash", "anthropic:claude"]
        rows = []
        for i in range(n_cases):
            tc_id = f"tc_{i:04d}"
            for backend in backends:
                score = np.clip(rng.normal(0.7, 0.2), 0.0, 1.0)
                rows.append({
                    "test_case_id": tc_id,
                    "llm_backend": backend,
                    "eval_passed": score >= 0.6,
                    "eval_score": score,
                })
        return pd.DataFrame(rows)

    def test_basic_comparison(self):
        df = self._make_paired_df(50)
        result = pairwise_backend_comparison(df)
        assert len(result) == 3  # C(3,2) = 3 pairs
        assert "mcnemar_p" in result.columns
        assert "wilcoxon_p" in result.columns

    def test_p_values_valid(self):
        df = self._make_paired_df(50)
        result = pairwise_backend_comparison(df)
        for _, row in result.iterrows():
            assert 0.0 <= row["mcnemar_p"] <= 1.0
            assert 0.0 <= row["wilcoxon_p"] <= 1.0

    def test_too_few_common(self):
        """With very few common test cases, should skip."""
        df = pd.DataFrame({
            "test_case_id": ["a", "b", "c", "d"],
            "llm_backend": ["b1", "b1", "b2", "b2"],
            "eval_passed": [True, False, True, False],
            "eval_score": [0.8, 0.3, 0.7, 0.4],
        })
        result = pairwise_backend_comparison(df)
        assert len(result) == 0  # < 10 common


# ---------------------------------------------------------------------------
# ANOVA
# ---------------------------------------------------------------------------

class TestANOVA:
    def test_snr_effect(self):
        df = _make_results_df(n=500)
        result = parameter_effects_anova(df, ["snr_db"])
        assert "snr_db" in result
        assert result["snr_db"]["p_value"] < 0.05  # SNR should have clear effect
        assert result["snr_db"]["eta_squared"] > 0.0

    def test_multiple_factors(self):
        df = _make_results_df(n=500)
        result = parameter_effects_anova(df, ["snr_db", "llm_backend", "noise_type"])
        assert len(result) >= 2

    def test_single_group_skipped(self):
        df = _make_results_df()
        df["constant"] = "same"
        result = parameter_effects_anova(df, ["constant"])
        assert "constant" not in result


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

class TestSummaryStatistics:
    def test_basic(self):
        df = _make_results_df()
        result = summary_statistics(df)
        assert result["total_tests"] == 200
        assert result["completed"] > 0
        assert 0.0 <= result["overall_pass_rate"] <= 1.0
        assert 0.0 <= result["overall_mean_score"] <= 1.0
        assert result["mean_latency_ms"] > 0

    def test_no_errors(self):
        df = _make_results_df()
        result = summary_statistics(df)
        assert result["errors"] == 0  # All None errors


# ---------------------------------------------------------------------------
# Aggregation: build_results_dataframe
# ---------------------------------------------------------------------------

class TestBuildResultsDataFrame:
    def test_type_coercion(self):
        records = [
            {"eval_score": "0.85", "total_latency_ms": "200", "eval_passed": True,
             "snr_db": "10.0", "delay_ms": "50", "gain_db": "-20"},
            {"eval_score": "0.3", "total_latency_ms": "150", "eval_passed": False,
             "snr_db": "-5.0", "delay_ms": "100", "gain_db": "-40"},
        ]
        df = build_results_dataframe(records)
        assert df["eval_score"].dtype in [np.float64, float]
        assert df["snr_db"].dtype in [np.float64, float]
        assert df["eval_passed"].dtype == bool

    def test_handles_missing(self):
        records = [{"eval_score": None, "eval_passed": None}]
        df = build_results_dataframe(records)
        assert len(df) == 1


# ---------------------------------------------------------------------------
# Aggregation: pivot_heatmap
# ---------------------------------------------------------------------------

class TestPivotHeatmap:
    def test_basic_pivot(self):
        df = _make_results_df()
        pivot = pivot_heatmap(df, "snr_db", "delay_ms")
        assert pivot.shape[0] == 5  # 5 SNR values
        assert pivot.shape[1] == 4  # 4 delay values

    def test_sorted(self):
        df = _make_results_df()
        pivot = pivot_heatmap(df, "snr_db", "delay_ms")
        assert list(pivot.index) == sorted(pivot.index)

    def test_values_in_range(self):
        df = _make_results_df()
        pivot = pivot_heatmap(df, "snr_db", "delay_ms")
        for val in pivot.values.flat:
            if not np.isnan(val):
                assert 0.0 <= val <= 1.0


# ---------------------------------------------------------------------------
# Aggregation: sweep_summary
# ---------------------------------------------------------------------------

class TestSweepSummary:
    def test_basic_sweep(self):
        df = _make_results_df()
        result = sweep_summary(df, ["snr_db", "llm_backend"])
        assert len(result) > 0
        assert "eval_score_mean" in result.columns
        assert "eval_passed_mean" in result.columns


# ---------------------------------------------------------------------------
# Aggregation: export_results
# ---------------------------------------------------------------------------

class TestExportResults:
    def test_csv_export(self):
        df = _make_results_df(n=10)
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            export_results(df, f.name, "csv")
            loaded = pd.read_csv(f.name)
            assert len(loaded) == 10
        os.unlink(f.name)

    def test_json_export(self):
        df = _make_results_df(n=10)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            export_results(df, f.name, "json")
            loaded = pd.read_json(f.name)
            assert len(loaded) == 10
        os.unlink(f.name)

    def test_invalid_format(self):
        df = _make_results_df(n=10)
        with pytest.raises(ValueError):
            export_results(df, "/tmp/bad.xyz", "xyz")
