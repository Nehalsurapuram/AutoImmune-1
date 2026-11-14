"""Empirical risk estimation: P(unsafe | recorded validation evidence).

    python -m tools.risk_model                 # writes results/risk/
    python -m tools.risk_model --out some/dir

Research question (RQ2 extension): can the probability that a candidate patch is unsafe be estimated from the
validation evidence the pipeline actually records, and how reliable is that estimate on data it was not fitted on?

Offline analysis only. It does not change the decision engine, which stays a rule-based tier (AGENTS.md), and
its output is never used to deploy anything. Method write-up: docs/research/RISK_AND_COST_METHODS.md.

Data
- Research units come from analyse.units_of (same exclusions as every other result). One observation per
  DISTINCT judged patch: units collapsed by patch identity (scripted: content-hash candidate_id; live:
  patch_sha256). The same diff evaluated under two diagnosis modes or in several runs is one observation.
- Label: offline oracle (faults/*/candidates/labels.json for scripted, results/oracle_report.jsonl for live).
  unsafe = analyse.UNSAFE, safe = analyse.SAFE. Patches labelled invalid/unknown or unlabelled are excluded and
  counted; they are never treated as safe.
- Cohorts are estimated and reported separately. Pooled data is only ever a training set, and its scores are
  still reported per cohort.

Evidence groups (empirical estimator), by gate outcome only
  v0_failed          V0 did not pass
  later_gate_failed  V0 passed, V1, V2 or V3 did not pass
  all_passed         V0-V3 all passed (the decision-relevant case: what the gates let through)
  auto_apply         all_passed and the rule engine decided AUTO_APPLY (a subset of all_passed)
A group with fewer than MIN_GROUP_N labelled distinct patches is reported as counts only, with no estimate.

Features (logistic model; fixed before any results were looked at; all pre-deploy evidence the engine uses)
  gate_fail, new_findings, log_diff_lines, multi_file, sensitive_path
Deliberately NOT used: top1_hit / top3_hit (computed from the known fault location), oracle_localisation,
deployed / rolled_back / recovery_s (post-deploy), the rule tier and decision, labels or hidden-test results.

Models: base_rate, gate_table (rate within the training patches sharing gate_fail), logistic (L2, Newton).
Evaluation (every scored probability is out of sample): lofo_scripted, scripted_to_llm, lofo_pooled.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

from analyse import (GATES, REPO, SAFE, UNSAFE, eligible_rows, load_analysis_exclusions, load_labels,
                     load_oracle_live, load_rows, status, units_of, wilson)
from pipeline.decide import _sensitive_match

SCHEMA_VERSION = 1
MODEL_VERSION = "logistic-l2-v1"
FEATURES = ("gate_fail", "new_findings", "log_diff_lines", "multi_file", "sensitive_path")
MODELS = ("base_rate", "gate_table", "logistic")
COHORTS = ("scripted", "llm")
L2 = 1.0
EPS = 1e-6
MIN_GROUP_N = 5
GROUPS = (
    ("v0_failed", "V0 failed"),
    ("later_gate_failed", "Passed V0, failed V1, V2 or V3"),
    ("all_passed", "Passed V0-V3"),
    ("auto_apply", "Passed V0-V3 and decided AUTO_APPLY"),
)
HEADLINE_GROUP = "all_passed"
NOT_USED = (
    ("diagnosis_agreement", "Diagnosis agreement",
     "Not recorded: every run used one diagnosis sample (diag_samples = 1), so samples_disagree is empty."),
    ("diagnosed_file_alignment", "Diagnosed-file alignment",
     "Not used: in rule mode the diagnosed file comes from fault.json (oracle localisation), so it would leak."),
    ("provider_model", "Provider or model",
     "Not a feature: cohorts are estimated separately; model-level samples are too small to split further."),
    ("gate_durations", "Gate durations",
     "Not used: they depend on machine load as much as on the patch."),
    ("rule_tier", "Rule-based risk tier and decision",
     "Not used: the tier is derived from the same evidence and is not a probability."),
)


# --------------------------------------------------------------------------- dataset

def features_of(unit: dict, sensitive_paths: list[str]) -> dict[str, float]:
    files = unit.get("files_touched") or []
    findings = (unit.get("new_findings") or {}).get("count") or 0
    return {
        "gate_fail": float(any(status(unit, g) != "pass" for g in GATES)),
        "new_findings": float(findings > 0),
        "log_diff_lines": math.log1p(unit.get("diff_lines") or 0),
        "multi_file": float(len(files) > 1),
        "sensitive_path": float(any(_sensitive_match(f, sensitive_paths) for f in files)),
    }


def group_of(unit: dict) -> str:
    st = {g: status(unit, g) for g in GATES}
    if st["V0"] != "pass":
        return "v0_failed"
    if any(st[g] != "pass" for g in GATES[1:]):
        return "later_gate_failed"
    return "all_passed"


def in_group(item: dict, gid: str) -> bool:
    if gid == "auto_apply":
        return item["group"] == "all_passed" and item["decision"] == "AUTO_APPLY"
    return item["group"] == gid


def patch_id(unit: dict) -> str:
    if unit["_cohort"] == "scripted":
        return unit["candidate_id"]
    return unit.get("patch_sha256") or f"{unit['run_id']}|{unit['candidate_id']}"


def build_dataset(evidence: Path, faults_dir: Path, config: dict) -> tuple[list[dict], dict]:
    """Distinct judged patches with features and label; info holds every unit and the counting funnel."""
    rows = load_rows(evidence)
    excluded_runs = set(load_analysis_exclusions(evidence))
    units = units_of(rows, excluded_runs)
    labels = load_labels(faults_dir)
    oracle = load_oracle_live(evidence.parent / "oracle_report.jsonl")
    excluded: Counter = Counter()
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for u in units:
        if u["_cohort"] == "scripted":
            label = labels.get(u["candidate_id"], {}).get("label", "")
        else:
            label = oracle.get((u["run_id"], u["candidate_id"]), "")
        u["_label"] = label
        u["_patch"] = patch_id(u)
        u["_group"] = group_of(u)
        if label not in UNSAFE and label not in SAFE:
            excluded[(u["_cohort"], label or "unlabelled")] += 1
            continue
        groups[(u["_cohort"], u["_patch"])].append(u)

    data, conflicts = [], 0
    for (cohort, pid), members in sorted(groups.items()):
        members.sort(key=lambda m: (m["timestamp"], m["run_id"]))
        u = members[-1]
        if len({m["_label"] in UNSAFE for m in members}) > 1:
            conflicts += 1
        data.append({
            "cohort": cohort,
            "fault": u["fault_id"],
            "patch_id": pid,
            "candidate_id": u["candidate_id"],
            "run_id": u["run_id"],
            "units": len(members),
            "label": u["_label"],
            "unsafe": int(u["_label"] in UNSAFE),
            "gates": "/".join(status(u, g) for g in GATES),
            "statuses": {g: status(u, g) for g in GATES},
            "seconds": {g: u[g.lower()].get("seconds") for g in GATES},
            "group": u["_group"],
            "decision": u["decision"],
            "diff_lines": u.get("diff_lines"),
            "x": features_of(u, config["sensitive_paths"]),
        })

    eligible = eligible_rows(rows, excluded_runs)
    funnel = {c: {
        "raw_rows": sum(1 for r in rows if _cohort_of_row(r) == c),
        "eligible_rows": sum(1 for r in eligible if _cohort_of_row(r) == c),
        "research_units": sum(1 for u in units if u["_cohort"] == c),
        "labelled_units": sum(1 for u in units if u["_cohort"] == c and (u["_label"] in UNSAFE or u["_label"] in SAFE)),
        "distinct_judged_patches": sum(1 for d in data if d["cohort"] == c),
        "distinct_unsafe": sum(d["unsafe"] for d in data if d["cohort"] == c),
        "excluded_units": {lab: n for (co, lab), n in sorted(excluded.items()) if co == c},
    } for c in COHORTS}
    return data, {"excluded": excluded, "label_conflicts": conflicts, "units": units, "funnel": funnel,
                  "excluded_run_ids": sorted(excluded_runs)}


def _cohort_of_row(row: dict) -> str:
    return "llm" if row.get("patch_mode") in ("live", "replay") else "scripted"


# --------------------------------------------------------------------------- models

def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting (a is small and, with L2, positive definite)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        if abs(m[c][c]) < 1e-12:
            raise ValueError("singular system")
        for r in range(c + 1, n):
            f = m[r][c] / m[c][c]
            for k in range(c, n + 1):
                m[r][k] -= f * m[c][k]
    out = [0.0] * n
    for r in range(n - 1, -1, -1):
        out[r] = (m[r][n] - sum(m[r][k] * out[k] for k in range(r + 1, n))) / m[r][r]
    return out


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


class Logistic:
    """L2-regularised logistic regression on standardised features; intercept unpenalised."""

    def __init__(self, l2: float = L2):
        self.l2 = l2
        self.mean: list[float] = []
        self.sd: list[float] = []
        self.w: list[float] = []

    def _design(self, xs: list[list[float]]) -> list[list[float]]:
        return [[1.0] + [(v - m) / s for v, m, s in zip(x, self.mean, self.sd)] for x in xs]

    def fit(self, xs: list[list[float]], ys: list[int], iters: int = 100) -> "Logistic":
        k = len(xs[0])
        self.mean = [sum(x[j] for x in xs) / len(xs) for j in range(k)]
        self.sd = []
        for j in range(k):
            var = sum((x[j] - self.mean[j]) ** 2 for x in xs) / len(xs)
            self.sd.append(math.sqrt(var) if var > 1e-12 else 1.0)   # constant feature: leave unscaled (it is 0)
        d = self._design(xs)
        w = [0.0] * (k + 1)
        for _ in range(iters):
            p = [_sigmoid(sum(wi * xi for wi, xi in zip(w, row))) for row in d]
            grad = [sum((p[i] - ys[i]) * d[i][j] for i in range(len(d))) + (self.l2 * w[j] if j else 0.0)
                    for j in range(k + 1)]
            hess = [[sum(p[i] * (1 - p[i]) * d[i][a] * d[i][b] for i in range(len(d)))
                     + (self.l2 if a == b and a else 0.0) for b in range(k + 1)] for a in range(k + 1)]
            hess[0][0] += 1e-9   # keeps the intercept solvable if every label is the same
            step = _solve(hess, grad)
            w = [wi - si for wi, si in zip(w, step)]
            if max(abs(s) for s in step) < 1e-10:
                break
        self.w = w
        return self

    def predict(self, xs: list[list[float]]) -> list[float]:
        return [_sigmoid(sum(wi * xi for wi, xi in zip(self.w, row))) for row in self._design(xs)]


def _vec(item: dict) -> list[float]:
    return [item["x"][f] for f in FEATURES]


def laplace(k: int, n: int) -> float:
    return (k + 1) / (n + 2)


def fit_predict(train: list[dict], test: list[dict]) -> dict[str, list[float]]:
    base = laplace(sum(t["unsafe"] for t in train), len(train))
    by_gate: dict[float, list[int]] = defaultdict(list)
    for t in train:
        by_gate[t["x"]["gate_fail"]].append(t["unsafe"])

    def gate_p(item: dict) -> float:
        ys = by_gate.get(item["x"]["gate_fail"])
        return laplace(sum(ys), len(ys)) if ys else base

    model = Logistic().fit([_vec(t) for t in train], [t["unsafe"] for t in train])
    return {
        "base_rate": [base] * len(test),
        "gate_table": [gate_p(t) for t in test],
        "logistic": model.predict([_vec(t) for t in test]),
    }


# --------------------------------------------------------------------------- metrics

def brier(p: list[float], y: list[int]) -> float:
    return sum((pi - yi) ** 2 for pi, yi in zip(p, y)) / len(y)


def log_loss(p: list[float], y: list[int]) -> float:
    return -sum(yi * math.log(max(pi, EPS)) + (1 - yi) * math.log(max(1 - pi, EPS)) for pi, yi in zip(p, y)) / len(y)


def auc(p: list[float], y: list[int]) -> float | None:
    """Probability a random unsafe patch scores above a random safe one (ties count half). None if one class."""
    pos = [pi for pi, yi in zip(p, y) if yi]
    neg = [pi for pi, yi in zip(p, y) if not yi]
    if not pos or not neg:
        return None
    wins = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


def reliability(p: list[float], y: list[int], edges=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0)) -> list[tuple]:
    out = []
    for lo, hi in zip(edges, edges[1:]):
        idx = [i for i, pi in enumerate(p) if lo <= pi < hi or (hi == edges[-1] and pi == hi)]
        if idx:
            out.append((lo, hi, len(idx), sum(p[i] for i in idx) / len(idx), sum(y[i] for i in idx) / len(idx)))
    return out


def score(p: list[float], y: list[int], base_p: list[float]) -> dict:
    b, b0 = brier(p, y), brier(base_p, y)
    return {"n": len(y), "unsafe": sum(y), "brier": b, "brier_skill": (1 - b / b0) if b0 > 0 else None,
            "log_loss": log_loss(p, y), "auc": auc(p, y)}


# --------------------------------------------------------------------------- estimates and evaluation

def group_estimate(items: list[dict], gid: str, min_n: int = MIN_GROUP_N) -> dict:
    """Empirical P(unsafe | group) for one cohort's items. No estimate below min_n; nothing invented at n = 0."""
    s = [d for d in items if in_group(d, gid)]
    k, n = sum(d["unsafe"] for d in s), len(s)
    if n == 0:
        return {"group": gid, "unsafe": 0, "labelled": 0, "status": "no_labelled_support",
                "estimate": None, "ci95_low": None, "ci95_high": None}
    if n < min_n:
        return {"group": gid, "unsafe": k, "labelled": n, "status": "insufficient",
                "estimate": None, "ci95_low": None, "ci95_high": None}
    lo, hi = wilson(k, n)
    return {"group": gid, "unsafe": k, "labelled": n, "status": "ok", "estimate": k / n,
            "ci95_low": lo, "ci95_high": hi}


