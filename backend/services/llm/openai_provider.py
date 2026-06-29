from __future__ import annotations

from openai import AsyncOpenAI

from backend.services.llm.base import LLMResponse, estimate_cost


class OpenAIProvider:
    """OpenAI-compatible chat client.

    Works against the OpenAI cloud or any compatible server (LM Studio, Ollama,
    vLLM, LocalAI, Groq, Together, OpenRouter, …) when ``base_url`` is supplied.
    """

    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        if not api_key:
            raise ValueError("OpenAI api_key is required")
        # base_url=None falls back to the OpenAI cloud default.
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self._model = model

    async def complete(
        self,
        system: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        chat_messages: list[dict] = []
        if system:
            chat_messages.append({"role": "system", "content": system})
        chat_messages.extend(messages)

        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=chat_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = (resp.choices[0].message.content or "").strip()
        usage = resp.usage
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=estimate_cost(self._model, input_tokens, output_tokens),
            raw=resp.model_dump() if hasattr(resp, "model_dump") else None,
        )
