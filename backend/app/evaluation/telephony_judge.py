"""Comprehensive LLM-as-judge evaluators for telephony testing.

Provides multiple evaluation modes for 2-way phone call scenarios:

  1. Uplink Quality Judge  — rates clarity of near-end speech as received by
     the far end (after AEC, AGC, codec, network).
  2. Downlink Quality Judge — rates quality of far-end audio as heard by the
     car occupant (after codec + network).
  3. Speaker Attribution   — can the LLM correctly identify what each speaker
     said in a doubletalk segment?
  4. Barge-In Detection    — does the LLM correctly prioritize the near-end
     command when it interrupts an ongoing far-end utterance?
  5. Conversational Quality — can the LLM maintain context across degraded
     multi-turn conversation?

Each judge returns an EvaluationResult with mode-specific details.
"""

from __future__ import annotations

import json
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum

from ..llm.base import LLMBackend
from ..pipeline.base import PipelineInput, PipelineResult
from .base import EvaluationResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Judge mode enumeration
# ---------------------------------------------------------------------------

class TelephonyJudgeMode(str, Enum):
    uplink_quality = "uplink_quality"
    downlink_quality = "downlink_quality"
    speaker_attribution = "speaker_attribution"
    barge_in = "barge_in"
    conversational = "conversational"


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

UPLINK_QUALITY_PROMPT = """You are evaluating the audio quality of a phone call in a car.

You are listening to the UPLINK — the speech from the person IN THE CAR as it would be
received by the person on the other end of the call.  This audio has passed through:
cabin noise, echo cancellation, automatic gain control, Bluetooth codec, and cellular/VoIP network.

The person in the car said: "{near_end_text}"

Rate the uplink audio quality on a 1-5 scale (ITU-T P.800 MOS-like):
1: Bad — speech is unintelligible, severe distortion/noise/dropouts
2: Poor — speech is very difficult to understand, heavy degradation
3: Fair — speech is understandable with effort, noticeable degradation
4: Good — speech is clearly understandable, minor artifacts
5: Excellent — speech is clean and natural, no perceptible degradation

Consider: intelligibility, background noise level, echo residual, codec artifacts,
clipping, temporal gaps (packet loss), and overall naturalness.

Respond with ONLY valid JSON:
{{"score": <integer 1-5>, "intelligibility": <1-5>, "noise_level": <1-5>, "artifacts": <1-5>, "reasoning": "<brief explanation>"}}"""

DOWNLINK_QUALITY_PROMPT = """You are evaluating the audio quality of a phone call in a car.

You are listening to the DOWNLINK — the speech from the REMOTE CALLER as heard through
the car's speakers.  This audio has passed through Bluetooth codec and network degradation.

The remote caller said: "{far_end_text}"

Rate the downlink audio quality on a 1-5 scale (ITU-T P.800 MOS-like):
1: Bad — speech is unintelligible, severe distortion/noise/dropouts
2: Poor — speech is very difficult to understand, heavy degradation
3: Fair — speech is understandable with effort, noticeable degradation
4: Good — speech is clearly understandable, minor artifacts
5: Excellent — speech is clean and natural, no perceptible degradation

Consider: intelligibility, codec artifacts, temporal gaps, naturalness.

Respond with ONLY valid JSON:
{{"score": <integer 1-5>, "intelligibility": <1-5>, "artifacts": <1-5>, "reasoning": "<brief explanation>"}}"""

SPEAKER_ATTRIBUTION_PROMPT = """You are evaluating a phone call recording from inside a car.
Two people are speaking at the same time (doubletalk):

- NEAR-END speaker (person in the car) said: "{near_end_text}"
- FAR-END speaker (remote caller through car speakers) said: "{far_end_text}"

Listen to the audio and determine:
1. Can you identify what the NEAR-END speaker (car occupant) is saying?
2. Can you identify what the FAR-END speaker (remote caller) is saying?
3. Can you distinguish between the two speakers?

Respond with ONLY valid JSON:
{{"near_end_understood": <true/false>, "near_end_transcript": "<what you think the near-end said>", "far_end_understood": <true/false>, "far_end_transcript": "<what you think the far-end said>", "speakers_distinguishable": <true/false>, "confidence": <1-5>, "reasoning": "<brief explanation>"}}"""

