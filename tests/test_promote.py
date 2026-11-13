# Phase 5 – B5 Step 6: Layer A tests for production → golden-dataset promotion (injected rows, no BigQuery).

import datetime
import json
import shutil

import pytest

import planner
from evals.harness.dataset import DATASETS_DIR, load_dataset
from evals.harness.promote import candidates_path, promote_to_dataset, rows_to_candidates, write_candidates


def row(trace_id, hard_failed=(), rating=None, comment="", **request_overrides):
    request = {**json.loads(json.dumps(planner.VACATION_INFO_DICT)), **request_overrides}
    return {"trace_id": trace_id, "ts": "2026-11-13 14:00:00", "prompt_version": "v1",
            "request_json": json.dumps(request), "hard_failed": list(hard_failed), "rating": rating,
            "comment": comment, "task_success": not hard_failed}


def test_flagged_rows_become_draft_candidates_with_synthetic_names():
    cands = rows_to_candidates([row("aaaa1111", ["weather_safety"]), row("bbbb2222", rating="down",
                                comment="day 2 too empty", budget=90)], existing_ids={"G1", "G2"})
    assert [c.case_id for c in cands] == ["P1", "P2"]
    assert all(c.review.status == "draft" for c in cands)
    assert [t.name for t in cands[0].vacation_info.travelers] == ["Traveler A", "Traveler B"]  # never real names
    assert "constraints" in cands[0].tags and "weather" in cands[0].tags
    assert cands[1].tags == ["relevancy"] and cands[1].expectations.max_cost == 90
    assert "trace aaaa1111" in cands[0].expectations.notes and "weather_safety" in cands[0].expectations.notes
    assert 'comment: "day 2 too empty"' in cands[1].expectations.notes


def test_duplicate_requests_are_deduplicated_and_ids_continue():
    cands = rows_to_candidates([row("a1", ["parse"]), row("a2", ["parse"]), row("a3", ["parse"], budget=99)],
                               existing_ids={"P1", "P2"})
    assert [c.case_id for c in cands] == ["P3", "P4"]


def test_pipeline_test_feedback_is_marked_for_rejection():
    (cand,) = rows_to_candidates([row("t1", rating="down", comment="pipeline test")], existing_ids=set())
    assert "[PIPELINE TEST – reject]" in cand.expectations.notes


# Phase 5 – B5 Step 6: approval → new MINOR version; existing cases untouched; manifest/changelog consistent
def test_promote_creates_minor_version_with_changelog(tmp_path):
    shutil.copytree(DATASETS_DIR / "itinerary_golden", tmp_path / "itinerary_golden")
    base_manifest, base_cases = load_dataset("itinerary_golden", tmp_path)
    cands = rows_to_candidates([row("c1", ["cost_arithmetic"]), row("c2", rating="down", budget=70)],
                               {c.case_id for c in base_cases})
    write_candidates(cands, candidates_path(datasets_dir=tmp_path))

    new_path = promote_to_dataset(["P1"], "reviewer-x", datasets_dir=tmp_path, today=datetime.date(2026, 11, 20))

    manifest, cases = load_dataset("itinerary_golden", tmp_path)  # hash + counts verified by the loader
    assert new_path.name == "v1.1.0.jsonl" and manifest.version == "1.1.0"
    assert [c.case_id for c in cases] == [c.case_id for c in base_cases] + ["P1"]
    assert cases[:len(base_cases)] == base_cases  # existing cases unchanged
    assert cases[-1].review.status == "approved" and cases[-1].review.reviewer == "reviewer-x"
    assert manifest.changelog[-1].version == "1.1.0" and "P1" in manifest.changelog[-1].changes
    assert (tmp_path / "itinerary_golden" / f"v{base_manifest.version}.jsonl").exists()  # old version kept


def test_promote_rejects_unknown_ids(tmp_path):
    shutil.copytree(DATASETS_DIR / "itinerary_golden", tmp_path / "itinerary_golden")
    write_candidates([], candidates_path(datasets_dir=tmp_path))
    with pytest.raises(KeyError):
        promote_to_dataset(["P9"], "r", datasets_dir=tmp_path)
