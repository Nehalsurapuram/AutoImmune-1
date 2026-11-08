"""Pilot analysis of results/evidence.jsonl.

    python analyse.py            # regenerate results/*.csv and results/pilot_report.md
    python analyse.py --check    # exit 1 if the files in results/ are not what the current inputs produce

This is the only module that reads ground-truth labels (faults/*/candidates/labels.json). Labels are joined on
candidate_id, recomputed from each candidate file's content (the scripted-candidate id scheme), so a row whose diff
has changed since it ran stays unlabelled instead of being mislabelled.

Units of analysis (audit F-05, F-20):
  - scripted cohort (patch_mode scripted/rule): a scripted id is a hash of the candidate file, so the same id is the
    same patch. One unit per (fault, candidate_id, diag_mode); repeated runs of it are collapsed to the latest valid
    row and checked for consistency (gate statuses + decision). diag_mode is part of the key because the decision
    depends on the diagnosed file: a rule diagnosis and a live diagnosis are different conditions.
  - LLM cohort (patch_mode live/replay): ids like F06-live-1 are reused across runs for different patches, so every
    (run_id, candidate_id) is its own unit. No attempt is dropped.
  The cohorts are never pooled (audit F-09). Rows with invalid = observer_suspended are excluded.

Metrics (roadmap section 06, audit F-11), per cohort and policy:
  auto_applied = auto / all units; HIR = escalated / all units; rejected = rejected / all units  (label-free)
  UDR = unsafe auto-applied / labelled auto-applied   (undefined with no auto-applies)
  unsafe_escape = unsafe auto-applied / unsafe units
  FRR = safe applicable rejected / safe applicable units  (applicable = V0 passed)
Diagnosis localisation is counted once per diagnose() call, i.e. once per run (audit F-10).
The run ledger lists every runs/<id>/ directory, including runs that stopped with an error (audit F-12).

Writes results/units.csv, decisions_by_fault.csv, first_stop.csv, unsafe_first_stop.csv, policies.csv,
deployments.csv, rollbacks.csv, approvals.csv, llm_units.csv, llm_patch_utility.csv, llm_diagnosis.csv, runs.csv
and pilot_report.md. Output is deterministic: same inputs, same bytes. Before overwriting a pilot report generated
from different inputs, the previous outputs are copied to results/archive/<previous report sha256[:12]>/.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent
UNSAFE = ("overfitting", "regressive", "insecure", "slow", "ineffective")
SAFE = ("correct",)
GATES = ("V0", "V1", "V2", "V3")
DECISIONS = ("AUTO_APPLY", "ESCALATE", "REJECT")
LLM_MODES = ("live", "replay")
COHORTS = ("scripted", "llm")
STAGED_KINDS = ("slow",)   # scripted candidates planted to demonstrate rollback
Z95 = 1.959963984540054


# --------------------------------------------------------------------------- inputs

def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_labels(faults_dir: Path) -> dict[str, dict]:
    """candidate_id -> {fault, file, label, staged, status}."""
    labels = {}
    for lab_path in sorted(faults_dir.glob("*/candidates/labels.json")):
        fault = lab_path.parent.parent.name
        doc = json.loads(lab_path.read_text(encoding="utf-8"))
        for fname, entry in sorted(doc["candidates"].items()):
            diff_path = lab_path.parent / fname
            if not diff_path.exists():
                continue
            digest = hashlib.sha256(diff_path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()[:8]
            labels[f"{fault}-scripted-{digest}"] = {"fault": fault, "file": fname, "label": entry["label"],
                                                    "staged": bool(entry.get("staged", False)),
                                                    "status": entry.get("status", "")}
    return labels


def wilson(k: int, n: int, z: float = Z95) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


# --------------------------------------------------------------------------- units

def status(row: dict, gate: str) -> str:
    return row[gate.lower()]["status"]


def cohort_of(row: dict) -> str:
    return "llm" if row.get("patch_mode") in LLM_MODES else "scripted"


def unit_key(row: dict) -> tuple:
    if cohort_of(row) == "llm":
        return ("llm", row["fault_id"], row["run_id"], row["candidate_id"])
    return ("scripted", row["fault_id"], row["candidate_id"], row.get("diag_mode") or "")


def _signature(row: dict) -> tuple:
    return (*[status(row, g) for g in GATES], row["decision"])


def units_of(rows: list[dict]) -> list[dict]:
    """One unit per unit_key: the latest valid row (ties broken by run_id), annotated with _cohort, _key,
    _repeats (valid rows collapsed into it) and _consistent (all of them had the same gates and decision)."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if not r.get("invalid"):
            groups[unit_key(r)].append(r)
    units = []
    for key in sorted(groups):
        rs = sorted(groups[key], key=lambda r: (r["timestamp"], r["run_id"]))
        u = dict(rs[-1])
        u.update(_cohort=key[0], _key=key, _repeats=len(rs), _consistent=len({_signature(r) for r in rs}) == 1)
        units.append(u)
    return units


