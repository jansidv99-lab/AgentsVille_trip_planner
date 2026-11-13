# Phase 5 – B3 Step 1: relevancy graders – "Is the plan relevant to THESE travelers, and are its reasons honest?"
# Deterministic and online-safe (soft severity: quality signals, not task-success gates).
# Relevancy is measured against what was POSSIBLE: an interest counts only if some weather-safe activity
# on the trip dates offers it (whole-day weather policy + approved labels).

import datetime
import re

from project_lib import ACTIVITY_CALENDAR, Interest
from quality.graders.base import GradingInput, grader, not_applicable
from quality.graders.grounding import CALENDAR, FORECAST, plan_activities
from quality.labels import BAD_WEATHER, SAFE_IN_BAD_WEATHER, setting_of
from quality.schema import GraderResult

INTEREST_NAMES = [i.value for i in Interest]


# Phase 5 – B3 Step 1: interests offered by a weather-safe activity on the trip dates
def coverable_interests(inp: GradingInput) -> set[str]:
    vi = inp.vacation_info
    days = {(vi.date_of_arrival + datetime.timedelta(days=i)).isoformat()
            for i in range((vi.date_of_departure - vi.date_of_arrival).days + 1)}
    offered: set[str] = set()
    for a in ACTIVITY_CALENDAR:
        day = a["start_time"][:10]
        if day not in days:
            continue
        fc = FORECAST.get((vi.destination, day))
        if fc and fc["condition"] in BAD_WEATHER and setting_of(a["activity_id"]) not in SAFE_IN_BAD_WEATHER:
            continue
        offered.update(a["related_interests"])
    return offered


def _true_interests(activity) -> set[str]:
    """Interests from the calendar (ground truth) for known ids, else what the plan claims."""
    known = CALENDAR.get(activity.activity_id)
    return set(known["related_interests"]) if known else {str(i) for i in activity.related_interests}


# Phase 5 – B3 Step 1: each traveler's coverable interests are served by the chosen activities
@grader("B3")
def grade_interest_coverage(inp: GradingInput) -> GraderResult:
    name = "interest_coverage"
    if inp.plan is None:
        return not_applicable(name, "soft", "no plan")
    offered = coverable_interests(inp)
    covered = set().union(*(_true_interests(a) for _, a in plan_activities(inp))) if plan_activities(inp) else set()
    per_traveler, ratios, unserved = {}, [], []
    for t in inp.vacation_info.travelers:
        coverable = sorted({str(i) for i in t.interests} & offered)
        got = sorted(set(coverable) & covered)
        per_traveler[t.name] = {"covered": got, "coverable": coverable,
                                "missing": sorted(set(coverable) - covered)}
        if coverable:
            ratios.append(len(got) / len(coverable))
            if not got:
                unserved.append(t.name)
    if not ratios:
        return not_applicable(name, "soft", "no traveler has a coverable interest")
    return GraderResult(grader=name, severity="soft", passed=not unserved, score=round(sum(ratios) / len(ratios), 3),
                        details={"travelers": per_traveler, **({"unserved_travelers": unserved} if unserved else {})})


# Phase 5 – B3 Step 1: golden "obvious best match" activities are included (offline only)
@grader("B3")
def grade_must_include(inp: GradingInput) -> GraderResult:
    name = "must_include"
    wanted = inp.expectations.must_include_activity_ids
    if inp.plan is None or not wanted:
        return not_applicable(name, "soft", "no plan" if inp.plan is None else "no must-include expectation")
    chosen = {a.activity_id for _, a in plan_activities(inp)}
    missing = [aid for aid in wanted if aid not in chosen]
    return GraderResult(grader=name, severity="soft", passed=not missing,
                        score=round((len(wanted) - len(missing)) / len(wanted), 3),
                        details={"missing": missing} if missing else {})


# Phase 5 – B3 Step 1: reasons that name an interest the activity doesn't have (keyword heuristic).
# Known false-alarm mode: contextual mentions ("after the morning hiking event"). The judge adjudicates;
# calibration measures this heuristic's precision against human labels.
@grader("B3")
def grade_reason_grounding(inp: GradingInput) -> GraderResult:
    name = "reason_grounding"
    if inp.plan is None:
        return not_applicable(name, "soft", "no plan")
    flagged, total = [], 0
    for day in inp.plan.itinerary_days:
        for rec in day.activity_recommendations:
            have = _true_interests(rec.activity)
            for reason in rec.reasons_for_recommendation:
                total += 1
                claimed = {i for i in INTEREST_NAMES if re.search(rf"\b{i}\b", reason.lower())}
                if claimed - have:
                    flagged.append({"id": rec.activity.activity_id, "claims": sorted(claimed - have), "reason": reason})
    return GraderResult(grader=name, severity="soft", passed=not flagged,
                        score=round(1 - len(flagged) / total, 3) if total else 1.0,
                        details={"flagged": flagged} if flagged else {})
