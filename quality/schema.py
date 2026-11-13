# Phase 5 – B0 Step 1: Layer B schemas. EvalRecord is the ONE record shape used by offline eval runs
# and (from Layer C – C1) by production logs, so dashboards and queries work for both.

import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from models import VacationInfo
from project_lib import Interest

Tag = Literal["grounding", "constraints", "weather", "budget", "relevancy", "scale", "utilization"]
Severity = Literal["hard", "soft", "info"]


# Phase 5 – B0 Step 1: per-case ground truth – rule-based and human-approved
class Expectations(BaseModel):
    max_cost: int = Field(gt=0, description="Budget ceiling, normally equal to vacation_info.budget")
    min_activities_per_day: int = Field(default=1, ge=0)
    allowed_activity_ids_by_date: Optional[dict[datetime.date, list[str]]] = Field(
        default=None,
        description="Exhaustive allow-list for days whose right answer is precise (e.g. one indoor option)",
    )
    must_include_activity_ids: list[str] = Field(default_factory=list, description="Soft relevancy expectation")
    uncoverable_interests: list[Interest] = Field(
        default_factory=list,
        description="Interests no activity on the trip dates offers; claiming to cover them is a hallucination",
    )
    notes: str = ""


# Phase 5 – B0 Step 1: human review status – the harness only runs approved cases
class Review(BaseModel):
    status: Literal["draft", "approved"] = "draft"
    reviewer: Optional[str] = None
    reviewed_on: Optional[datetime.date] = None


# Phase 5 – B0 Step 1: one golden dataset row (one line of the JSONL file)
class EvalCase(BaseModel):
    case_id: str
    title: str
    tags: list[Tag]
    smoke: bool = False
    vacation_info: VacationInfo
    expectations: Expectations
    review: Review = Field(default_factory=Review)


# Phase 5 – B0 Step 1: the outcome of one grader on one LLM run
class GraderResult(BaseModel):
    grader: str
    severity: Severity
    passed: Optional[bool] = None
    score: Optional[float] = Field(default=None, ge=0, le=1)
    details: dict = Field(default_factory=dict)


# Phase 5 – B0 Step 1: one LLM run, graded (offline eval row or production log line)
class EvalRecord(BaseModel):
    schema_version: Literal["1"] = "1"
    trace_id: str
    timestamp: datetime.datetime
    source: Literal["offline", "prod"]
    case_id: Optional[str] = None
    dataset: Optional[str] = None  # e.g. "itinerary_golden@1.0.0"; None in production
    prompt_version: str
    model: str
    repeat: int = 0
    latency_ms: Optional[float] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    parsed: bool
    error: Optional[str] = None
    grader_results: list[GraderResult] = Field(default_factory=list)
    cache_key: Optional[str] = None
    git_sha: Optional[str] = None

    # Phase 5 – B0 Step 1: convenience lookup used by reports and tests
    def result(self, grader: str) -> Optional[GraderResult]:
        return next((r for r in self.grader_results if r.grader == grader), None)
