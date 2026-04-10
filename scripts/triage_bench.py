#!/usr/bin/env python3
"""Triage classifier benchmark — tests prompt variants × models against Ollama.

Usage:
    python scripts/triage_bench.py --server http://10.10.70.10:11434
    python scripts/triage_bench.py --keyword-only
    python scripts/triage_bench.py --models qwen2.5:0.5b --prompts chat_few_shot,json_format
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from triage_keyword import classify_keyword

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Utterance:
    text: str
    label: int
    category: str


@dataclass
class Result:
    utterance: Utterance
    predicted: int | None
    raw_response: str
    latency_ms: float
    tokens: int

    @property
    def correct(self) -> bool:
        return self.predicted == self.utterance.label


# ---------------------------------------------------------------------------
# Prompt variant definitions
# ---------------------------------------------------------------------------

SYSTEM_BARE = (
    "You are a binary classifier. You MUST reply with exactly one character: 0 or 1.\n"
    "\n"
    "0 = The user wants to control something in their car (examples: climate, windows, "
    "doors, locks, seats, mirrors, wipers, lights, music, volume, navigation, driving mode, "
    "trunk, horn, cruise control, sunroof, parking, phone calls)\n"
    "1 = Everything else (questions, conversation, math, facts, reminders, timers, "
    "translations, recommendations, weather, news)\n"
    "\n"
    "RULES:\n"
    "- Output ONLY the digit 0 or 1\n"
    "- NEVER output words, sentences, or explanations\n"
    "- If uncertain, output 1"
)

SYSTEM_JSON = (
    "You are a binary classifier for an in-car voice assistant router.\n"
    "Classify the user input and respond ONLY with JSON.\n"
    "\n"
    'Output {"class": 0} if the user wants to control their car (climate, windows, '
    "doors, locks, seats, mirrors, wipers, lights, music, volume, navigation, driving mode, "
    "trunk, horn, cruise control, sunroof, parking, phone calls).\n"
    "\n"
    'Output {"class": 1} for everything else (questions, conversation, math, facts, '
    "reminders, timers, translations, recommendations, weather, news).\n"
    "\n"
    "Output ONLY the JSON object, nothing else."
)

FEW_SHOT_EXAMPLES = [
    ("set the temperature to 70", "0"),
    ("open the sunroof", "0"),
    ("navigate to the nearest gas station", "0"),
    ("what is the capital of France", "1"),
    ("tell me a joke", "1"),
    ("how many miles is a kilometer", "1"),
]

FEW_SHOT_BLOCK = "\n".join(
    f"Input: {inp}\nOutput: {out}" for inp, out in FEW_SHOT_EXAMPLES
)

FEW_SHOT_JSON_EXAMPLES = [
    ("turn on the AC", '{"class": 0}'),
    ("lock the doors", '{"class": 0}'),
    ("play my playlist", '{"class": 0}'),
    ("what is 2 plus 2", '{"class": 1}'),
    ("tell me about black holes", '{"class": 1}'),
    ("translate hello to Spanish", '{"class": 1}'),
]


@dataclass
class PromptVariant:
    name: str
    endpoint: str  # "generate" or "chat"
    system: str
    build_prompt: object  # callable(text) -> str | list[dict]
    options: dict = field(default_factory=dict)
    format_json: bool = False


def _bare_prompt(text: str) -> str:
    return text


def _few_shot_prompt(text: str) -> str:
    return f"{FEW_SHOT_BLOCK}\nInput: {text}\nOutput:"


def _chat_few_shot_messages(text: str) -> list[dict]:
    msgs = [{"role": "system", "content": SYSTEM_BARE}]
    for inp, out in FEW_SHOT_EXAMPLES:
        msgs.append({"role": "user", "content": inp})
        msgs.append({"role": "assistant", "content": out})
    msgs.append({"role": "user", "content": text})
    return msgs


def _chat_json_messages(text: str) -> list[dict]:
    msgs = [{"role": "system", "content": SYSTEM_JSON}]
    for inp, out in FEW_SHOT_JSON_EXAMPLES:
        msgs.append({"role": "user", "content": inp})
        msgs.append({"role": "assistant", "content": out})
    msgs.append({"role": "user", "content": text})
    return msgs


VARIANTS: dict[str, PromptVariant] = {
    "bare_1tok": PromptVariant(
        name="bare_1tok",
        endpoint="generate",
        system=SYSTEM_BARE,
        build_prompt=_bare_prompt,
        options={"temperature": 0, "num_predict": 1},
    ),
    "bare_5tok": PromptVariant(
        name="bare_5tok",
        endpoint="generate",
        system=SYSTEM_BARE,
        build_prompt=_bare_prompt,
        options={"temperature": 0, "num_predict": 5},
    ),
    "few_shot": PromptVariant(
        name="few_shot",
        endpoint="generate",
        system=SYSTEM_BARE,
        build_prompt=_few_shot_prompt,
        options={"temperature": 0, "num_predict": 5},
    ),
    "chat_few_shot": PromptVariant(
        name="chat_few_shot",
        endpoint="chat",
        system=SYSTEM_BARE,
        build_prompt=_chat_few_shot_messages,
        options={"temperature": 0, "num_predict": 5},
    ),
    "json_format": PromptVariant(
        name="json_format",
        endpoint="generate",
        system=SYSTEM_JSON,
        build_prompt=_bare_prompt,
        options={"temperature": 0, "num_predict": 20},
        format_json=True,
    ),
    "chat_json": PromptVariant(
        name="chat_json",
        endpoint="chat",
        system=SYSTEM_JSON,
        build_prompt=_chat_json_messages,
        options={"temperature": 0, "num_predict": 20},
        format_json=True,
    ),
}


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def parse_class(raw: str) -> int | None:
    """Extract 0 or 1 from model output, handling various formats."""
    text = raw.strip()
    if not text:
        return None

    # Try JSON
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            for key in ("class", "label", "result", "output", "category"):
                if key in obj:
                    val = int(obj[key])
                    if val in (0, 1):
                        return val
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # First digit 0 or 1
    for ch in text:
        if ch in "01":
            return int(ch)

    # Word fallback
    lower = text.lower()
    if any(w in lower for w in ("vehicle", "command", "car", "control")):
        return 0
    if any(w in lower for w in ("general", "question", "other", "everything")):
        return 1

    return None


# ---------------------------------------------------------------------------
# Ollama classifiers
# ---------------------------------------------------------------------------

async def classify_ollama(
    text: str,
    client: httpx.AsyncClient,
    server: str,
    model: str,
    variant: PromptVariant,
    timeout: float,
) -> Result:
    """Run a single classification through Ollama."""
    t0 = time.monotonic()

    try:
        if variant.endpoint == "generate":
            payload: dict = {
                "model": model,
                "prompt": variant.build_prompt(text),
                "system": variant.system,
                "stream": False,
                "options": variant.options,
            }
            if variant.format_json:
                payload["format"] = "json"

            resp = await client.post(f"{server}/api/generate", json=payload, timeout=timeout)

        else:  # chat
            messages = variant.build_prompt(text)
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": variant.options,
            }
            if variant.format_json:
                payload["format"] = "json"

            resp = await client.post(f"{server}/api/chat", json=payload, timeout=timeout)

        resp.raise_for_status()
        data = resp.json()
        latency = (time.monotonic() - t0) * 1000

        if variant.endpoint == "generate":
            raw_text = data.get("response", "")
            tokens = data.get("eval_count", 0)
        else:
            raw_text = data.get("message", {}).get("content", "")
            tokens = data.get("eval_count", 0)

        predicted = parse_class(raw_text)

    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        raw_text = f"ERROR: {e}"
        tokens = 0
        predicted = None

    # Create a dummy utterance — caller will replace
    return Result(
        utterance=Utterance(text=text, label=-1, category=""),
        predicted=predicted,
        raw_response=raw_text,
        latency_ms=latency,
        tokens=tokens,
    )


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

async def warmup(client: httpx.AsyncClient, server: str, model: str, timeout: float):
    """Send a throwaway request to load the model into VRAM."""
    print(f"  Warming up {model}...", end=" ", flush=True)
    try:
        resp = await client.post(
            f"{server}/api/generate",
            json={
                "model": model,
                "prompt": "hi",
                "system": "reply ok",
                "stream": False,
                "options": {"num_predict": 1},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        print("ready.")
    except Exception as e:
        print(f"warning: {e}")


async def run_ollama_benchmark(
    dataset: list[Utterance],
    client: httpx.AsyncClient,
    server: str,
    model: str,
    variant: PromptVariant,
    concurrency: int,
    timeout: float,
) -> list[Result]:
    """Run all utterances through an Ollama variant."""
    sem = asyncio.Semaphore(concurrency)
    results: list[Result] = []

    async def classify_one(utt: Utterance) -> Result:
        async with sem:
            r = await classify_ollama(utt.text, client, server, model, variant, timeout)
            r.utterance = utt
            return r

    tasks = [classify_one(u) for u in dataset]
    results = await asyncio.gather(*tasks)
    return list(results)


def run_keyword_benchmark(dataset: list[Utterance]) -> list[Result]:
    """Run all utterances through the keyword classifier."""
    results = []
    for utt in dataset:
        t0 = time.monotonic()
        predicted = classify_keyword(utt.text)
        latency = (time.monotonic() - t0) * 1000
        results.append(Result(
            utterance=utt,
            predicted=predicted,
            raw_response=str(predicted),
            latency_ms=latency,
            tokens=0,
        ))
    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(results: list[Result], variant_name: str, model_name: str):
    total = len(results)
    correct = sum(1 for r in results if r.correct)
    unparseable = sum(1 for r in results if r.predicted is None)

    class0 = [r for r in results if r.utterance.label == 0]
    class1 = [r for r in results if r.utterance.label == 1]
    correct0 = sum(1 for r in class0 if r.correct)
    correct1 = sum(1 for r in class1 if r.correct)

    # Confusion matrix
    tp = sum(1 for r in class0 if r.predicted == 0)  # true vehicle
    fn = sum(1 for r in class0 if r.predicted == 1)  # vehicle misclassified as general
    fp = sum(1 for r in class1 if r.predicted == 0)  # general misclassified as vehicle
    tn = sum(1 for r in class1 if r.predicted == 1)  # true general
    unp0 = sum(1 for r in class0 if r.predicted is None)
    unp1 = sum(1 for r in class1 if r.predicted is None)

    avg_latency = sum(r.latency_ms for r in results) / total if total else 0
    avg_tokens = sum(r.tokens for r in results) / total if total else 0

    print(f"\n{'='*70}")
    print(f"  {variant_name} | {model_name}")
    print(f"{'='*70}")
    print(f"  Total: {total}  Correct: {correct}  Accuracy: {correct/total*100:.1f}%")
    print(f"  Vehicle (0): {correct0}/{len(class0)} ({correct0/len(class0)*100:.1f}%)")
    print(f"  General (1): {correct1}/{len(class1)} ({correct1/len(class1)*100:.1f}%)")
    print(f"  Unparseable: {unparseable}")
    print()
    print(f"  Confusion Matrix:")
    print(f"                 Pred 0    Pred 1    Unparse")
    print(f"    Actual 0  {tp:>8}  {fn:>8}  {unp0:>8}")
    print(f"    Actual 1  {fp:>8}  {tn:>8}  {unp1:>8}")
    print()
    print(f"  Avg latency: {avg_latency:.0f}ms | Avg tokens: {avg_tokens:.1f}")

    # Print failures
    failures = [r for r in results if not r.correct]
    if failures:
        print(f"\n  Failures ({len(failures)}):")
        for r in failures:
            pred_str = str(r.predicted) if r.predicted is not None else "None"
            raw_short = r.raw_response[:60].replace("\n", "\\n")
            print(f'    [{r.utterance.label}→{pred_str}] "{r.utterance.text}"  raw={raw_short}')
    print()

    return correct / total if total else 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_dataset(path: str) -> list[Utterance]:
    with open(path) as f:
        data = json.load(f)
    return [Utterance(text=d["text"], label=d["label"], category=d["category"]) for d in data]


async def main():
    parser = argparse.ArgumentParser(description="Triage classifier benchmark")
    parser.add_argument("--server", default="http://10.10.70.10:11434", help="Ollama server URL")
    parser.add_argument("--models", default="qwen2.5:0.5b,qwen2.5:1.5b", help="Comma-separated model list")
    parser.add_argument("--prompts", default="all", help="Comma-separated prompt variant names, or 'all'")
    parser.add_argument("--keyword-only", action="store_true", help="Only run keyword classifier")
    parser.add_argument("--dataset", default=str(Path(__file__).parent / "triage_dataset.json"))
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    dataset = load_dataset(args.dataset)
    print(f"Loaded {len(dataset)} utterances "
          f"({sum(1 for u in dataset if u.label == 0)} vehicle, "
          f"{sum(1 for u in dataset if u.label == 1)} general)")

    summary: list[tuple[str, str, float]] = []

    # Always run keyword baseline
    print("\nRunning keyword classifier...")
    kw_results = run_keyword_benchmark(dataset)
    acc = print_report(kw_results, "keyword", "regex")
    summary.append(("keyword", "regex", acc))

    if args.keyword_only:
        print_summary(summary)
        return

    # Determine variants to run
    if args.prompts == "all":
        variant_names = list(VARIANTS.keys())
    else:
        variant_names = [v.strip() for v in args.prompts.split(",")]

    models = [m.strip() for m in args.models.split(",")]

    async with httpx.AsyncClient() as client:
        for model in models:
            await warmup(client, args.server, model, args.timeout * 2)

            for vname in variant_names:
                variant = VARIANTS.get(vname)
                if variant is None:
                    print(f"Unknown variant: {vname}, skipping")
                    continue

                print(f"\nRunning {vname} with {model}...")
                results = await run_ollama_benchmark(
                    dataset, client, args.server, model, variant,
                    args.concurrency, args.timeout,
                )
                acc = print_report(results, vname, model)
                summary.append((vname, model, acc))

    print_summary(summary)


def print_summary(summary: list[tuple[str, str, float]]):
    print(f"\n{'='*70}")
    print("  SUMMARY — sorted by accuracy")
    print(f"{'='*70}")
    for variant, model, acc in sorted(summary, key=lambda x: -x[2]):
        bar = "█" * int(acc * 40)
        print(f"  {acc*100:5.1f}%  {bar:<40s}  {variant} | {model}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
