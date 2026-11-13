# Phase 5 – B1 Step 1: what every grader receives (GradingInput) and how graders are declared.
# Graders get the traveler's REQUEST, not only a golden case, so the same code grades offline eval
# runs (golden expectations) and live production traffic (expectations derived from the request).

from dataclasses import dataclass
from typing import Callable, Literal, Optional

from models import TravelPlan, VacationInfo
from quality.schema import EvalCase, Expectations, GraderResult


# Phase 5 – B1 Step 1: the single input type for all graders
@dataclass(frozen=True)
class GradingInput:
    vacation_info: VacationInfo
    plan: Optional[TravelPlan]       # None when the reply didn't parse
    raw_response: str
    expectations: Expectations
    source: Literal["offline", "prod"] = "offline"

    # Phase 5 – B1 Step 1: offline – a golden case and its human-approved expectations
    @classmethod
    def for_case(cls, case: EvalCase, plan: Optional[TravelPlan], raw_response: str) -> "GradingInput":
        return cls(case.vacation_info, plan, raw_response, case.expectations, "offline")

    # Phase 5 – B1 Step 1: production – no answer key, so expectations come from the request itself
    @classmethod
    def for_request(cls, vacation_info: VacationInfo, plan: Optional[TravelPlan], raw_response: str) -> "GradingInput":
        return cls(vacation_info, plan, raw_response, Expectations(max_cost=vacation_info.budget), "prod")


Grader = Callable[[GradingInput], GraderResult]


# Phase 5 – B1 Step 1: decorator that tags a grader with the slice that introduced it (for reports)
def grader(slice_: str) -> Callable[[Grader], Grader]:
    def decorate(fn: Grader) -> Grader:
        fn.slice = slice_  # type: ignore[attr-defined]
        return fn
    return decorate


# Phase 5 – B1 Step 1: standard "not applicable" verdict (excluded from pass rates)
def not_applicable(name: str, severity: str, reason: str) -> GraderResult:
    return GraderResult(grader=name, severity=severity, passed=None, score=None, details={"skipped": reason})
