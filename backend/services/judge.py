"""Judge: evaluates conversations and individual turns."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

from backend.models.test_case import TestCase
from backend.services.llm import LLMProvider

VerdictResult = Literal["pass", "fail", "inconclusive"]


@dataclass
class Verdict:
    result: VerdictResult
    reasoning: str
    score: float  # 0.0 – 1.0
    # per-turn extras (None / empty for overall transcript verdict)
    need_satisfied: bool | None = None
    issues: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    suggestion: str = ""
    # per-criterion scores: {"Criterion Name": {"score": float, "reasoning": str}}
    criteria_scores: dict[str, dict] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def to_analysis_dict(self) -> dict:
        """Serialisable dict for the turn_analysis JSON column."""
        return {
            "need_satisfied": self.need_satisfied,
            "issues": self.issues,
            "strengths": self.strengths,
            "suggestion": self.suggestion,
            "criteria_scores": self.criteria_scores,
        }


# ── Criteria helpers ──────────────────────────────────────────────────────────

def _build_criteria_section(eval_criteria: list[dict]) -> str:
    """Format criteria list into a numbered block for injection into prompts."""
    lines = [
        "=== EVALUATION CRITERIA ===",
        "Score each criterion independently (0.0–1.0) and give one sentence of reasoning.\n",
    ]
    for i, c in enumerate(eval_criteria, start=1):
        weight_pct = c.get("weight", 1.0)
        lines.append(f'{i}. {c["name"]} (weight: {weight_pct:.2f})')
        if c.get("description"):
            lines.append(f'   {c["description"]}')
    return "\n".join(lines)


def _compute_weighted_score(criteria_scores: dict, eval_criteria: list[dict]) -> float:
    """Weighted average of per-criterion scores; normalises weights automatically."""
    total_weight = sum(
        c["weight"] for c in eval_criteria if c["name"] in criteria_scores
    )
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(
        criteria_scores[c["name"]]["score"] * c["weight"]
        for c in eval_criteria
        if c["name"] in criteria_scores
    )
    return max(0.0, min(1.0, weighted_sum / total_weight))


# ── Overall transcript judge ──────────────────────────────────────────────────

_JUDGE_BASE = (
    "You are a strict, fair evaluator of chatbot conversations. You will be "
    "given a transcript between a USER and an ASSISTANT, plus a usecase and "
    "success criteria. Decide whether the assistant achieved the usecase "
    "while satisfying the success criteria.\n"
    "Use 'inconclusive' if there isn't enough evidence to decide."
)

JUDGE_SYSTEM = (
    _JUDGE_BASE + "\n\n"
    "Reply ONLY with a single JSON object — no markdown, no preamble — with this exact shape:\n"
    '{"result": "pass" | "fail" | "inconclusive", '
    '"reasoning": "<1-3 sentences>", '
    '"score": <float between 0.0 and 1.0>}\n'
)


def _judge_system_with_criteria(eval_criteria: list[dict]) -> str:
    criteria_block = _build_criteria_section(eval_criteria)
    names_block = "\n".join(
        f'    "{c["name"]}": {{"score": <0.0-1.0>, "reasoning": "<one sentence>"}}'
        for c in eval_criteria
    )
    return (
        _JUDGE_BASE + "\n\n"
        + criteria_block + "\n\n"
        "Reply ONLY with a single JSON object — no markdown, no preamble — with this exact shape:\n"
        "{\n"
        '  "result": "pass" | "fail" | "inconclusive",\n'
        '  "reasoning": "<1-3 sentences overall>",\n'
        '  "criteria": {\n'
        + names_block + "\n"
        "  }\n"
        "}\n"
        "IMPORTANT: Do NOT include a top-level 'score' field — it will be computed from the "
        "criterion weights automatically. Your 'result' should reflect holistic judgment after "
        "scoring each criterion."
    )


def build_user_prompt(
    test_case: TestCase,
    transcript: list[dict[str, str]],
    success_criteria_override: str | None = None,
) -> str:
    criteria = success_criteria_override if success_criteria_override else (test_case.success_criteria or "(unspecified)")
    lines: list[str] = [
        "=== USECASE ===", test_case.usecase or "(unspecified)", "",
        "=== SUCCESS CRITERIA ===", criteria, "",
        "=== TRANSCRIPT ===",
    ]
    for m in transcript:
        lines.append(f"[{m.get('role','?').upper()}]: {m.get('content','')}")
    lines.append("\nNow produce the verdict JSON object.")
    return "\n".join(lines)


# ── Per-turn judge ─────────────────────────────────────────────────────────────

_TURN_JUDGE_BASE = """\
You are evaluating ONE turn in a chatbot conversation.
Given the overall goal, success criteria, and this specific exchange, analyse how well the bot handled it."""

TURN_JUDGE_SYSTEM = _TURN_JUDGE_BASE + """

