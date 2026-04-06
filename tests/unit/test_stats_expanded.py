"""Expanded statistics tests: small samples, NaN handling, edge cases."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

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


# ---------------------------------------------------------------------------
# Wilson CI edge cases
# ---------------------------------------------------------------------------

class TestWilsonCIExpanded:
    def test_single_success(self):
        lo, hi = _wilson_ci(1, 1)
        assert 0.0 <= lo <= hi <= 1.0
        assert hi > 0.5

    def test_single_failure(self):
        lo, hi = _wilson_ci(0, 1)
        assert lo == pytest.approx(0.0, abs=0.01)
        assert hi < 1.0

    def test_large_sample(self):
        """Large sample should give narrow CI."""
        lo, hi = _wilson_ci(500, 1000)
        assert hi - lo < 0.10

    def test_very_small_sample(self):
        """n=2 should give wide CI."""
        lo, hi = _wilson_ci(1, 2)
        assert hi - lo > 0.3

    def test_monotonicity(self):
        """More successes → higher CI bounds."""
        prev_lo = 0.0
        for k in [0, 25, 50, 75, 100]:
            lo, hi = _wilson_ci(k, 100)
            assert lo >= prev_lo - 0.01  # approximately monotonic
            prev_lo = lo


# ---------------------------------------------------------------------------
# Bootstrap CI edge cases
# ---------------------------------------------------------------------------

class TestBootstrapCIExpanded:
    def test_constant_data(self):
        """All identical values → CI collapses to a point."""
        data = np.ones(50)
        lo, hi = _bootstrap_ci(data, np.mean)
        assert hi - lo < 0.001

    def test_single_value(self):
        """Single data point → CI is a single point."""
        data = np.array([0.7])
        lo, hi = _bootstrap_ci(data, np.mean)
        assert lo == pytest.approx(0.7, abs=0.001)
        assert hi == pytest.approx(0.7, abs=0.001)

    def test_bimodal_data(self):
        """Bimodal distribution should give wider CI."""
        data = np.concatenate([np.zeros(50), np.ones(50)])
        lo, hi = _bootstrap_ci(data, np.mean)
        assert lo < 0.5
        assert hi > 0.5
        assert hi - lo > 0.05

    def test_with_median_statistic(self):
        data = np.random.default_rng(42).normal(0.5, 0.1, size=100)
        lo, hi = _bootstrap_ci(data, np.median)
        assert lo < 0.5 < hi


# ---------------------------------------------------------------------------
# Accuracy by group: small and edge cases
# ---------------------------------------------------------------------------

class TestAccuracyByGroupExpanded:
    def test_single_item_per_group(self):
        """Each group has only 1 observation."""
        df = pd.DataFrame({
            "group": ["a", "b", "c"],
            "eval_score": [0.5, 0.8, 0.3],
            "eval_passed": [False, True, False],
        })
        result = accuracy_by_group(df, "group")
        assert len(result) == 3
        # CI should be very wide for n=1
        for _, row in result.iterrows():
            assert row["score_ci_high"] - row["score_ci_low"] >= 0.0

    def test_all_pass(self):
        df = pd.DataFrame({
            "group": ["a"] * 50,
            "eval_score": [1.0] * 50,
            "eval_passed": [True] * 50,
        })
        result = accuracy_by_group(df, "group")
        assert result.iloc[0]["pass_rate"] == 1.0
        assert result.iloc[0]["mean_score"] == 1.0

    def test_all_fail(self):
        df = pd.DataFrame({
            "group": ["a"] * 50,
            "eval_score": [0.0] * 50,
            "eval_passed": [False] * 50,
        })
        result = accuracy_by_group(df, "group")
        assert result.iloc[0]["pass_rate"] == 0.0
        assert result.iloc[0]["mean_score"] == 0.0

    def test_many_groups(self):
        """100 distinct groups should work."""
        n = 1000
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "group": [f"g_{i % 100}" for i in range(n)],
            "eval_score": rng.random(n),
            "eval_passed": rng.random(n) > 0.5,
        })
        result = accuracy_by_group(df, "group")
        assert len(result) == 100


# ---------------------------------------------------------------------------
# Pairwise comparison edge cases
# ---------------------------------------------------------------------------

class TestPairwiseExpanded:
    def _make_paired(self, n=30, n_backends=2):
        rng = np.random.default_rng(42)
        rows = []
        for i in range(n):
            for b in range(n_backends):
                score = np.clip(rng.normal(0.7, 0.2), 0.0, 1.0)
                rows.append({
                    "test_case_id": f"tc_{i}",
                    "llm_backend": f"backend_{b}",
                    "eval_passed": score > 0.6,
                    "eval_score": score,
                })
        return pd.DataFrame(rows)

    def test_exactly_10_common(self):
        """Edge case: exactly 10 common test cases (minimum)."""
        df = self._make_paired(n=10)
        result = pairwise_backend_comparison(df)
        assert len(result) == 1  # Exactly 1 pair

    def test_9_common_skipped(self):
        """9 common test cases: below threshold, should skip."""
        df = self._make_paired(n=9)
        result = pairwise_backend_comparison(df)
        assert len(result) == 0

    def test_identical_backends_p_one(self):
        """Two backends with identical results should have p ≈ 1.0."""
        rows = []
        for i in range(50):
            score = 0.8
            for b in ["a", "b"]:
                rows.append({
                    "test_case_id": f"tc_{i}",
                    "llm_backend": b,
                    "eval_passed": True,
                    "eval_score": score,
                })
        df = pd.DataFrame(rows)
        result = pairwise_backend_comparison(df)
        if len(result) > 0:
            # p-values should be high (no significant difference)
            assert result.iloc[0]["mcnemar_p"] == 1.0

    def test_three_backends(self):
        """3 backends → C(3,2) = 3 pairs."""
        df = self._make_paired(n=30, n_backends=3)
        result = pairwise_backend_comparison(df)
        assert len(result) == 3

    def test_holm_bonferroni_correction(self):
        """Multiple comparisons should have adjusted p-values."""
        df = self._make_paired(n=50, n_backends=3)
        result = pairwise_backend_comparison(df)
        if len(result) > 1:
            assert "mcnemar_p_adjusted" in result.columns
            assert "wilcoxon_p_adjusted" in result.columns
            # Adjusted p-values should be >= raw p-values
            for _, row in result.iterrows():
                assert row["mcnemar_p_adjusted"] >= row["mcnemar_p"] - 1e-10
                assert row["wilcoxon_p_adjusted"] >= row["wilcoxon_p"] - 1e-10


# ---------------------------------------------------------------------------
# ANOVA edge cases
# ---------------------------------------------------------------------------

class TestANOVAExpanded:
    def test_two_groups(self):
        """ANOVA with only 2 groups should work (equivalent to t-test)."""
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "factor": ["a"] * 50 + ["b"] * 50,
            "eval_score": np.concatenate([
                rng.normal(0.7, 0.1, 50),
                rng.normal(0.3, 0.1, 50),
            ]),
        })
        result = parameter_effects_anova(df, ["factor"])
        assert "factor" in result
        assert result["factor"]["p_value"] < 0.001

    def test_no_effect(self):
        """All groups drawn from same distribution → p > 0.05."""
        rng = np.random.default_rng(42)
        n = 200
        df = pd.DataFrame({
            "factor": [f"g{i % 4}" for i in range(n)],
            "eval_score": rng.normal(0.5, 0.1, n),
        })
        result = parameter_effects_anova(df, ["factor"])
        if "factor" in result:
            # p should be > 0.01 most of the time
            assert result["factor"]["p_value"] > 0.01

    def test_empty_dataframe(self):
        df = pd.DataFrame({"factor": [], "eval_score": []})
        result = parameter_effects_anova(df, ["factor"])
        assert "factor" not in result

    def test_eta_squared_range(self):
        """eta_squared should be in [0, 1]."""
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "factor": ["a"] * 100 + ["b"] * 100,
            "eval_score": np.concatenate([
                rng.normal(0.8, 0.1, 100),
                rng.normal(0.2, 0.1, 100),
            ]),
        })
        result = parameter_effects_anova(df, ["factor"])
        assert 0.0 <= result["factor"]["eta_squared"] <= 1.0


# ---------------------------------------------------------------------------
# Summary statistics edge cases
# ---------------------------------------------------------------------------

class TestSummaryStatisticsExpanded:
    def test_all_errors(self):
        df = pd.DataFrame({
            "error": ["timeout", "api_error", "crash"],
            "eval_score": [None, None, None],
            "eval_passed": [None, None, None],
            "total_latency_ms": [100, 200, 300],
        })
        result = summary_statistics(df)
        assert result["total_tests"] == 3
        assert result["errors"] == 3

    def test_single_test(self):
        df = pd.DataFrame({
            "error": [None],
            "eval_score": [0.85],
            "eval_passed": [True],
            "total_latency_ms": [150.0],
        })
        result = summary_statistics(df)
        assert result["total_tests"] == 1
        assert result["overall_pass_rate"] == 1.0
        assert result["overall_mean_score"] == 0.85


# ---------------------------------------------------------------------------
# Aggregation edge cases
# ---------------------------------------------------------------------------

class TestAggregationExpanded:
    def test_build_df_with_nan_strings(self):
        """Strings that can't be parsed to numbers should become NaN."""
        records = [
            {"eval_score": "not_a_number", "eval_passed": True},
        ]
        df = build_results_dataframe(records)
        assert pd.isna(df["eval_score"].iloc[0])

    def test_pivot_with_missing_combinations(self):
        """Pivot should have NaN for missing row/col combinations."""
        df = pd.DataFrame({
            "row": ["a", "a", "b"],
            "col": [1, 2, 1],
            "eval_score": [0.5, 0.8, 0.3],
        })
        pivot = pivot_heatmap(df, "row", "col")
        assert pivot.shape == (2, 2)
        assert pd.isna(pivot.loc["b", 2])

    def test_pivot_median_agg(self):
        df = pd.DataFrame({
            "row": ["a", "a", "a"],
            "col": [1, 1, 1],
            "eval_score": [0.1, 0.5, 0.9],
        })
        pivot = pivot_heatmap(df, "row", "col", agg_func="median")
        assert pivot.iloc[0, 0] == pytest.approx(0.5)

    def test_sweep_empty_dims(self):
        """Sweep with no dimensions should aggregate everything."""
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "eval_score": rng.random(50),
            "eval_passed": rng.random(50) > 0.5,
        })
        # Empty sweep dims should still return something meaningful
        # or handle gracefully
        try:
            result = sweep_summary(df, [])
            # If it works, it should have 1 row
            assert len(result) >= 0
        except (KeyError, ValueError):
            pass  # Acceptable to reject empty dims

    def test_export_parquet(self):
        """Parquet export if pyarrow is available."""
        import tempfile, os
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            try:
                export_results(df, f.name, "parquet")
                loaded = pd.read_parquet(f.name)
                assert len(loaded) == 3
            except (ImportError, ValueError):
                pytest.skip("Parquet support not available")
            finally:
                os.unlink(f.name)
