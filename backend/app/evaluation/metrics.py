"""Quantitative metrics: WER, CER, and utilities."""

from __future__ import annotations

import re


def _normalize_for_wer(text: str) -> list[str]:
    """Normalize text for WER calculation."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    return text.split()


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Compute Word Error Rate (WER) using Levenshtein distance on words.

    WER = (substitutions + insertions + deletions) / len(reference)
    Returns 0.0 for perfect match, can exceed 1.0 if hypothesis is much longer.
    """
    ref_words = _normalize_for_wer(reference)
    hyp_words = _normalize_for_wer(hypothesis)

    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    # Dynamic programming edit distance
    n = len(ref_words)
    m = len(hyp_words)
    d = [[0] * (m + 1) for _ in range(n + 1)]

    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                d[i][j] = 1 + min(
                    d[i - 1][j],      # deletion
                    d[i][j - 1],      # insertion
                    d[i - 1][j - 1],  # substitution
                )

    return d[n][m] / n


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Compute Character Error Rate (CER) using Levenshtein distance on characters."""
    ref = reference.lower().strip()
    hyp = hypothesis.lower().strip()

    if not ref:
        return 0.0 if not hyp else 1.0

    n = len(ref)
    m = len(hyp)

    # Space-optimized: only need two rows
    prev = list(range(m + 1))
    curr = [0] * (m + 1)

    for i in range(1, n + 1):
        curr[0] = i
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                curr[j] = prev[j - 1]
            else:
                curr[j] = 1 + min(prev[j], curr[j - 1], prev[j - 1])
        prev, curr = curr, prev

    return prev[m] / n
