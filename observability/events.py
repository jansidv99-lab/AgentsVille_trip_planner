# Phase 7 – C1 Step 1: structured log events. One JSON line per event on stdout: Cloud Run's logging agent
# parses it into jsonPayload (and recognizes "severity"/"message"); a log sink copies it into BigQuery.
#
# Decisions (B5 §8): traveler names ARE logged (private GCP); the raw LLM reply is logged only when a hard
# grader failed; feedback comments are capped at 500 characters.

import datetime
import json
import sys
from typing import Optional

from models import PromptTrace, VacationInfo
from quality.graders import HALLUCINATION_GRADERS, task_succeeded
from quality.schema import GraderResult

APP = "agentsville"
EVENT_SCHEMA_VERSION = "1"
MAX_COMMENT_CHARS = 500


# Phase 7 – C1 Step 1: write one event line (and return it, for tests and callers)
def emit(event: str, payload: dict, message: str, severity: str = "INFO", stream=None) -> dict:
    record = {
        "app": APP, "event": event, "schema_version": EVENT_SCHEMA_VERSION, "severity": severity,
        "message": message, "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), **payload,
    }
    # ASCII-safe JSON: a Windows console (cp1252) would crash on "–", "°" or emoji; Cloud Logging decodes XXXX.
    print(json.dumps(record, default=str, ensure_ascii=True), file=stream or sys.stdout, flush=True)
    return record


# Phase 7 – C1 Step 1: request features used for drift analysis (B5 input profile)
def request_features(vi: VacationInfo) -> dict:
    return {
        "travelers": len(vi.travelers),
        "interests": sorted(str(i) for t in vi.travelers for i in t.interests),
        "ages": [t.age for t in vi.travelers],
        "budget": vi.budget,
        "trip_days": (vi.date_of_departure - vi.date_of_arrival).days + 1,
        "arrival": vi.date_of_arrival.isoformat(),
        "departure": vi.date_of_departure.isoformat(),
    }


# Phase 7 – C1 Step 1: one generated itinerary, graded online (same EvalRecord idea, source = prod)
def llm_run_event(trace: PromptTrace, vacation_info: VacationInfo, results: list[GraderResult],
                  error: Optional[str] = None, stream=None) -> dict:
    hard_failed = [r.grader for r in results if r.severity == "hard" and r.passed is False]
    hallucination = any(r.grader in HALLUCINATION_GRADERS and r.passed is False for r in results)
    success = task_succeeded(results)
    payload = {
        "source": "prod",
        "trace_id": trace.trace_id,
        "prompt_version": trace.prompt_version,
        "model": trace.model,
        "latency_ms": trace.latency_ms,
        "prompt_tokens": trace.prompt_tokens,
        "completion_tokens": trace.completion_tokens,
        "cost_usd": trace.cost_usd,
        "parsed": trace.travel_plan is not None,
        "error": error,
        "task_success": success,
        "hallucination": hallucination,
        "hard_failed": hard_failed,
        "graders": [{"grader": r.grader, "slice": r.slice, "severity": r.severity, "passed": r.passed,
                     "score": r.score, **({"details": r.details} if r.passed is False else {})} for r in results],
        "request": vacation_info.model_dump(mode="json"),  # includes traveler names (decision)
        "features": request_features(vacation_info),
        "raw_response": trace.raw_response if hard_failed else None,  # only for runs that need review
    }
    msg = f"llm_run trace={trace.trace_id[:8]} task_success={success} hard_failed={hard_failed or 'none'}"
    return emit("llm_run", payload, msg, severity="WARNING" if hard_failed else "INFO", stream=stream)


# Phase 7 – C1 Step 1: an LLM call that produced no trace at all (auth/network/rate-limit errors)
def llm_error_event(vacation_info: VacationInfo, model: str, error: str, stream=None) -> dict:
    return emit("llm_error", {"source": "prod", "model": model, "error": error,
                              "features": request_features(vacation_info)},
                f"llm_error {error[:120]}", severity="ERROR", stream=stream)


# Phase 7 – C1 Step 1 / B5 Step 3: user feedback, joined to its run by trace_id
def feedback_event(trace_id: str, rating: str, comment: str, prompt_version: Optional[str], stream=None) -> dict:
    if rating not in ("up", "down"):
        raise ValueError(f"rating must be 'up' or 'down', not {rating!r}")
    comment = (comment or "").strip()[:MAX_COMMENT_CHARS]
    return emit("feedback", {"source": "prod", "trace_id": trace_id, "rating": rating, "comment": comment,
                             "prompt_version": prompt_version},
                f"feedback trace={trace_id[:8]} rating={rating}", stream=stream)
