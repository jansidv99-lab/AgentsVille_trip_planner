# Phase 3 – Step 3: render a TravelPlan in Streamlit (summary metrics, one expander per day,
# JSON download). Only display logic lives here; app.py decides *what* to show.

import streamlit as st

from models import ActivityRecommendation, ItineraryDay, PromptTrace, TravelPlan

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


# Phase 3 – Step 6: "Prompt inspector" – system prompt, user prompt, raw and final response
def render_prompt_trace(trace: PromptTrace) -> None:
    with st.expander("🔍 Prompt inspector", expanded=False):
        system_tab, user_tab, raw_tab, final_tab = st.tabs(
            ["System prompt", "User prompt", "Raw response", "Final response"]
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

        st.caption(
            f"model: {trace.model} · system prompt {len(trace.system_prompt):,} chars · "
            f"user prompt {len(trace.user_prompt):,} chars · reply {len(trace.raw_response):,} chars"
        )
        st.download_button(
            "Download trace JSON",
            data=trace.model_dump_json(indent=2),
            file_name="prompt_trace.json",
            mime="application/json",
            key="download_trace",
        )
