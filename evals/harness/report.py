# Phase 5 – B0 Step 4: summarize EvalRecords into report.json + report.md.

import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Optional

from quality.graders import task_succeeded

# Phase 5 – B3 Step 6: judge metrics are report-only until human labels exist (calibration trust rule)
HUMAN_LABELS_PATH = Path(__file__).resolve().parent.parent / "calibration" / "b3_human_labels.v1.jsonl"
from quality.graders.grounding import HALLUCINATION_GRADERS
from quality.schema import EvalRecord


# Phase 5 – B2 Step 4: task success (goal completion) = parse + no hallucination + all hard constraints
def task_success_rate(records: list[EvalRecord]) -> Optional[float]:
    if not records:
        return None
    return round(sum(task_succeeded(r.grader_results) for r in records) / len(records), 3)


# Phase 5 – B2 Step 4: constraint details – weather violations, cost errors, plan shape per case
def constraint_summary(records: list[EvalRecord]) -> dict:
    weather, cost, shape = [], [], defaultdict(list)
    for r in records:
        run_id = f"{r.case_id}#{r.repeat}"
        ws, ca, ps = r.result("weather_safety"), r.result("cost_arithmetic"), r.result("plan_shape")
        for day, ids in ((ws.details.get("unsafe") or {}).items() if ws else []):
            weather.append({"run": run_id, "day": day, "ids": ids})
        if ca is not None and ca.passed is False:
            cost.append({"run": run_id, "stated": ca.details.get("stated"), "computed": ca.details.get("computed"),
                         "hint": ca.details.get("hint", "")})
        if ps is not None and "activities_per_day" in ps.details:  # skip "not applicable" (unparsed) runs
            shape[r.case_id].append(ps.details)
    return {
        "task_success_rate": task_success_rate(records),
        "failed_runs": [f"{r.case_id}#{r.repeat}" for r in records if not task_succeeded(r.grader_results)],
        "weather_violations": weather,
        "cost_errors": cost,
        "plan_shape": {
            cid: {"activities_per_day": round(statistics.fmean(d["activities_per_day"] for d in ds), 2),
                  "budget_utilization": round(statistics.fmean(d["budget_utilization"] for d in ds), 3)}
            for cid, ds in sorted(shape.items())
        },
    }