def group_feature_summary(data: list[dict]) -> list[dict]:
    """Observed evidence values inside each cohort's group (distinct judged patches)."""
    out = []
    for c in COHORTS:
        for gid, _ in GROUPS:
            s = [d for d in data if d["cohort"] == c and in_group(d, gid)]
            lines = sorted(d["diff_lines"] for d in s if d.get("diff_lines") is not None)
            out.append({
                "cohort": c, "group": gid, "n": len(s),
                "new_findings": sum(d["x"]["new_findings"] == 1 for d in s),
                "multi_file": sum(d["x"]["multi_file"] == 1 for d in s),
                "sensitive_path": sum(d["x"]["sensitive_path"] == 1 for d in s),
                "diff_lines_median": statistics.median(lines) if lines else None,
                "diff_lines_max": lines[-1] if lines else None,
            })
    return out


def profile_rates(data: list[dict]) -> list[dict]:
    return [{"cohort": c, **group_estimate([d for d in data if d["cohort"] == c], gid)}
            for c in COHORTS for gid, _ in GROUPS]


def _key(item: dict) -> str:
    return item["cohort"] + "|" + item["patch_id"]


def lofo(data: list[dict]) -> dict[str, dict[str, float]]:
    """Leave-one-fault-out: key -> model -> out-of-fold probability. A held-out fault never trains."""
    out: dict[str, dict[str, float]] = {}
    for fault in sorted({d["fault"] for d in data}):
        train = [d for d in data if d["fault"] != fault]
        test = [d for d in data if d["fault"] == fault]
        if not train:
            continue
        preds = fit_predict(train, test)
        for i, t in enumerate(test):
            out[_key(t)] = {m: preds[m][i] for m in MODELS}
    return out


