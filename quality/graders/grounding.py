# Phase 5 – B1 Step 2: hallucination & grounding graders – "Is everything in the plan real?"
# Every fact in the structured TravelPlan must trace back to the mock APIs (ACTIVITY_CALENDAR,
# WEATHER_FORECAST) or to the traveler's request. All graders are deterministic and online-safe.
#
# Scope note: these catch FABRICATED or ALTERED facts. Whether the free-text reasons honestly
# describe relevance (over-claiming, e.g. "close to your theatre interest") is B3's job; here it is
# only surfaced as an `info` signal (uncoverable_interest_mentions).

import datetime

from models import Activity, ItineraryDay
from project_lib import ACTIVITY_CALENDAR, WEATHER_FORECAST
from quality.graders.base import GradingInput, grader, not_applicable
from quality.schema import GraderResult

CALENDAR: dict[str, dict] = {a["activity_id"]: a for a in ACTIVITY_CALENDAR}
FORECAST: dict[tuple[str, str], dict] = {(w["city"], w["date"]): w for w in WEATHER_FORECAST}
CALENDAR_TIME_FORMAT = "%Y-%m-%d %H:%M"
DETAIL_FIELDS = ("name", "start_time", "end_time", "location", "price", "related_interests")


# Phase 5 – B1 Step 2: every (day, activity) pair in the plan
def plan_activities(inp: GradingInput) -> list[tuple[ItineraryDay, Activity]]:
    return [(day, rec.activity) for day in inp.plan.itinerary_days for rec in day.activity_recommendations]


def _ratio(ok: int, total: int) -> float:
    return round(ok / total, 3) if total else 1.0


# Phase 5 – B1 Step 2: normalize a calendar value and a plan value so they compare exactly
def _expected_value(field: str, source: dict):
    if field in ("start_time", "end_time"):
        return datetime.datetime.strptime(source[field], CALENDAR_TIME_FORMAT)
    if field == "related_interests":
        return sorted(source[field])
    return source[field]


def _actual_value(field: str, activity: Activity):
    value = getattr(activity, field)
    if field == "related_interests":
        return sorted(str(i) for i in value)
    return value


# Phase 5 – B1 Step 2: invented activities
@grader("B1")
def grade_activity_exists(inp: GradingInput) -> GraderResult:
    name = "activity_exists"
    if inp.plan is None:
        return not_applicable(name, "hard", "no plan")
    items = plan_activities(inp)
    unknown = [a.activity_id for _, a in items if a.activity_id not in CALENDAR]
    return GraderResult(grader=name, severity="hard", passed=not unknown,
                        score=_ratio(len(items) - len(unknown), len(items)),
                        details={"unknown_ids": unknown} if unknown else {})


# Phase 5 – B1 Step 2: real activity, but altered facts (price, time, place, interests, name)
@grader("B1")
def grade_activity_details_match(inp: GradingInput) -> GraderResult:
    name = "activity_details_match"
    if inp.plan is None:
        return not_applicable(name, "hard", "no plan")
    known = [a for _, a in plan_activities(inp) if a.activity_id in CALENDAR]  # unknown ids: activity_exists
    mismatches: dict[str, dict] = {}
    for a in known:
        diffs = {}
        for field in DETAIL_FIELDS:
            expected, got = _expected_value(field, CALENDAR[a.activity_id]), _actual_value(field, a)
            if expected != got:
                diffs[field] = {"expected": str(expected), "got": str(got)}
        if diffs:
            mismatches[a.activity_id] = diffs
    return GraderResult(grader=name, severity="hard", passed=not mismatches,
                        score=_ratio(len(known) - len(mismatches), len(known)),
                        details={"mismatches": mismatches} if mismatches else {})


# Phase 5 – B1 Step 2: a real activity placed on the wrong day
@grader("B1")
def grade_activity_on_its_date(inp: GradingInput) -> GraderResult:
    name = "activity_on_its_date"
    if inp.plan is None:
        return not_applicable(name, "hard", "no plan")
    known = [(d, a) for d, a in plan_activities(inp) if a.activity_id in CALENDAR]
    misplaced = []
    for day, a in known:
        actual = CALENDAR[a.activity_id]["start_time"][:10]
        if actual != day.date.isoformat():
            misplaced.append({"id": a.activity_id, "listed": day.date.isoformat(), "actual": actual})
    return GraderResult(grader=name, severity="hard", passed=not misplaced,
                        score=_ratio(len(known) - len(misplaced), len(known)),
                        details={"misplaced": misplaced} if misplaced else {})


