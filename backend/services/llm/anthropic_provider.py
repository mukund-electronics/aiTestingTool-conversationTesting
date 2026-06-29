from __future__ import annotations

from anthropic import AsyncAnthropic

from backend.services.llm.base import LLMResponse, estimate_cost


class AnthropicProvider:
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("Anthropic api_key is required")
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(
        self,
        system: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        # Anthropic expects user/assistant turns only; the system prompt is a
        # top-level parameter, not a message.
        normalized: list[dict] = []
        for m in messages:
            role = m.get("role")
            if role not in ("user", "assistant"):
                continue
            normalized.append({"role": role, "content": m.get("content", "")})

        resp = await self._client.messages.create(
            model=self._model,
            system=system or "",
            messages=normalized,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        text_parts: list[str] = []
        for block in resp.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(getattr(block, "text", ""))
        text = "".join(text_parts).strip()

        usage = resp.usage
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0

        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=estimate_cost(self._model, input_tokens, output_tokens),
            raw=resp.model_dump() if hasattr(resp, "model_dump") else None,
        )