Reply ONLY with this JSON — no markdown, no preamble:
{
  "verdict":        "pass" | "fail" | "inconclusive",
  "score":          <float 0.0–1.0>,
  "need_satisfied": <true|false>,
  "reasoning":      "<1-2 sentences overall assessment>",
  "issues":         ["<specific problem>", ...],
  "strengths":      ["<what was done well>", ...],
  "suggestion":     "<one sentence: what could be improved, or 'None' if perfect>"
}

Scoring guide:
  1.0  — perfect response, fully addresses the need, no issues
  0.7+ — good, minor gaps only
  0.4–0.7 — partially helpful, notable issues
  <0.4 — unhelpful, wrong, or actively harmful
"""


def _turn_judge_system_with_criteria(eval_criteria: list[dict]) -> str:
    criteria_block = _build_criteria_section(eval_criteria)
    names_block = "\n".join(
        f'    "{c["name"]}": {{"score": <0.0-1.0>, "reasoning": "<one sentence>"}}'
        for c in eval_criteria
    )
    return (
        _TURN_JUDGE_BASE + "\n\n"
        + criteria_block + "\n\n"
        "Reply ONLY with this JSON — no markdown, no preamble:\n"
        "{\n"
        '  "verdict":        "pass" | "fail" | "inconclusive",\n'
        '  "need_satisfied": <true|false>,\n'
        '  "reasoning":      "<1-2 sentences overall assessment>",\n'
        '  "issues":         ["<specific problem>", ...],\n'
        '  "strengths":      ["<what was done well>", ...],\n'
        '  "suggestion":     "<one sentence: what could be improved, or \'None\' if perfect>",\n'
        '  "criteria": {\n'
        + names_block + "\n"
        "  }\n"
        "}\n"
        "IMPORTANT: Do NOT include a top-level 'score' field — it will be computed from the "
        "criterion weights automatically.\n\n"
        "Scoring guide per criterion:\n"
        "  1.0  — fully met\n"
        "  0.7+ — mostly met, minor gap\n"
        "  0.4–0.7 — partially met, notable gap\n"
        "  <0.4 — not met or harmful"
    )


def build_turn_prompt(
    test_case: TestCase,
    turn_number: int,
    user_query: str,
    bot_reply: str,
    history_before: list[dict[str, str]],
    success_criteria_override: str | None = None,
) -> str:
    criteria = success_criteria_override if success_criteria_override else (test_case.success_criteria or "(unspecified)")
    lines: list[str] = [
        f"=== OVERALL GOAL ===\n{test_case.usecase or '(unspecified)'}\n",
        f"=== SUCCESS CRITERIA ===\n{criteria}\n",
    ]
    if history_before:
        lines.append("=== CONVERSATION BEFORE THIS TURN ===")
        for m in history_before:
            lines.append(f"[{m['role'].upper()}]: {m['content']}")
        lines.append("")
    lines += [
        f"=== TURN {turn_number} BEING EVALUATED ===",
        f"[USER ASKED]: {user_query}",
        f"[BOT REPLIED]: {bot_reply or '(no reply)'}",
        "\nNow produce the per-turn verdict JSON.",
    ]
    return "\n".join(lines)


# ── Shared JSON parser ─────────────────────────────────────────────────────────

_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    if not text:
        raise ValueError("Empty judge response")
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        m = _JSON_OBJ_RE.search(candidate)
        if not m:
            raise ValueError(f"No JSON found in judge response: {text[:200]!r}")
        return json.loads(m.group(0))


def _parse_criteria_scores(
    data: dict,
    eval_criteria: list[dict],
) -> tuple[dict[str, dict], float]:
    """Extract per-criterion scores from LLM response; fill missing with score=0."""
    raw = data.get("criteria") or {}
    criteria_scores: dict[str, dict] = {}
    for c in eval_criteria:
        name = c["name"]
        entry = raw.get(name) or {}
        try:
            score = max(0.0, min(1.0, float(entry.get("score", 0.0))))
        except (TypeError, ValueError):
            score = 0.0
        criteria_scores[name] = {
            "score": score,
            "reasoning": str(entry.get("reasoning", "(not scored)")).strip(),
        }
    weighted_score = _compute_weighted_score(criteria_scores, eval_criteria)
    return criteria_scores, weighted_score


def parse_verdict_text(text: str, eval_criteria: list[dict] | None = None) -> Verdict:
    """Parse overall-transcript verdict."""
    data = _extract_json(text)

    result = str(data.get("result", "")).lower().strip()
    if result not in ("pass", "fail", "inconclusive"):
        raise ValueError(f"Invalid verdict result: {result!r}")

    if eval_criteria:
        criteria_scores, score = _parse_criteria_scores(data, eval_criteria)
    else:
        criteria_scores = {}
        try:
            score = max(0.0, min(1.0, float(data.get("score", 0.0))))
        except (TypeError, ValueError):
            score = 0.0

    return Verdict(
        result=result,
        reasoning=str(data.get("reasoning", "")).strip(),
        score=score,
        criteria_scores=criteria_scores,
    )


def parse_turn_verdict_text(text: str, eval_criteria: list[dict] | None = None) -> Verdict:
    """Parse per-turn verdict (richer format, tolerates missing extras)."""
    data = _extract_json(text)

    result = str(data.get("verdict", data.get("result", ""))).lower().strip()
    if result not in ("pass", "fail", "inconclusive"):
        result = "inconclusive"

    if eval_criteria:
        criteria_scores, score = _parse_criteria_scores(data, eval_criteria)
    else:
        criteria_scores = {}
        try:
            score = max(0.0, min(1.0, float(data.get("score", 0.0))))
        except (TypeError, ValueError):
            score = 0.0

    need_raw = data.get("need_satisfied")
    if isinstance(need_raw, bool):
        need_satisfied: bool | None = need_raw
    elif isinstance(need_raw, str):
        need_satisfied = need_raw.lower() in ("true", "yes", "1")
    else:
        need_satisfied = None

    def _str_list(val) -> list[str]:
        if isinstance(val, list):
            return [str(v).strip() for v in val if str(v).strip()]
        return []

    return Verdict(
        result=result,
        reasoning=str(data.get("reasoning", "")).strip(),
        score=score,
        need_satisfied=need_satisfied,
        issues=_str_list(data.get("issues")),
        strengths=_str_list(data.get("strengths")),
        suggestion=str(data.get("suggestion", "")).strip(),
        criteria_scores=criteria_scores,
    )


# ── Public async functions ────────────────────────────────────────────────────

async def judge_turn(
    provider: LLMProvider,
    test_case: TestCase,
    turn_number: int,
    user_query: str,
    bot_reply: str,
    history_before: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    success_criteria_override: str | None = None,
) -> Verdict:
    criteria = test_case.eval_criteria or []
    if criteria:
        system = _turn_judge_system_with_criteria(criteria)
    else:
        system = TURN_JUDGE_SYSTEM

    prompt = build_turn_prompt(
        test_case, turn_number, user_query, bot_reply, history_before,
        success_criteria_override=success_criteria_override,
    )
    resp = await provider.complete(
        system=system,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    verdict = parse_turn_verdict_text(resp.text, eval_criteria=criteria or None)
    verdict.input_tokens = resp.input_tokens
    verdict.output_tokens = resp.output_tokens
    verdict.cost_usd = resp.cost_usd
    return verdict


async def judge_transcript(
    provider: LLMProvider,
    test_case: TestCase,
    transcript: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    success_criteria_override: str | None = None,
) -> Verdict:
    criteria = test_case.eval_criteria or []
    if criteria:
        system = _judge_system_with_criteria(criteria)
    else:
        system = JUDGE_SYSTEM

    user_prompt = build_user_prompt(test_case, transcript, success_criteria_override=success_criteria_override)
    resp = await provider.complete(
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    verdict = parse_verdict_text(resp.text, eval_criteria=criteria or None)
    verdict.input_tokens = resp.input_tokens
    verdict.output_tokens = resp.output_tokens
    verdict.cost_usd = resp.cost_usd
    return verdict
