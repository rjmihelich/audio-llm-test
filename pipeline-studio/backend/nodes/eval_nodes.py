"""Evaluation and output node executors."""

from __future__ import annotations

from typing import Any

from ..engine.graph_executor import ExecutionContext, GraphNode


async def execute_eval_analysis(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Combined Evaluation & Analysis Engine.

    Runs configured evaluators and collects metrics.
    """
    text_in = inputs.get("text_in", "")
    audio_in = inputs.get("audio_in")

    evaluators = config.get("evaluators", "command_match")
    pass_threshold = config.get("pass_threshold", 0.6)
    enable_latency = config.get("enable_latency_tracking", True)

    results = {}
    scores = []

    # Prefer explicit query_in input; fall back to ctx.pipeline_input
    query_in = inputs.get("query_in", "")
    pipeline_input = ctx.pipeline_input
    if query_in and pipeline_input:
        # Override the pipeline input text with the wired query_in
        pipeline_input = type(pipeline_input)(
            original_text=str(query_in),
            **{k: v for k, v in pipeline_input.__dict__.items() if k != "original_text"},
        )

    # Command Match evaluation
    if evaluators in ("command_match", "all"):
        from backend.app.evaluation.command_match import CommandMatchEvaluator
        evaluator = CommandMatchEvaluator(pass_threshold=pass_threshold)
        from backend.app.pipeline.base import PipelineInput, PipelineResult
        from backend.app.llm.base import LLMResponse

        fake_result = PipelineResult(
            llm_response=LLMResponse(text=text_in, latency_ms=0),
            pipeline_type="graph",
        )

        eval_result = await evaluator.evaluate(pipeline_input, fake_result)
        results["command_match"] = {
            "score": eval_result.score,
            "passed": eval_result.passed,
            "details": eval_result.details,
        }
        scores.append(eval_result.score)

    # WER evaluation
    if evaluators in ("wer", "all"):
        from backend.app.evaluation.metrics import word_error_rate
        wer = word_error_rate(pipeline_input.original_text, text_in)
        wer_score = max(0, 1.0 - wer)
        results["wer"] = {
            "score": wer_score,
            "wer": wer,
            "passed": wer_score >= pass_threshold,
        }
        scores.append(wer_score)

    # LLM Judge evaluation
    if evaluators in ("llm_judge", "all"):
        try:
            from backend.app.evaluation.llm_judge import LLMJudgeEvaluator
            from backend.app.pipeline.base import PipelineResult
            from backend.app.llm.base import LLMResponse

            judge = LLMJudgeEvaluator(pass_threshold=pass_threshold)
            fake_result = PipelineResult(
                llm_response=LLMResponse(text=text_in, latency_ms=0),
                pipeline_type="graph",
            )
            eval_result = await judge.evaluate(pipeline_input, fake_result)
            results["llm_judge"] = {
                "score": eval_result.score,
                "passed": eval_result.passed,
                "details": eval_result.details,
            }
            scores.append(eval_result.score)
        except Exception as e:
            results["llm_judge"] = {"error": str(e)}

    # Aggregate
    avg_score = sum(scores) / len(scores) if scores else 0.0
    overall_passed = avg_score >= pass_threshold

    eval_output = {
        "score": avg_score,
        "passed": overall_passed,
        "evaluators": results,
        "threshold": pass_threshold,
    }

    # Latency tracking
    if enable_latency:
        eval_output["latency"] = ctx.metadata.get("latency_ms", {})

    # Binary text output: "0" = pass, "1" = fail
    return {"eval_out": eval_output, "text_out": "0" if overall_passed else "1"}


async def execute_text_output(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Text output sink — captures the text for result collection."""
    return {"_text": inputs.get("text_in", "")}


async def execute_audio_output(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Audio output sink — optionally saves to file."""
    audio = inputs.get("audio_in")
    if audio and config.get("save_to_file") and config.get("file_path"):
        from backend.app.audio.io import save_audio
        save_audio(audio, config["file_path"])
    return {"_audio": audio}


async def execute_eval_output(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Eval output sink — captures evaluation results."""
    return {"_eval": inputs.get("eval_in", {})}