def evaluate(data: list[dict]) -> tuple[list[dict], dict[str, dict[str, dict[str, float]]]]:
    scripted = [d for d in data if d["cohort"] == "scripted"]
    llm = [d for d in data if d["cohort"] == "llm"]
    oof = {"lofo_scripted": lofo(scripted), "lofo_pooled": lofo(data)}
    if scripted and llm:
        preds = fit_predict(scripted, llm)
        oof["scripted_to_llm"] = {_key(t): {m: preds[m][i] for m in MODELS} for i, t in enumerate(llm)}
    rows = []
    for name, cohorts in (("lofo_scripted", ("scripted",)), ("scripted_to_llm", ("llm",)),
                          ("lofo_pooled", ("scripted", "llm"))):
        for c in cohorts:
            items = [d for d in data if d["cohort"] == c and _key(d) in oof.get(name, {})]
            if not items:
                continue
            y = [d["unsafe"] for d in items]
            base = [oof[name][_key(d)]["base_rate"] for d in items]
            for m in MODELS:
                p = [oof[name][_key(d)][m] for d in items]
                rows.append({"evaluation": name, "cohort": c, "model": m, **score(p, y, base)})
    return rows, oof


def allpass_separation(data: list[dict], oof: dict) -> list[dict]:
    """Among patches that passed every gate: does the logistic score rank unsafe above safe out of sample?"""
    out = []
    for name, c in (("lofo_scripted", "scripted"), ("scripted_to_llm", "llm"), ("lofo_pooled", "scripted"),
                    ("lofo_pooled", "llm")):
        items = [d for d in data if d["cohort"] == c and d["group"] == "all_passed" and _key(d) in oof.get(name, {})]
        y = [d["unsafe"] for d in items]
        out.append({"evaluation": name, "cohort": c, "n": len(items), "unsafe": sum(y),
                    "auc": auc([oof[name][_key(d)]["logistic"] for d in items], y) if items else None})
    return out


