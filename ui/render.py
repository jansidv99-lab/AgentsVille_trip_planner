# Phase 3 – Step 3: render a TravelPlan in Streamlit (summary metrics, one expander per day,
# JSON download). Only display logic lives here; app.py decides *what* to show.

import streamlit as st

from models import ActivityRecommendation, ItineraryDay, PromptTrace, TravelPlan, VacationInfo
from quality.graders import CONSTRAINT_GRADERS, HALLUCINATION_GRADERS, GradingInput, run_graders, task_succeeded

INSPECTOR_HEIGHT = 400  # px; long prompts scroll inside the box

WEATHER_ICONS = {
    "clear": "☀️",
    "sunny": "☀️",
    "partly cloudy": "⛅",
    "cloudy": "☁️",
    "rainy": "🌧️",
    "thunderstorm": "⛈️",
}


# Phase 3 – Step 3: map a weather condition to an emoji (fallback for unknown conditions)
def weather_icon(condition: str) -> str:
    return WEATHER_ICONS.get(condition.lower(), "🌤️")


# Phase 3 – Step 3: headline numbers for the whole trip
def render_summary(plan: TravelPlan, budget: int) -> None:
    n_activities = sum(len(day.activity_recommendations) for day in plan.itinerary_days)
    col1, col2, col3 = st.columns(3)
    col1.metric("Total cost", f"{plan.total_cost} / {budget}")
    col2.metric("Days", len(plan.itinerary_days))
    col3.metric("Activities", n_activities)
    if plan.total_cost <= budget:
        st.success(f"✅ Within budget ({budget - plan.total_cost} left)")
    else:
        st.warning(f"⚠️ Over budget by {plan.total_cost - budget}")


# Phase 3 – Step 3: one recommended activity
def render_activity(rec: ActivityRecommendation) -> None:
    a = rec.activity
    time = f"{a.start_time:%H:%M}–{a.end_time:%H:%M}"
    st.markdown(f"**{time} · {a.name}** — {a.price}")
    st.caption(f"📍 {a.location} · Interests: {', '.join(str(i) for i in a.related_interests)}")
    for reason in rec.reasons_for_recommendation:
        st.markdown(f"- {reason}")


# Phase 3 – Step 3: one day as an expander; the header shows date and weather at a glance
def render_day(n: int, day: ItineraryDay) -> None:
    w = day.weather
    header = (
        f"Day {n} – {day.date:%a %d %b %Y}   "
        f"{weather_icon(w.condition)} {w.temperature:.0f}° {w.temperature_unit} · {w.condition}"
    )
    with st.expander(header, expanded=(n == 1)):
        if not day.activity_recommendations:
            st.info("No activities planned for this day.")
        for i, rec in enumerate(day.activity_recommendations):
            if i:
                st.divider()
            render_activity(rec)


# Phase 3 – Step 3: entry point used by app.py
def render_travel_plan(plan: TravelPlan, budget: int) -> None:
    st.header(f"Your {plan.city} itinerary")
    st.caption(f"{plan.start_date:%d %b %Y} → {plan.end_date:%d %b %Y}")
    render_summary(plan, budget)
    for n, day in enumerate(plan.itinerary_days, start=1):
        render_day(n, day)
    st.download_button(
        "Download JSON",
        data=plan.model_dump_json(indent=2),
        file_name=f"{plan.city.lower()}_itinerary.json",
        mime="application/json",
    )


# Phase 3 – Step 6: one inspector tab: a fixed-height scrollable code block (has a copy button)
def _code_tab(text: str, language: str) -> None:
    with st.container(height=INSPECTOR_HEIGHT):
        st.code(text, language=language, wrap_lines=True)


VERDICT_ICONS = {True: "✅", False: "❌", None: "➖"}


# Phase 5 – B1 Step 5: online grading – run the deterministic graders on this live itinerary
def render_quality_checks(trace: PromptTrace, vacation_info: VacationInfo) -> None:
    results = run_graders(GradingInput.for_request(vacation_info, trace.travel_plan, trace.raw_response))
    hard = [r for r in results if r.severity == "hard" and r.passed is not None]
    hallucinated = [r.grader for r in results if r.grader in HALLUCINATION_GRADERS and r.passed is False]
    violated = [r.grader for r in results if r.grader in CONSTRAINT_GRADERS and r.passed is False]
    st.markdown(
        f"**Hard checks passed: {sum(r.passed for r in hard)}/{len(hard)}** · "
        + ("✅ task success" if task_succeeded(results) else "❌ task failed") + " · "
        + ("❌ hallucination detected: " + ", ".join(hallucinated) if hallucinated else "✅ no hallucination detected")
        + " · "
        + ("❌ constraints violated: " + ", ".join(violated) if violated else "✅ all constraints met")
    )
    st.caption("The same deterministic graders the offline evals use (Layer B), run here on live output. "
               "➖ = not applicable · info checks are signals, not verdicts.")
    for r in results:
        icon = "ℹ️" if r.severity == "info" else VERDICT_ICONS[r.passed]
        score = f" · score {r.score:.0%}" if r.score is not None else ""
        st.markdown(f"{icon} `{r.grader}` — {r.slice} · {r.severity}{score}")
        show = r.passed is False or (r.severity == "info" and r.details.get("count"))
        if show:
            st.json(r.details, expanded=False)


# Phase 3 – Step 6: "Prompt inspector" – system prompt, user prompt, raw and final response
# Phase 5 – B1 Step 5: + "Quality checks" tab (online grading); caption shows latency/tokens/cost
def render_prompt_trace(trace: PromptTrace, vacation_info: VacationInfo) -> None:
    with st.expander("🔍 Prompt inspector", expanded=False):
        system_tab, user_tab, raw_tab, final_tab, quality_tab = st.tabs(
            ["System prompt", "User prompt", "Raw response", "Final response", "Quality checks"]
        )
        with system_tab:
            _code_tab(trace.system_prompt, "markdown")
        with user_tab:
            _code_tab(trace.user_prompt, "json")
        with raw_tab:
            _code_tab(trace.raw_response or "(empty reply)", "markdown")
        with final_tab:
            if trace.travel_plan is None:
                st.warning("No valid TravelPlan – see the Raw response tab.")
            else:
                _code_tab(trace.travel_plan.model_dump_json(indent=2), "json")
        with quality_tab:
            render_quality_checks(trace, vacation_info)

        metrics = ""
        if trace.latency_ms is not None:
            metrics = f" · {trace.latency_ms / 1000:.1f} s"
        if trace.prompt_tokens is not None:
            metrics += f" · tokens {trace.prompt_tokens:,} in / {trace.completion_tokens:,} out"
        if trace.cost_usd is not None:
            metrics += f" · ≈ ${trace.cost_usd:.4f}"
        st.caption(
            f"model: {trace.model}{metrics} · system prompt {len(trace.system_prompt):,} chars · "
            f"reply {len(trace.raw_response):,} chars · trace {trace.trace_id[:8]}"
        )
        st.download_button(
            "Download trace JSON",
            data=trace.model_dump_json(indent=2),
            file_name="prompt_trace.json",
            mime="application/json",
            key="download_trace",
        )
