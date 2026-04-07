"""Statistical analysis for test results."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def accuracy_by_group(
    df: pd.DataFrame,
    group_col: str,
    score_col: str = "eval_score",
    passed_col: str = "eval_passed",
) -> pd.DataFrame:
    """Compute accuracy metrics grouped by a parameter.

    Returns DataFrame with columns: group, mean_score, pass_rate, count,
    score_ci_low, score_ci_high, pass_ci_low, pass_ci_high (95% CIs).
    """
    results = []
    for group_val, group_df in df.groupby(group_col):
        scores = group_df[score_col].dropna()
        passed = group_df[passed_col].dropna()
        n = len(scores)
        if n == 0:
            continue

        mean_score = scores.mean()
        pass_rate = passed.mean()

        # 95% CI for mean score (bootstrap if n < 30, t-distribution otherwise)
        if n >= 30:
            se = scores.std(ddof=1) / np.sqrt(n)
            ci = stats.t.interval(0.95, df=n - 1, loc=mean_score, scale=se)
        else:
            ci = _bootstrap_ci(scores.values, np.mean)

        # Wilson score CI for pass rate (better for proportions than normal approx)
        pass_ci = _wilson_ci(int(passed.sum()), n)

        results.append({
            "group": group_val,
            "mean_score": mean_score,
            "pass_rate": pass_rate,
            "count": n,
            "score_ci_low": ci[0],
            "score_ci_high": ci[1],
            "pass_ci_low": pass_ci[0],
            "pass_ci_high": pass_ci[1],
        })

    return pd.DataFrame(results)


def _wilson_ci(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score confidence interval for a proportion."""
    if n == 0:
        return (0.0, 1.0)
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    p_hat = successes / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    spread = z * np.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))


def _bootstrap_ci(
    data: np.ndarray, stat_func, n_bootstrap: int = 10000, confidence: float = 0.95
) -> tuple[float, float]:
    """Bootstrap confidence interval."""
    rng = np.random.default_rng(42)
    boot_stats = np.array([
        stat_func(rng.choice(data, size=len(data), replace=True))
        for _ in range(n_bootstrap)
    ])
    alpha = (1 - confidence) / 2
    return (float(np.percentile(boot_stats, 100 * alpha)),
            float(np.percentile(boot_stats, 100 * (1 - alpha))))


def pairwise_backend_comparison(
    df: pd.DataFrame,
    backend_col: str = "llm_backend",
    passed_col: str = "eval_passed",
    score_col: str = "eval_score",
) -> pd.DataFrame:
    """Pairwise statistical comparison between backends.

    Uses McNemar's test for binary pass/fail and Wilcoxon signed-rank for scores.
    Only compares on test cases that both backends have results for.
    """
    backends = df[backend_col].unique()
    results = []

    for i, b1 in enumerate(backends):
        for b2 in backends[i + 1:]:
            df1 = df[df[backend_col] == b1].set_index("test_case_id")
            df2 = df[df[backend_col] == b2].set_index("test_case_id")
            common = df1.index.intersection(df2.index)

            if len(common) < 10:
                continue

            # McNemar's test on pass/fail
            p1 = df1.loc[common, passed_col].astype(bool)
            p2 = df2.loc[common, passed_col].astype(bool)
            b = (p1 & ~p2).sum()  # b1 pass, b2 fail
            c = (~p1 & p2).sum()  # b1 fail, b2 pass

            if b + c > 0:
                mcnemar_stat = (abs(b - c) - 1) ** 2 / (b + c) if b + c > 25 else None
                mcnemar_p = stats.binomtest(int(b), int(b + c), 0.5).pvalue if b + c <= 25 else (
                    1 - stats.chi2.cdf(mcnemar_stat, 1) if mcnemar_stat else 1.0
                )
            else:
                mcnemar_p = 1.0

            # Wilcoxon signed-rank on scores
            s1 = df1.loc[common, score_col].values
            s2 = df2.loc[common, score_col].values
            diff = s1 - s2
            nonzero = diff[diff != 0]
            if len(nonzero) >= 10:
                wilcoxon_stat, wilcoxon_p = stats.wilcoxon(nonzero)
            else:
                wilcoxon_p = 1.0

            results.append({
                "backend_1": b1,
                "backend_2": b2,
                "n_common": len(common),
                "pass_rate_1": p1.mean(),
                "pass_rate_2": p2.mean(),
                "mean_score_1": s1.mean(),
                "mean_score_2": s2.mean(),
                "mcnemar_p": mcnemar_p,
                "wilcoxon_p": wilcoxon_p,
                "significant_0.05": mcnemar_p < 0.05 or wilcoxon_p < 0.05,
            })

    result_df = pd.DataFrame(results)

    # Holm-Bonferroni correction for multiple comparisons
    if len(result_df) > 1:
        for col in ("mcnemar_p", "wilcoxon_p"):
            adj_col = f"{col}_adjusted"
            pvals = result_df[col].values.copy()
            n = len(pvals)
            order = np.argsort(pvals)
            adjusted = np.ones(n)
            for rank, idx in enumerate(order):
                adjusted[idx] = min(pvals[idx] * (n - rank), 1.0)
            # Enforce monotonicity: adjusted[order[i]] >= adjusted[order[i-1]]
            for i in range(1, n):
                adjusted[order[i]] = max(adjusted[order[i]], adjusted[order[i - 1]])
            result_df[adj_col] = adjusted

    return result_df