# --------------------------------------------------------------------------- candidate explorer

def candidate_entries(units: list[dict], data: list[dict], profiles: list[dict], oof_pooled: dict,
                      sensitive_paths: list[str]) -> list[dict]:
    """Every research unit, with its evidence group's cohort rate and (judged patches only) its model score.

    The group rate is a rate for the group, never a probability specific to the candidate. The model score is
    the out-of-fold logistic prediction and exists only for judged patches; other candidates get None.
    """
    prof = {(p["cohort"], p["group"]): p for p in profiles}
    judged = {_key(d) for d in data}
    out = []
    for u in units:
        key = u["_cohort"] + "|" + u["_patch"]
        g = prof[(u["_cohort"], u["_group"])]
        is_judged = key in judged
        model_p = oof_pooled.get(key, {}).get("logistic") if is_judged else None
        out.append({
            "cohort": u["_cohort"],
            "fault_id": u["fault_id"],
            "candidate_id": u["candidate_id"],
            "run_id": u["run_id"],
            "model": u.get("model") or None,
            "diag_mode": u.get("diag_mode") or None,
            "gates": {g_: {"status": status(u, g_), "seconds": u[g_.lower()].get("seconds")} for g_ in GATES},
            "tier": u.get("tier"),
            "decision": u.get("decision"),
            "evidence_group": u["_group"],
            "group_estimate": {k: g[k] for k in ("status", "unsafe", "labelled", "estimate", "ci95_low", "ci95_high")},
            "model_probability": model_p,
            "model_probability_note": ("out-of-fold logistic prediction (leave-one-fault-out); exploratory"
                                       if model_p is not None else
                                       "not computed: this candidate has no safe/unsafe oracle label, so it is "
                                       "outside the evaluated set"),
            "feature_values": features_of(u, sensitive_paths),
            "inputs": {
                "diff_lines": u.get("diff_lines"),
                "files_touched": u.get("files_touched") or [],
                "new_findings_count": (u.get("new_findings") or {}).get("count") or 0,
                "sensitive_matches": [f for f in (u.get("files_touched") or []) if _sensitive_match(f, sensitive_paths)],
            },
            "oracle_label": u["_label"] or None,
            "judged": is_judged,
        })
    return out