BARGE_IN_PROMPT = """You are evaluating an in-car voice assistant's ability to handle a barge-in (interruption).

Scenario: The car occupant is on a phone call.  The remote caller is speaking, and the car
occupant INTERRUPTS with a voice command.  The voice assistant must detect and prioritize
the car occupant's command over the ongoing phone audio.

The car occupant's command was: "{near_end_text}"
Expected action: "{expected_intent}"
The remote caller was saying: "{far_end_text}"

The voice assistant responded: "{llm_response}"

Rate the barge-in handling:
1. Did the assistant detect that the car occupant interrupted?
2. Did the assistant correctly understand the car occupant's command?
3. Did the assistant ignore the far-end caller's speech (not confuse it with a command)?

Respond with ONLY valid JSON:
{{"barge_in_detected": <true/false>, "command_understood": <true/false>, "far_end_rejected": <true/false>, "response_appropriate": <true/false>, "score": <integer 1-5>, "reasoning": "<brief explanation>"}}"""

CONVERSATIONAL_QUALITY_PROMPT = """You are evaluating whether a voice assistant can maintain conversational
context during a degraded phone call.

The car occupant is having a multi-turn conversation.  Each turn has been degraded by
telephony effects (noise, echo, codec, network).

Current turn — the car occupant said: "{near_end_text}"
Expected response/action: "{expected_intent}"
Assistant's response: "{llm_response}"

Rate the conversational quality:
1: Assistant lost all context, response is completely irrelevant
2: Assistant partially lost context, response is confused
3: Assistant understood the turn but missed nuance or context
4: Good contextual understanding, appropriate response
5: Perfect — maintained full context despite audio degradation

Respond with ONLY valid JSON:
{{"score": <integer 1-5>, "context_maintained": <true/false>, "reasoning": "<brief explanation>"}}"""


# ---------------------------------------------------------------------------
# Telephony Judge Evaluator
# ---------------------------------------------------------------------------

@dataclass
class TelephonyEvaluationResult:
    """Composite result from all telephony evaluation modes."""

    # Per-mode results
    uplink_quality: EvaluationResult | None = None
    downlink_quality: EvaluationResult | None = None
    speaker_attribution: EvaluationResult | None = None
    barge_in: EvaluationResult | None = None
    conversational: EvaluationResult | None = None

    # Composite
    overall_score: float = 0.0
    modes_run: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {
            "overall_score": round(self.overall_score, 4),
            "modes_run": self.modes_run,
        }
        if self.uplink_quality:
            d["uplink_quality"] = {
                "score": self.uplink_quality.score,
                "passed": self.uplink_quality.passed,
                "details": self.uplink_quality.details,
            }
        if self.downlink_quality:
            d["downlink_quality"] = {
                "score": self.downlink_quality.score,
                "passed": self.downlink_quality.passed,
                "details": self.downlink_quality.details,
            }
        if self.speaker_attribution:
            d["speaker_attribution"] = {
                "score": self.speaker_attribution.score,
                "passed": self.speaker_attribution.passed,
                "details": self.speaker_attribution.details,
            }
        if self.barge_in:
            d["barge_in"] = {
                "score": self.barge_in.score,
                "passed": self.barge_in.passed,
                "details": self.barge_in.details,
            }
        if self.conversational:
            d["conversational"] = {
                "score": self.conversational.score,
                "passed": self.conversational.passed,
                "details": self.conversational.details,
            }
        return d


