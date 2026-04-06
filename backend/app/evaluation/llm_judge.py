"""LLM-as-judge evaluator for open-ended responses."""

from __future__ import annotations

import json
import asyncio

from ..llm.base import LLMBackend
from ..pipeline.base import PipelineInput, PipelineResult
from .base import EvaluationResult

JUDGE_PROMPT = """You are evaluating an in-car voice assistant's response to a user's spoken request.

Your job is to determine whether the assistant correctly understood the user's intent and provided an appropriate response.

User's original speech: "{original_text}"
Expected intent/behavior: "{expected_intent}"
Assistant's actual response: "{llm_response}"

Rate the response on a 1-5 scale:
1: Completely wrong, dangerous, or unrelated
2: Misunderstood the request or gave wrong information
3: Partially correct — understood some aspects but missed key parts
4: Correct response but could be better (e.g., verbose, slightly off-topic)
5: Perfect response — correctly understood intent and provided appropriate action/answer

Respond with ONLY valid JSON in this exact format:
{{"score": <integer 1-5>, "reasoning": "<brief explanation>"}}"""


class LLMJudgeEvaluator:
    """Uses a separate LLM to judge response quality."""

    def __init__(
        self,
        judge_backend: LLMBackend,
        num_judges: int = 3,
        pass_threshold: float = 0.6,
    ):
        self._judge = judge_backend
        self._num_judges = num_judges
        self._pass_threshold = pass_threshold

    @property
    def name(self) -> str:
        return f"llm_judge:{self._judge.name}"

    async def _single_judge_call(
        self, original_text: str, expected_intent: str, llm_response: str
    ) -> tuple[int, str]:
        """Make a single judge call, return (score, reasoning)."""
        prompt = JUDGE_PROMPT.format(
            original_text=original_text,
            expected_intent=expected_intent,
            llm_response=llm_response,
        )

        response = await self._judge.query_with_text(
            prompt,
            system_prompt="You are a precise evaluation judge. Respond only with valid JSON.",
        )

        try:
            parsed = json.loads(response.text.strip())
            score = int(parsed["score"])
            score = max(1, min(5, score))  # Clamp
            return score, parsed.get("reasoning", "")
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            # Try to extract a number from the response
            for char in response.text:
                if char.isdigit() and 1 <= int(char) <= 5:
                    return int(char), response.text
            return 3, f"Failed to parse judge response: {response.text[:200]}"

    async def evaluate(
        self, input: PipelineInput, result: PipelineResult
    ) -> EvaluationResult:
        if result.error or not result.llm_response:
            return EvaluationResult(
                score=0.0, passed=False, evaluator=self.name,
                details={"error": result.error or "No LLM response"},
            )

        response_text = result.llm_response.text

        # Run multiple judge calls concurrently for reliability
        judge_tasks = [
            self._single_judge_call(
                input.original_text, input.expected_intent, response_text
            )
            for _ in range(self._num_judges)
        ]
        judge_results = await asyncio.gather(*judge_tasks, return_exceptions=True)

        scores = []
        reasonings = []
        for r in judge_results:
            if isinstance(r, Exception):
                reasonings.append(f"Judge error: {r}")
            else:
                scores.append(r[0])
                reasonings.append(r[1])

        if not scores:
            return EvaluationResult(
                score=0.0, passed=False, evaluator=self.name,
                details={"error": "All judge calls failed", "reasonings": reasonings},
            )

        # Majority vote: use median score
        scores.sort()
        n = len(scores)
        if n % 2 == 1:
            median_score = scores[n // 2]
        else:
            median_score = (scores[n // 2 - 1] + scores[n // 2]) / 2.0

        # Normalize 1-5 to 0-1
        normalized = (median_score - 1) / 4.0

        return EvaluationResult(
            score=normalized,
            passed=normalized >= self._pass_threshold,
            evaluator=self.name,
            details={
                "raw_scores": scores,
                "median_score": median_score,
                "normalized_score": normalized,
                "reasonings": reasonings,
                "num_judges": self._num_judges,
            },
        )
