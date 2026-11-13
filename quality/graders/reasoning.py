# Phase 5 – B3 Step 1: reasoning graders – does the step-by-step ANALYSIS have the required structure, and
# does it actually discuss the choices that end up in the final plan? Deterministic, online-safe, soft.
# Whether the ANALYSIS is FAITHFUL (its decisions match the plan) needs judgement → the LLM judge (judge.py).

from quality.graders.base import GradingInput, grader, not_applicable
from quality.graders.grounding import plan_activities
from quality.schema import GraderResult

REQUIRED_STEPS = ("Weather Analysis", "Interest Mapping", "Budget Planning", "Day-by-Day Planning", "Validation")


# Phase 5 – B3 Step 1: the ANALYSIS section = everything before "FINAL OUTPUT" (or before the JSON)
def analysis_text(raw_response: str) -> str:
    marker = raw_response.find("FINAL OUTPUT")
    if marker >= 0:
        return raw_response[:marker]
    brace = raw_response.find("{")
    return raw_response[:brace] if brace >= 0 else raw_response


# Phase 5 – B3 Step 1: the 5 steps the prompt requires are present (cheap regression guard)
@grader("B3")
def grade_analysis_structure(inp: GradingInput) -> GraderResult:
    name = "analysis_structure"
    text = analysis_text(inp.raw_response).lower()
    missing = [s for s in REQUIRED_STEPS if s.lower() not in text]
    return GraderResult(grader=name, severity="soft", passed=not missing,
                        score=round((len(REQUIRED_STEPS) - len(missing)) / len(REQUIRED_STEPS), 3),
                        details={"missing_steps": missing} if missing else {})


# Phase 5 – B3 Step 1: every final activity is discussed (by id or name) in the ANALYSIS – no unexplained choices
@grader("B3")
def grade_reasoning_covers_choices(inp: GradingInput) -> GraderResult:
    name = "reasoning_covers_choices"
    if inp.plan is None:
        return not_applicable(name, "soft", "no plan")
    text = analysis_text(inp.raw_response).lower()
    acts = [a for _, a in plan_activities(inp)]
    unexplained = [a.activity_id for a in acts
                   if a.activity_id.lower() not in text and a.name.lower()[:25] not in text]
    return GraderResult(grader=name, severity="soft", passed=not unexplained,
                        score=round((len(acts) - len(unexplained)) / len(acts), 3) if acts else 1.0,
                        details={"unexplained": unexplained} if unexplained else {})
