# Phase 5 – B0 Step 1: Layer A tests for the golden dataset. They double as a ground-truth AUDIT:
# every human-approved expectation must be consistent with the mock activity and weather data.

import datetime

import pytest

from evals.harness.dataset import DATASETS_DIR, content_sha256, dataset_path, load_dataset, load_manifest
from project_lib import ACTIVITY_CALENDAR

DATASET = "itinerary_golden"
MOCK_START, MOCK_END = datetime.date(2025, 6, 10), datetime.date(2025, 6, 15)
ACTIVITIES = {a["activity_id"]: a for a in ACTIVITY_CALENDAR}

MANIFEST = load_manifest(DATASET)
_, CASES = load_dataset(DATASET)


def activity_date(activity_id: str) -> datetime.date:
    return datetime.date.fromisoformat(ACTIVITIES[activity_id]["start_time"][:10])


def trip_days(case) -> list[datetime.date]:
    info = case.vacation_info
    n = (info.date_of_departure - info.date_of_arrival).days
    return [info.date_of_arrival + datetime.timedelta(days=i) for i in range(n + 1)]


# Phase 5 – B0 Step 1: the file matches its manifest (any edit forces a version bump)
def test_manifest_matches_file():
    path = dataset_path(DATASET, MANIFEST.version)
    assert content_sha256(path) == MANIFEST.sha256
    assert MANIFEST.case_count == len(CASES)
    assert MANIFEST.approved_count == sum(c.review.status == "approved" for c in CASES)
    assert MANIFEST.smoke_cases == [c.case_id for c in CASES if c.smoke]
    assert MANIFEST.changelog[-1].version == MANIFEST.version


def test_hash_ignores_line_endings(tmp_path):
    lf, crlf = tmp_path / "lf.jsonl", tmp_path / "crlf.jsonl"
    lf.write_bytes(b'{"a": 1}\n{"b": 2}\n')
    crlf.write_bytes(b'{"a": 1}\r\n{"b": 2}\r\n')
    assert content_sha256(lf) == content_sha256(crlf)


def test_case_ids_are_unique():
    ids = [c.case_id for c in CASES]
    assert len(ids) == len(set(ids))


# Phase 5 – B0 Step 1: per-case ground-truth audit
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.case_id)
def test_case_is_consistent_with_mock_data(case):
    info, exp = case.vacation_info, case.expectations
    days = trip_days(case)

    # Dates are inside the range the mock APIs cover.
    assert MOCK_START <= days[0] and days[-1] <= MOCK_END

    # The budget ceiling is the traveler's budget.
    assert exp.max_cost == info.budget

    # A valid plan is feasible: the cheapest activities still fit the budget.
    cheapest = sum(
        sorted(a["price"] for a in ACTIVITY_CALENDAR if activity_date(a["activity_id"]) == d)[0]
        for d in days
    ) * exp.min_activities_per_day
    assert cheapest <= exp.max_cost, f"cheapest valid plan costs {cheapest} > budget {exp.max_cost}"

    # Allow-listed activities exist, fall on that date, and the date is part of the trip.
    for day, ids in (exp.allowed_activity_ids_by_date or {}).items():
        assert day in days, f"allow-list date {day} is outside the trip"
        assert ids, f"empty allow-list for {day}"
        for aid in ids:
            assert aid in ACTIVITIES, f"allow-listed {aid} doesn't exist"
            assert activity_date(aid) == day, f"allow-listed {aid} is not on {day}"

    # Must-include activities exist within the trip.
    for aid in exp.must_include_activity_ids:
        assert aid in ACTIVITIES, f"must-include {aid} doesn't exist"
        assert activity_date(aid) in days, f"must-include {aid} is outside the trip dates"

    # "Uncoverable" interests really aren't offered (safely) on the trip dates.
    allowed = exp.allowed_activity_ids_by_date or {}
    for interest in exp.uncoverable_interests:
        offering = [
            aid for aid, a in ACTIVITIES.items()
            if activity_date(aid) in days and interest.value in a["related_interests"]
            and (activity_date(aid) not in allowed or aid in allowed[activity_date(aid)])
        ]
        assert not offering, f"{interest} is coverable via {offering}"

    # Every uncoverable interest belongs to some traveler (otherwise it's a pointless expectation).
    all_interests = {i for t in info.travelers for i in t.interests}
    assert set(exp.uncoverable_interests) <= all_interests


def test_smoke_subset_is_small():
    assert 1 <= len(MANIFEST.smoke_cases) <= 5  # keeps the PR smoke eval within ~5 LLM calls


def test_datasets_dir_layout():
    assert (DATASETS_DIR / DATASET / "manifest.json").exists()
