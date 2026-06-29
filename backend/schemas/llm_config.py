from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["simulator", "judge", "either"]


class LLMConfigBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # Free-form label. "anthropic"/"claude" use the Anthropic SDK; any other
    # value is treated as OpenAI-compatible (openai, lmstudio, ollama, vllm,
    # groq, together, openrouter, deepseek, mistral, …).
    provider: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1)
    # Base URL for OpenAI-compatible / local servers, e.g.
    # http://localhost:1234/v1 (LM Studio). Blank → provider cloud default.
    base_url: str | None = Field(default=None, max_length=2048)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=200_000)
    role: Role = "either"


class LLMConfigCreate(LLMConfigBase):
    # Optional: cloud providers need a key; local servers usually don't.
    api_key: str = Field(default="", description="Provider API key (optional for local servers)")


class LLMConfigUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    role: Role | None = None


class LLMConfigOut(LLMConfigBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    has_api_key: bool
    created_at: datetime
    updated_at: datetime