class TelephonyJudgeEvaluator:
    """Comprehensive LLM-as-judge evaluator for telephony test cases.

    Runs one or more evaluation modes depending on what data is available:
    - uplink_quality: always (uses degraded_audio)
    - downlink_quality: when far-end/downlink audio available
    - speaker_attribution: when doubletalk detected (DT ratio > 0)
    - barge_in: when far-end present and near-end is a command
    - conversational: when evaluating multi-turn context

    Each mode makes independent LLM judge calls (majority vote of num_judges).
    """

    def __init__(
        self,
        judge_backend: LLMBackend,
        modes: list[TelephonyJudgeMode] | None = None,
        num_judges: int = 3,
        pass_threshold: float = 0.6,
    ):
        self._judge = judge_backend
        self._modes = modes  # None = auto-detect which modes to run
        self._num_judges = num_judges
        self._pass_threshold = pass_threshold

    @property
    def name(self) -> str:
        return f"telephony_judge:{self._judge.name}"

    async def _judge_call(self, prompt: str) -> dict:
        """Make a single LLM judge call, return parsed JSON dict."""
        response = await self._judge.query_with_text(
            prompt,
            system_prompt="You are a precise telecommunications quality evaluation judge. Respond only with valid JSON.",
        )
        try:
            return json.loads(response.text.strip())
        except json.JSONDecodeError:
            # Try to extract JSON from response
            text = response.text.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return {"error": f"Failed to parse: {text[:200]}"}

    async def _majority_vote(self, prompt: str) -> list[dict]:
        """Run num_judges calls and return all results."""
        tasks = [self._judge_call(prompt) for _ in range(self._num_judges)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        parsed = []
        for r in results:
            if isinstance(r, Exception):
                parsed.append({"error": str(r)})
            else:
                parsed.append(r)
        return parsed

    def _median_score(self, results: list[dict], key: str = "score") -> float:
        """Extract median score from judge results."""
        scores = []
        for r in results:
            val = r.get(key)
            if isinstance(val, (int, float)) and 1 <= val <= 5:
                scores.append(val)
        if not scores:
            return 3.0  # default neutral
        scores.sort()
        n = len(scores)
        if n % 2 == 1:
            return float(scores[n // 2])
        return (scores[n // 2 - 1] + scores[n // 2]) / 2.0

    # --- Individual mode evaluators ---

    async def _eval_uplink_quality(
        self, near_end_text: str
    ) -> EvaluationResult:
        """Evaluate uplink speech quality (near-end after full chain)."""
        prompt = UPLINK_QUALITY_PROMPT.format(near_end_text=near_end_text)
        results = await self._majority_vote(prompt)
        median = self._median_score(results, "score")
        normalized = (median - 1) / 4.0

        # Also extract sub-scores
        intelligibility = self._median_score(results, "intelligibility")
        noise_level = self._median_score(results, "noise_level")
        artifacts = self._median_score(results, "artifacts")

        return EvaluationResult(
            score=normalized,
            passed=normalized >= self._pass_threshold,
            evaluator=f"{self.name}:uplink",
            details={
                "mos_score": median,
                "intelligibility": intelligibility,
                "noise_level": noise_level,
                "artifacts": artifacts,
                "raw_results": results,
            },
        )

    async def _eval_downlink_quality(
        self, far_end_text: str
    ) -> EvaluationResult:
        """Evaluate downlink audio quality (far-end after codec + network)."""
        prompt = DOWNLINK_QUALITY_PROMPT.format(far_end_text=far_end_text)
        results = await self._majority_vote(prompt)
        median = self._median_score(results, "score")
        normalized = (median - 1) / 4.0

        intelligibility = self._median_score(results, "intelligibility")
        artifacts = self._median_score(results, "artifacts")

        return EvaluationResult(
            score=normalized,
            passed=normalized >= self._pass_threshold,
            evaluator=f"{self.name}:downlink",
            details={
                "mos_score": median,
                "intelligibility": intelligibility,
                "artifacts": artifacts,
                "raw_results": results,
            },
        )

    async def _eval_speaker_attribution(
        self, near_end_text: str, far_end_text: str
    ) -> EvaluationResult:
        """Evaluate speaker attribution during doubletalk."""
        prompt = SPEAKER_ATTRIBUTION_PROMPT.format(
            near_end_text=near_end_text,
            far_end_text=far_end_text,
        )
        results = await self._majority_vote(prompt)

        # Score based on how many judges got attribution right
        ne_correct = sum(1 for r in results if r.get("near_end_understood") is True)
        fe_correct = sum(1 for r in results if r.get("far_end_understood") is True)
        distinguishable = sum(1 for r in results if r.get("speakers_distinguishable") is True)
        n = len(results)

        # Composite: near-end understanding weighted higher (it's the command)
        score = (
            0.5 * (ne_correct / max(n, 1))
            + 0.3 * (fe_correct / max(n, 1))
            + 0.2 * (distinguishable / max(n, 1))
        )

        confidence = self._median_score(results, "confidence")

        return EvaluationResult(
            score=score,
            passed=score >= self._pass_threshold,
            evaluator=f"{self.name}:speaker_attribution",
            details={
                "near_end_understood_ratio": ne_correct / max(n, 1),
                "far_end_understood_ratio": fe_correct / max(n, 1),
                "speakers_distinguishable_ratio": distinguishable / max(n, 1),
                "confidence": confidence,
                "raw_results": results,
            },
        )

    async def _eval_barge_in(
        self,
        near_end_text: str,
        far_end_text: str,
        expected_intent: str,
        llm_response: str,
    ) -> EvaluationResult:
        """Evaluate barge-in (interruption) handling."""
        prompt = BARGE_IN_PROMPT.format(
            near_end_text=near_end_text,
            far_end_text=far_end_text,
            expected_intent=expected_intent,
            llm_response=llm_response,
        )
        results = await self._majority_vote(prompt)

        detected = sum(1 for r in results if r.get("barge_in_detected") is True)
        understood = sum(1 for r in results if r.get("command_understood") is True)
        rejected = sum(1 for r in results if r.get("far_end_rejected") is True)
        appropriate = sum(1 for r in results if r.get("response_appropriate") is True)
        n = len(results)

        # Score: barge-in detection + command understanding + far-end rejection
        score = (
            0.3 * (detected / max(n, 1))
            + 0.4 * (understood / max(n, 1))
            + 0.3 * (rejected / max(n, 1))
        )

        median = self._median_score(results, "score")

        return EvaluationResult(
            score=score,
            passed=score >= self._pass_threshold,
            evaluator=f"{self.name}:barge_in",
            details={
                "barge_in_detected_ratio": detected / max(n, 1),
                "command_understood_ratio": understood / max(n, 1),
                "far_end_rejected_ratio": rejected / max(n, 1),
                "response_appropriate_ratio": appropriate / max(n, 1),
                "mos_score": median,
                "raw_results": results,
            },
        )

    async def _eval_conversational(
        self,
        near_end_text: str,
        expected_intent: str,
        llm_response: str,
    ) -> EvaluationResult:
        """Evaluate conversational quality / context retention."""
        prompt = CONVERSATIONAL_QUALITY_PROMPT.format(
            near_end_text=near_end_text,
            expected_intent=expected_intent,
            llm_response=llm_response,
        )
        results = await self._majority_vote(prompt)
        median = self._median_score(results, "score")
        normalized = (median - 1) / 4.0

        context_maintained = sum(
            1 for r in results if r.get("context_maintained") is True
        )

        return EvaluationResult(
            score=normalized,
            passed=normalized >= self._pass_threshold,
            evaluator=f"{self.name}:conversational",
            details={
                "mos_score": median,
                "context_maintained_ratio": context_maintained / max(len(results), 1),
                "raw_results": results,
            },
        )

    # --- Main evaluate method ---

    async def evaluate(
        self,
        input: PipelineInput,
        result: PipelineResult,
    ) -> TelephonyEvaluationResult:
        """Run all applicable telephony evaluation modes.

        Automatically determines which modes to run based on available data,
        or uses the explicitly configured modes list.
        """
        tel_meta = result.telephony_metadata or {}
        has_far_end = tel_meta.get("has_far_end", False)
        far_end_text = tel_meta.get("far_end_text", "")
        dt_metrics = tel_meta.get("doubletalk_metrics", {})
        dt_ratio = dt_metrics.get("doubletalk_ratio", 0.0) if dt_metrics else 0.0
        llm_response_text = result.llm_response.text if result.llm_response else ""

        # Determine which modes to run
        if self._modes is not None:
            modes = self._modes
        else:
            # Auto-detect
            modes = [TelephonyJudgeMode.uplink_quality]
            if has_far_end:
                modes.append(TelephonyJudgeMode.downlink_quality)
            if dt_ratio > 0.05:  # At least 5% doubletalk
                modes.append(TelephonyJudgeMode.speaker_attribution)
            if has_far_end and input.expected_action:
                modes.append(TelephonyJudgeMode.barge_in)

        # Run all modes concurrently
        tasks = {}
        for mode in modes:
            if mode == TelephonyJudgeMode.uplink_quality:
                tasks[mode] = self._eval_uplink_quality(input.original_text)
            elif mode == TelephonyJudgeMode.downlink_quality and far_end_text:
                tasks[mode] = self._eval_downlink_quality(far_end_text)
            elif mode == TelephonyJudgeMode.speaker_attribution and far_end_text:
                tasks[mode] = self._eval_speaker_attribution(
                    input.original_text, far_end_text
                )
            elif mode == TelephonyJudgeMode.barge_in and far_end_text:
                tasks[mode] = self._eval_barge_in(
                    input.original_text,
                    far_end_text,
                    input.expected_intent,
                    llm_response_text,
                )
            elif mode == TelephonyJudgeMode.conversational:
                tasks[mode] = self._eval_conversational(
                    input.original_text,
                    input.expected_intent,
                    llm_response_text,
                )

        # Execute all concurrently
        mode_keys = list(tasks.keys())
        if mode_keys:
            results_list = await asyncio.gather(
                *[tasks[k] for k in mode_keys],
                return_exceptions=True,
            )
        else:
            results_list = []

        # Collect results
        composite = TelephonyEvaluationResult()
        scores = []

        for mode, res in zip(mode_keys, results_list):
            if isinstance(res, Exception):
                logger.warning(f"Telephony judge mode {mode.value} failed: {res}")
                continue

            if mode == TelephonyJudgeMode.uplink_quality:
                composite.uplink_quality = res
            elif mode == TelephonyJudgeMode.downlink_quality:
                composite.downlink_quality = res
            elif mode == TelephonyJudgeMode.speaker_attribution:
                composite.speaker_attribution = res
            elif mode == TelephonyJudgeMode.barge_in:
                composite.barge_in = res
            elif mode == TelephonyJudgeMode.conversational:
                composite.conversational = res

            scores.append(res.score)
            composite.modes_run.append(mode.value)

        composite.overall_score = sum(scores) / len(scores) if scores else 0.0

        return composite
