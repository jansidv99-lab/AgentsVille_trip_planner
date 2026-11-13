# Phase 5 – B2 Step 3: constraint compliance graders – "Does the plan satisfy the hard constraints?"
# Budget, cost arithmetic (group pricing: total = sum of activity prices – decision Q1), day coverage,
# no time overlaps, weather safety (human-approved indoor/outdoor/flex labels), plus an info signal on
# plan shape. Deterministic and online-safe: in production, max_cost comes from the user's budget.

import datetime
from collections import defaultdict

from project_lib import ACTIVITY_CALENDAR
from quality.graders.base import GradingInput, grader, not_applicable
from quality.graders.grounding import CALENDAR, FORECAST, plan_activities
from quality.labels import BAD_WEATHER, setting_of
from quality.schema import GraderResult


def _trip_days(inp: GradingInput) -> list[datetime.date]:
    vi = inp.vacation_info
    return [vi.date_of_arrival + datetime.timedelta(days=i)
            for i in range((vi.date_of_departure - vi.date_of_arrival).days + 1)]


def _ratio(ok: int, total: int) -> float:
    return round(ok / total, 3) if total else 1.0


# Phase 5 – B2 Step 3: total cost within the budget
@grader("B2")
# Phase 5 – B4 fix: judge the REAL spend (sum of the chosen activities' prices, group pricing), not the stated
# total – v3's G1 stated 130 but actually spent 148, and the stated total hid the overspend.
def grade_budget_within_limit(inp: GradingInput) -> GraderResult:
    name = "budget_within_limit"
    if inp.plan is None:
        return not_applicable(name, "hard", "no plan")
    spend = sum(a.price for _, a in plan_activities(inp))
    limit = inp.expectations.max_cost
    ok = spend <= limit
    details = {"real_spend": spend, "stated_total": inp.plan.total_cost, "max_cost": limit}
    if not ok:
        details["over_by"] = spend - limit
    return GraderResult(grader=name, severity="hard", passed=ok,
                        score=1.0 if ok else round(min(1.0, limit / spend), 3), details=details)


# Phase 5 – B2 Step 3: stated total equals the sum of the activity prices (group pricing)
@grader("B2")
def grade_cost_arithmetic(inp: GradingInput) -> GraderResult:
    name = "cost_arithmetic"
    if inp.plan is None:
        return not_applicable(name, "hard", "no plan")
    stated = inp.plan.total_cost
    computed = sum(a.price for _, a in plan_activities(inp))
    ok = stated == computed
    details: dict = {"stated": stated, "computed": computed}
    if not ok:
        details["diff"] = stated - computed
        travelers = len(inp.vacation_info.travelers)
        if travelers > 1 and stated == computed * travelers:
            details["hint"] = f"stated = computed × {travelers} travelers (per-person pricing; spec is group pricing)"
    return GraderResult(grader=name, severity="hard", passed=ok, score=1.0 if ok else 0.0, details=details)


# Phase 5 – B2 Step 3: every trip day has at least min_activities_per_day activities
@grader("B2")
def grade_day_coverage(inp: GradingInput) -> GraderResult:
    name = "day_coverage"
    if inp.plan is None:
        return not_applicable(name, "hard", "no plan")
    counts: dict[datetime.date, int] = defaultdict(int)
    for day in inp.plan.itinerary_days:
        counts[day.date] += len(day.activity_recommendations)
    need = inp.expectations.min_activities_per_day
    days = _trip_days(inp)
    missing = [d.isoformat() for d in days if counts[d] == 0]
    underfilled = [d.isoformat() for d in days if 0 < counts[d] < need]
    bad = len(missing) + len(underfilled)
    details = {k: v for k, v in {"missing_days": missing, "underfilled_days": underfilled}.items() if v}
    return GraderResult(grader=name, severity="hard", passed=bad == 0,
                        score=_ratio(len(days) - bad, len(days)), details=details)


# Phase 5 – B2 Step 3: no two activities on the same day overlap in time
@grader("B2")
def grade_no_time_overlaps(inp: GradingInput) -> GraderResult:
    name = "no_time_overlaps"
    if inp.plan is None:
        return not_applicable(name, "hard", "no plan")
    overlaps = []
    days = inp.plan.itinerary_days
    for day in days:
        acts = sorted((r.activity for r in day.activity_recommendations), key=lambda a: a.start_time)
        for prev, nxt in zip(acts, acts[1:]):
            if nxt.start_time < prev.end_time:
                overlaps.append({"day": day.date.isoformat(), "pair": [prev.activity_id, nxt.activity_id]})
    bad_days = len({o["day"] for o in overlaps})
    return GraderResult(grader=name, severity="hard", passed=not overlaps,
                        score=_ratio(len(days) - bad_days, len(days)),
                        details={"overlaps": overlaps} if overlaps else {})


# Phase 5 – B2 Step 3: no outdoor activity on a rainy/thunderstorm day (forecast is the truth)
@grader("B2")
def grade_weather_safety(inp: GradingInput) -> GraderResult:
    name = "weather_safety"
    if inp.plan is None:
        return not_applicable(name, "hard", "no plan")
    unsafe: dict[str, list[str]] = {}
    bad_days = []
    for day in inp.plan.itinerary_days:
        fc = FORECAST.get((inp.vacation_info.destination, day.date.isoformat()))
        if fc is None or fc["condition"] not in BAD_WEATHER:
            continue
        bad_days.append(day.date.isoformat())
        outdoor = [r.activity.activity_id for r in day.activity_recommendations
                   if r.activity.activity_id in CALENDAR and setting_of(r.activity.activity_id) == "outdoor"]
        if outdoor:
            unsafe[day.date.isoformat()] = outdoor
    return GraderResult(grader=name, severity="hard", passed=not unsafe,
                        score=_ratio(len(bad_days) - len(unsafe), len(bad_days)),
                        details={"bad_weather_days": bad_days, **({"unsafe": unsafe} if unsafe else {})})


# Phase 5 – B2 Step 3: info – how full is the plan? (B4's prompt-v2 target, not a gate)
@grader("B2")
def grade_plan_shape(inp: GradingInput) -> GraderResult:
    name = "plan_shape"
    if inp.plan is None:
        return not_applicable(name, "info", "no plan")
    days = _trip_days(inp)
    trip = {d.isoformat() for d in days}
    n = len(plan_activities(inp))
    max_spend = sum(a["price"] for a in ACTIVITY_CALENDAR if a["start_time"][:10] in trip)
    ceiling = min(inp.vacation_info.budget, max_spend) or 1
    return GraderResult(grader=name, severity="info", passed=None, score=None, details={
        "activities": n,
        "activities_per_day": round(n / len(days), 2),
        "budget_utilization": round(inp.plan.total_cost / ceiling, 3),
        "max_possible_spend": max_spend,
    })


CONSTRAINT_GRADERS = ("budget_within_limit", "cost_arithmetic", "day_coverage", "no_time_overlaps", "weather_safety")