def parameter_effects_anova(
    df: pd.DataFrame,
    factors: list[str],
    score_col: str = "eval_score",
) -> dict:
    """One-way ANOVA for each factor to quantify effect on score.

    Returns dict of factor -> {F_statistic, p_value, eta_squared}.
    """
    results = {}
    for factor in factors:
        groups = [group[score_col].dropna().values for _, group in df.groupby(factor)]
        groups = [g for g in groups if len(g) >= 2]
        if len(groups) < 2:
            continue

        f_stat, p_val = stats.f_oneway(*groups)

        # Eta-squared (effect size)
        grand_mean = df[score_col].mean()
        ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in groups)
        ss_total = sum(((g - grand_mean) ** 2).sum() for g in groups)
        eta_sq = ss_between / ss_total if ss_total > 0 else 0

        results[factor] = {
            "F_statistic": float(f_stat),
            "p_value": float(p_val),
            "eta_squared": float(eta_sq),
            "n_groups": len(groups),
        }

    return results


def wer_by_group(
    df: pd.DataFrame,
    group_col: str,
    wer_col: str = "wer",
) -> pd.DataFrame:
    """Compute mean WER grouped by a parameter.

    Returns DataFrame with columns: group, mean_wer, count, wer_ci_low, wer_ci_high.
    Only includes rows where WER is available (Pipeline B with ASR transcripts).
    """
    wer_df = df[df[wer_col].notna()].copy() if wer_col in df.columns else pd.DataFrame()
    if wer_df.empty or group_col not in wer_df.columns:
        return pd.DataFrame()

    results = []
    for group_val, group_df in wer_df.groupby(group_col):
        wers = group_df[wer_col].dropna()
        n = len(wers)
        if n == 0:
            continue

        mean_wer = wers.mean()
        if n >= 30:
            se = wers.std(ddof=1) / np.sqrt(n)
            ci = stats.t.interval(0.95, df=n - 1, loc=mean_wer, scale=se)
        else:
            ci = _bootstrap_ci(wers.values, np.mean)

        results.append({
            "group": group_val,
            "mean_wer": float(mean_wer),
            "count": n,
            "wer_ci_low": float(max(0.0, ci[0])),
            "wer_ci_high": float(ci[1]),
        })

    return pd.DataFrame(results)


def summary_statistics(df: pd.DataFrame) -> dict:
    """Compute overall summary statistics for a results DataFrame."""
    out: dict = {
        "total_tests": len(df),
        "completed": int(df["eval_score"].notna().sum()),
        "errors": int(df["error"].notna().sum()),
        "overall_pass_rate": float(df["eval_passed"].mean()) if "eval_passed" in df and df["eval_passed"].notna().any() else None,
        "overall_mean_score": float(df["eval_score"].mean()) if "eval_score" in df and df["eval_score"].notna().any() else None,
        "mean_latency_ms": float(df["total_latency_ms"].mean()) if "total_latency_ms" in df and df["total_latency_ms"].notna().any() else None,
        "median_latency_ms": float(df["total_latency_ms"].median()) if "total_latency_ms" in df and df["total_latency_ms"].notna().any() else None,
    }
    # WER summary — only for Pipeline B rows that have ASR transcripts
    if "wer" in df.columns and df["wer"].notna().any():
        wer_series = df["wer"].dropna()
        out["mean_wer"] = float(wer_series.mean())
        out["median_wer"] = float(wer_series.median())
        out["wer_sample_size"] = int(len(wer_series))
    return out
