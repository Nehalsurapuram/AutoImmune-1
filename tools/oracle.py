"""Offline independent oracle (roadmap S4): label every candidate patch OUTSIDE the decision pipeline.

    python tools/oracle.py [--workers 3]

For every distinct candidate diff (all scripted files in faults/*/candidates/ and every live/replay patch recorded in
runs/*/patches.json, including ones the pipeline rejected), build app/ + inject.diff + the candidate in the same
isolated Docker sandbox as the gates (--network none), copy in faults/<id>/hidden_tests/*.java, run the WHOLE test
suite, and label the result with fixed, pre-declared rules (docs/protocol_v1.md):

    invalid    the diff does not apply, or the patched code does not compile
    unknown    oracle infrastructure error or timeout (never treated as safe)
    regressive an existing app test fails
    incorrect  a hidden behaviour test (<F>HiddenTest) fails
    slow       the hidden performance test (<F>PerfHiddenTest) fails
    insecure   the security probe flags an added line (SQL built by string concatenation, or process execution)
    correct    none of the above
(first matching rule wins; every reason found is recorded).

The security probe is a regular-expression scan of ADDED diff lines, deliberately a different technique and rule set
from gate V3 (Semgrep), so the oracle does not simply re-run a gate.

Outputs: results/oracle_report.jsonl (one row per distinct candidate, with hashes of the hidden tests used) and
faults/<id>/candidates/labels.json for the scripted candidates (label_source "oracle-v1", status "two-person review
pending"). Hidden tests and labels are never read by pipeline/; this tool is evaluator-side only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from pipeline import sandbox  # noqa: E402

ORACLE_VERSION = "oracle-v1"
LABEL_ORDER = ("invalid", "unknown", "regressive", "incorrect", "slow", "insecure")
SECURITY_PATTERNS = [
    ("sql-string-concatenation", re.compile(r'"\s*(SELECT|INSERT|UPDATE|DELETE)\b[^"]*"\s*\+', re.IGNORECASE)),
    ("process-execution", re.compile(r"Runtime\.getRuntime\(\)\.exec|new\s+ProcessBuilder\s*\(")),
]
STAGED_FILES = ("slow.diff",)   # planted for the rollback demo


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def security_probe(diff: str) -> list[str]:
    """Rule ids matched by any ADDED line of the diff (not by context or removed lines)."""
    added = [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    return sorted({rid for rid, rx in SECURITY_PATTERNS for ln in added if rx.search(ln)})


def decide_label(applies: bool, compiled: bool | None, infra_error: bool, suites: dict[str, dict],
                 fault_id: str, security: list[str]) -> tuple[str, list[str]]:
    """Apply the pre-declared rules. suites: test class simple name -> {tests, failures, errors}."""
    reasons = []
    if not applies:
        reasons.append("invalid: diff does not apply")
    elif compiled is False:
        reasons.append("invalid: does not compile")
    if infra_error:
        reasons.append("unknown: oracle infrastructure error or timeout")
    if applies and compiled and not infra_error:
        behaviour, perf = f"{fault_id}HiddenTest", f"{fault_id}PerfHiddenTest"
        if behaviour not in suites or perf not in suites:
            reasons.append(f"unknown: hidden test results missing ({sorted(set([behaviour, perf]) - set(suites))})")
        bad = lambda s: s["failures"] + s["errors"] > 0  # noqa: E731
        for name, s in sorted(suites.items()):
            if name in (behaviour, perf) or not bad(s):
                continue
            reasons.append(f"regressive: existing test {name} failed ({s['failures']} failures, {s['errors']} errors)")
        if behaviour in suites and bad(suites[behaviour]):
            reasons.append(f"incorrect: {behaviour} failed {suites[behaviour]['failures'] + suites[behaviour]['errors']}"
                           f" of {suites[behaviour]['tests']}")
        if perf in suites and bad(suites[perf]):
            reasons.append(f"slow: {perf} failed")
    if applies:
        reasons += [f"insecure: security probe {rid}" for rid in security]
    for label in LABEL_ORDER:
        if any(r.startswith(label + ":") for r in reasons):
            return label, reasons
    return "correct", reasons


def parse_surefire(reports: Path) -> dict[str, dict]:
    out = {}
    for xml in sorted(reports.glob("TEST-*.xml")):
        root = ET.parse(xml).getroot()
        name = root.get("name", xml.stem).rsplit(".", 1)[-1]
        out[name] = {k: int(float(root.get(k, 0))) for k in ("tests", "failures", "errors", "skipped")}
    return out


def collect_candidates(repo: Path = REPO) -> list[dict]:
    """Distinct (fault, diff) pairs with every place they occurred."""
    found: dict[tuple, dict] = {}

    def add(fault, diff, origin, occurrence):
        key = (fault, sha256_text(diff))
        c = found.setdefault(key, {"fault_id": fault, "patch_sha256": key[1], "diff": diff, "origins": set(),
                                   "scripted_file": None, "occurrences": []})
        c["origins"].add(origin)
        if origin == "scripted":
            c["scripted_file"] = occurrence
        else:
            c["occurrences"].append(occurrence)

    for diff_path in sorted((repo / "faults").glob("F*/candidates/*.diff")):
        add(diff_path.parent.parent.name, diff_path.read_text(encoding="utf-8"), "scripted", diff_path.name)
    for pj in sorted((repo / "runs").glob("*/patches.json")):
        try:
            patches = json.loads(pj.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for p in patches if isinstance(patches, list) else []:
            if p.get("provider_mode") in ("live", "replay") and p.get("diff"):
                fault = p["candidate_id"].split("-", 1)[0]
                add(fault, p["diff"], p["provider_mode"],
                    {"run_id": pj.parent.name, "candidate_id": p["candidate_id"], "model": p.get("model")})
    out = []
    for c in sorted(found.values(), key=lambda c: (c["fault_id"], c["scripted_file"] or "~", c["patch_sha256"])):
        c["origins"] = sorted(c["origins"])
        out.append(c)
    return out


def evaluate(c: dict, repo: Path = REPO, timeout: float = 600) -> dict:
    fault = c["fault_id"]
    fault_dir = repo / "faults" / fault
    hidden = sorted((fault_dir / "hidden_tests").glob("*.java"))
    start = time.monotonic()
    applies, compiled, infra, suites, log_tail = False, None, False, {}, ""
    with tempfile.TemporaryDirectory(prefix="autoimmune-oracle-") as tmp:
        tmp = Path(tmp)
        base = sandbox._copy_tree(repo / "app", tmp / "w" / "app").parent
        inj = sandbox._git_apply(base, (fault_dir / "inject.diff").read_text(encoding="utf-8"), check=False)
        if inj.returncode != 0:
            raise RuntimeError(f"inject.diff does not apply for {fault}: {inj.stderr}")
        applies = sandbox._git_apply(base, c["diff"], check=True).returncode == 0
        if applies and hidden:
            sandbox._git_apply(base, c["diff"], check=False)
            test_dir = base / sandbox.TEST_DIR
            for f in hidden:
                shutil.copy2(f, test_dir / f.name)
            ex = sandbox._maven(base / "app", "oracle", ["test", "-Dsurefire.failIfNoSpecifiedTests=false"], timeout)
            log_tail = sandbox._tail(ex.output, 40)
            suites = parse_surefire(base / "app" / "target" / "surefire-reports")
            if ex.timed_out or sandbox.classify(ex) == "error":
                infra = True
            elif "COMPILATION ERROR" in ex.output or (not suites and ex.exit_code != 0):
                compiled = False
            else:
                compiled = True
        elif applies and not hidden:
            infra = True
            log_tail = f"no hidden tests in {fault_dir / 'hidden_tests'}"
    label, reasons = decide_label(applies, compiled, infra, suites, fault, security_probe(c["diff"]) if applies else [])
    return {
        "oracle_version": ORACLE_VERSION, "fault_id": fault, "patch_sha256": c["patch_sha256"],
        "origins": c["origins"], "scripted_file": c["scripted_file"], "occurrences": c["occurrences"],
        "label": label, "reasons": reasons, "applies": applies, "compiled": compiled, "suites": suites,
        "hidden_tests_sha256": {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in hidden},
        "seconds": round(time.monotonic() - start, 1), "log_tail": log_tail,
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def write_outputs(rows: list[dict], repo: Path = REPO) -> None:
    out = repo / "results" / "oracle_report.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8", newline="\n")
    by_fault: dict[str, dict] = {}
    for r in rows:
        if r["scripted_file"]:
            by_fault.setdefault(r["fault_id"], {})[r["scripted_file"]] = {
                "label": r["label"], "label_source": ORACLE_VERSION, "reasons": r["reasons"],
                "status": "oracle-v1 (hidden tests + probes); two-person review pending",
                "staged": r["scripted_file"] in STAGED_FILES}
    for fault, cands in by_fault.items():
        p = repo / "faults" / fault / "candidates" / "labels.json"
        p.write_text(json.dumps({"oracle_version": ORACLE_VERSION, "candidates": dict(sorted(cands.items()))},
                                indent=2) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args(argv)
    cands = collect_candidates()
    print(f"{len(cands)} distinct candidates "
          f"({sum('scripted' in c['origins'] for c in cands)} scripted, "
          f"{sum('scripted' not in c['origins'] for c in cands)} live/replay)", flush=True)
    rows = []
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for r in pool.map(evaluate, cands):
            name = r["scripted_file"] or ", ".join(f"{o['run_id']}/{o['candidate_id']}" for o in r["occurrences"][:2])
            print(f"  {r['fault_id']} {name[:70]:70s} -> {r['label']:10s} ({r['seconds']} s)", flush=True)
            rows.append(r)
    write_outputs(rows)
    print(f"wrote results/oracle_report.jsonl and labels.json for {len({r['fault_id'] for r in rows})} faults")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
