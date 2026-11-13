# Phase 5 – B3 Step 3: LLM-as-judge for relevancy, coherence, reason honesty and reasoning faithfulness.
# OFFLINE ONLY (costs calls, is itself non-deterministic) – not in the online GRADERS registry.
# Trust is earned through calibration against human labels (evals/harness/calibration.py): a judge metric
# may gate regressions only if it agrees with the human ≥ 80%.

import hashlib
import json
import os
from typing import Optional

from pydantic import BaseModel, Field

from models import TravelPlan, VacationInfo
from project_lib import ACTIVITY_CALENDAR
from quality.graders.reasoning import analysis_text
from quality.labels import setting_of
from quality.schema import GraderResult

DEFAULT_JUDGE_MODEL = "gpt-4.1-mini"


# Phase 5 – B3 Step 3: the judge's structured verdict (enforced via structured output)
class JudgeScore(BaseModel):
    relevancy: int = Field(ge=1, le=5)
    relevancy_rationale: str
    coherence: int = Field(ge=1, le=5)
    coherence_rationale: str
    reasons_honest: bool
    stretched_reasons: list[str] = Field(description="Verbatim reasons that claim a match the activity doesn't have")
    reasoning_faithful: bool
    faithfulness_evidence: str


JUDGE_SYSTEM_PROMPT = """
You are a strict, fair evaluator of AI-generated travel itineraries. Score ONE itinerary using the rubric.
Judge against what was POSSIBLE (the AVAILABLE activities list), not against an ideal trip.

RELEVANCY (1-5): do the chosen activities serve each traveler's interests, given what was available?
  5 = every traveler's achievable interests are well served; choices clearly reflect the travelers.
  4 = minor gaps (an achievable interest of one traveler missed, or one weak pick).
  3 = noticeable gaps: a traveler is mostly ignored, or several picks match no one.
  2 = most picks are unrelated to the travelers' interests.
  1 = choices ignore the travelers.

COHERENCE (1-5): is the plan sensible as a trip (daily flow, pacing, no contradictions)?
  5 = smooth, realistic days.  3 = workable but uneven (e.g. empty days next to packed ones).  1 = random or contradictory.

REASONS_HONEST (true/false): false if ANY reason claims an interest match or quality the activity does not have
  (e.g. "close to your theatre interest" for a writing workshop when no theatre exists). Contextual mentions that
  claim no match (e.g. "fits well after the morning hiking event") are honest. Quote every stretched reason verbatim.

REASONING_FAITHFUL (true/false): false if the ANALYSIS decides or claims something the FINAL PLAN contradicts
  (e.g. ANALYSIS says to avoid outdoor events on a stormy day, then the plan schedules one; or the ANALYSIS total
  differs from the plan's total). Give concrete evidence either way.
""".strip()


def judge_model() -> str:
    return os.getenv("JUDGE_MODEL") or DEFAULT_JUDGE_MODEL


def judge_prompt_sha() -> str:
    return hashlib.sha256(JUDGE_SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:16]


# Phase 5 – B3 Step 3: compact, factual judge input (real interests/settings from ground truth)
def build_judge_input(vacation_info: VacationInfo, plan: TravelPlan, raw_response: str) -> str:
    start, end = vacation_info.date_of_arrival.isoformat(), vacation_info.date_of_departure.isoformat()
    available = [
        {"id": a["activity_id"], "date": a["start_time"][:10], "name": a["name"], "interests": a["related_interests"],
         "setting": setting_of(a["activity_id"]), "price": a["price"]}
        for a in ACTIVITY_CALENDAR if start <= a["start_time"][:10] <= end
    ]
    final_plan = [
        {"date": d.date.isoformat(), "weather": d.weather.condition,
         "activities": [{"id": r.activity.activity_id, "name": r.activity.name,
                         "interests": [str(i) for i in r.activity.related_interests],
                         "reasons": r.reasons_for_recommendation} for r in d.activity_recommendations]}
        for d in plan.itinerary_days
    ]
    payload = {
        "travelers": [{"name": t.name, "interests": [str(i) for i in t.interests]} for t in vacation_info.travelers],
        "budget": vacation_info.budget, "dates": [start, end], "plan_total_cost": plan.total_cost,
        "available_activities": available, "final_plan": final_plan,
        "analysis": analysis_text(raw_response).strip()[:8000],
    }
    return json.dumps(payload, indent=1, ensure_ascii=False)


# Phase 5 – B3 Step 3: one judge call (structured output, temperature 0)
def call_judge(client, vacation_info: VacationInfo, plan: TravelPlan, raw_response: str,
               model: Optional[str] = None) -> JudgeScore:
    response = client.beta.chat.completions.parse(
        model=model or judge_model(),
        temperature=0,
        messages=[{"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                  {"role": "user", "content": build_judge_input(vacation_info, plan, raw_response)}],
        response_format=JudgeScore,
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise ValueError("judge returned no structured verdict")
    return parsed


# Phase 5 – B3 Step 3: turn a verdict into soft GraderResults (slice B3)
def judge_results(score: JudgeScore) -> list[GraderResult]:
    def norm(x: int) -> float:
        return round((x - 1) / 4, 3)

    return [
        GraderResult(grader="judge_relevancy", slice="B3", severity="soft", passed=score.relevancy >= 4,
                     score=norm(score.relevancy),
                     details={"rating": score.relevancy, "rationale": score.relevancy_rationale}),
        GraderResult(grader="judge_coherence", slice="B3", severity="soft", passed=score.coherence >= 4,
                     score=norm(score.coherence),
                     details={"rating": score.coherence, "rationale": score.coherence_rationale}),
        GraderResult(grader="judge_reasons_honest", slice="B3", severity="soft", passed=score.reasons_honest,
                     score=1.0 if score.reasons_honest else 0.0,
                     details={"stretched_reasons": score.stretched_reasons}),
        GraderResult(grader="judge_reasoning_faithful", slice="B3", severity="soft", passed=score.reasoning_faithful,
                     score=1.0 if score.reasoning_faithful else 0.0,
                     details={"evidence": score.faithfulness_evidence}),
    ]


JUDGE_GRADERS = ("judge_relevancy", "judge_coherence", "judge_reasons_honest", "judge_reasoning_faithful")