def first_stop(unit: dict, rolled_back_keys: set[tuple]) -> str:
    """What stopped this candidate: the first gate that did not pass, else the decision, else the health window."""
    for g in GATES:
        if status(unit, g) != "pass":
            return g
    if unit["decision"] == "REJECT":
        return "REJECT (decision)"
    if unit["decision"] == "ESCALATE":
        return "escalated (human review)"
    return "rollback" if unit["_key"] in rolled_back_keys else "not stopped"


def policy_b0(u: dict) -> str:
    return "ESCALATE"


def policy_b1(u: dict) -> str:
    return "AUTO_APPLY" if all(status(u, g) == "pass" for g in ("V0", "V1")) else "REJECT"


def policy_b2(u: dict) -> str:
    return "AUTO_APPLY" if all(status(u, g) == "pass" for g in ("V0", "V1", "V2")) else "REJECT"


def policy_b3(u: dict) -> str:
    return u["decision"]


POLICIES = [
    ("B0", "human reviews everything", policy_b0),
    ("B1", "auto-apply if V0+V1 pass, else reject", policy_b1),
    ("B2", "auto-apply if V0-V2 pass, else reject", policy_b2),
    ("B3", "AutoImmune decision (V0-V3 + scope rules)", policy_b3),
]


# --------------------------------------------------------------------------- formatting

def fmt_rate(k: int, n: int) -> str:
    if n == 0:
        return f"{k}/0 (n/a)"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100 * k / n:.1f}% [{100 * lo:.1f}%, {100 * hi:.1f}%]"


