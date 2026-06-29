"""Tests for the generic LLM provider factory.

Covers the routing rules that make the tool work with any OpenAI-compatible
provider (cloud or local) rather than just OpenAI and Anthropic.
"""
from __future__ import annotations

import pytest

from backend.services.llm import build_provider
from backend.services.llm.anthropic_provider import AnthropicProvider
from backend.services.llm.base import estimate_cost
from backend.services.llm.openai_provider import OpenAIProvider


def test_anthropic_routes_to_anthropic_sdk():
    p = build_provider("anthropic", "claude-sonnet-4-6", "sk-ant-xxx")
    assert isinstance(p, AnthropicProvider)


def test_claude_alias_routes_to_anthropic_sdk():
    p = build_provider("claude", "claude-sonnet-4-6", "sk-ant-xxx")
    assert isinstance(p, AnthropicProvider)


def test_anthropic_requires_key():
    with pytest.raises(ValueError):
        build_provider("anthropic", "claude-sonnet-4-6", "")


def test_openai_cloud_requires_key_without_base_url():
    with pytest.raises(ValueError):
        build_provider("openai", "gpt-4o-mini", "")


def test_openai_cloud_with_key():
    p = build_provider("openai", "gpt-4o-mini", "sk-xxx")
    assert isinstance(p, OpenAIProvider)


def test_unknown_provider_is_openai_compatible():
    # Any non-anthropic label is treated as OpenAI-compatible.
    p = build_provider("groq", "llama-3.1-8b-instant", "gsk_xxx")
    assert isinstance(p, OpenAIProvider)


def test_local_server_needs_no_key():
    # A base_url (local / self-hosted) makes the API key optional.
    p = build_provider("lmstudio", "qwen2.5-7b-instruct", "", "http://localhost:1234/v1")
    assert isinstance(p, OpenAIProvider)


def test_base_url_is_applied_to_client():
    p = build_provider("ollama", "llama3.1", "", "http://localhost:11434/v1")
    # The OpenAI SDK normalizes/stores the configured base_url on the client.
    assert "11434" in str(p._client.base_url)


def test_unknown_model_costs_zero():
    # Local/custom models aren't in the price table → cost tracking is 0.
    assert estimate_cost("some-local-model", 1000, 1000) == 0.0
