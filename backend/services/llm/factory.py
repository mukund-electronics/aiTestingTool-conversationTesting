from __future__ import annotations

from backend.services.llm.base import LLMProvider

# Provider labels routed through the native Anthropic SDK. Every other label is
# treated as OpenAI-compatible — the de-facto standard spoken by OpenAI, LM
# Studio, Ollama, vLLM, LocalAI, Groq, Together, OpenRouter, DeepSeek, Mistral,
# and most others — so a single client with a configurable base_url covers them
# all without per-provider code.
_ANTHROPIC_PROVIDERS = {"anthropic", "claude"}


def build_provider(
    provider: str,
    model: str,
    api_key: str = "",
    base_url: str | None = None,
) -> LLMProvider:
    """Instantiate an LLM provider from a stored LLMConfig.

    ``provider`` is a free-form label. "anthropic"/"claude" use the native
    Anthropic SDK; anything else is treated as OpenAI-compatible and routed
    through the OpenAI client, optionally pointed at ``base_url``. That is how
    local servers (LM Studio, Ollama, vLLM, …) and other OpenAI-compatible APIs
    are supported without provider-specific code.

    SDK imports are deferred to keep ``import backend.services.llm`` cheap and
    to avoid forcing test environments to install every provider SDK.
    """
    key = (api_key or "").strip()
    url = (base_url or "").strip()
    provider_lc = provider.lower().strip()

    if provider_lc in _ANTHROPIC_PROVIDERS:
        if not key:
            raise ValueError(
                "Anthropic API key is missing. Set it on this LLM config in Configs → LLMs."
            )
        from backend.services.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=key, model=model)

    # OpenAI-compatible (default for any other label). A base_url means a
    # local/self-hosted or third-party endpoint, which typically ignores the
    # key — so a placeholder is fine there. Only the OpenAI cloud (no base_url)
    # strictly requires a real key.
    if not url and not key:
        raise ValueError(
            "API key is missing. Set it on this LLM config in Configs → LLMs, "
            "or set a Base URL to use a local / OpenAI-compatible server."
        )
    from backend.services.llm.openai_provider import OpenAIProvider
    return OpenAIProvider(api_key=key or "not-needed", model=model, base_url=url or None)
