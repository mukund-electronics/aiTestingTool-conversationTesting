"""Simulator: produces the next user query given a test case + transcript."""

from __future__ import annotations

from dataclasses import dataclass

from backend.models.test_case import TestCase
from backend.services.llm import LLMProvider

DONE_TOKEN = "<<<DONE>>>"


@dataclass
class SimulatorOutput:
    user_query: str
    done: bool
    input_tokens: int
    output_tokens: int
    cost_usd: float


def build_system_prompt(test_case: TestCase) -> str:
    facts = test_case.known_facts or []
    if facts:
        facts_block = "\n".join(f"- {f}" for f in facts)
    else:
        facts_block = "(none)"
    return (
        "You are simulating a user interacting with a chatbot to test it.\n"
        "\n"
        f"Your goal: {test_case.usecase}\n"
        f"Your persona: {test_case.persona or '(unspecified)'}\n"
        "Facts you know (reveal only when relevant or asked):\n"
        f"{facts_block}\n"
        "\n"
        "Rules:\n"
        "- Stay in character. You are the USER, not the assistant.\n"
        "- Generate only the next user message. No meta-commentary.\n"
        "- Pursue your goal naturally across turns.\n"
        f"- If the bot has fully achieved your goal, end with the exact token {DONE_TOKEN} "
        "on its own line after your message."
    )


def parse_simulator_text(text: str) -> tuple[str, bool]:
    """Split off the optional DONE token from the simulator's response."""
    if not text:
        return "", False
    stripped = text.strip()
    if DONE_TOKEN in stripped:
        # Remove the token and any trailing/leading whitespace it left behind.
        cleaned = stripped.replace(DONE_TOKEN, "").strip()
        return cleaned, True
    return stripped, False


async def generate_user_query(
    provider: LLMProvider,
    test_case: TestCase,
    transcript: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> SimulatorOutput:
    """Call the simulator LLM and return the next user message.

    ``transcript`` is the OpenAI-style messages list of the conversation so
    far between USER and ASSISTANT (from the chatbot's perspective). Before
    we send it to the simulator, we must flip the roles, because the
    simulator IS the user, and from its POV the chatbot's replies are the
    "assistant" turns to react to.
    """
    flipped: list[dict[str, str]] = []
    for m in transcript:
        role = m.get("role")
        if role == "user":
            flipped.append({"role": "assistant", "content": m.get("content", "")})
        elif role == "assistant":
            flipped.append({"role": "user", "content": m.get("content", "")})

    # The simulator needs a user turn to respond to. If we just started or
    # the last message was already a user (simulator) turn, append a
    # neutral prompt to elicit the next message.
    if not flipped or flipped[-1]["role"] != "user":
        flipped.append(
            {
                "role": "user",
                "content": "(Begin the conversation with your first message to the bot.)"
                if not flipped
                else "(Continue the conversation. What do you say next?)",
            }
        )

    system = build_system_prompt(test_case)
    resp = await provider.complete(
        system=system,
        messages=flipped,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    user_query, done = parse_simulator_text(resp.text)
    return SimulatorOutput(
        user_query=user_query,
        done=done,
        input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens,
        cost_usd=resp.cost_usd,
    )
