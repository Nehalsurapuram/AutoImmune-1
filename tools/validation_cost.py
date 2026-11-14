"""Validation cost per gate: what each gate stops, and what it costs to run (RQ3).

    python -m tools.validation_cost            # writes results/cost/

Two populations, kept apart on purpose:
- Execution timing: every eligible evidence row (analyse.eligible_rows, same exclusions) in which the gate
  executed (status not "not_run"), per cohort. Repeated runs are real executions, so they all count here. A gate
  that executed but recorded 0.0 s (the host-side apply check of V0) is counted as executed and untimed and is
  left out of the duration statistics.
- Safety benefit: the distinct judged patches of tools.risk_model (same labels, same de-duplication), per cohort.
  The pipeline stops a patch at its first non-passing gate, so each unsafe patch is attributed to the gate that
  stopped it first. Whether a later gate would also have caught it is unknown, because later gates never ran.

Catches per gate-minute for gate g = unsafe patches first stopped at g / (sum of g's recorded seconds over the
judged patches that reached g / 60). Undefined (None) when g recorded no time. Tool errors and timeouts stop a
patch but are counted separately, never as a safety catch.

Offline analysis only; nothing here changes the gates or the decision engine.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from analyse import GATES, REPO, eligible_rows, load_analysis_exclusions, load_rows, status
from tools.risk_model import COHORTS, _cohort_of_row, _md, _rel, build_dataset, sha12

SCHEMA_VERSION = 1
QUALITY_FAIL = "fail"
TOOL_FAIL = ("error", "timeout")


def median(vals: list[float]) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def p95(vals: list[float]) -> float | None:
    """Nearest-rank 95th percentile."""
    if not vals:
        return None
    s = sorted(vals)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def gate_timing(rows: list[dict], cohort: str) -> list[dict]:
    out = []
    mine = [r for r in rows if _cohort_of_row(r) == cohort]
    for g in GATES:
        execs = [r for r in mine if status(r, g) != "not_run"]
        timed = [r[g.lower()]["seconds"] for r in execs if (r[g.lower()].get("seconds") or 0) > 0]
        out.append({
            "gate": g,
            "executions": len(execs),
            "timed": len(timed),
            "untimed": len(execs) - len(timed),
            "outcomes": dict(sorted(Counter(status(r, g) for r in execs).items())),
            "median_s": median(timed),
            "p95_s": p95(timed),
            "mean_s": sum(timed) / len(timed) if timed else None,
            "total_s": sum(timed),
        })
    return out


def incremental(data: list[dict], cohort: str) -> dict:
    items = [d for d in data if d["cohort"] == cohort]
    unsafe_total = sum(d["unsafe"] for d in items)
    alive = list(items)
    rows, cum_s, cum_unsafe, anomalies = [], 0.0, 0, 0
    for g in GATES:
        reached = [d for d in alive if d["statuses"][g] != "not_run"]
        anomalies += len(alive) - len(reached)
        stopped = [d for d in reached if d["statuses"][g] != "pass"]
        unsafe_stopped = [d for d in stopped if d["unsafe"] and d["statuses"][g] == QUALITY_FAIL]
        safe_stopped = [d for d in stopped if not d["unsafe"] and d["statuses"][g] == QUALITY_FAIL]
        tool_stopped = [d for d in stopped if d["statuses"][g] in TOOL_FAIL]
        secs = [d["seconds"][g] or 0.0 for d in reached]
        spent = sum(secs)
        cum_s += spent
        cum_unsafe += len(unsafe_stopped)
        alive = [d for d in reached if d["statuses"][g] == "pass"]
        rows.append({
            "gate": g,
            "reached": len(reached),
            "unsafe_reached": sum(d["unsafe"] for d in reached),
            "unsafe_stopped": len(unsafe_stopped),
            "safe_stopped": len(safe_stopped),
            "tool_error_stopped": len(tool_stopped),
            "untimed": sum(1 for s in secs if s <= 0),
            "seconds": spent,
            "catches_per_gate_minute": (len(unsafe_stopped) / (spent / 60)) if spent > 0 else None,
            "cumulative_seconds": cum_s,
            "cumulative_unsafe_stopped": cum_unsafe,
            "unsafe_escaping_after": sum(d["unsafe"] for d in alive),
        })
    return {"cohort": cohort, "judged_patches": len(items), "unsafe_patches": unsafe_total,
            "path_anomalies": anomalies, "gates": rows}


def conclusions(inc: dict) -> list[str]:
    """Statements generated from the numbers, with their limits."""
    c = inc["cohort"]
    who = "hand-built" if c == "scripted" else "AI-written"
    out = []
    rated = [r for r in inc["gates"] if r["unsafe_stopped"] > 0 and r["catches_per_gate_minute"] is not None]
    if rated:
        best = max(rated, key=lambda r: r["catches_per_gate_minute"])
        out.append(f"For {who} patches, {best['gate']} stopped the most unsafe patches per gate-minute "
                   f"({best['unsafe_stopped']} in {best['seconds'] / 60:.1f} min).")
    for r in inc["gates"]:
        if r["gate"] == "V0":
            out.append("V0's job is rejecting patches that do not apply or compile. Those are labelled invalid, which "
                       "is neither safe nor unsafe, so they are outside this comparison and V0 shows no unsafe catch "
                       "here by definition.")
            continue
        if r["reached"] and r["unsafe_stopped"] == 0:
            out.append(f"{r['gate']} stopped no unsafe {who} patch among the {r['reached']} judged patches that "
                       f"reached it ({r['unsafe_reached']} of them unsafe); its benefit on this cohort cannot be "
                       "established from these observations.")
        if not r["reached"]:
            out.append(f"No judged {who} patch reached {r['gate']}; nothing can be said about it for this cohort.")
    out.append(f"After all four gates, {inc['gates'][-1]['unsafe_escaping_after']} of {inc['unsafe_patches']} unsafe "
               f"{who} patches were still not stopped.")
    return out


def run(evidence: Path, faults_dir: Path, config_path: Path, results_dir: Path) -> dict[str, str]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    rows = load_rows(evidence)
    eligible = eligible_rows(rows, set(load_analysis_exclusions(evidence)))
    data, _ = build_dataset(evidence, faults_dir, config)
    cohorts = {}
    for c in COHORTS:
        inc = incremental(data, c)
        cohorts[c] = {"timing": gate_timing(eligible, c), "benefit": inc, "conclusions": conclusions(inc)}

    # Cross-reference: analyse.py's own incremental table, computed by its code on the CURRENT inputs, because the
    # file on disk can be stale (analyse.py --check). Whether the on-disk copy matches is recorded, not hidden.
    import csv
    import io
    from analyse import analyse as analyse_results
    gi_path = results_dir / "gate_incremental.csv"
    runs_dir = REPO / "runs"
    current, _ = analyse_results(evidence, faults_dir, runs_dir if runs_dir.is_dir() else None)
    gi_now = current["gate_incremental.csv"]
    cross = list(csv.DictReader(io.StringIO(gi_now)))
    on_disk_matches = gi_path.is_file() and gi_path.read_text(encoding="utf-8") == gi_now

    payload = {
        "schema_version": SCHEMA_VERSION,
        "analysis": "validation_cost",
        "analysis_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "python -m tools.validation_cost",
        "methods_doc": "docs/research/RISK_AND_COST_METHODS.md",
        "definitions": {
            "executions": "eligible evidence rows in which the gate ran (status other than not_run), all repeats",
            "timed": "executions with a recorded duration above 0 s; duration statistics use only these",
            "untimed": "executions recorded as 0.0 s (the V0 apply check that runs on the host is not timed)",
            "p95": "nearest-rank 95th percentile of timed durations",
            "reached": "distinct judged patches that passed every earlier gate, so this gate ran on them",
            "unsafe_stopped": "unsafe judged patches whose first non-passing gate is this one, with status fail",
            "tool_error_stopped": "patches stopped by an error or timeout at this gate; never a safety catch",
            "seconds": "sum of this gate's recorded seconds over the judged patches that reached it",
            "catches_per_gate_minute": "unsafe_stopped / (seconds / 60); null when seconds is 0",
            "uniqueness": ("each unsafe patch is attributed to the first gate that stopped it; later gates did not "
                           "run, so whether they would also have caught it is unknown"),
        },
        "cohorts": cohorts,
        "cross_reference": {
            "source": "analyse.analyse() on the current inputs (the code that writes results/gate_incremental.csv)",
            "on_disk_matches": on_disk_matches,
            "on_disk_note": ("results/gate_incremental.csv matches the current inputs." if on_disk_matches else
                             "results/gate_incremental.csv on disk is stale (analyse.py --check); these rows were "
                             "recomputed from the current inputs. Run python analyse.py to refresh the file."),
            "note": ("Different population: research units, not distinct patches; 'labelled' there includes units "
                     "labelled invalid, and its per-unit medians count gates that did not run as 0 s."),
            "rows": cross,
        },
        "source_artifacts": [{"path": _rel(p), "sha256_12": sha12(p)}
                             for p in (evidence, evidence.parent / "oracle_report.jsonl", config_path, gi_path,
                                       Path(__file__)) if p.is_file()],
    }

    def f1(x):
        return "" if x is None else f"{x:.1f}"

    md = ["# Validation cost per gate", "", "Generated by `python -m tools.validation_cost`. Method: "
          "`docs/research/RISK_AND_COST_METHODS.md`.", ""]
    for c in COHORTS:
        t, b = cohorts[c]["timing"], cohorts[c]["benefit"]
        md += [f"## {c}", "", "### Execution timing (all eligible executions)", "",
               _md(["gate", "executions", "timed", "median s", "p95 s", "mean s"],
                   [[r["gate"], r["executions"], r["timed"], f1(r["median_s"]), f1(r["p95_s"]), f1(r["mean_s"])]
                    for r in t]),
               "", f"### Safety benefit ({b['judged_patches']} distinct judged patches, {b['unsafe_patches']} unsafe)",
               "",
               _md(["gate", "reached", "unsafe stopped", "safe stopped", "tool error", "seconds",
                    "catches / gate-min", "unsafe escaping after"],
                   [[r["gate"], r["reached"], r["unsafe_stopped"], r["safe_stopped"], r["tool_error_stopped"],
                     f1(r["seconds"]), "" if r["catches_per_gate_minute"] is None else f"{r['catches_per_gate_minute']:.2f}",
                     r["unsafe_escaping_after"]] for r in b["gates"]]),
               "", *[f"- {s}" for s in cohorts[c]["conclusions"]], ""]
    return {"validation_cost.json": json.dumps(payload, indent=2) + "\n", "validation_cost.md": "\n".join(md)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Per-gate execution cost and safety benefit.")
    ap.add_argument("--evidence", type=Path, default=REPO / "results" / "evidence.jsonl")
    ap.add_argument("--faults", type=Path, default=REPO / "faults")
    ap.add_argument("--config", type=Path, default=REPO / "config" / "decision.yaml")
    ap.add_argument("--results", type=Path, default=REPO / "results")
    ap.add_argument("--out", type=Path, default=REPO / "results" / "cost")
    args = ap.parse_args(argv)
    files = run(args.evidence, args.faults, args.config, args.results)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (args.out / name).write_text(text, encoding="utf-8")
    print(f"wrote {', '.join(sorted(files))} to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
