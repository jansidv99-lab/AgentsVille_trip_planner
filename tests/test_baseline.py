# Phase 5 – B4 Step 2: Layer A tests for consistency (pass^k / pass@k), baselines and regression comparison.

import datetime

from evals.harness.baseline import HARD_GRADERS, compare, consistency
from quality.schema import EvalRecord, GraderResult


def rec(case_id: str, repeat: int, fail: tuple[str, ...] = ()) -> EvalRecord:
    """A record where every hard grader passes except those in `fail`."""
    results = [GraderResult(grader=g, severity="hard", passed=g not in fail) for g in HARD_GRADERS]
    return EvalRecord(trace_id=f"{case_id}{repeat}", timestamp=datetime.datetime(2026, 11, 13), source="offline",
                      case_id=case_id, repeat=repeat, prompt_version="v1", model="gpt-4.1-mini",
                      parsed="parse" not in fail, grader_results=results)


# Phase 5 – B4 Step 2: pass^k = reliably works; pass@k = can work; the gap = flaky
def test_consistency_pass_k_vs_pass_at_k():
    records = [rec("A", 0), rec("A", 1), rec("A", 2),                                 # always succeeds
               rec("B", 0), rec("B", 1, ("weather_safety",)), rec("B", 2),            # flaky
               rec("C", 0, ("parse",)), rec("C", 1, ("parse",)), rec("C", 2, ("parse",))]  # never
    c = consistency(records)
    assert c["k"] == 3
    assert c["pass_k_rate"] == round(1 / 3, 3)
    assert c["pass_at_k_rate"] == round(2 / 3, 3)
    assert c["flaky_cases"] == ["B"]


def snap(task, halluc, pass_rates, per_case):
    return {"metrics": {"task_success_rate": task, "hallucination_rate": halluc, "pass_rates": pass_rates},
            "per_case": per_case}


BASE = snap(0.58, 0.0, {"parse": 0.96, "weather_safety": 0.65, "cost_arithmetic": 0.91},
            {"G1": {"hard_failures": ["parse"]}, "G2": {"hard_failures": ["weather_safety"]}, "G3": {"hard_failures": []}})


def test_improvement_without_regression_passes():
    cur = snap(0.9, 0.0, {"parse": 1.0, "weather_safety": 1.0, "cost_arithmetic": 0.91},
               {"G1": {"hard_failures": []}, "G2": {"hard_failures": []}, "G3": {"hard_failures": []}})
    c = compare(cur, BASE)
    assert c["passed"] is True
    assert "task_success_rate" in c["improvements"] and "pass_rate.weather_safety" in c["improvements"]
    assert c["deltas"]["task_success_rate"]["delta"] == 0.32


# Phase 5 – B4 Step 2: a seeded regression – a case that used to pass a hard grader now fails it
def test_new_case_failure_is_a_regression_even_if_averages_improve():
    cur = snap(0.7, 0.0, {"parse": 1.0, "weather_safety": 1.0, "cost_arithmetic": 0.95},
               {"G1": {"hard_failures": []}, "G2": {"hard_failures": []}, "G3": {"hard_failures": ["budget_within_limit"]}})
    c = compare(cur, BASE)
    assert c["passed"] is False
    assert c["new_case_failures"] == {"G3": ["budget_within_limit"]}


def test_pre_existing_failures_are_not_new():
    cur = snap(0.58, 0.0, BASE["metrics"]["pass_rates"], BASE["per_case"])
    assert compare(cur, BASE)["passed"] is True


def test_any_hallucination_is_a_regression():
    cur = snap(0.9, 0.04, {"parse": 1.0, "weather_safety": 1.0, "cost_arithmetic": 1.0}, BASE["per_case"])
    c = compare(cur, BASE)
    assert c["passed"] is False and "hallucination_rate" in c["regressions"]


def test_hard_pass_rate_drop_beyond_tolerance_is_a_regression():
    cur = snap(0.58, 0.0, {"parse": 0.80, "weather_safety": 0.65, "cost_arithmetic": 0.91}, BASE["per_case"])
    assert "pass_rate.parse" in compare(cur, BASE)["regressions"]
    assert "pass_rate.parse" not in compare(cur, BASE, tolerance=0.2)["regressions"]
