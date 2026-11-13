# Phase 5 – B0 Step 4: grader registry. B1–B3 only ADD graders to GRADERS; the harness doesn't change.
# Phase 5 – B1 Step 1: graders take a GradingInput (request + plan + reply + expectations), so the
# same deterministic code grades offline eval runs and live production traffic.

from quality.graders.base import Grader, GradingInput, grader, not_applicable
from quality.graders.grounding import (
    HALLUCINATION_GRADERS,
    grade_activity_details_match,
    grade_activity_exists,
    grade_activity_on_its_date,
    grade_description_verbatim,
    grade_plan_matches_request,
    grade_uncoverable_interest_mentions,
    grade_weather_matches_forecast,
)
from quality.graders.parse import grade_parse
from quality.schema import GraderResult

GRADERS: list[Grader] = [
    grade_parse,
    # B1 – hallucination & grounding
    grade_activity_exists,
    grade_activity_details_match,
    grade_activity_on_its_date,
    grade_weather_matches_forecast,
    grade_plan_matches_request,
    grade_description_verbatim,
    grade_uncoverable_interest_mentions,
]


# Phase 5 – B1 Step 1: run every registered grader and stamp each result with its slice
def run_graders(inp: GradingInput) -> list[GraderResult]:
    return [g(inp).model_copy(update={"slice": getattr(g, "slice", None)}) for g in GRADERS]


__all__ = ["GRADERS", "HALLUCINATION_GRADERS", "Grader", "GradingInput", "grader", "not_applicable", "run_graders"]
