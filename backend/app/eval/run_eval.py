"""
Evaluation harness scaffold.

What this gives you today: a runnable script that fires every prompt in
gold_dataset.json through the real council and records, per case, whether
the Decision Architect selected the council you'd expect, how long it took,
what the consensus scores came out to, and whether the challenge round ran
or was skipped. That's an honest, working "does dynamic council selection +
adaptive debate behave sensibly" check.

What this does NOT give you: a verdict on whether the council's answers are
BETTER than a single GPT-5/Claude/Gemini call. That needs (a) API access to
those models, which isn't available in this environment, and (b) a judging
methodology (a blind pairwise judge model, or human raters) — faking either
would produce a number that looks like evidence but isn't. Wire in a
baseline_models.py that calls whichever providers you have keys for, and a
judge() function using an LLM-as-judge or human review, then extend
run_one() below to also collect and compare those.

Usage:
    python -m app.eval.run_eval
"""

import asyncio
import json
import time
from pathlib import Path

from ..council import run_council

DATASET_PATH = Path(__file__).parent / "gold_dataset.json"
RESULTS_PATH = Path(__file__).parent / "results.json"


async def run_one(case: dict) -> dict:
    started = time.perf_counter()
    try:
        result = await run_council(case["prompt"], use_cache=False)
        expected = set(case.get("expected_council_includes", []))
        actual = set(result.council_composition)
        return {
            "id": case["id"],
            "category": case.get("category"),
            "success": True,
            "wall_time_s": round(time.perf_counter() - started, 2),
            "council_selected": result.council_composition,
            "expected_council_overlap": sorted(expected & actual),
            "expected_council_missing": sorted(expected - actual),
            "agreement_score": result.agreement_score,
            "confidence_score": result.confidence_score,
            "debate_skipped": result.debate_skipped,
            "member_failures": [m.role_name for m in result.round1 + result.round2 if not m.success],
        }
    except Exception as error:
        return {
            "id": case["id"],
            "category": case.get("category"),
            "success": False,
            "wall_time_s": round(time.perf_counter() - started, 2),
            "error": str(error),
        }


async def main() -> None:
    dataset = json.loads(DATASET_PATH.read_text())
    results = []
    for case in dataset["cases"]:
        print(f"Running {case['id']}...")
        results.append(await run_one(case))

    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    successes = [r for r in results if r["success"]]
    print(f"\n{len(successes)}/{len(results)} cases completed.")
    if successes:
        avg_time = sum(r["wall_time_s"] for r in successes) / len(successes)
        print(f"Average wall time: {avg_time:.1f}s")
    print(f"Full results written to {RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())