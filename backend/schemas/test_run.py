from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RunStatus = Literal["running", "completed", "failed", "stopped", "paused"]
Verdict = Literal["pass", "fail", "inconclusive"]
StopReason = Literal[
    "endpoint_error",
    "endpoint_signaled_end",
    "goal_achieved",
    "max_turns",
    "cost_cap",
    "user_stopped",
    "simulator_error",
    "judge_error",
    "step_pause",
]


class TestRunCreate(BaseModel):
    name: str | None = None
    test_case_id: int
    endpoint_config_id: int
    simulator_llm_id: int
    judge_llm_id: int
    max_cost_usd: float | None = Field(default=None, ge=0.0)
    judge_criteria_override: str | None = None
    skip_judge: bool = False
    step_mode: bool = False
    ws_connect_delay_sec: float = Field(default=2.0, ge=0.0, le=30.0)


class TestRunUpdate(BaseModel):
    name: str | None = None
    # Tester annotations. marker_color accepts a hex string ("#RRGGBB") to set,
    # or "" / null to clear. Use model_fields_set in the handler to distinguish
    # "not provided" from an explicit clear.
    reviewed: bool | None = None
    marker_color: str | None = None


class TestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str | None = None
    test_case_id: int
    endpoint_config_id: int
    simulator_llm_id: int
    judge_llm_id: int
    started_at: datetime
    finished_at: datetime | None
    status: RunStatus
    stop_reason: StopReason | None
    verdict: Verdict | None
    verdict_reasoning: str | None
    verdict_score: float | None
    run_analysis: dict[str, Any] | None = None
    conclusion:   dict[str, Any] | None = None
    judge_criteria_override: str | None = None
    skip_judge: bool = False
    total_tokens: int
    total_cost_usd: float
    max_cost_usd: float | None
    reviewed: bool = False
    marker_color: str | None = None
    step_mode: bool = False
    next_pending_query: str | None = None
    ws_connect_delay_sec: float = 2.0
    # Turn-verdict aggregates, attached by the list/detail read paths. Default to
    # the "no turns / no verdicts" state for write paths that don't compute them.
    turn_total: int = 0
    turn_failed: int = 0
    turn_has_verdict: bool = False