# --------------------------------------------------------------------------- interpretation

def _rng(vals: list[float]) -> str:
    vals = [v for v in vals if v is not None]
    if not vals:
        return "n/a"
    return f"{min(vals):.2f}" if min(vals) == max(vals) else f"{min(vals):.2f} to {max(vals):.2f}"


def interpretation(funnel: dict, profiles: list[dict], metrics: list[dict], allpass: list[dict]) -> list[dict]:
    """Plain-language findings generated from the computed numbers, so text and figures cannot drift apart."""
    p = {(x["cohort"], x["group"]): x for x in profiles}
    ap_aucs = [a["auc"] for a in allpass if a["auc"] is not None]
    gate_skill = [m["brier_skill"] for m in metrics if m["model"] == "gate_table"]
    separates = bool(ap_aucs) and min(ap_aucs) > 0.6
    fr = {c: funnel[c] for c in COHORTS}

    def kn(c, g):
        x = p[(c, g)]
        return f"{x['unsafe']}/{x['labelled']}"

    return [
        {"topic": "measured", "text": (
            f"Gate outcomes, new Semgrep findings, diff size, files touched and sensitive paths for "
            f"{fr['scripted']['distinct_judged_patches']} distinct hand-built and {fr['llm']['distinct_judged_patches']} "
            f"distinct AI-written patches, each with an offline oracle label.")},
        {"topic": "estimated", "text": (
            "An observed unsafe rate for each gate-outcome group, with a Wilson 95% interval, and an L2 logistic "
            "model whose probabilities were scored only on faults or cohorts it was not fitted on.")},
        {"topic": "observed", "text": (
            f"Every judged patch that passed V0 and then failed a gate was unsafe (hand-built {kn('scripted', 'later_gate_failed')}, "
            f"AI {kn('llm', 'later_gate_failed')}). Of the patches that passed all four gates, hand-built "
            f"{kn('scripted', 'all_passed')} and AI {kn('llm', 'all_passed')} were unsafe. No judged patch failed V0: "
            f"V0 failures were all labelled invalid, so that group has no estimate.")},
        {"topic": "reliability", "text": (
            f"Out of sample, splitting by gate outcome improves on the base rate (Brier skill {_rng(gate_skill)}). "
            f"Among patches that passed every gate, the logistic ranking of unsafe above safe has AUC {_rng(ap_aucs)} "
            "across evaluations, where 0.5 is chance: "
            + ("a consistent separation." if separates else "no consistent separation."))},
        {"topic": "inconclusive", "text": (
            "Whether any recorded pre-deploy evidence can tell a correct patch from an incorrect one once both pass "
            f"all gates. The AI sample is {fr['llm']['distinct_judged_patches']} distinct patches; "
            ""
            + ", ".join(f"{n} AI units are {'labelled ' + lab if lab != 'unlabelled' else 'unlabelled'}"
                        for lab, n in fr["llm"]["excluded_units"].items())
            + " (neither safe nor unsafe); and the labels have not yet had the planned independent two-person "
            "review.")},
    ]


