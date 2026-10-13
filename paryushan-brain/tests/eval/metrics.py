"""Local metrics for `agents-cli eval grade`, wired in from
tests/eval/eval_config.yaml.

Both run fully in-process — no GCP project or Vertex Evaluation Service
required, matching this project's Claude-via-LiteLLM setup (see
brain/agent.py). `custom_response_quality` is an LLM-as-judge using the
same Claude model as the agent; `escalation_used_when_expected` is a
deterministic trace check with no LLM call at all.
"""

import json
import os

import litellm

_JUDGE_MODEL = "anthropic/claude-haiku-4-5-20251001"

_EXTRA_HEADERS = {}
_workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID", "")
if _workspace_id:
    _EXTRA_HEADERS["anthropic-workspace-id"] = _workspace_id


def evaluate(instance):
    """LLM-as-judge: rate the agent's final response 1-5 for accuracy,
    relevance, and clarity, using each case's `reference` when present."""
    reference = instance.get("reference")
    rubric = (
        "Grade the agent's final response on a 1-5 scale (1 poor, 5 excellent) for "
        "accuracy, relevance, and clarity."
    )
    if reference:
        rubric += (
            " The response should agree with the expected answer below; penalize "
            "factual disagreement with it."
        )
    prompt = (
        f"You are an expert QA evaluator for a WhatsApp community assistant. {rubric}\n"
        f"User Prompt: {instance.get('prompt', '')}\n"
        f"Final Response: {instance.get('response', '')}\n"
    )
    if reference:
        prompt += f"Expected Answer (ground truth): {reference}\n"
    prompt += f"Full Agent Trace: {instance.get('agent_data', '')}\n"
    prompt += '\nRespond with ONLY a JSON object: {"score": <1-5 integer>, "explanation": "<one sentence>"}'

    response = litellm.completion(
        model=_JUDGE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        extra_headers=_EXTRA_HEADERS or None,
    )
    text = response.choices[0].message.content or ""
    try:
        # Judges sometimes wrap JSON in prose or a code fence despite instructions.
        start, end = text.index("{"), text.rindex("}") + 1
        verdict = json.loads(text[start:end])
        score = int(verdict.get("score", 0))
        explanation = verdict.get("explanation", "")
    except (ValueError, KeyError):
        return {"score": 0, "explanation": f"Could not parse judge output: {text!r}"}

    return {"score": max(1, min(5, score)), "explanation": explanation}
