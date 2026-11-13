# Phase 5 – B0 Step 4: grader registry. A grader is a plain function
#     grade(case, plan, raw_response) -> GraderResult
# B0 has one grader (parse). B1–B3 only ADD functions to GRADERS; the harness doesn't change.
# Graders must be deterministic and side-effect free, so the app can also run them online.

from typing import Callable, Optional

from models import TravelPlan
from quality.schema import EvalCase, GraderResult

Grader = Callable[[Optional[EvalCase], Optional[TravelPlan], str], GraderResult]


# Phase 5 – B0 Step 4: did the reply become a valid TravelPlan?
def grade_parse(case: Optional[EvalCase], plan: Optional[TravelPlan], raw_response: str) -> GraderResult:
    return GraderResult(
        grader="parse",
        severity="hard",
        passed=plan is not None,
        score=1.0 if plan is not None else 0.0,
        details={} if plan is not None else {"reply_chars": len(raw_response)},
    )


GRADERS: list[Grader] = [grade_parse]


# Phase 5 – B0 Step 4: run every registered grader; case is None for production traffic
def run_graders(case: Optional[EvalCase], plan: Optional[TravelPlan], raw_response: str) -> list[GraderResult]:
    return [grade(case, plan, raw_response) for grade in GRADERS]
