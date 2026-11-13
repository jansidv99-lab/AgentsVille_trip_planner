# Phase 4 – Step 2: Layer A tests for the Pydantic models in models.py.
# These check the validation rules the Streamlit form relies on, without any LLM calls.

import copy

import pytest
from pydantic import ValidationError

import planner
from models import TravelPlan, VacationInfo


# Phase 4 – Step 2: a fresh, editable copy of the sample trip for each test
def trip(**changes) -> dict:
    data = copy.deepcopy(planner.VACATION_INFO_DICT)
    data.update(changes)
    return data


def first_traveler(**changes) -> dict:
    data = trip()
    data["travelers"][0].update(changes)
    return data


# Phase 4 – Step 2: the happy path
def test_sample_trip_is_valid():
    info = VacationInfo.model_validate(trip())
    assert info.destination == "AgentsVille"
    assert [t.name for t in info.travelers] == ["Yuri", "Hiro"]


def test_same_day_trip_is_valid():
    info = VacationInfo.model_validate(trip(date_of_departure="2025-06-10"))
    assert info.date_of_arrival == info.date_of_departure


# Phase 4 – Step 2: each invalid input must fail at the expected field (Pydantic's error "loc")
@pytest.mark.parametrize(
    ("data", "expected_loc"),
    [
        pytest.param(first_traveler(name=""), ("travelers", 0, "name"), id="empty-name"),
        pytest.param(first_traveler(interests=[]), ("travelers", 0, "interests"), id="no-interests"),
        pytest.param(
            first_traveler(interests=["skydiving"]), ("travelers", 0, "interests", 0), id="unknown-interest"
        ),
        pytest.param(first_traveler(age=121), ("travelers", 0, "age"), id="age-too-high"),
        pytest.param(trip(budget=0), ("budget",), id="zero-budget"),
        pytest.param(trip(travelers=[]), ("travelers",), id="no-travelers"),
    ],
)
def test_invalid_field_is_rejected(data, expected_loc):
    with pytest.raises(ValidationError) as exc_info:
        VacationInfo.model_validate(data)
    locs = [err["loc"] for err in exc_info.value.errors()]
    assert expected_loc in locs


# Phase 4 – Step 2: the cross-field check from the model_validator
def test_departure_before_arrival_is_rejected():
    with pytest.raises(ValidationError, match="date_of_departure must be on or after date_of_arrival"):
        VacationInfo.model_validate(trip(date_of_arrival="2025-06-12", date_of_departure="2025-06-10"))


# Phase 4 – Step 2: guard the test fixture itself, so it can't go stale when models change
def test_sample_plan_json_matches_travel_plan(sample_plan_json):
    plan = TravelPlan.model_validate_json(sample_plan_json)
    assert plan.city == "AgentsVille"
    assert len(plan.itinerary_days) == 3
    assert plan.total_cost == sum(
        rec.activity.price for day in plan.itinerary_days for rec in day.activity_recommendations
    )
