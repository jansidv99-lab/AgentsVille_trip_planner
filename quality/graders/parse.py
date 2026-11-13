# Phase 5 – B0 Step 4: the parse grader – did the reply become a valid TravelPlan?
# Phase 5 – B1 Step 1: migrated to the GradingInput signature.

from quality.graders.base import GradingInput, grader
from quality.schema import GraderResult


@grader("B0")
def grade_parse(inp: GradingInput) -> GraderResult:
    ok = inp.plan is not None
    return GraderResult(
        grader="parse",
        severity="hard",
        passed=ok,
        score=1.0 if ok else 0.0,
        details={} if ok else {"reply_chars": len(inp.raw_response)},
    )
