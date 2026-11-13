# Phase 5 – B1 Step 2: Layer A mutation tests for the grounding graders (no LLM).
# Each test breaks the known-good sample plan in ONE way and asserts that exactly the matching
# grader fails – proving each grader catches its own failure mode and nothing else.

import datetime

import pytest

from models import ActivityRecommendation, ItineraryDay
from quality.graders import GRADERS, HALLUCINATION_GRADERS, GradingInput, run_graders
from quality.schema import Expectations

THEATRE_EXPECTATIONS = Expectations(max_cost=130, uncoverable_interests=["theatre"])


def grade(vacation_info, plan, expectations=THEATRE_EXPECTATIONS, raw="raw reply"):
    inp = GradingInput(vacation_info, plan, raw, expectations, "offline")
    return {r.grader: r for r in run_graders(inp)}


def failing(results) -> set[str]:
    return {name for name, r in results.items() if r.passed is False}


def first_activity(plan, day=0, rec=0):
    return plan.itinerary_days[day].activity_recommendations[rec].activity


# Phase 5 – B1 Step 2: the known-good plan (built from the mock data) passes everything
def test_sample_plan_passes_all_grounding_graders(vacation_info, sample_plan):
    results = grade(vacation_info, sample_plan)
    assert failing(results) == set()
    assert all(results[g].score == 1.0 for g in HALLUCINATION_GRADERS)
    assert results["uncoverable_interest_mentions"].details["count"] == 0


# Phase 5 – B1 Step 2: one mutation per failure mode → exactly one failing grader
def _fake_id(p):
    first_activity(p).activity_id = "event-2025-06-10-99"


# Phase 5 – B2 Step 3: mutations keep total_cost = sum of prices, so B2's cost_arithmetic stays green and
# each mutation still breaks exactly ONE property.
def _price(p):
    p.total_cost -= first_activity(p).price - 5
    first_activity(p).price = 5


def _location(p):
    first_activity(p).location = "The Moon"


def _relabel_theatre(p):
    first_activity(p).related_interests.append("theatre")


def _move_day(p):
    rec = p.itinerary_days[0].activity_recommendations.pop(0)
    p.itinerary_days[1].activity_recommendations.append(rec)


def _sunny_storm(p):
    p.itinerary_days[2].weather.condition = "sunny"


def _extra_day(p):
    # A real 06-13 activity with the real 06-13 weather – only the trip boundary is wrong.
    template = p.itinerary_days[0].activity_recommendations[0]
    from project_lib import ACTIVITY_CALENDAR
    act = next(a for a in ACTIVITY_CALENDAR if a["activity_id"] == "event-2025-06-13-0")
    rec = ActivityRecommendation(activity=act, reasons_for_recommendation=template.reasons_for_recommendation)
    weather = {"temperature": 15, "temperature_unit": "celsius", "condition": "rainy"}
    p.itinerary_days.append(ItineraryDay(date=datetime.date(2025, 6, 13), weather=weather, activity_recommendations=[rec]))
    p.total_cost += act["price"]


def _wrong_city(p):
    p.city = "Atlantis"


def _paraphrase(p):
    first_activity(p).description = "A fun tech breakfast."


@pytest.mark.parametrize(
    ("mutate", "expected_failure", "detail_key"),
    [
        pytest.param(_fake_id, "activity_exists", "unknown_ids", id="fake-id"),
        pytest.param(_price, "activity_details_match", "mismatches", id="price-altered"),
        pytest.param(_location, "activity_details_match", "mismatches", id="location-altered"),
        pytest.param(_relabel_theatre, "activity_details_match", "mismatches", id="interest-relabeled"),
        pytest.param(_move_day, "activity_on_its_date", "misplaced", id="moved-to-other-day"),
        pytest.param(_sunny_storm, "weather_matches_forecast", "mismatches", id="weather-altered"),
        pytest.param(_extra_day, "plan_matches_request", "days_outside_trip", id="day-outside-trip"),
        pytest.param(_wrong_city, "plan_matches_request", "city", id="wrong-city"),
        pytest.param(_paraphrase, "description_verbatim", "paraphrased_ids", id="description-paraphrased"),
    ],
)
def test_each_mutation_fails_exactly_its_grader(vacation_info, sample_plan, mutate, expected_failure, detail_key):
    plan = sample_plan.model_copy(deep=True)
    mutate(plan)
    results = grade(vacation_info, plan)

    assert failing(results) == {expected_failure}
    assert detail_key in results[expected_failure].details
    assert 0 <= results[expected_failure].score < 1


# Phase 5 – B1 Step 2: details pinpoint WHAT changed (expected vs got)
def test_details_show_expected_and_got(vacation_info, sample_plan):
    plan = sample_plan.model_copy(deep=True)
    _price(plan)
    mismatch = grade(vacation_info, plan)["activity_details_match"].details["mismatches"]
    assert mismatch == {"event-2025-06-10-0": {"price": {"expected": "20", "got": "5"}}}


# Phase 5 – B1 Step 2: a fabricated id is counted once (by activity_exists), not three times
def test_fabricated_id_is_not_double_counted(vacation_info, sample_plan):
    plan = sample_plan.model_copy(deep=True)
    _fake_id(plan)
    results = grade(vacation_info, plan)
    assert results["activity_details_match"].passed is True
    assert results["activity_on_its_date"].passed is True


# Phase 5 – B1 Step 2: score is the fraction of items that pass
def test_score_is_partial_credit(vacation_info, sample_plan):
    plan = sample_plan.model_copy(deep=True)
    _price(plan)  # 1 of 6 activities altered
    assert grade(vacation_info, plan)["activity_details_match"].score == pytest.approx(5 / 6, abs=0.001)


# Phase 5 – B1 Step 2: the G5 lesson – reasons mentioning an uncoverable interest are surfaced (info)
def test_uncoverable_interest_mentions_are_info_only(vacation_info, sample_plan):
    plan = sample_plan.model_copy(deep=True)
    rec = plan.itinerary_days[0].activity_recommendations[0]
    rec.reasons_for_recommendation.append("Aligns closely with the theatre interest")
    result = grade(vacation_info, plan)["uncoverable_interest_mentions"]

    assert result.passed is None and result.severity == "info"
    assert result.details["count"] == 1
    assert result.details["mentions"][0]["id"] == "event-2025-06-10-0"
    assert failing(grade(vacation_info, plan)) == set()  # never fails the run


# Phase 5 – B1 Step 2: production mode – no golden answer key, graders still work
def test_graders_run_in_prod_mode(vacation_info, sample_plan):
    inp = GradingInput.for_request(vacation_info, sample_plan, "raw")
    assert inp.source == "prod" and inp.expectations.max_cost == vacation_info.budget
    results = {r.grader: r for r in run_graders(inp)}
    assert failing(results) == set()
    assert results["uncoverable_interest_mentions"].details["count"] == 0  # no golden uncoverables in prod


# Phase 5 – B1 Step 2: no plan → every grounding grader is "not applicable", not a failure
def test_unparsed_reply_makes_grounding_not_applicable(vacation_info):
    results = grade(vacation_info, None)
    assert results["parse"].passed is False
    assert all(results[g].passed is None for g in HALLUCINATION_GRADERS)


def test_every_grader_has_a_slice_and_unique_name(vacation_info, sample_plan):
    results = run_graders(GradingInput.for_request(vacation_info, sample_plan, "raw"))
    assert all(r.slice in ("B0", "B1", "B2") for r in results)
    assert len({r.grader for r in results}) == len(GRADERS)
