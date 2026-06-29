from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./conv_tester.db"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    backend_url: str = "http://127.0.0.1:8000"

    # API keys for LLM providers are stored per-LLMConfig record, not here.
    # SECRET_KEY is used to encrypt those stored keys at rest (optional).
    secret_key: str = ""

    default_max_turns: int = Field(default=10, ge=1, le=200)
    default_http_timeout: int = Field(default=30, ge=1, le=600)
    default_http_retries: int = Field(default=3, ge=0, le=10)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
