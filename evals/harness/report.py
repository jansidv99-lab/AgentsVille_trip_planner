# Phase 5 – B0 Step 4: summarize EvalRecords into report.json + report.md.

import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Optional

from quality.graders.grounding import HALLUCINATION_GRADERS
from quality.schema import EvalRecord


# Phase 5 – B0 Step 4: nearest-rank percentile (p95 of latencies)
def percentile(values: list[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


def _mean(values: list[float]) -> Optional[float]:
    return round(statistics.fmean(values), 1) if values else None


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
            "cases": {cid: stats(rs) for cid, rs in sorted(by_case.items())}}


def _fmt(value, pct: bool = False) -> str:
    if value is None:
        return "–"
    return f"{value:.0%}" if pct else f"{value}"


# Phase 5 – B0 Step 4: human-readable Markdown version of the summary
def render_markdown(summary: dict) -> str:
    m, o, graders = summary["meta"], summary["overall"], summary["graders"]
    slices, h = summary.get("slices", {}), summary.get("hallucination") or {}

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
        "_Constraint (B2) and relevancy/reasoning (B3) graders are added in later slices._",
        "",
    ]
    return "\n".join(lines)


# Phase 5 – B0 Step 4: write report.json and report.md next to records.jsonl
def write_report(out_dir: Path, records: list[EvalRecord], meta: dict) -> dict:
    summary = build_summary(records, meta)
    (out_dir / "report.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (out_dir / "report.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary
