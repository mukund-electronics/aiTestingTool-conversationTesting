from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EndpointConfigBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1)
    protocol: Literal["http", "websocket"] = "http"
    http_method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "POST"
    headers: dict[str, Any] = Field(default_factory=dict)
    request_body_template: str = "{}"
    response_extractors: dict[str, str] = Field(default_factory=dict)
    auth_type: Literal["none", "bearer", "api_key", "basic"] = "none"
    auth_value: str = ""
    timeout_seconds: int = Field(default=30, ge=1, le=600)
    max_retries: int = Field(default=3, ge=0, le=10)


class EndpointConfigCreate(EndpointConfigBase):
    pass


class EndpointConfigUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    protocol: Literal["http", "websocket"] | None = None
    http_method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] | None = None
    headers: dict[str, Any] | None = None
    request_body_template: str | None = None
    response_extractors: dict[str, str] | None = None
    auth_type: Literal["none", "bearer", "api_key", "basic"] | None = None
    auth_value: str | None = None
    timeout_seconds: int | None = None
    max_retries: int | None = None


class EndpointConfigOut(EndpointConfigBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
