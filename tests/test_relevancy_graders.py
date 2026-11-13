# Phase 5 – B3 Step 1: Layer A mutation tests for the deterministic relevancy & reasoning graders (no LLM).

import pytest

from models import TravelPlan
from quality.graders import GradingInput, run_graders
from quality.graders.reasoning import REQUIRED_STEPS, analysis_text
from quality.schema import Expectations

B3 = ("interest_coverage", "must_include", "reason_grounding", "analysis_structure", "reasoning_covers_choices")


def good_raw(plan: TravelPlan, drop_step: str = "", skip_activity: str = "") -> str:
    """A realistic reply: all 5 ANALYSIS steps, each final activity discussed, then the JSON."""
    lines = ["ANALYSIS:"]
    for n, step in enumerate(REQUIRED_STEPS, start=1):
        if step != drop_step:
            lines.append(f"{n}. {step}: ...")
    for day in plan.itinerary_days:
        for rec in day.activity_recommendations:
            if rec.activity.activity_id != skip_activity:
                lines.append(f"- {day.date}: {rec.activity.activity_id} ({rec.activity.name})")
    return "\n".join(lines) + f"\n\nFINAL OUTPUT:\n```json\n{plan.model_dump_json()}\n```"


def grade(vacation_info, plan, raw=None, expectations=Expectations(max_cost=130)):
    raw = good_raw(plan) if raw is None and plan is not None else (raw or "")
    return {r.grader: r for r in run_graders(GradingInput(vacation_info, plan, raw, expectations, "offline"))}


def failing_b3(results) -> set[str]:
    return {g for g in B3 if results[g].passed is False}


# Phase 5 – B3 Step 1: the known-good plan + reply passes every B3 grader
def test_sample_plan_passes_b3(vacation_info, sample_plan):
    results = grade(vacation_info, sample_plan)
    assert failing_b3(results) == set()
    cov = results["interest_coverage"].details["travelers"]
    # Relevancy against what's POSSIBLE: comedy (Yuri) and theatre (Hiro) aren't offered on 06-10..12.
    assert cov["Yuri"]["coverable"] == ["cooking", "technology", "tennis"]
    assert cov["Hiro"]["coverable"] == ["art", "music", "reading"]
    assert results["interest_coverage"].score == 1.0
    assert results["must_include"].passed is None  # no golden must-include for this input


def _drop_hiro_activities(plan):
    hiro = {"event-2025-06-10-3", "event-2025-06-11-1", "event-2025-06-11-2"}  # reading/art/music
    for day in plan.itinerary_days:
        day.activity_recommendations = [r for r in day.activity_recommendations if r.activity.activity_id not in hiro]


def _overclaim(plan):
    plan.itinerary_days[0].activity_recommendations[0].reasons_for_recommendation.append(
        "Perfect for the traveler's theatre interest")


@pytest.mark.parametrize(
    ("mutate_plan", "raw_kwargs", "expectations", "expected_failure", "detail_key"),
    [
        pytest.param(_drop_hiro_activities, {}, Expectations(max_cost=130), "interest_coverage",
                     "unserved_travelers", id="traveler-unserved"),
        pytest.param(None, {}, Expectations(max_cost=130, must_include_activity_ids=["event-2025-06-12-1"]),
                     "must_include", "missing", id="obvious-match-missing"),
        pytest.param(_overclaim, {}, Expectations(max_cost=130), "reason_grounding", "flagged", id="overclaimed-reason"),
        pytest.param(None, {"drop_step": "Budget Planning"}, Expectations(max_cost=130), "analysis_structure",
                     "missing_steps", id="analysis-step-missing"),
        pytest.param(None, {"skip_activity": "event-2025-06-11-2"}, Expectations(max_cost=130),
                     "reasoning_covers_choices", "unexplained", id="unexplained-choice"),
    ],
)
def test_each_mutation_fails_exactly_its_b3_grader(vacation_info, sample_plan, mutate_plan, raw_kwargs, expectations,
                                                    expected_failure, detail_key):
    plan = sample_plan.model_copy(deep=True)
    if mutate_plan:
        mutate_plan(plan)
    results = grade(vacation_info, plan, good_raw(plan, **raw_kwargs), expectations)
    assert failing_b3(results) == {expected_failure}
    assert detail_key in results[expected_failure].details


# Phase 5 – B3 Step 1: the G5 pattern is flagged with the quoted reason
def test_overclaimed_reason_is_quoted(vacation_info, sample_plan):
    plan = sample_plan.model_copy(deep=True)
    _overclaim(plan)
    flagged = grade(vacation_info, plan)["reason_grounding"].details["flagged"]
    assert flagged == [{"id": "event-2025-06-10-0", "claims": ["theatre"],
                        "reason": "Perfect for the traveler's theatre interest"}]


# Phase 5 – B3 Step 1: known heuristic false alarm (contextual mention) – documented, adjudicated by the judge
def test_contextual_mention_is_a_known_false_alarm(vacation_info, sample_plan):
    plan = sample_plan.model_copy(deep=True)
    plan.itinerary_days[2].activity_recommendations[0].reasons_for_recommendation.append(
        "Fits well after the morning hiking event")
    assert grade(vacation_info, plan)["reason_grounding"].passed is False


# Phase 5 – B3 Step 1: a traveler with no coverable interest (the G5 theatre case) isn't penalized
def test_no_coverable_interest_is_not_applicable(vacation_info, sample_plan):
    kai = type(vacation_info).model_validate(
        {**vacation_info.model_dump(), "travelers": [{"name": "Kai", "age": 22, "interests": ["theatre"]}]})
    assert grade(kai, sample_plan)["interest_coverage"].passed is None


def test_analysis_text_split():
    assert analysis_text("ANALYSIS: x\nFINAL OUTPUT: {}") == "ANALYSIS: x\n"
    assert analysis_text("thinking... {\"a\": 1}") == "thinking... "


def test_b3_graders_run_in_prod_mode(vacation_info, sample_plan):
    results = {r.grader: r for r in run_graders(GradingInput.for_request(vacation_info, sample_plan, good_raw(sample_plan)))}
    assert failing_b3(results) == set()
    assert results["must_include"].passed is None
