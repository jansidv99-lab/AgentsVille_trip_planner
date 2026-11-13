# Phase 7 – C1 Step 1: Layer A tests for structured log events (no network; captures stdout).

import io
import json

import pytest

from models import PromptTrace
from observability.events import MAX_COMMENT_CHARS, feedback_event, llm_error_event, llm_run_event
from quality.graders import GradingInput, run_graders


def trace_for(plan, raw="ANALYSIS ... FINAL OUTPUT ...", **kw):
    return PromptTrace(model="gpt-4.1-mini", prompt_version="v1", system_prompt="s", user_prompt="u",
                       raw_response=raw, travel_plan=plan, latency_ms=1234.5, prompt_tokens=4000,
                       completion_tokens=2000, cost_usd=0.0048, **kw)


def emitted(fn, *args, **kwargs) -> tuple[dict, dict]:
    buf = io.StringIO()
    record = fn(*args, stream=buf, **kwargs)
    line = buf.getvalue().strip()
    assert "\n" not in line, "exactly one JSON line per event"
    return record, json.loads(line)


def test_llm_run_event_for_a_clean_plan(vacation_info, sample_plan):
    results = run_graders(GradingInput.for_request(vacation_info, sample_plan, "raw"))
    record, line = emitted(llm_run_event, trace_for(sample_plan), vacation_info, results)

    assert line == json.loads(json.dumps(record, default=str))
    assert line["app"] == "agentsville" and line["event"] == "llm_run" and line["source"] == "prod"
    assert line["severity"] == "INFO" and line["task_success"] is True and line["hallucination"] is False
    assert line["hard_failed"] == [] and line["raw_response"] is None  # reply only when a hard grader fails
    assert {g["grader"] for g in line["graders"]} >= {"parse", "weather_safety", "interest_coverage"}
    assert line["request"]["travelers"][0]["name"] == "Yuri"  # names kept (decision)
    assert line["features"] == {"travelers": 2, "interests": sorted(["tennis", "cooking", "comedy", "technology",
                                                                     "reading", "music", "theatre", "art"]),
                                "ages": [30, 25], "budget": 130, "trip_days": 3,
                                "arrival": "2025-06-10", "departure": "2025-06-12"}
    assert line["prompt_version"] == "v1" and line["cost_usd"] == 0.0048


def test_llm_run_event_with_a_hard_failure_includes_reply_and_details(vacation_info, sample_plan):
    plan = sample_plan.model_copy(deep=True)
    plan.total_cost = 107  # cost_arithmetic fails
    results = run_graders(GradingInput.for_request(vacation_info, plan, "THE RAW REPLY"))
    _, line = emitted(llm_run_event, trace_for(plan, raw="THE RAW REPLY"), vacation_info, results)

    assert line["severity"] == "WARNING" and line["task_success"] is False
    assert line["hard_failed"] == ["cost_arithmetic"]
    assert line["raw_response"] == "THE RAW REPLY"
    failing = next(g for g in line["graders"] if g["grader"] == "cost_arithmetic")
    assert failing["details"]["diff"] == -1
    assert "details" not in next(g for g in line["graders"] if g["grader"] == "parse")  # passing → compact


def test_feedback_event_caps_comment_and_validates_rating():
    _, line = emitted(feedback_event, "trace-123", "down", "x" * 900, "v1")
    assert line["event"] == "feedback" and line["rating"] == "down" and line["trace_id"] == "trace-123"
    assert len(line["comment"]) == MAX_COMMENT_CHARS
    with pytest.raises(ValueError):
        feedback_event("t", "meh", "", "v1", stream=io.StringIO())


def test_llm_error_event(vacation_info):
    _, line = emitted(llm_error_event, vacation_info, "gpt-4.1-mini", "APIConnectionError: down")
    assert line["event"] == "llm_error" and line["severity"] == "ERROR" and line["features"]["budget"] == 130
