"""Generates a comprehensive behavioural-analysis conclusion for a test run."""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.models.endpoint_config import EndpointConfig
    from backend.models.llm_config import LLMConfig
    from backend.models.test_case import TestCase
    from backend.models.test_run import TestRun
    from backend.models.turn import Turn

_logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are an expert QA engineer and conversational-AI analyst. "
    "Your job is to read a chatbot test transcript and produce a thorough, "
    "honest behavioural analysis. Be specific — cite turn numbers, quote "
    "short phrases from the transcript. Focus on what actually happened, "
    "not generalities."
)

_SCHEMA = """\
Return ONLY a single JSON object — no markdown fences, no prose before or after.
Schema:
{
  "executive_summary":    "<2-3 sentence overall assessment>",
  "behavior_overview":    "<paragraph describing the system's overall behaviour pattern>",
  "strong_points":        ["<specific strength>", ...],
  "failures": [
    {"turn": <int>, "description": "<what went wrong>", "severity": "critical|major|minor"}
  ],
  "hallucinations": [
    {"turn": <int>, "claimed": "<what the bot stated>", "issue": "<why it is likely hallucination or fabrication>"}
  ],
  "off_track": [
    {"turn": <int>, "description": "<how the response deviated from the task or topic>"}
  ],
  "consistency_analysis": "<assessment of response consistency, tone, and style across turns>",
  "communication_quality": "<clarity, structure, professionalism, appropriate length>",
  "task_completion":       "<did the system accomplish the intended use case? give detail>",
  "user_experience":       "<how a real end-user would likely experience this interaction>",
  "factual_concerns":      ["<any claim that seems questionable or unverifiable>", ...],
  "critical_issues":       ["<most impactful issue>", ...],
  "recommendations":       ["<specific, actionable improvement>", ...],
  "conclusion":            "<final paragraph with overall verdict and next steps>"
}"""


def _build_prompt(
    run: "TestRun",
    tc: "TestCase | None",
    ep: "EndpointConfig | None",
    turns: list["Turn"],
) -> str:
    lines: list[str] = [
        f"SYSTEM BEING TESTED: {ep.name if ep else 'Unknown endpoint'}",
        f"TEST CASE:           {tc.name if tc else '—'}",
        f"USE CASE:            {(tc.usecase or '(unspecified)') if tc else '—'}",
        f"SUCCESS CRITERIA:    {(tc.success_criteria or '(unspecified)') if tc else '—'}",
        f"OVERALL VERDICT:     {(run.verdict or '—').upper()}  "
        f"(score: {f'{run.verdict_score:.2f}' if run.verdict_score is not None else '—'}/1.0)",
        f"TOTAL TURNS:         {len(turns)}",
        "",
        "=== TRANSCRIPT WITH JUDGE ANALYSIS ===",
        "",
    ]

    for t in turns:
        lines.append(f"Turn {t.turn_number}:")
        lines.append(f"  User : {t.user_query or '(empty)'}")
        lines.append(f"  Bot  : {t.extracted_reply or '(no reply)'}")
        if t.error:
            lines.append(f"  Error: {t.error}")
        if t.turn_verdict:
            score_str = f"{t.turn_score:.2f}" if t.turn_score is not None else "—"
            lines.append(
                f"  Judge: {t.turn_verdict.upper()}  score={score_str}"
                + (f"  — {t.turn_reasoning}" if t.turn_reasoning else "")
            )
            ana = t.turn_analysis or {}
            if ana.get("issues"):
                lines.append(f"    Issues: {', '.join(ana['issues'])}")
            if ana.get("strengths"):
                lines.append(f"    Strengths: {', '.join(ana['strengths'])}")
        lines.append("")

    if run.verdict_reasoning:
        lines += [
            "=== OVERALL JUDGE REASONING ===",
            run.verdict_reasoning,
            "",
        ]

    lines.append(_SCHEMA)
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """Try to extract a JSON object from LLM output (handles fences + stray text)."""
    stripped = text.strip()
    # Remove common markdown fences
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.I)
    stripped = re.sub(r"\s*```$", "", stripped)
    stripped = stripped.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        # Find first { … last }
        start = stripped.find("{")
        end   = stripped.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(stripped[start:end])
            except json.JSONDecodeError:
                pass
    return {"_parse_error": True, "raw": text}


async def generate_conclusion(
    run: "TestRun",
    tc: "TestCase | None",
    ep: "EndpointConfig | None",
    turns: list["Turn"],
    judge_llm: "LLMConfig",
) -> dict[str, Any]:
    from backend.services.llm import build_provider

    provider = build_provider(
        judge_llm.provider, judge_llm.model, judge_llm.api_key, judge_llm.base_url
    )
    prompt = _build_prompt(run, tc, ep, turns)

    try:
        resp = await provider.complete(
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=min(judge_llm.max_tokens, 3000),
        )
    except Exception as exc:
        _logger.exception("Conclusion LLM call failed for run %s", run.id)
        raise exc

    result = _extract_json(resp.text)
    result["_meta"] = {
        "run_id": run.id,
        "tokens": resp.input_tokens + resp.output_tokens,
        "cost_usd": resp.cost_usd,
        "model": judge_llm.model,
    }
    return result
