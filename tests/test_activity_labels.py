# Phase 5 – B2 Step 1: Layer A audits for the activity setting labels (ground truth for weather safety).
# Cross-checks the labels against the mock calendar AND against the golden dataset's allow-lists,
# so the two human-approved ground truths can never disagree.

import json

import pytest

from evals.harness.dataset import load_dataset
from project_lib import ACTIVITY_CALENDAR, WEATHER_FORECAST
from quality.labels import BAD_WEATHER, LABELS_PATH, SAFE_IN_BAD_WEATHER, UnapprovedLabelsError, load_labels

LABELS = load_labels()
CALENDAR = {a["activity_id"]: a for a in ACTIVITY_CALENDAR}


def test_every_activity_has_exactly_one_label():
    assert set(LABELS.labels) == set(CALENDAR)


def test_labels_are_approved():
    assert LABELS.review.status == "approved" and LABELS.review.reviewer


# Phase 5 – B2 Step 1: each label is backed by a verbatim quote from its own description
@pytest.mark.parametrize("activity_id", sorted(CALENDAR))
def test_evidence_is_quoted_from_the_description(activity_id):
    label = LABELS.labels[activity_id]
    assert label.evidence in CALENDAR[activity_id]["description"]
    cue = {"indoor": "indoor", "outdoor": "outdoor", "flex": "rain"}[label.setting]
    assert cue in label.evidence.lower() or (label.setting == "outdoor" and "open sky" in label.evidence)


# Phase 5 – B2 Step 1: dataset allow-lists for bad-weather days == indoor + flex activities that day
@pytest.mark.parametrize("case", load_dataset("itinerary_golden")[1], ids=lambda c: c.case_id)
def test_dataset_allow_lists_match_labels(case):
    bad_days = {w["date"] for w in WEATHER_FORECAST if w["condition"] in BAD_WEATHER}
    for day, allowed in (case.expectations.allowed_activity_ids_by_date or {}).items():
        assert day.isoformat() in bad_days, f"{case.case_id}: allow-list on a good-weather day {day}"
        safe = {aid for aid, a in CALENDAR.items()
                if a["start_time"].startswith(day.isoformat())
                and LABELS.labels[aid].setting in SAFE_IN_BAD_WEATHER}
        assert set(allowed) == safe, f"{case.case_id} {day}: allow-list {sorted(allowed)} != safe {sorted(safe)}"


# Phase 5 – B2 Step 1: every bad-weather day still has at least one safe option (plans are feasible)
def test_every_bad_weather_day_has_a_safe_option():
    for w in WEATHER_FORECAST:
        if w["condition"] in BAD_WEATHER:
            safe = [aid for aid, a in CALENDAR.items()
                    if a["start_time"].startswith(w["date"]) and LABELS.labels[aid].setting in SAFE_IN_BAD_WEATHER]
            assert safe, f"no indoor/flex activity on {w['date']}"


def test_draft_labels_are_refused(tmp_path):
    data = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    data["review"]["status"] = "draft"
    draft = tmp_path / "labels.json"
    draft.write_text(json.dumps(data), encoding="utf-8")
    load_labels.cache_clear()
    try:
        with pytest.raises(UnapprovedLabelsError):
            load_labels(draft)
    finally:
        load_labels.cache_clear()
