# Phase 7 – C2/C3: Layer A contract tests for the monitoring config (no GCP calls).
# Metrics, alerts and the dashboard must only reference (1) log fields the app really emits and (2) metrics that
# are really defined – so renaming an event field fails CI instead of silently flat-lining a chart or an alert.

import io
import json
import re
from pathlib import Path

import pytest
import yaml

from models import PromptTrace
from observability.events import feedback_event, llm_error_event, llm_run_event
from quality.graders import GradingInput, run_graders

ROOT = Path(__file__).resolve().parent.parent
MON = ROOT / "deploy" / "monitoring"
BASE = ('resource.type="cloud_run_revision" AND resource.labels.service_name="agentsville-trip-planner" '
        'AND jsonPayload.app="agentsville"')
METRICS = {p.stem: yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((MON / "metrics").glob("*.yaml"))}
ALERTS = {p.stem: yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((MON / "alerts").glob("*.yaml"))}
DASHBOARD = json.loads((MON / "dashboard.json").read_text(encoding="utf-8"))
METRIC_REF = re.compile(r"logging_googleapis_com:user_([a-z0-9_]+?)(?:_bucket|_sum|_count)?\{")


@pytest.fixture(scope="module")
def emitted_fields(request) -> set[str]:
    """Every top-level jsonPayload key the app emits, across all event types."""
    import planner
    from models import TravelPlan, VacationInfo
    vi = VacationInfo.model_validate(planner.VACATION_INFO_DICT)
    plan = TravelPlan.model_validate_json((ROOT / "sample_plan.json").read_text(encoding="utf-8"))
    trace = PromptTrace(model="gpt-4.1-mini", prompt_version="v1", system_prompt="s", user_prompt="u",
                        raw_response="r", travel_plan=plan, latency_ms=1.0, prompt_tokens=1, completion_tokens=1,
                        cost_usd=0.1)
    results = run_graders(GradingInput.for_request(vi, plan, "r"))
    keys: set[str] = set()
    for rec in (llm_run_event(trace, vi, results, stream=io.StringIO()),
                feedback_event("t", "up", "", "v1", stream=io.StringIO()),
                llm_error_event(vi, "m", "e", stream=io.StringIO())):
        keys |= set(rec)
    return keys


# ---- C2 metrics -----------------------------------------------------------------------------------------------
def test_metric_files_are_named_and_scoped(emitted_fields):
    assert len(METRICS) == 10
    for stem, m in METRICS.items():
        assert m["name"] == stem and stem.startswith("agentsville_")
        assert m["filter"].startswith(BASE), stem  # never count another service's logs


def test_metrics_only_reference_emitted_fields(emitted_fields):
    for stem, m in METRICS.items():
        text = " ".join([m["filter"], m.get("valueExtractor", ""), *m.get("labelExtractors", {}).values()])
        fields = set(re.findall(r"jsonPayload\.([a-z_]+)", text))
        missing = fields - emitted_fields
        assert not missing, f"{stem} references fields the app never emits: {missing}"


def test_label_extractors_match_descriptor_labels():
    for stem, m in METRICS.items():
        declared = {lbl["key"] for lbl in m["metricDescriptor"].get("labels", [])}
        assert declared == set(m.get("labelExtractors", {})), stem


# ---- C3 alerts ------------------------------------------------------------------------------------------------
def test_alerts_reference_defined_metrics_and_have_runbooks():
    assert len(ALERTS) == 8  # A1–A7 + A9 (A8 uptime not built – decision)
    for stem, a in ALERTS.items():
        query = a["conditions"][0]["conditionPrometheusQueryLanguage"]["query"]
        refs = set(METRIC_REF.findall(query))
        assert refs <= set(METRICS), f"{stem} uses undefined metrics {refs - set(METRICS)}"
        assert refs or "run_googleapis_com" in query, stem
        assert 'service_name="agentsville-trip-planner"' in query, stem
        assert "**First steps:**" in a["documentation"]["content"], stem
        assert a["alertStrategy"]["autoClose"] == "3600s" and a["severity"] in ("CRITICAL", "WARNING")


def test_rate_alerts_have_minimum_volume_guards():
    for stem in ("a2-task-success-drift", "a3-weather-spike", "a6-unhappy-users"):
        query = ALERTS[stem]["conditions"][0]["conditionPrometheusQueryLanguage"]["query"]
        assert " / " in query and ">= 5" in query, f"{stem} must not fire on 1–2 events"


def test_thresholds_match_the_accepted_table():
    q = {k: v["conditions"][0]["conditionPrometheusQueryLanguage"]["query"] for k, v in ALERTS.items()}
    assert q["a1-hallucination"].endswith("> 0") and "[1h]" in q["a1-hallucination"]
    assert "> 0.6" in q["a2-task-success-drift"] and "[6h]" in q["a2-task-success-drift"]
    assert "> 0.5" in q["a3-weather-spike"]
    assert ">= 3" in q["a4-llm-errors"] and "[10m]" in q["a4-llm-errors"]
    assert "> 60000" in q["a5-slow-responses"] and "0.95" in q["a5-slow-responses"]
    assert "> 0.5" in q["a6-unhappy-users"] and "[24h]" in q["a6-unhappy-users"]
    assert "> 60" in q["a7-cost-guard"] and "[1h]" in q["a7-cost-guard"]
    assert 'response_code_class="5xx"' in q["a9-server-errors"]


# ---- C2 dashboard ---------------------------------------------------------------------------------------------
def test_dashboard_tiles_reference_defined_metrics():
    tiles = DASHBOARD["mosaicLayout"]["tiles"]
    queries = [ds["timeSeriesQuery"]["prometheusQuery"] for t in tiles if "xyChart" in t["widget"]
               for ds in t["widget"]["xyChart"]["dataSets"]]
    assert queries
    for q in queries:
        assert METRIC_REF.findall(q) or "run_googleapis_com" in q, q
        assert set(METRIC_REF.findall(q)) <= set(METRICS), q
    assert all(t["xPos"] + t["width"] <= 48 for t in tiles)


# ---- synthetic alert-test events never reach analytics / golden data ------------------------------------------
@pytest.mark.parametrize("view", ["llm_runs", "feedback"])
def test_views_exclude_synthetic_events(view):
    sql = (ROOT / "observability" / "bigquery" / f"{view}.sql").read_text(encoding="utf-8")
    assert "STARTS_WITH(IFNULL(jsonPayload.trace_id, ''), 'synthetic-')" in sql and "NOT STARTS_WITH" in sql
