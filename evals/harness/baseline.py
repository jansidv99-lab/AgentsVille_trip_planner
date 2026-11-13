# Phase 5 – B4 Step 2: consistency (pass^k / pass@k), baselines, and regression comparison.
# A baseline is an ACCEPTED snapshot of metrics for (dataset@version, model, prompt version, mode).
# New runs are compared against it; the bar only moves on purpose (--accept-baseline, via a PR).

import datetime
import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

from quality.graders import CONSTRAINT_GRADERS, HALLUCINATION_GRADERS, task_succeeded
from quality.schema import EvalRecord

BASELINES_DIR = Path(__file__).resolve().parent.parent / "baselines"
HARD_GRADERS = ("parse", *HALLUCINATION_GRADERS, *CONSTRAINT_GRADERS)


# Phase 5 – B4 Step 2: per-case reliability under non-determinism
def consistency(records: list[EvalRecord]) -> dict:
    by_case: dict[str, list[bool]] = defaultdict(list)
    for r in records:
        by_case[r.case_id].append(task_succeeded(r.grader_results))
    cases = {cid: {"runs": len(ok), "successes": sum(ok), "pass_k": all(ok), "pass_at_k": any(ok)}
             for cid, ok in sorted(by_case.items())}
    n = len(cases) or 1
    return {
        "k": max((c["runs"] for c in cases.values()), default=0),
        "pass_k_rate": round(sum(c["pass_k"] for c in cases.values()) / n, 3),        # reliably works
        "pass_at_k_rate": round(sum(c["pass_at_k"] for c in cases.values()) / n, 3),  # can work
        "flaky_cases": [cid for cid, c in cases.items() if c["pass_at_k"] and not c["pass_k"]],
        "cases": cases,
    }


def baseline_path(dataset_ref: str, model: str, prompt_version: str, mode: str,
                  directory: Path = BASELINES_DIR) -> Path:
    return directory / f"{dataset_ref}__{model}__{prompt_version}__{mode}.json"


# Phase 5 – B4 Step 2: the comparable snapshot of a run (also used for the current run in compare())
def snapshot(summary: dict, records: list[EvalRecord]) -> dict:
    meta, overall = summary["meta"], summary["overall"]
    rv = (summary.get("relevancy") or {}).get("judge")
    per_case = {}
    for cid, c in consistency(records)["cases"].items():
        case_records = [r for r in records if r.case_id == cid]
        per_case[cid] = {
            "task_success_rate": round(c["successes"] / c["runs"], 3),
            "pass_k": c["pass_k"],
            "hard_failures": sorted({g for r in case_records for g in HARD_GRADERS
                                     if r.result(g) is not None and r.result(g).passed is False}),
        }
    return {
        "dataset": meta["dataset"], "model": meta["model"], "prompt_version": meta["prompt_version"],
        "mode": meta["mode"], "repeats": meta["repeats"], "git_sha": meta.get("git_sha"),
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "metrics": {
            "task_success_rate": summary["constraints"]["task_success_rate"],
            "hallucination_rate": summary["hallucination"]["rate"],
            "pass_rates": overall["pass_rates"],
            "consistency": {k: v for k, v in consistency(records).items() if k != "cases"},
            "plan_shape": summary["constraints"]["plan_shape"],
        },
        "per_case": per_case,
        "judge": ({**rv, "report_only": True} if rv else None),  # report-only until calibrated (B3)
    }


def write_baseline(snap: dict, directory: Path = BASELINES_DIR) -> Path:
    path = baseline_path(snap["dataset"], snap["model"], snap["prompt_version"], snap["mode"], directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def load_baseline(path: Path) -> Optional[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# Phase 5 – B4 Step 2: current vs baseline → deltas, regressions, improvements
def compare(current: dict, baseline: dict, tolerance: float = 0.0) -> dict:
    cm, bm = current["metrics"], baseline["metrics"]
    regressions, improvements, deltas = [], [], {}

    def delta(name, cur, base, higher_is_better=True):
        if cur is None or base is None:
            return
        d = round(cur - base, 3)
        deltas[name] = {"baseline": base, "current": cur, "delta": d}
        worse = (d < -tolerance) if higher_is_better else (d > tolerance)
        better = (d > 0) if higher_is_better else (d < 0)
        (regressions if worse else improvements if better else []).append(name)

    delta("task_success_rate", cm["task_success_rate"], bm["task_success_rate"])
    delta("hallucination_rate", cm["hallucination_rate"], bm["hallucination_rate"], higher_is_better=False)
    for g in HARD_GRADERS:
        delta(f"pass_rate.{g}", cm["pass_rates"].get(g), bm["pass_rates"].get(g))
    for g in ("reason_grounding", "reasoning_covers_choices", "interest_coverage"):  # soft: report, never gate
        if g in cm["pass_rates"] and g in bm["pass_rates"]:
            c, b = cm["pass_rates"][g], bm["pass_rates"][g]
            if c is not None and b is not None:
                deltas[f"soft.{g}"] = {"baseline": b, "current": c, "delta": round(c - b, 3)}

    if (cm["hallucination_rate"] or 0) > 0 and "hallucination_rate" not in regressions:
        regressions.append("hallucination_rate")  # ANY hallucination is a regression, whatever the baseline

    # Per case: a hard grader that never failed on this case in the baseline now fails → new failure
    new_failures = {}
    for cid, cur in current["per_case"].items():
        base = baseline["per_case"].get(cid)
        if base is None:
            continue
        added = sorted(set(cur["hard_failures"]) - set(base["hard_failures"]))
        if added:
            new_failures[cid] = added
    return {"regressions": regressions, "improvements": improvements, "deltas": deltas,
            "new_case_failures": new_failures,
            "passed": not regressions and not new_failures}
