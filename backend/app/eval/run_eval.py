\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\


import asyncio
import json
import time
from pathlib import Path

from ..council import run_council

REQUIRED_HEADINGS = {
    "recommendation", "why this wins", "execution plan",
    "guardrails and reversal triggers", "confidence and key uncertainty",
}

DATASET_PATH = Path(__file__).parent / "gold_dataset.json"
RESULTS_PATH = Path(__file__).parent / "results.json"


async def run_one(case: dict) -> dict:
    started = time.perf_counter()
    try:
        result = await run_council(case["prompt"], use_cache=False)
        expected = set(case.get("expected_council_includes", []))
        actual = set(result.council_composition)
        output_lower = result.final_answer.lower()
        missing_headings = sorted(heading for heading in REQUIRED_HEADINGS if heading not in output_lower)
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
            "missing_required_headings": missing_headings,
            "directive_complete": not missing_headings,
        }
    except Exception as error:  # noqa: BLE001
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
        complete = sum(r["directive_complete"] for r in successes)
        print(f"Complete directives: {complete}/{len(successes)}")
    print(f"Full results written to {RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
