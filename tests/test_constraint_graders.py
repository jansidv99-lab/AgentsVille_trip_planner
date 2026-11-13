# Phase 5 – B2 Step 3: Layer A mutation tests for the constraint graders (no LLM).
# Each mutation breaks the known-good sample plan in ONE way (adjusting total_cost where needed so the
# arithmetic stays consistent) and asserts that exactly the matching grader fails.

import pytest

from models import ActivityRecommendation
from project_lib import ACTIVITY_CALENDAR
from quality.graders import CONSTRAINT_GRADERS, GradingInput, run_graders, task_succeeded
from quality.schema import Expectations

CALENDAR = {a["activity_id"]: a for a in ACTIVITY_CALENDAR}
DEFAULT_EXPECTATIONS = Expectations(max_cost=130)


def grade(vacation_info, plan, expectations=DEFAULT_EXPECTATIONS):
    return {r.grader: r for r in run_graders(GradingInput(vacation_info, plan, "raw", expectations, "offline"))}


def failing(results) -> set[str]:
    return {name for name, r in results.items() if r.passed is False}


def add_activity(plan, day_index, activity_id):
    """Add a real calendar activity to a day and keep total_cost = sum of prices."""
    act = CALENDAR[activity_id]
    plan.itinerary_days[day_index].activity_recommendations.append(
        ActivityRecommendation(activity=act, reasons_for_recommendation=["test"]))
    plan.total_cost += act["price"]


# Phase 5 – B2 Step 3: the known-good plan meets every constraint
def test_sample_plan_meets_all_constraints(vacation_info, sample_plan):
    results = grade(vacation_info, sample_plan)
    assert failing(results) == set()
    assert task_succeeded(list(results.values()))
    assert results["weather_safety"].details["bad_weather_days"] == ["2025-06-12"]
    shape = results["plan_shape"].details
    assert shape["activities"] == 6 and shape["activities_per_day"] == 2.0
    assert shape["budget_utilization"] == pytest.approx(108 / 130, abs=0.001)


def _empty_day(plan):
    removed = plan.itinerary_days[1].activity_recommendations
    plan.total_cost -= sum(r.activity.price for r in removed)
    plan.itinerary_days[1].activity_recommendations = []


@pytest.mark.parametrize(
    ("mutate", "expectations", "expected_failure", "detail_key"),
    [
        pytest.param(None, Expectations(max_cost=100), "budget_within_limit", "over_by", id="over-budget"),
        pytest.param(lambda p: setattr(p, "total_cost", 107), DEFAULT_EXPECTATIONS, "cost_arithmetic", "diff",
                     id="wrong-total"),
        pytest.param(_empty_day, DEFAULT_EXPECTATIONS, "day_coverage", "missing_days", id="empty-day"),
        pytest.param(lambda p: add_activity(p, 2, "event-2025-06-12-3"), DEFAULT_EXPECTATIONS, "no_time_overlaps",
                     "overlaps", id="same-activity-twice"),
        pytest.param(lambda p: add_activity(p, 2, "event-2025-06-12-0"), DEFAULT_EXPECTATIONS, "weather_safety",
                     "unsafe", id="outdoor-in-thunderstorm"),
    ],
)
def test_each_mutation_fails_exactly_its_grader(vacation_info, sample_plan, mutate, expectations, expected_failure,
                                                 detail_key):
    plan = sample_plan.model_copy(deep=True)
    if mutate:
        mutate(plan)
    results = grade(vacation_info, plan, expectations)

    assert failing(results) == {expected_failure}
    assert detail_key in results[expected_failure].details
    assert not task_succeeded(list(results.values()))


# Phase 5 – B2 Step 3: the G2/G7 failure, reported precisely (and partial credit per bad-weather day)
def test_weather_safety_details(vacation_info, sample_plan):
    plan = sample_plan.model_copy(deep=True)
    add_activity(plan, 2, "event-2025-06-12-0")
    result = grade(vacation_info, plan)["weather_safety"]
    assert result.details["unsafe"] == {"2025-06-12": ["event-2025-06-12-0"]}
    assert result.score == 0.0  # the only bad-weather day is unsafe


def test_flex_activity_is_safe_in_bad_weather(vacation_info, sample_plan):
    plan = sample_plan.model_copy(deep=True)
    add_activity(plan, 2, "event-2025-06-12-1")  # moves indoors if it rains
    assert grade(vacation_info, plan)["weather_safety"].passed is True


# Phase 5 – B2 Step 3: the G1#1 failure – a per-person total is diagnosed with a hint
def test_per_person_pricing_is_diagnosed(vacation_info, sample_plan):
    plan = sample_plan.model_copy(deep=True)
    plan.total_cost = 108 * len(vacation_info.travelers)
    details = grade(vacation_info, plan, Expectations(max_cost=500))["cost_arithmetic"].details
    assert details["diff"] == 108 and "per-person pricing" in details["hint"]


# Phase 5 – B2 Step 3: production mode uses the request's budget
def test_constraints_run_in_prod_mode(vacation_info, sample_plan):
    tight = vacation_info.model_copy(update={"budget": 100})
    results = {r.grader: r for r in run_graders(GradingInput.for_request(tight, sample_plan, "raw"))}
    assert results["budget_within_limit"].passed is False
    assert results["budget_within_limit"].details["max_cost"] == 100


def test_unparsed_reply_fails_task_but_constraints_not_applicable(vacation_info):
    results = grade(vacation_info, None)
    assert all(results[g].passed is None for g in CONSTRAINT_GRADERS)
    assert not task_succeeded(list(results.values()))
