"""Lightweight standalone eval runner, standing in for `agents-cli eval
generate` + `eval grade`.

Why this exists: `agents-cli eval generate` constructs a `vertexai.Client`
internally (for tracing infra) regardless of the agent's own model
provider, which needs working Google Cloud ADC. This project uses Claude
via LiteLLM with no GCP project, and the local `gcloud` CLI installation is
independently broken, so that path isn't available. This script runs the
same dataset (tests/eval/datasets/basic-dataset.json) against the real
agent and scores it with the same logic as tests/eval/metrics.py's
LLM-as-judge, plus the deterministic escalation check from
tests/eval/eval_config.yaml (duplicated here — keep both in sync by hand).

Usage (from paryushan-brain/):
    uv run python tests/eval/run_local_eval.py
"""

import asyncio
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # for `import metrics`

from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

import metrics  # noqa: E402
from brain.agent import root_agent  # noqa: E402

_DATASET_PATH = Path(__file__).parent / "datasets" / "basic-dataset.json"
_RESULTS_DIR = Path(__file__).parent.parent.parent / "artifacts" / "grade_results"

_EXPECT_ESCALATION_CASE_IDS = {
    "unanswerable_logistics_question_escalates",
    "dietary_ambiguity_must_escalate_not_fabricate",
    "unsupported_action_escalates_gracefully",
}


def _escalation_used_when_expected(instance: dict) -> dict:
    case_id = instance.get("eval_case_id", "")
    if case_id not in _EXPECT_ESCALATION_CASE_IDS:
        return {"score": 1, "explanation": "Not an escalation-expected case; N/A."}

    turns = (instance.get("agent_data") or {}).get("turns", [])
    called_escalate = False
    for turn in turns:
        for event in turn.get("events", []):
            content = event.get("content") or {}
            for part in content.get("parts") or []:
                fc = part.get("function_call")
                if fc and fc.get("name") == "escalate":
                    called_escalate = True

    if called_escalate:
        return {"score": 1, "explanation": "escalate() was called, as expected."}
    return {
        "score": 0,
        "explanation": "escalate() was NOT called — agent likely answered/fabricated instead of deferring to an admin.",
    }


async def _run_case(case: dict) -> dict:
    case_id = case["eval_case_id"]
    prompt_text = case["prompt"]["parts"][0]["text"]

    state = {"user_id": 0, "language": "en", "personal_features_enabled": True}
    state.update(case.get("initial_state", {}))  # our own extension, not part of the official schema

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="eval",
        user_id="eval_user",
        session_id=case_id,
        state=state,
    )
    runner = Runner(agent=root_agent, app_name="eval", session_service=session_service)

    events_out = []
    final_text = ""
    async for event in runner.run_async(
        user_id="eval_user",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part.from_text(text=prompt_text)]),
    ):
        events_out.append(
            {
                "author": event.author,
                "content": event.content.model_dump(exclude_none=True) if event.content else {},
            }
        )
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(p.text or "" for p in event.content.parts)

    return {
        "eval_case_id": case_id,
        "prompt": prompt_text,
        "response": final_text,
        "reference": case.get("reference"),
        "agent_data": {"turns": [{"turn_index": 0, "events": events_out}]},
    }


async def main() -> None:
    dataset = json.loads(_DATASET_PATH.read_text())
    results = []

    for case in dataset["eval_cases"]:
        print(f"Running: {case['eval_case_id']}...", flush=True)
        instance = await _run_case(case)

        quality = metrics.evaluate(instance)
        escalation = _escalation_used_when_expected(instance)

        results.append(
            {
                "eval_case_id": instance["eval_case_id"],
                "prompt": instance["prompt"],
                "response": instance["response"],
                "custom_response_quality": quality,
                "escalation_used_when_expected": escalation,
            }
        )

    print("\n" + "=" * 100)
    print(f"{'case_id':<48} {'quality':>7} {'escalate':>9}  response")
    print("-" * 100)
    for r in results:
        q = r["custom_response_quality"]["score"]
        e = r["escalation_used_when_expected"]["score"]
        preview = r["response"][:60].replace("\n", " ")
        print(f"{r['eval_case_id']:<48} {q:>7} {e:>9}  {preview}")
    print("=" * 100)

    failures = [
        r
        for r in results
        if r["custom_response_quality"]["score"] < 3 or r["escalation_used_when_expected"]["score"] == 0
    ]
    if failures:
        print(f"\n{len(failures)} case(s) below threshold:")
        for r in failures:
            print(f"\n[{r['eval_case_id']}]")
            print(f"  prompt: {r['prompt']}")
            print(f"  response: {r['response']}")
            print(f"  quality: {r['custom_response_quality']}")
            print(f"  escalation: {r['escalation_used_when_expected']}")
    else:
        print("\nAll cases passed threshold (quality >= 3, escalation == 1 where expected).")

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = _RESULTS_DIR / f"local_results_{ts}.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