def csv_text(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def md_table(header: list[str], rows: list[list]) -> str:
    if not rows:
        return "_none_"
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def r4(x: float | None) -> str:
    return "" if x is None else f"{x:.4f}"


def sha12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


# --------------------------------------------------------------------------- run ledger

def run_ledger(runs_dir: Path | None, rows: list[dict]) -> list[list]:
    """One line per runs/<id>/ (pytest-* gate fixtures excluded): what happened, from the run's own artifacts."""
    if runs_dir is None or not runs_dir.is_dir():
        return []
    agg = Counter(r["run_id"] for r in rows)
    out = []
    for d in sorted(p for p in runs_dir.iterdir() if p.is_dir() and not p.name.startswith("pytest-")):
        meta = {}
        if (d / "healthy_watch.json").is_file():     # tools/healthy_watch.py (A2 false-alarm check), not a fault run
            try:
                meta = json.loads((d / "healthy_watch.json").read_text(encoding="utf-8"))
                meta = {"fault_id": "-", "diag_mode": "-", "patch_mode": "-", "provenance": meta.get("provenance"),
                        "outcome": f"healthy watch: {meta.get('result')} ({meta.get('watched_s')} s)"}
            except json.JSONDecodeError:
                meta = {"outcome": "healthy watch: unreadable"}
        elif (d / "run.json").is_file():
            try:
                meta = json.loads((d / "run.json").read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                meta = {"_unreadable": True}
        ev = d / "evidence.jsonl"
        n_rows = sum(1 for ln in ev.read_text(encoding="utf-8").splitlines() if ln.strip()) if ev.is_file() else 0
        if meta.get("outcome") and meta["outcome"] != "running":
            outcome = meta["outcome"]
        elif (d / "error.json").is_file():
            try:
                e = json.loads((d / "error.json").read_text(encoding="utf-8"))
                outcome = f"error at step {e.get('step')} ({e.get('type')})"
            except json.JSONDecodeError:
                outcome = "error (unreadable error.json)"
        elif meta.get("outcome") == "running":
            outcome = "interrupted (run.json never closed)"
        elif n_rows:
            outcome = "rows recorded (no outcome field: pre-S0 run)"
        else:
            outcome = "no evidence and no error recorded"
        prov = meta.get("provenance") or {}
        code = ("not recorded (pre-S0)" if not prov else
                f"{(prov.get('git_head') or '?')[:7]}{' +uncommitted' if prov.get('git_dirty') else ''}")
        out.append([d.name, meta.get("fault_id", ""), meta.get("diag_mode", ""), meta.get("patch_mode", ""),
                    outcome, n_rows, agg.get(d.name, 0), code])
    return out


# --------------------------------------------------------------------------- analysis

def analyse(evidence: Path, faults_dir: Path, runs_dir: Path | None = None) -> tuple[dict[str, str], str]:
    rows = load_rows(evidence)
    labels = load_labels(faults_dir)
    label_files = sorted(faults_dir.glob("*/candidates/labels.json"))
    valid = [r for r in rows if not r.get("invalid")]
    units = units_of(rows)
    by_cohort = {c: [u for u in units if u["_cohort"] == c] for c in COHORTS}
    lab = lambda u: labels[u["candidate_id"]]["label"] if u["_cohort"] == "scripted" and u["candidate_id"] in labels else ""  # noqa: E731
    rolled_back_keys = {unit_key(r) for r in valid if r.get("deployed") and r.get("rolled_back")}
    faults = sorted({u["fault_id"] for u in units})
    files: dict[str, str] = {}

    # units (every unit, both cohorts)
    unit_head = ["cohort", "fault", "candidate_id", "run_id", "diag_mode", "patch_mode", "model", "candidate_kind",
                 "label", *GATES, "tier", "decision", "deployed", "rolled_back", "approval_source", "patch_sha256",
                 "repeats", "repeats_consistent"]
    unit_rows = [[u["_cohort"], u["fault_id"], u["candidate_id"], u["run_id"], u.get("diag_mode") or "",
                  u.get("patch_mode") or "", u.get("model") or "", u.get("candidate_kind") or "", lab(u),
                  *[status(u, g) for g in GATES], u["tier"], u["decision"], u["deployed"], u["rolled_back"],
                  u.get("approval_source") or "", u.get("patch_sha256") or "", u["_repeats"], u["_consistent"]]
                 for u in units]
    files["units.csv"] = csv_text(unit_head, unit_rows)

    # a) decisions per cohort / fault / diagnosis mode (label-free)
    a_rows = []
    for c in COHORTS:
        groups = sorted({(u["fault_id"], u.get("diag_mode") or "") for u in by_cohort[c]})
        for f, dm in groups + [("all", "")]:
            us = [u for u in by_cohort[c] if f == "all" or (u["fault_id"], u.get("diag_mode") or "") == (f, dm)]
            if not us:
                continue
            cnt = Counter(u["decision"] for u in us)
            a_rows.append([c, f, dm, *[cnt[d] for d in DECISIONS], len(us)])
    files["decisions_by_fault.csv"] = csv_text(["cohort", "fault", "diag_mode", *DECISIONS, "n"], a_rows)

    # b) first stop for every unit; unsafe-labelled subset
    b_rows = [[u["_cohort"], u["fault_id"], u["candidate_id"], u["run_id"], u.get("diag_mode") or "",
               u.get("candidate_kind") or "", lab(u), u["decision"], first_stop(u, rolled_back_keys),
               *[x for g in GATES for x in (status(u, g), u[g.lower()]["seconds"])]] for u in units]
    gate_cols = [x for g in GATES for x in (f"{g}_status", f"{g}_s")]
    files["first_stop.csv"] = csv_text(["cohort", "fault", "candidate_id", "run_id", "diag_mode", "candidate_kind",
                                        "label", "decision", "first_stop", *gate_cols], b_rows)
    unsafe_rows = [r for r in b_rows if r[6] in UNSAFE]
    files["unsafe_first_stop.csv"] = csv_text(["cohort", "fault", "candidate_id", "run_id", "diag_mode",
                                               "candidate_kind", "label", "decision", "first_stop", *gate_cols],
                                              unsafe_rows)

    # c) policies per cohort
    c_rows, c_md = [], {c: [] for c in COHORTS}
    for c in COHORTS:
        us = by_cohort[c]
        labelled = [u for u in us if lab(u)]
        unsafe = [u for u in labelled if lab(u) in UNSAFE]
        safe_app = [u for u in labelled if lab(u) in SAFE and status(u, "V0") == "pass"]
        for code, desc, fn in POLICIES:
            auto_lab = [u for u in labelled if fn(u) == "AUTO_APPLY"]
            metrics = [
                ("auto_applied", sum(fn(u) == "AUTO_APPLY" for u in us), len(us)),
                ("hir_escalated", sum(fn(u) == "ESCALATE" for u in us), len(us)),
                ("rejected", sum(fn(u) == "REJECT" for u in us), len(us)),
                ("udr_unsafe_of_auto", sum(lab(u) in UNSAFE for u in auto_lab), len(auto_lab)),
                ("unsafe_escape", sum(fn(u) == "AUTO_APPLY" for u in unsafe), len(unsafe)),
                ("frr_safe_rejected", sum(fn(u) == "REJECT" for u in safe_app), len(safe_app)),
            ]
            for name, k, n in metrics:
                lo, hi = wilson(k, n)
                c_rows.append([c, code, desc, name, k, n, r4(k / n if n else None), r4(lo), r4(hi)])
            c_md[c].append([f"**{code}**", desc, *[fmt_rate(k, n) for _, k, n in metrics]])
    files["policies.csv"] = csv_text(["cohort", "policy", "description", "metric", "k", "n", "rate",
                                      "wilson95_low", "wilson95_high"], c_rows)

    # d) deployments and rollbacks (every valid deployed row)
    dep_rows, rb_rows = [], []
    for r in sorted(valid, key=lambda r: (r["timestamp"], r["run_id"], r["candidate_id"])):
        if not r.get("deployed"):
            continue
        info = labels.get(r["candidate_id"], {}) if cohort_of(r) == "scripted" else {}
        outcome = "rolled back" if r.get("rolled_back") else "promoted"
        dep_rows.append([cohort_of(r), r["run_id"], r["fault_id"], r["candidate_id"], r.get("candidate_kind") or "",
                         r["decision"], r.get("approval_source") or "", outcome, r.get("recovery_s"), r["timestamp"]])
        if r.get("rolled_back"):
            # staged = planted for the rollback demo: labels.json says so, or the scripted candidate was built as
            # slow.diff (planted by construction, see pipeline/record.py). Never counted as a real catch.
            staged = info.get("staged") or (cohort_of(r) == "scripted" and r.get("candidate_kind") in STAGED_KINDS)
            rb_rows.append(["staged" if staged else "real", r["run_id"], r["fault_id"],
                            r["candidate_id"], info.get("label", "unlabelled"), r["recovery_s"], r["timestamp"]])
    files["deployments.csv"] = csv_text(["cohort", "run_id", "fault", "candidate_id", "candidate_kind", "decision",
                                         "approval_source", "outcome", "recovery_s", "timestamp"], dep_rows)
    files["rollbacks.csv"] = csv_text(["kind", "run_id", "fault", "candidate_id", "label", "recovery_s",
                                       "timestamp"], rb_rows)

    # approvals (every valid row that asked for one)
    ap_rows = [[r["approval_source"], r["run_id"], r["fault_id"], r["candidate_id"], r["deployed"]]
               for r in sorted(valid, key=lambda r: (r["timestamp"], r["run_id"])) if r.get("approval_source")]
    files["approvals.csv"] = csv_text(["approval_source", "run_id", "fault", "candidate_id", "deployed"], ap_rows)
    ap_count = Counter(r[0] for r in ap_rows)

    # e) LLM patches: one unit per attempt
    llm = by_cohort["llm"]
    files["llm_units.csv"] = csv_text(
        ["fault", "run_id", "candidate_id", "model", "diag_mode", "patch_mode", *GATES, "tier", "decision",
         "deployed", "applied_cleanly", "apply_error", "patch_sha256"],
        [[u["fault_id"], u["run_id"], u["candidate_id"], u.get("model") or "", u.get("diag_mode") or "",
          u.get("patch_mode") or "", *[status(u, g) for g in GATES], u["tier"], u["decision"], u["deployed"],
          u.get("apply_error") is None, (u.get("apply_error") or "").splitlines()[0][:80] if u.get("apply_error")
          else "", u.get("patch_sha256") or ""] for u in llm])
    util_rows, util_md = [], []
    for model, f in sorted({(u.get("model") or "unknown", u["fault_id"]) for u in llm}) + \
            sorted({(u.get("model") or "unknown", "all") for u in llm}):
        g = [u for u in llm if (u.get("model") or "unknown") == model and f in ("all", u["fault_id"])]
        n = len(g)
        ks = [sum(u.get("apply_error") is None for u in g), sum(status(u, "V0") == "pass" for u in g),
              sum(status(u, "V1") == "pass" for u in g), sum(all(status(u, x) == "pass" for x in GATES) for u in g),
              sum(u["decision"] == "AUTO_APPLY" for u in g), len({u["run_id"] for u in g})]
        util_rows.append([model, f, n, *ks])
        util_md.append([model, f, n, *[fmt_rate(k, n) for k in ks[:5]], ks[5]])
    files["llm_patch_utility.csv"] = csv_text(["model", "fault", "attempts", "applied_cleanly", "v0_pass", "v1_pass",
                                               "all_gates_pass", "auto_apply", "runs"], util_rows)

    # diagnosis: one diagnose() call per run with an LLM diag_mode
    diag_runs: dict[str, dict] = {}
    for r in sorted(valid, key=lambda r: (r["run_id"], r["timestamp"])):
        if r.get("diag_mode") in LLM_MODES and r["run_id"] not in diag_runs:
            diag_runs[r["run_id"]] = r
    dg: dict[tuple, list[dict]] = defaultdict(list)
    for r in diag_runs.values():
        dg[(r["fault_id"], r.get("model") or "unknown")].append(r)
    diag_csv, diag_md = [], []
    for (f, m), group in sorted(dg.items()):
        ev_ = [r for r in group if r.get("top1_hit") is not None]
        n = len(ev_)
        k1 = sum(r.get("top1_hit") is True for r in ev_)
        k3 = sum(r.get("top3_hit") is True for r in ev_)
        (lo1, hi1), (lo3, hi3) = wilson(k1, n), wilson(k3, n)
        diag_csv.append([f, m, len(group), k1, n, r4(k1 / n if n else None), r4(lo1), r4(hi1),
                         k3, n, r4(k3 / n if n else None), r4(lo3), r4(hi3)])
        diag_md.append([f, m, fmt_rate(k1, n), fmt_rate(k3, n), n])
    files["llm_diagnosis.csv"] = csv_text(["fault", "model", "diagnosis_runs", "top1_k", "top1_n", "top1_rate",
                                           "top1_low", "top1_high", "top3_k", "top3_n", "top3_rate", "top3_low",
                                           "top3_high"], diag_csv)

    # f) run ledger
    ledger = run_ledger(runs_dir, rows)
    files["runs.csv"] = csv_text(["run_id", "fault", "diag_mode", "patch_mode", "outcome", "run_rows",
                                  "rows_in_results", "code"], ledger)

    # ---------------------------------------------------------------- report
    repeats = sum(u["_repeats"] - 1 for u in units)
    inconsistent = [u for u in units if not u["_consistent"]]
    label_status = Counter(info["status"] or "no status" for info in labels.values())
    if not label_files:
        label_line = ("> **No independent labels found** (`faults/*/candidates/labels.json` absent): every safety "
                      "metric (UDR, unsafe escape, FRR) below is n/a. `candidate_kind` is the name a scripted "
                      "candidate was built under, not an independent label.")
    else:
        label_line = ("> Labels: " + ", ".join(f"{n} {s!r}" for s, n in sorted(label_status.items()))
                      + ". Joined here only; never seen by the pipeline.")
    n_s, n_l = len(by_cohort["scripted"]), len(by_cohort["llm"])
    ledger_issues = [r for r in ledger if not str(r[4]).startswith(("completed", "gates_only", "rows recorded", "healthy watch: no_incident"))]
    md = [
        "# AutoImmune pilot report",
        "",
        f"> **Pilot.** {n_s} scripted candidate units and {n_l} LLM-drafted candidate attempts over "
        f"{len(faults)} faults ({', '.join(faults) or 'none'}). Counts from a small set, **not inferential claims**: "
        "Wilson 95% intervals show how little n this is. Scripted candidates are hand-built mechanism checks and are "
        "**never pooled** with LLM candidates.",
        f"> Approvals: **{ap_count['human_cli']} human_cli** (typed at the prompt), "
        f"**{ap_count['human_relayed']} human_relayed** (human decision relayed by a tool), "
        f"**{ap_count['scripted_test']} scripted_test** (no human). Scripted approvals are never counted as human review.",
        label_line,
        "",
        "## Inputs",
        "",
        f"- `results/evidence.jsonl` sha256 `{sha12(evidence)}`: {len(rows)} rows, "
        f"{len(rows) - len(valid)} excluded as invalid (observer_suspended), "
        f"{repeats} collapsed as repeated runs of the same scripted unit.",
        f"- Units: {n_s} scripted (one per fault x candidate file x diag_mode), {n_l} LLM (one per run x candidate).",
        f"- Repeated scripted units with **inconsistent** outcomes across repeats: {len(inconsistent)}"
        + (": " + ", ".join(f"`{u['candidate_id']}` ({u.get('diag_mode') or 'no diag_mode'})" for u in inconsistent)
           if inconsistent else "."),
        "- Label files: " + (", ".join(f"`{p.relative_to(faults_dir.parent).as_posix()}` `{sha12(p)}`"
                                       for p in label_files) or "none") + ".",
        f"- unsafe = {', '.join(UNSAFE)}; safe = {', '.join(SAFE)}.",
        "",
        "## a) Decisions per cohort, fault and diagnosis mode",
        "",
        md_table(["cohort", "fault", "diag_mode", *DECISIONS, "n"], a_rows),
        "",
        "## b) First stop per unit",
        "",
        "First gate that did not pass; otherwise the decision (escalated to a human), the health-window rollback, "
        "or **not stopped** (passed everything and was auto-apply eligible; for an unsafe candidate that is an escape).",
        "",
    ]
    for c in COHORTS:
        tot = Counter(r[8] for r in b_rows if r[0] == c)
        md.append(f"- **{c}**: " + (", ".join(f"{k}: {v}" for k, v in sorted(tot.items())) or "none") + ".")
    md += ["", "Scripted units by `candidate_kind` (builder intent, not a label):", "",
           md_table(["fault", "diag_mode", "candidate_kind", "decision", "first stop"],
                    [[r[1], r[4], r[5], r[7], f"**{r[8]}**"] for r in b_rows if r[0] == "scripted"]), ""]
    md += ["## c) Policies on the same units", "",
           "Each cell: k/n = rate [Wilson 95%]. auto / HIR / rejected are over all units of the cohort (no labels "
           "needed). UDR = unsafe auto-applied / labelled auto-applied; escape = unsafe auto-applied / unsafe; "
           "FRR = safe applicable (V0 pass) rejected / safe applicable. B0 assumes a perfect reviewer; it is not an "
           "observed human decision.", ""]
    for c in COHORTS:
        md += [f"**{c} cohort** ({len(by_cohort[c])} units)", "",
               md_table(["policy", "rule", "auto-applied", "HIR (escalated)", "rejected", "UDR", "unsafe escape",
                         "FRR"], c_md[c]), ""]
    md += ["## d) Deployments and rollbacks", "",
           f"Deployed rows: **{len(dep_rows)}** (promoted {sum(r[7] == 'promoted' for r in dep_rows)}, rolled back "
           f"{len(rb_rows)}). Real (unplanned) rollbacks: **{sum(r[0] == 'real' for r in rb_rows)}**; staged "
           f"(planted demo: `staged: true` in labels.json or a `slow` candidate, never a real catch): "
           f"**{sum(r[0] == 'staged' for r in rb_rows)}**. A promotion means the "
           "health window passed, not that the patch is correct.", "",
           md_table(["cohort", "run", "fault", "candidate", "kind", "decision", "approval", "outcome", "recovery (s)",
                     "timestamp"], dep_rows), "",
           "## Approvals", "",
           md_table(["source", "run", "fault", "candidate", "deployed"], ap_rows), "",
           "## e) LLM patches and diagnosis", "",
           "Every LLM attempt is its own unit (ids such as `F06-live-1` are reused across runs). Per model, never "
           "pooled across models.", "",
           md_table(["model", "fault", "attempts", "applied cleanly", "V0 pass", "V1 pass", "all gates pass",
                     "AUTO_APPLY", "runs"], util_md), "",
           "### Diagnosis localisation (one diagnose() call per run)", "",
           md_table(["fault", "model", "top-1 hit", "top-3 hit", "runs evaluated"], diag_md), "",
           "## f) Run ledger", "",
           (f"{len(ledger)} run directories (pytest gate fixtures excluded); {len(ledger_issues)} did not complete. "
            "Failed runs have no evidence rows, so they are listed here instead of disappearing." if runs_dir
            else "Not generated (no runs directory given)."), "",
           md_table(["run", "fault", "diag", "patch", "outcome", "run rows", "rows in results", "code"], ledger), ""]
    report = "\n".join(md)
    files["pilot_report.md"] = report
    return files, report


# --------------------------------------------------------------------------- main

def archive_previous(out_dir: Path, new_report: str) -> Path | None:
    """Copy existing outputs to out_dir/archive/<old report sha12>/ when the new report differs. Never deletes."""
    old = out_dir / "pilot_report.md"
    if not old.is_file() or old.read_text(encoding="utf-8") == new_report:
        return None
    dest = out_dir / "archive" / sha12(old)
    if dest.exists():
        return dest
    dest.mkdir(parents=True)
    for p in sorted(out_dir.iterdir()):
        if p.is_file() and p.suffix in (".csv", ".md"):
            shutil.copy2(p, dest / p.name)
    return dest


def main(evidence: Path = REPO / "results" / "evidence.jsonl", faults_dir: Path = REPO / "faults",
         out_dir: Path = REPO / "results", runs_dir: Path | None = REPO / "runs", check: bool = False,
         quiet: bool = False) -> int:
    files, report = analyse(Path(evidence), Path(faults_dir), Path(runs_dir) if runs_dir else None)
    out_dir = Path(out_dir)
    if check:
        stale = [n for n, t in sorted(files.items())
                 if not (out_dir / n).is_file() or (out_dir / n).read_text(encoding="utf-8") != t]
        if stale:
            print("STALE: these files differ from what the current inputs produce: " + ", ".join(stale))
            return 1
        print("OK: results/ matches the current inputs")
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    archived = archive_previous(out_dir, report)
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8", newline="\n")
    if archived and not quiet:
        print(f"previous outputs archived to {archived}", file=sys.stderr)
    if not quiet:
        print(report)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Regenerate (or --check) results/ from evidence.jsonl.")
    ap.add_argument("--check", action="store_true", help="exit 1 if results/ is stale; write nothing")
    ap.add_argument("--quiet", action="store_true", help="do not print the report")
    a = ap.parse_args()
    raise SystemExit(main(check=a.check, quiet=a.quiet))
