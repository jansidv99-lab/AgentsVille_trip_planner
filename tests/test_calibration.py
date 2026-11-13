# Phase 5 – B3 Step 5: Layer A tests for calibration (label parsing + agreement math) – synthetic data, no LLM.

import datetime

from evals.harness.calibration import SAMPLE, TRUST_THRESHOLD, agreement, parse_labels
from quality.schema import EvalRecord, GraderResult


def record(cid, rep, j_rel, j_honest, j_faithful, k_honest):
    def res(name, passed, rating=None):
        return GraderResult(grader=name, severity="soft", passed=passed,
                            details={"rating": rating} if rating is not None else {})
    return EvalRecord(trace_id=f"{cid}-{rep}", timestamp=datetime.datetime(2026, 11, 13), source="offline",
                      case_id=cid, repeat=rep, prompt_version="v1", model="gpt-4.1-mini", parsed=True,
                      grader_results=[res("judge_relevancy", j_rel >= 4, j_rel),
                                      res("judge_reasons_honest", j_honest),
                                      res("judge_reasoning_faithful", j_faithful),
                                      res("reason_grounding", k_honest)])


def test_parse_labels_accepts_compact_chat_formats():
    text = "1: 4 y y\n2) 3 N y\n  3 - 5 y n\nnot a label\n10: 2 n n"
    assert parse_labels(text) == {1: (4, True, True), 2: (3, False, True), 3: (5, True, False), 10: (2, False, False)}


def test_agreement_math_and_trust_rule():
    # Judge always says relevancy 5, honest, faithful (lenient). Keyword flags items 1 and 2.
    records = {(c, r): record(c, r, 5, True, True, k_honest=(n > 2)) for n, (c, r) in enumerate(SAMPLE, start=1)}
    # Human: items 1–2 dishonest with relevancy 3; the rest honest with relevancy 5; all faithful.
    labels = {n: ((3, False, True) if n <= 2 else (5, True, True)) for n in range(1, 11)}
    report = agreement(labels, records)

    assert report["n"] == 10
    a = report["agreement"]
    assert a["judge_relevancy_exact"] == 0.8          # 8 of 10 exact
    assert a["judge_relevancy_within_1"] == 0.8       # 5 vs 3 is off by 2
    assert a["judge_reasons_honest"] == 0.8           # judge missed the 2 dishonest items
    assert a["keyword_heuristic_honest"] == 1.0       # keyword caught exactly those 2
    assert a["judge_reasoning_faithful"] == 1.0
    assert report["honesty_errors"]["judge_missed_dishonest"] == ["1 (G5#0)", "2 (G5#2)"]
    assert report["honesty_errors"]["keyword_false_alarm"] == []
    assert all(report["trusted_as_gate"][k] == (v >= TRUST_THRESHOLD) for k, v in a.items())


def test_partial_labels_only_count_labeled_items():
    records = {(c, r): record(c, r, 4, True, True, True) for c, r in SAMPLE}
    report = agreement({1: (4, True, True)}, records)
    assert report["n"] == 1 and report["agreement"]["judge_relevancy_exact"] == 1.0