# Phase 5 – B0 Step 4: nearest-rank percentile (p95 of latencies)
def percentile(values: list[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


def _mean(values: list[float]) -> Optional[float]:
    return round(statistics.fmean(values), 1) if values else None


# Phase 5 – B3 Step 6: mean score of one grader over the records where it applied
def mean_score(records: list[EvalRecord], grader: str) -> Optional[float]:
    scores = [r.result(grader).score for r in records if r.result(grader) and r.result(grader).score is not None]
    return round(statistics.fmean(scores), 3) if scores else None


# Phase 5 – B3 Step 6: relevancy & reasoning – deterministic signals + (optional) judge metrics
def relevancy_summary(records: list[EvalRecord]) -> dict:
    flagged, unexplained = [], []
    for r in records:
        run_id = f"{r.case_id}#{r.repeat}"
        rg, rc = r.result("reason_grounding"), r.result("reasoning_covers_choices")
        flagged += [{"run": run_id, **f} for f in ((rg.details.get("flagged") or []) if rg else [])]
        if rc is not None and rc.details.get("unexplained"):
            unexplained.append({"run": run_id, "ids": rc.details["unexplained"]})
    judged = any(r.result("judge_relevancy") for r in records)
    return {
        "interest_coverage_mean": mean_score(records, "interest_coverage"),
        "reason_flags": flagged,
        "unexplained_choices": unexplained,
        "judge": {
            "answer_relevancy": mean_score(records, "judge_relevancy"),
            "coherence": mean_score(records, "judge_coherence"),
            "reasons_honest_rate": pass_rate(records, "judge_reasons_honest"),
            "reasoning_faithful_rate": pass_rate(records, "judge_reasoning_faithful"),
            "dishonest_runs": [f"{r.case_id}#{r.repeat}" for r in records
                               if r.result("judge_reasons_honest") and r.result("judge_reasons_honest").passed is False],
        } if judged else None,
    }


# Phase 5 – B0 Step 4: pass rate of one grader over a set of records
def pass_rate(records: list[EvalRecord], grader: str) -> Optional[float]:
    results = [r.result(grader) for r in records]
    judged = [res.passed for res in results if res is not None and res.passed is not None]
    return round(sum(judged) / len(judged), 3) if judged else None


# Phase 5 – B1 Step 3: hallucination rate = share of parsed runs where ANY hard grounding grader fails
def hallucination_rate(records: list[EvalRecord]) -> Optional[float]:
    def verdicts(r: EvalRecord) -> list[Optional[bool]]:
        return [r.result(g).passed for g in HALLUCINATION_GRADERS if r.result(g) is not None]

    judged = [r for r in records if r.parsed and any(v is not None for v in verdicts(r))]
    if not judged:
        return None
    return round(sum(any(v is False for v in verdicts(r)) for r in judged) / len(judged), 3)


# Phase 5 – B1 Step 3: hallucination details – failing runs, most-altered fields, info mentions
def hallucination_summary(records: list[EvalRecord]) -> dict:
    field_counts: dict[str, int] = defaultdict(int)
    failing: list[str] = []
    mentions: list[dict] = []
    for r in records:
        run_id = f"{r.case_id}#{r.repeat}"
        if any(r.result(g) is not None and r.result(g).passed is False for g in HALLUCINATION_GRADERS):
            failing.append(run_id)
        for g, prefix in (("activity_details_match", ""), ("weather_matches_forecast", "weather.")):
            res = r.result(g)
            for diffs in (res.details.get("mismatches") or {}).values() if res else []:
                for fld in diffs:
                    field_counts[prefix + fld] += 1
        info = r.result("uncoverable_interest_mentions")
        mentions += [{"run": run_id, **m} for m in (info.details.get("mentions") or [])] if info else []
    return {
        "rate": hallucination_rate(records),
        "failing_runs": failing,
        "top_mismatched_fields": dict(sorted(field_counts.items(), key=lambda kv: -kv[1])),
        "uncoverable_interest_mentions": mentions,
    }


# Phase 5 – B0 Step 4: aggregate numbers per case and overall
# Phase 5 – B1 Step 3: graders kept in registry order and tagged with their slice; hallucination section
def build_summary(records: list[EvalRecord], meta: dict) -> dict:
    graders: list[str] = []
    slices: dict[str, Optional[str]] = {}
    for r in records:
        for res in r.grader_results:
            if res.grader not in slices:
                graders.append(res.grader)
                slices[res.grader] = res.slice
    by_case: dict[str, list[EvalRecord]] = defaultdict(list)
    for r in records:
        by_case[r.case_id or "-"].append(r)

    def stats(rs: list[EvalRecord]) -> dict:
        lat = [r.latency_ms for r in rs if r.latency_ms is not None]
        costs = [r.cost_usd for r in rs if r.cost_usd is not None]
        return {
            "runs": len(rs),
            "pass_rates": {g: pass_rate(rs, g) for g in graders},
            "latency_ms_mean": _mean(lat),
            "latency_ms_p95": percentile(lat, 95),
            "prompt_tokens_mean": _mean([r.prompt_tokens for r in rs if r.prompt_tokens is not None]),
            "completion_tokens_mean": _mean([r.completion_tokens for r in rs if r.completion_tokens is not None]),
            "cost_usd_total": round(sum(costs), 6) if costs else None,
            "errors": [r.error for r in rs if r.error],
        }

    return {"meta": meta, "graders": graders, "slices": slices, "overall": stats(records),
            "hallucination": hallucination_summary(records),
            "constraints": constraint_summary(records),
            "relevancy": relevancy_summary(records),
            "cases": {cid: stats(rs) for cid, rs in sorted(by_case.items())}}


def _fmt(value, pct: bool = False) -> str:
    if value is None:
        return "–"
    return f"{value:.0%}" if pct else f"{value}"


# Phase 5 – B0 Step 4: human-readable Markdown version of the summary
def render_markdown(summary: dict) -> str:
    m, o, graders = summary["meta"], summary["overall"], summary["graders"]
    slices, h = summary.get("slices", {}), summary.get("hallucination") or {}
    c = summary.get("constraints") or {}
    rv = summary.get("relevancy") or {}
    jm = rv.get("judge") or {}
    judge_meta = m.get("judge") or {}

    def label(g: str) -> str:
        return f"{slices.get(g) or '?'} · {g}"

    # Info graders (no pass/fail) are listed in their own sections, not as pass-rate columns.
    rated = [g for g in graders if o["pass_rates"][g] is not None]

    lines = [
        f"# Eval report – {m['dataset']} · {m['mode']}",
        "",
        f"- **Model:** {m['model']} · **Prompt:** {m['prompt_version']} · **Repeats:** {m['repeats']}",
        f"- **Git SHA:** {m.get('git_sha') or '–'} · **Started:** {m['started']}",
        f"- **Calls:** {m['live_calls']} live, {m['cached_calls']} from cache · "
        f"**Skipped drafts:** {', '.join(m['skipped_drafts']) or 'none'}",
        "",
        "## Overall",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| **Task success rate** (target 100%) | **{_fmt(c.get('task_success_rate'), pct=True)}** |",
        f"| **Hallucination rate** (target 0%) | **{_fmt(h.get('rate'), pct=True)}** |",
        *[f"| {label(g)} pass rate | {_fmt(o['pass_rates'][g], pct=True)} |" for g in rated],
        f"| Latency mean / p95 (ms) | {_fmt(o['latency_ms_mean'])} / {_fmt(o['latency_ms_p95'])} |",
        f"| Tokens mean (prompt / completion) | {_fmt(o['prompt_tokens_mean'])} / {_fmt(o['completion_tokens_mean'])} |",
        f"| Estimated cost (USD) | {_fmt(o['cost_usd_total'])} |",
        "",
        "## Per case",
        "",
        "| Case | Runs | " + " | ".join(rated) + " | Latency mean (ms) | Cost (USD) | Errors |",
        "|---|---|" + "---|" * len(rated) + "---|---|---|",
    ]
    for cid, s in summary["cases"].items():
        rates = " | ".join(_fmt(s["pass_rates"][g], pct=True) for g in rated)
        lines.append(f"| {cid} | {s['runs']} | {rates} | {_fmt(s['latency_ms_mean'])} | "
                     f"{_fmt(s['cost_usd_total'])} | {len(s['errors'])} |")
    mentions = h.get("uncoverable_interest_mentions") or []
    fields = h.get("top_mismatched_fields") or {}
    lines += [
        "",
        "## Hallucination (B1)",
        "",
        f"- **Rate:** {_fmt(h.get('rate'), pct=True)} of parsed runs contained a fabricated or altered fact",
        f"- **Failing runs:** {', '.join(h.get('failing_runs') or []) or 'none'}",
        f"- **Most-altered fields:** {', '.join(f'{k} ×{v}' for k, v in fields.items()) or 'none'}",
        f"- **Reasons mentioning an uncoverable interest** (info – honesty is judged in B3): {len(mentions)}",
        *[f"  - {mm['run']} `{mm['id']}` ({mm['interest']}): \"{mm['reason']}\"" for mm in mentions[:10]],
        "",
        "## Constraints & task success (B2)",
        "",
        f"- **Task success:** {_fmt(c.get('task_success_rate'), pct=True)} of runs parsed, had no hallucination "
        "and met every hard constraint",
        f"- **Failed runs:** {', '.join(c.get('failed_runs') or []) or 'none'}",
        f"- **Weather violations** (outdoor activity on a rainy/thunderstorm day): {len(c.get('weather_violations') or [])}",
        *[f"  - {w['run']} {w['day']}: {', '.join(w['ids'])}" for w in (c.get("weather_violations") or [])],
        f"- **Cost errors** (total ≠ sum of prices): {len(c.get('cost_errors') or [])}",
        *[f"  - {e['run']}: stated {e['stated']}, computed {e['computed']}" + (f" ({e['hint']})" if e["hint"] else "")
          for e in (c.get("cost_errors") or [])],
        "",
        "| Case | Activities / day | Budget utilization |",
        "|---|---|---|",
        *[f"| {cid} | {s['activities_per_day']} | {s['budget_utilization']:.0%} |"
          for cid, s in (c.get("plan_shape") or {}).items()],
        "",
        "## Relevancy & reasoning (B3)",
        "",
        f"- **Interest coverage** (mean, vs coverable interests): {_fmt(rv.get('interest_coverage_mean'), pct=True)}",
        f"- **Reasons naming an interest the activity lacks** (keyword heuristic; may include contextual "
        f"false alarms): {len(rv.get('reason_flags') or [])}",
        *[f"  - {f['run']} `{f['id']}` claims {', '.join(f['claims'])}: \"{f['reason']}\""
          for f in (rv.get("reason_flags") or [])[:12]],
        f"- **Unexplained choices** (final activities not discussed in the ANALYSIS): "
        + (", ".join(f"{u['run']} ({len(u['ids'])})" for u in (rv.get("unexplained_choices") or [])) or "none"),
        "",
        *([
            f"**LLM judge** ({judge_meta.get('model')}, {judge_meta.get('live_calls')} live / "
            f"{judge_meta.get('cached_calls')} cached calls, ≈ ${judge_meta.get('cost_usd')}) – "
            + ("_Calibration: human labels present – see the agreement report; trust only metrics with ≥ 80% agreement._"
             if HUMAN_LABELS_PATH.exists() else
             "_⚠️ Calibration PENDING (no human labels yet): these judge metrics are **report-only** and must not "
             "gate anything._"),
            "",
            "| Judge metric | Value |",
            "|---|---|",
            f"| Answer relevancy (0–1) | {_fmt(jm.get('answer_relevancy'))} |",
            f"| Coherence (0–1) | {_fmt(jm.get('coherence'))} |",
            f"| Reasons honest rate | {_fmt(jm.get('reasons_honest_rate'), pct=True)} |",
            f"| Reasoning faithful rate | {_fmt(jm.get('reasoning_faithful_rate'), pct=True)} |",
            f"| Judged dishonest | {', '.join(jm.get('dishonest_runs') or []) or 'none'} |",
        ] if jm else ["_LLM judge not run (use `--judge`)._"]),
        "",
    ]
    return "\n".join(lines)


# Phase 5 – B0 Step 4: write report.json and report.md next to records.jsonl
def write_report(out_dir: Path, records: list[EvalRecord], meta: dict) -> dict:
    summary = build_summary(records, meta)
    (out_dir / "report.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (out_dir / "report.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary
