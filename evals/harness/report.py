# Phase 5 – B0 Step 4: summarize EvalRecords into report.json + report.md.

import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Optional

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


# Phase 5 – B0 Step 4: aggregate numbers per case and overall
def build_summary(records: list[EvalRecord], meta: dict) -> dict:
    graders = sorted({res.grader for r in records for res in r.grader_results})
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

    return {"meta": meta, "graders": graders, "overall": stats(records),
            "cases": {cid: stats(rs) for cid, rs in sorted(by_case.items())}}


def _fmt(value, pct: bool = False) -> str:
    if value is None:
        return "–"
    return f"{value:.0%}" if pct else f"{value}"


# Phase 5 – B0 Step 4: human-readable Markdown version of the summary
def render_markdown(summary: dict) -> str:
    m, o, graders = summary["meta"], summary["overall"], summary["graders"]
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
        *[f"| {g} pass rate | {_fmt(o['pass_rates'][g], pct=True)} |" for g in graders],
        f"| Latency mean / p95 (ms) | {_fmt(o['latency_ms_mean'])} / {_fmt(o['latency_ms_p95'])} |",
        f"| Tokens mean (prompt / completion) | {_fmt(o['prompt_tokens_mean'])} / {_fmt(o['completion_tokens_mean'])} |",
        f"| Estimated cost (USD) | {_fmt(o['cost_usd_total'])} |",
        "",
        "## Per case",
        "",
        "| Case | Runs | " + " | ".join(f"{g} pass" for g in graders) + " | Latency mean (ms) | Cost (USD) | Errors |",
        "|---|---|" + "---|" * len(graders) + "---|---|---|",
    ]
    for cid, s in summary["cases"].items():
        rates = " | ".join(_fmt(s["pass_rates"][g], pct=True) for g in graders)
        lines.append(f"| {cid} | {s['runs']} | {rates} | {_fmt(s['latency_ms_mean'])} | "
                     f"{_fmt(s['cost_usd_total'])} | {len(s['errors'])} |")
    lines += ["", "_Graders for hallucination (B1), constraints (B2) and relevancy (B3) are added in later slices._", ""]
    return "\n".join(lines)


# Phase 5 – B0 Step 4: write report.json and report.md next to records.jsonl
def write_report(out_dir: Path, records: list[EvalRecord], meta: dict) -> dict:
    summary = build_summary(records, meta)
    (out_dir / "report.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (out_dir / "report.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary
