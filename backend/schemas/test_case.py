from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Mode = Literal["single_turn", "multi_turn"]


class EvalCriterion(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    weight: float = Field(default=1.0, ge=0.0, le=1.0)


class TestCaseBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    usecase: str = Field(min_length=1)
    persona: str = ""
    known_facts: list[Any] = Field(default_factory=list)
    success_criteria: str = Field(min_length=1)
    starting_query: str = ""
    max_turns: int = Field(default=10, ge=1, le=200)
    mode: Mode = "multi_turn"
    eval_criteria: list[dict[str, Any]] | None = None
    pass_threshold: float = Field(default=0.7, ge=0.0, le=1.0)

    @field_validator("pass_threshold", mode="before")
    @classmethod
    def _coerce_pass_threshold(cls, v: Any) -> float:
        if v is None:
            return 0.7
        return v


class TestCaseCreate(TestCaseBase):
    pass


class TestCaseUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    usecase: str | None = None
    persona: str | None = None
    known_facts: list[Any] | None = None
    success_criteria: str | None = None
    starting_query: str | None = None
    max_turns: int | None = None
    mode: Mode | None = None
    eval_criteria: list[dict[str, Any]] | None = None
    pass_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class TestCaseOut(TestCaseBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
