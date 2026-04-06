"""Command matching evaluator — for predefined commands with expected outputs."""

from __future__ import annotations

import re

from Levenshtein import ratio as levenshtein_ratio

from ..pipeline.base import PipelineInput, PipelineResult
from .base import EvaluationResult


# ---------------------------------------------------------------------------
# Multi-language stop words
# ---------------------------------------------------------------------------

STOP_WORDS: dict[str, set[str]] = {
    "en": {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "to", "in", "on", "at", "for", "of", "and", "or", "it", "i", "me",
        "my", "you", "your", "he", "she", "we", "they", "this", "that",
        "with", "from", "by", "as", "but", "not", "so", "if", "do", "does",
        "did", "has", "have", "had", "will", "would", "can", "could",
    },
    "de": {
        "der", "die", "das", "ein", "eine", "und", "ist", "sind", "war",
        "zu", "in", "auf", "an", "für", "von", "mit", "den", "dem", "des",
        "er", "sie", "es", "ich", "wir", "ihr", "aber", "oder", "wenn",
        "zum", "zur", "im", "am",
    },
    "fr": {
        "le", "la", "les", "un", "une", "des", "et", "est", "sont", "de",
        "du", "au", "aux", "en", "dans", "sur", "pour", "avec", "par",
        "il", "elle", "je", "nous", "vous", "ils", "elles", "ce", "cette",
        "mais", "ou", "si",
    },
    "es": {
        "el", "la", "los", "las", "un", "una", "de", "del", "en", "y",
        "es", "son", "a", "al", "por", "para", "con", "que", "se", "su",
        "yo", "tu", "él", "ella", "nosotros", "pero", "o", "si",
    },
    "ja": {
        "の", "に", "は", "を", "た", "が", "で", "て", "と", "し",
        "れ", "さ", "ある", "いる", "も", "する", "から", "な", "こと",
        "として", "い", "や", "など", "なっ", "ない", "この", "ため",
    },
}


def _get_stop_words(lang: str = "en") -> set[str]:
    """Return stop words for a language, falling back to English."""
    return STOP_WORDS.get(lang, STOP_WORDS["en"])


# ---------------------------------------------------------------------------
# Negation detection
# ---------------------------------------------------------------------------

NEGATION_PATTERNS: dict[str, list[str]] = {
    "en": [
        r"\bno\b", r"\bnot\b", r"\bnever\b",
        r"\bdon'?t\b", r"\bdont\b", r"\bdoesn'?t\b", r"\bdoesnt\b",
        r"\bcan'?t\b", r"\bcant\b", r"\bcannot\b",
        r"\bwon'?t\b", r"\bwont\b", r"\bwouldn'?t\b",
        r"\bisn'?t\b", r"\bisnt\b", r"\baren'?t\b", r"\barent\b",
        r"\bunable\b", r"\brefuse\b",
        r"\bsorry\b.*\b(?:can'?t|cannot|unable|won'?t)\b",
    ],
    "de": [
        r"\bnicht\b", r"\bkein\b", r"\bkeine\b", r"\bkeinen\b",
        r"\bnie\b", r"\bniemals\b",
    ],
    "fr": [
        r"\bne\b.*\bpas\b", r"\bne\b.*\bjamais\b",
        r"\bnon\b", r"\baucun\b",
    ],
    "es": [
        r"\bno\b", r"\bnunca\b", r"\bjamás\b",
        r"\bningún\b", r"\bninguno\b",
    ],
}


def _detect_negation(text: str, lang: str = "en") -> bool:
    """Detect negation in text using language-specific patterns."""
    lowered = text.lower()
    patterns = NEGATION_PATTERNS.get(lang, NEGATION_PATTERNS["en"])
    for pattern in patterns:
        if re.search(pattern, lowered):
            return True
    return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, strip punctuation, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _keyword_score(response: str, expected: str, lang: str = "en") -> float:
    """Score based on presence of key words from expected in response."""
    expected_words = set(_normalize(expected).split())
    response_words = set(_normalize(response).split())
    stop_words = _get_stop_words(lang)
    expected_words -= stop_words
    if not expected_words:
        return 1.0
    matches = expected_words & response_words
    return len(matches) / len(expected_words)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class CommandMatchEvaluator:
    """Evaluates LLM response by matching against expected actions/intents."""

    def __init__(
        self,
        fuzzy_threshold: float = 0.8,
        keyword_threshold: float = 0.6,
        pass_threshold: float = 0.6,
        negation_penalty: float = 0.5,
        lang: str = "en",
    ):
        self._fuzzy_threshold = fuzzy_threshold
        self._keyword_threshold = keyword_threshold
        self._pass_threshold = pass_threshold
        self._negation_penalty = negation_penalty
        self._lang = lang

    @property
    def name(self) -> str:
        return "command_match"

    async def evaluate(
        self, input: PipelineInput, result: PipelineResult
    ) -> EvaluationResult:
        if result.error or not result.llm_response:
            return EvaluationResult(
                score=0.0, passed=False, evaluator=self.name,
                details={"error": result.error or "No LLM response"},
            )

        response_text = result.llm_response.text
        expected = input.expected_action or input.expected_intent

        if not expected:
            return EvaluationResult(
                score=0.0, passed=False, evaluator=self.name,
                details={"error": "No expected action or intent provided"},
            )

        # 1. Exact normalized match (word-boundary)
        norm_response = _normalize(response_text)
        norm_expected = _normalize(expected)
        exact_match = bool(
            re.search(r'(?:^|\s)' + re.escape(norm_expected) + r'(?:\s|$)', norm_response)
        )

        # 2. Fuzzy match (Levenshtein)
        fuzzy_score = levenshtein_ratio(norm_response, norm_expected)

        # 3. Keyword match
        keyword_score = _keyword_score(response_text, expected, lang=self._lang)

        # Take the best score
        best_score = max(
            1.0 if exact_match else 0.0,
            fuzzy_score,
            keyword_score,
        )

        # 4. Negation detection
        negated = _detect_negation(response_text, lang=self._lang)
        if negated:
            best_score *= (1.0 - self._negation_penalty)

        return EvaluationResult(
            score=best_score,
            passed=best_score >= self._pass_threshold,
            evaluator=self.name,
            details={
                "exact_match": exact_match,
                "fuzzy_score": fuzzy_score,
                "keyword_score": keyword_score,
                "best_score": best_score,
                "negated": negated,
                "response_normalized": norm_response[:500],
                "expected_normalized": norm_expected[:500],
            },
        )