# Phase 5 – B1 Step 2: invented or altered weather
@grader("B1")
def grade_weather_matches_forecast(inp: GradingInput) -> GraderResult:
    name = "weather_matches_forecast"
    if inp.plan is None:
        return not_applicable(name, "hard", "no plan")
    days = inp.plan.itinerary_days
    mismatches: dict[str, dict] = {}
    for day in days:
        key = day.date.isoformat()
        fc = FORECAST.get((inp.vacation_info.destination, key))
        if fc is None:
            mismatches[key] = {"forecast": {"expected": "a forecast for this date", "got": "none exists"}}
            continue
        w, diffs = day.weather, {}
        if w.condition.strip().lower() != fc["condition"].lower():
            diffs["condition"] = {"expected": fc["condition"], "got": w.condition}
        if abs(w.temperature - fc["temperature"]) > 0.01:
            diffs["temperature"] = {"expected": fc["temperature"], "got": w.temperature}
        if w.temperature_unit.strip().lower() != fc["temperature_unit"].lower():
            diffs["temperature_unit"] = {"expected": fc["temperature_unit"], "got": w.temperature_unit}
        if diffs:
            mismatches[key] = diffs
    return GraderResult(grader=name, severity="hard", passed=not mismatches,
                        score=_ratio(len(days) - len(mismatches), len(days)),
                        details={"mismatches": mismatches} if mismatches else {})


# Phase 5 – B1 Step 2: the plan describes the trip that was actually requested
@grader("B1")
def grade_plan_matches_request(inp: GradingInput) -> GraderResult:
    name = "plan_matches_request"
    if inp.plan is None:
        return not_applicable(name, "hard", "no plan")
    plan, req = inp.plan, inp.vacation_info
    dates = [d.date for d in plan.itinerary_days]
    checks = {
        "city": plan.city == req.destination,
        "start_date": plan.start_date == req.date_of_arrival,
        "end_date": plan.end_date == req.date_of_departure,
        "days_within_trip": all(req.date_of_arrival <= d <= req.date_of_departure for d in dates),
        "no_duplicate_days": len(dates) == len(set(dates)),
    }
    problems = [k for k, ok in checks.items() if not ok]
    details = {}
    if problems:
        details["problems"] = problems
        outside = [d.isoformat() for d in dates if not req.date_of_arrival <= d <= req.date_of_departure]
        if outside:
            details["days_outside_trip"] = outside
        if not checks["city"]:
            details["city"] = {"expected": req.destination, "got": plan.city}
    return GraderResult(grader=name, severity="hard", passed=not problems,
                        score=_ratio(len(checks) - len(problems), len(checks)), details=details)


# Phase 5 – B1 Step 2: descriptions copied verbatim (the prompt asks for exact copies) – soft
@grader("B1")
def grade_description_verbatim(inp: GradingInput) -> GraderResult:
    name = "description_verbatim"
    if inp.plan is None:
        return not_applicable(name, "soft", "no plan")
    known = [a for _, a in plan_activities(inp) if a.activity_id in CALENDAR]
    changed = [a.activity_id for a in known
               if a.description.strip() != CALENDAR[a.activity_id]["description"].strip()]
    return GraderResult(grader=name, severity="soft", passed=not changed,
                        score=_ratio(len(known) - len(changed), len(known)),
                        details={"paraphrased_ids": changed} if changed else {})


# Phase 5 – B1 Step 2: reasons that mention an interest nothing offers – info only, judged in B3
@grader("B1")
def grade_uncoverable_interest_mentions(inp: GradingInput) -> GraderResult:
    name = "uncoverable_interest_mentions"
    if inp.plan is None:
        return not_applicable(name, "info", "no plan")
    interests = [str(i) for i in inp.expectations.uncoverable_interests]
    mentions = [
        {"id": rec.activity.activity_id, "interest": interest, "reason": reason}
        for day in inp.plan.itinerary_days
        for rec in day.activity_recommendations
        for reason in rec.reasons_for_recommendation
        for interest in interests
        if interest in reason.lower()
    ]
    return GraderResult(grader=name, severity="info", passed=None, score=None,
                        details={"mentions": mentions, "count": len(mentions)})


# The five hard graders that define the hallucination rate.
HALLUCINATION_GRADERS = (
    "activity_exists",
    "activity_details_match",
    "activity_on_its_date",
    "weather_matches_forecast",
    "plan_matches_request",
)
