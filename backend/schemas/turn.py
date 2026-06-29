from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TurnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    test_run_id: int
    turn_number: int
    user_query: str
    raw_request_payload: Any | None
    raw_response_payload: Any | None
    extracted_reply: str
    extracted_fields: dict[str, Any]
    latency_ms: int | None
    status_code: int | None
    error: str | None
    tokens_used: int
    cost_usd: float
    simulator_done: bool
    turn_verdict: str | None
    turn_score: float | None
    turn_reasoning: str | None
    turn_analysis: dict[str, Any] | None = None
    created_at: datetime
