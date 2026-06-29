from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BatchRunCreate(BaseModel):
    name: str | None = None
    count: int = Field(default=1, ge=1, le=10)
    test_case_id: int
    endpoint_config_id: int
    simulator_llm_id: int
    judge_llm_id: int
    skip_judge: bool = False
    max_cost_usd: float | None = Field(default=None, ge=0.0)
    judge_criteria_override: str | None = None
    per_run_overrides: list[dict[str, str]] | None = None
    # per_run_overrides[k] maps dot-notation field paths to static values for run k
    # e.g. [{"imei": "11111", "device.mid": "A"}, {"imei": "22222", "device.mid": "B"}]
    per_run_test_case_ids: list[int] | None = None
    # per_run_test_case_ids[k] = test case for run k; falls back to test_case_id if absent/0
    ws_connect_delay_sec: float = Field(default=2.0, ge=0.0, le=30.0)


class BatchRunResponse(BaseModel):
    batch_id: int
    run_ids: list[int]
    batch_size: int
    name: str


class RunBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    test_case_name: str
    endpoint_name: str
    count: int
    created_at: datetime
    run_ids: list[int]
