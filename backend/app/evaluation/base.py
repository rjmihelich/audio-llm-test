"""Evaluation base types and protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..pipeline.base import PipelineInput, PipelineResult


@dataclass
class EvaluationResult:
    """Result of evaluating an LLM response."""

    score: float  # 0.0 to 1.0, normalized
    passed: bool
    evaluator: str
    details: dict = field(default_factory=dict)


@runtime_checkable
class Evaluator(Protocol):
    """Interface for response evaluators."""

    @property
    def name(self) -> str: ...

    async def evaluate(
        self, input: PipelineInput, result: PipelineResult
    ) -> EvaluationResult: ...
