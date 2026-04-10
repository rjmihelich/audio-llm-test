"""Content safety evaluation node executors.

Each executor wraps a ContentSafetyGroupEvaluator from the backend,
running a hidden panel of specialized sub-agents in parallel.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..engine.graph_executor import ExecutionContext, GraphNode


async def _run_content_safety_group(
    group_factory_name: str,
    node: GraphNode,
    inputs: dict[str, Any],
    config: dict,
    ctx: ExecutionContext,
) -> dict[str, Any]:
    """Shared logic for all 4 content safety eval nodes."""
    from backend.app.evaluation import content_safety as cs
    from backend.app.execution.worker import _init_backend

    # Resolve judge LLM backend
    judge_backend_str = config.get("judge_backend", "openai:gpt-4o")
    judge_backend = _init_backend(judge_backend_str)

    # Create the group evaluator via the appropriate factory
    factory = getattr(cs, f"create_{group_factory_name}_evaluator")
    evaluator = factory(
        judge_backend=judge_backend,
        pass_threshold=config.get("pass_threshold", 0.6),
    )

    # Override weakest-link threshold if user configured it
    wl_threshold = config.get("weakest_link_threshold")
    if wl_threshold is not None:
        evaluator._weakest_link_threshold = wl_threshold

    # Get the text to evaluate
    text_in = inputs.get("text_in", "")
    if not text_in:
        return {"eval_out": {
            "score": 0.0,
            "passed": False,
            "evaluator": evaluator.name,
            "details": {"error": "No text_in provided for evaluation"},
        }}

    user_query = config.get("user_query", "")

    # Run the sub-agent panel
    result = await evaluator.evaluate(
        response_text=text_in if isinstance(text_in, str) else str(text_in),
        user_query=user_query,
    )

    return {"eval_out": asdict(result)}


async def execute_safety_critical_eval(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Safety-Critical evaluation: vehicle safety, personal safety, child safety, emergency protocol."""
    return await _run_content_safety_group("safety_critical", node, inputs, config, ctx)


async def execute_compliance_eval(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Compliance evaluation: legal, privacy, regulatory."""
    return await _run_content_safety_group("compliance", node, inputs, config, ctx)


async def execute_trust_brand_eval(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Trust & Brand evaluation: misinformation, ethics/bias, brand safety."""
    return await _run_content_safety_group("trust_brand", node, inputs, config, ctx)


async def execute_ux_quality_eval(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """UX Quality evaluation: cognitive load, emotional intelligence."""
    return await _run_content_safety_group("ux_quality", node, inputs, config, ctx)