# --------------------------------------------------------------------------- outputs

def r3(x) -> str:
    return "" if x is None else f"{x:.3f}"


def _csv(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def _md(header: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def sha12(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path.is_file() else None


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def run(evidence: Path, faults_dir: Path, config_path: Path) -> dict[str, str]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data, info = build_dataset(evidence, faults_dir, config)
    metrics, oof = evaluate(data)
    profiles = profile_rates(data)
    allpass = allpass_separation(data, oof)
    full = Logistic().fit([_vec(d) for d in data], [d["unsafe"] for d in data])
    pooled = oof["lofo_pooled"]
    label_name = dict(GROUPS)

    rel_rows = []
    for c in COHORTS:
        items = [d for d in data if d["cohort"] == c and _key(d) in pooled]
        for lo, hi, n, mp, mo in reliability([pooled[_key(d)]["logistic"] for d in items],
                                             [d["unsafe"] for d in items]):
            rel_rows.append({"cohort": c, "bin_low": lo, "bin_high": hi, "n": n, "mean_predicted": mp,
                             "observed_unsafe": mo})

    sources = [evidence, evidence.parent / "oracle_report.jsonl", config_path,
               *sorted(faults_dir.glob("*/candidates/labels.json")), Path(__file__)]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "analysis": "risk_estimation",
        "analysis_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "python -m tools.risk_model",
        "methods_doc": "docs/research/RISK_AND_COST_METHODS.md",
        "unit_of_analysis": ("distinct judged patch: research units from analyse.units_of collapsed by patch "
                             "identity (scripted content hash, live patch_sha256)"),
        "label_source": {
            "scripted": "faults/*/candidates/labels.json (hand-assigned when the candidates were built)",
            "llm": "results/oracle_report.jsonl (tools/oracle.py: hidden spec tests, hidden performance test, "
                   "full existing suite, security probe)",
            "unsafe_labels": list(UNSAFE), "safe_labels": list(SAFE),
            "excluded_labels": ["invalid", "unknown", "unlabelled"],
            "independent_adjudication": "pending (docs/label_adjudication.csv has no completed rows)",
        },
        "funnel": info["funnel"],
        "excluded_run_ids": info["excluded_run_ids"],
        "label_conflicts": info["label_conflicts"],
        "min_group_n": MIN_GROUP_N,
        "min_group_n_rule": (f"A presentation rule: a group with fewer than {MIN_GROUP_N} labelled distinct patches "
                             "is shown as counts only, without a percentage or interval."),
        "groups": [{"id": g, "label": label_name[g]} for g, _ in GROUPS],
        "headline_group": HEADLINE_GROUP,
        "empirical": {
            "method": "empirical conditional unsafe rate",
            "formula": "P(unsafe | E) = N(unsafe and E) / N(labelled and E)",
            "interval": "Wilson score 95% interval for the group rate (z = 1.96)",
            "estimates": profiles,
            "group_feature_summary": group_feature_summary(data),
        },
        "model": {
            "method": "L2-regularised logistic regression",
            "model_version": MODEL_VERSION,
            "l2": L2,
            "features": list(FEATURES),
            "feature_definitions": {
                "gate_fail": "1 if any of V0-V3 did not pass (timeout and tool error are not a pass)",
                "new_findings": "1 if V3 recorded at least one new Semgrep finding",
                "log_diff_lines": "log(1 + changed lines in the diff)",
                "multi_file": "1 if the diff touches more than one file",
                "sensitive_path": "1 if the diff touches a sensitive path in config/decision.yaml",
            },
            "not_used": [{"id": i, "label": lbl, "reason": why} for i, lbl, why in NOT_USED],
            "standardisation": "each feature centred and scaled by its training-set standard deviation",
            "coefficients_all_data": {"intercept": full.w[0], **dict(zip(FEATURES, full.w[1:]))},
            "coefficients_note": ("Fitted on all judged patches of both cohorts, for interpretation only. Scored "
                                  "probabilities below never come from this fit."),
            "evaluation_method": ("leave-one-fault-out within scripted; fit on scripted, score LLM; leave-one-fault-"
                                  "out on both cohorts with scores reported per cohort"),
            "metrics": metrics,
            "reliability_lofo_pooled": rel_rows,
            "allpass_separation": allpass,
        },
        "interpretation": interpretation(info["funnel"], profiles, metrics, allpass),
        "limitations": [
            "Pilot scale: few distinct patches and few faults, so intervals are wide.",
            "Partly circular: the oracle reuses the full existing suite (V2) and a security probe that overlaps V3, "
            "so 'gate failed, therefore unsafe' is partly true by construction.",
            "The hand-built unsafe share was set by design and does not describe model-written patches.",
            "Labels have not yet had the planned independent two-person review.",
            "Group rates describe groups of patches; they are not a probability for one specific patch.",
        ],
        "candidates": candidate_entries(info["units"], data, profiles, pooled, config["sensitive_paths"]),
        "source_artifacts": [{"path": _rel(p), "sha256_12": sha12(p)} for p in sources if p.is_file()],
    }

    files: dict[str, str] = {"risk_estimation.json": json.dumps(payload, indent=2) + "\n"}
    files["risk_dataset.csv"] = _csv(
        ["cohort", "fault", "patch_id", "candidate_id", "run_id", "units", "label", "unsafe", "gates", "group",
         "decision", *FEATURES],
        [[d["cohort"], d["fault"], d["patch_id"], d["candidate_id"], d["run_id"], d["units"], d["label"],
          d["unsafe"], d["gates"], d["group"], d["decision"], *[r3(d["x"][f]) for f in FEATURES]] for d in data])
    files["risk_predictions.csv"] = _csv(
        ["cohort", "fault", "patch_id", "label", "unsafe", "decision", "oof_base_rate", "oof_gate_table",
         "oof_logistic"],
        [[d["cohort"], d["fault"], d["patch_id"], d["label"], d["unsafe"], d["decision"],
          *[r3(pooled.get(_key(d), {}).get(m)) for m in MODELS]] for d in data])
    files["risk_metrics.csv"] = _csv(
        ["evaluation", "cohort", "model", "n", "unsafe", "brier", "brier_skill", "log_loss", "auc"],
        [[r["evaluation"], r["cohort"], r["model"], r["n"], r["unsafe"], r3(r["brier"]), r3(r["brier_skill"]),
          r3(r["log_loss"]), r3(r["auc"])] for r in metrics])
    fn = info["funnel"]
    files["risk_report.md"] = "\n".join([
        "# Risk estimation: P(unsafe | validation evidence)",
        "",
        "Generated by `python -m tools.risk_model`. Offline analysis only: the decision engine is unchanged and "
        "remains a rule-based tier. Method: `docs/research/RISK_AND_COST_METHODS.md`.",
        "",
        "## Data",
        "",
        _md(["cohort", "raw rows", "eligible rows", "research units", "labelled units", "distinct judged patches",
             "distinct unsafe", "excluded units"],
            [[c, fn[c]["raw_rows"], fn[c]["eligible_rows"], fn[c]["research_units"], fn[c]["labelled_units"],
              fn[c]["distinct_judged_patches"], fn[c]["distinct_unsafe"],
              ", ".join(f"{k} {v}" for k, v in fn[c]["excluded_units"].items()) or "none"] for c in COHORTS]),
        "",
        "## 1. Observed risk by evidence group",
        "",
        f"Groups with fewer than {MIN_GROUP_N} labelled distinct patches show counts only.",
        "",
        _md(["cohort", "evidence", "unsafe", "labelled", "P(unsafe)", "95% low", "95% high", "status"],
            [[p["cohort"], label_name[p["group"]], p["unsafe"], p["labelled"], r3(p["estimate"]), r3(p["ci95_low"]),
              r3(p["ci95_high"]), p["status"]] for p in profiles]),
        "",
        "## 2. Out-of-sample accuracy and calibration",
        "",
        _md(["evaluation", "cohort", "model", "n", "unsafe", "Brier", "Brier skill", "log loss", "AUC"],
            [[r["evaluation"], r["cohort"], r["model"], r["n"], r["unsafe"], r3(r["brier"]), r3(r["brier_skill"]),
              r3(r["log_loss"]), r3(r["auc"])] for r in metrics]),
        "",
        "### Among patches that passed all four gates",
        "",
        _md(["evaluation", "cohort", "n", "unsafe", "AUC (logistic)"],
            [[a["evaluation"], a["cohort"], a["n"], a["unsafe"], r3(a["auc"])] for a in allpass]),
        "",
        "### Reliability (logistic, leave-one-fault-out, both cohorts)",
        "",
        _md(["cohort", "predicted bin", "n", "mean predicted", "observed unsafe"],
            [[r["cohort"], f"{r['bin_low']:.1f}-{r['bin_high']:.1f}", r["n"], r3(r["mean_predicted"]),
              r3(r["observed_unsafe"])] for r in rel_rows]),
        "",
        "## 3. Logistic coefficients (all judged patches; standardised; interpretation only)",
        "",
        _md(["term", "weight"], [["intercept", r3(full.w[0])]] + [[f, r3(w)] for f, w in zip(FEATURES, full.w[1:])]),
        "",
        "## Interpretation",
        "",
        *[f"- **{i['topic']}**: {i['text']}" for i in payload["interpretation"]],
        "",
        "## Limits",
        "",
        *[f"- {x}" for x in payload["limitations"]],
        "",
    ])
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Estimate P(unsafe | validation evidence) and evaluate it out of sample.")
    ap.add_argument("--evidence", type=Path, default=REPO / "results" / "evidence.jsonl")
    ap.add_argument("--faults", type=Path, default=REPO / "faults")
    ap.add_argument("--config", type=Path, default=REPO / "config" / "decision.yaml")
    ap.add_argument("--out", type=Path, default=REPO / "results" / "risk")
    args = ap.parse_args(argv)
    files = run(args.evidence, args.faults, args.config)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (args.out / name).write_text(text, encoding="utf-8")
    print(f"wrote {', '.join(sorted(files))} to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
