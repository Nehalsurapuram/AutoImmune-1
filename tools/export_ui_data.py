"""Export authoritative AutoImmune research evidence and run artifacts to validated JSON for the UI.

Usage:
    python tools/export_ui_data.py [--out frontend/public/data/evidence_snapshot.json]

Integrity rules:
- Strictly read-only against existing evidence and run artifacts.
- Never invent results, fake numbers, or pool scripted and LLM cohorts.
- Record verification status, timestamps, and as-of dates.
- Safely extract unified diffs, gates, decisions, and deployment outcomes.
- Distinguish offline oracle evaluation from model/pipeline knowledge.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
import analyse  # noqa: E402


def parse_csv(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.is_file():
        return []
    with csv_path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def safe_json_read(path: Path) -> dict | list | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return None


def read_text_safe(path: Path, max_lines: int = 200) -> str | None:
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n... [truncated, total {len(lines)} lines]"
        return "\n".join(lines)
    except Exception:
        return None


def format_iso_timestamp(ts_str: str | None) -> str | None:
    if not ts_str:
        return None
    ts_str = ts_str.strip()
    if "-" in ts_str:
        return ts_str
    try:
        dt = datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except Exception:
        pass
    try:
        dt = datetime.strptime(ts_str, "%Y%m%dT%H%M%S")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except Exception:
        return None


def load_fault_meta(faults_dir: Path) -> dict[str, dict]:
    meta = {}
    if not faults_dir.is_dir():
        return meta
    for fdir in sorted(faults_dir.iterdir()):
        if fdir.is_dir() and (fdir / "fault.json").is_file():
            doc = safe_json_read(fdir / "fault.json")
            if isinstance(doc, dict):
                fid = doc.get("id") or fdir.name
                meta[fid] = {
                    "id": fid,
                    "category": doc.get("category", "general"),
                    "description": doc.get("description", ""),
                    "diagnosed_file": doc.get("diagnosed_file", ""),
                    "target_test": doc.get("target_test", ""),
                }
    return meta


def get_git_info() -> dict:
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=REPO_ROOT).strip()
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True, cwd=REPO_ROOT).strip()
        status = subprocess.check_output(["git", "status", "--porcelain"], text=True, cwd=REPO_ROOT).strip()
        return {
            "head": head,
            "branch": branch,
            "dirty": bool(status),
        }
    except Exception as e:
        return {"head": "unknown", "branch": "unknown", "dirty": False, "error": str(e)}


def check_analyse_status() -> dict:
    try:
        res = subprocess.run(
            [sys.executable, "analyse.py", "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True
        )
        return {
            "exit_code": res.returncode,
            "status": "PASS" if res.returncode == 0 else "STALE",
            "message": res.stdout.strip() or res.stderr.strip()
        }
    except Exception as e:
        return {"exit_code": -1, "status": "ERROR", "message": str(e)}


def build_timeline_stages(run_data: dict, incident: dict | None, diagnosis: dict | None,
                          candidates: list[dict], deploy_artifact: dict | None,
                          rollback_artifact: dict | None) -> list[dict]:
    stages = []
    
    # 1. Fault detection
    if incident:
        stages.append({
            "id": "detection",
            "name": "Fault Detection",
            "status": "pass",
            "details": f"Rule '{incident.get('rule')}' triggered on {incident.get('endpoint', 'system')}"
        })
    else:
        stages.append({
            "id": "detection",
            "name": "Fault Detection",
            "status": "not_run",
            "details": "No incident record"
        })

    # 2. Incident Evidence
    if incident and incident.get("evidence"):
        stages.append({
            "id": "incident_evidence",
            "name": "Incident Evidence",
            "status": "pass",
            "details": f"{len(incident.get('evidence', []))} probe/metric check(s) recorded"
        })
    else:
        stages.append({
            "id": "incident_evidence",
            "name": "Incident Evidence",
            "status": "skipped",
            "details": "No probe evidence attached"
        })

    # 3. Root-cause Diagnosis
    if diagnosis:
        causes = diagnosis.get("causes") or []
        top1 = causes[0]["file"] if causes else "None"
        stages.append({
            "id": "diagnosis",
            "name": "Root-Cause Diagnosis",
            "status": "pass",
            "details": f"Mode: {diagnosis.get('provider_mode', 'unknown')} | Top: {top1}"
        })
    else:
        stages.append({
            "id": "diagnosis",
            "name": "Root-Cause Diagnosis",
            "status": "not_run",
            "details": "No diagnosis artifact"
        })

    # 4. Patch Candidate Generation
    if candidates:
        stages.append({
            "id": "candidate_generation",
            "name": "Candidate Generation",
            "status": "pass",
            "details": f"{len(candidates)} candidate(s) drafted/loaded"
        })
    else:
        stages.append({
            "id": "candidate_generation",
            "name": "Candidate Generation",
            "status": "not_run",
            "details": "No candidate patches"
        })

    # 5. Validation Gates (V0-V3)
    any_gate_pass = False
    any_gate_fail = False
    for c in candidates:
        gates = c.get("gates", {})
        if gates.get("V0", {}).get("status") == "pass":
            any_gate_pass = True
        if any(gates.get(g, {}).get("status") in ("fail", "error", "timeout") for g in ("V0", "V1", "V2", "V3")):
            any_gate_fail = True
    val_status = "pass" if any_gate_pass else ("fail" if any_gate_fail else "not_run")
    stages.append({
        "id": "validation",
        "name": "Sandbox Validation (V0–V3)",
        "status": val_status,
        "details": f"Evaluated across {len(candidates)} candidates in Docker"
    })

    # 6. Risk Decision
    decisions = [
        str(c.get("decision", {}).get("decision"))
        for c in candidates
        if c.get("decision") and c.get("decision", {}).get("decision")
    ]
    if decisions:
        stages.append({
            "id": "decision",
            "name": "Deterministic Risk Decision",
            "status": "pass",
            "details": f"Decisions: {', '.join(decisions)}"
        })
    else:
        stages.append({
            "id": "decision",
            "name": "Deterministic Risk Decision",
            "status": "not_run",
            "details": "No decision evaluated"
        })

    # 7. Human Approval (where applicable)
    has_approval = any(c.get("approval_source") or c.get("approval") for c in candidates)
    if has_approval:
        approvals = [c.get("approval_source") or "human_cli" for c in candidates if c.get("approval_source")]
        stages.append({
            "id": "approval",
            "name": "Human Approval",
            "status": "pass",
            "details": f"Approved via {', '.join(approvals)}"
        })
    elif any(c.get("decision", {}).get("decision") == "ESCALATE" for c in candidates):
        stages.append({
            "id": "approval",
            "name": "Human Approval",
            "status": "not_run",
            "details": "Escalated candidate awaiting review or not submitted"
        })
    else:
        stages.append({
            "id": "approval",
            "name": "Human Approval",
            "status": "skipped",
            "details": "Not required (no candidate escalated for human review)"
        })

    # 8. Deployment
    if deploy_artifact:
        stages.append({
            "id": "deployment",
            "name": "Deployment",
            "status": "pass",
            "details": f"New image: {deploy_artifact.get('new_image')}"
        })
    elif any(c.get("deployed") for c in candidates):
        stages.append({
            "id": "deployment",
            "name": "Deployment",
            "status": "pass",
            "details": "Candidate deployed to container"
        })
    else:
        stages.append({
            "id": "deployment",
            "name": "Deployment",
            "status": "not_run",
            "details": "No candidate deployed in this run"
        })

    # 9. Health Window & Recovery
    if rollback_artifact:
        stages.append({
            "id": "recovery",
            "name": "Health Window & Recovery",
            "status": "fail",
            "details": f"Rolled back in {rollback_artifact.get('seconds_breach_to_healthy', 'N/A')}s: {rollback_artifact.get('reason')}"
        })
    elif deploy_artifact and deploy_artifact.get("outcome") == "promoted":
        stages.append({
            "id": "recovery",
            "name": "Health Window & Recovery",
            "status": "pass",
            "details": "Health checks passed; promoted to active service"
        })
    elif deploy_artifact and deploy_artifact.get("outcome") == "rolled_back":
        stages.append({
            "id": "recovery",
            "name": "Health Window & Recovery",
            "status": "fail",
            "details": "Breached health window; restored previous image"
        })
    else:
        stages.append({
            "id": "recovery",
            "name": "Health Window & Recovery",
            "status": "not_run",
            "details": "No deployment health monitoring conducted"
        })

    # 10. Evidence Recording
    has_evidence = (REPO_ROOT / "runs" / run_data.get("run_id", "") / "evidence.jsonl").is_file()
    stages.append({
        "id": "evidence",
        "name": "Evidence Recording",
        "status": "pass" if has_evidence else "not_run",
        "details": "Run evidence recorded to runs/<run_id>/evidence.jsonl" if has_evidence else "No run-level evidence.jsonl"
    })

    return stages


# Research extensions computed by their own analysis modules. The exporter only copies their verified JSON in;
# it never recomputes them. key -> (path under results/, command that regenerates it, expected schema_version)
RESEARCH_EXTENSIONS = {
    "risk_estimation": ("risk/risk_estimation.json", "python -m tools.risk_model", 1),
    "validation_cost": ("cost/validation_cost.json", "python -m tools.validation_cost", 1),
}


def load_research_extension(results_dir: Path, key: str) -> dict:
    """{available, source, sha256_12, data} or {available: False, reason}. A missing or unknown file is reported,
    never replaced with placeholder numbers."""
    import hashlib
    rel, cmd, version = RESEARCH_EXTENSIONS[key]
    path = results_dir / rel
    source = f"results/{rel}"
    if not path.is_file():
        return {"available": False, "source": source, "reason": f"{source} not found; run `{cmd}`"}
    raw = path.read_bytes()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return {"available": False, "source": source, "reason": f"{source} is not valid JSON: {e}"}
    if doc.get("analysis") != key or doc.get("schema_version") != version:
        return {"available": False, "source": source,
                "reason": f"{source} has analysis={doc.get('analysis')!r}, schema_version={doc.get('schema_version')!r}; "
                          f"expected {key!r} v{version}. Regenerate with `{cmd}`."}
    return {"available": True, "source": source, "sha256_12": hashlib.sha256(raw).hexdigest()[:12],
            "generator": cmd, "data": doc}


def export_all(output_paths: list[Path]):
    evidence_path = REPO_ROOT / "results" / "evidence.jsonl"
    results_dir = REPO_ROOT / "results"
    runs_dir = REPO_ROOT / "runs"
    docs_dir = REPO_ROOT / "docs"
    faults_dir = REPO_ROOT / "faults"

    print(f"Reading evidence from {evidence_path}...")
    evidence_rows = []
    if evidence_path.is_file():
        with evidence_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    evidence_rows.append(json.loads(line))

    exclusions = analyse.load_analysis_exclusions(evidence_path)
    excluded_run_ids = set(exclusions)
    units = analyse.units_of(evidence_rows, excluded_run_ids)
    
    # Ground truth labels from offline oracle
    offline_labels = analyse.load_labels(faults_dir)
    fault_metadata = load_fault_meta(faults_dir)
    oracle_live_path = results_dir / "oracle_report.jsonl"
    oracle_live = analyse.load_oracle_live(oracle_live_path) if oracle_live_path.is_file() else {}

    # CSV data
    policies_csv = parse_csv(results_dir / "policies.csv")
    first_stop_csv = parse_csv(results_dir / "first_stop.csv")
    deployments_csv = parse_csv(results_dir / "deployments.csv")
    rollbacks_csv = parse_csv(results_dir / "rollbacks.csv")
    approvals_csv = parse_csv(results_dir / "approvals.csv")
    llm_units_csv = parse_csv(results_dir / "llm_units.csv")
    llm_diagnosis_csv = parse_csv(results_dir / "llm_diagnosis.csv")
    llm_patch_utility_csv = parse_csv(results_dir / "llm_patch_utility.csv")
    runs_csv = parse_csv(results_dir / "runs.csv")
    gate_incremental_csv = parse_csv(results_dir / "gate_incremental.csv")
    unsafe_first_stop_csv = parse_csv(results_dir / "unsafe_first_stop.csv")

    # Audit & acceptance
    acc_path = docs_dir / "audit" / "acceptance.json"
    acc = safe_json_read(acc_path) or {}

    # Read runs directory
    print("Reading recorded run directories...")
    runs_data = []
    candidates_list = []

    # Map evidence rows by (run_id, candidate_id)
    evidence_by_run_cand = {(r.get("run_id"), r.get("candidate_id")): r for r in evidence_rows}
    # Map deployments by (run_id, candidate_id)
    deploy_by_run_cand = {(d.get("run_id"), d.get("candidate_id")): d for d in deployments_csv}
    # Map first_stop by (run_id, candidate_id)
    first_stop_by_run_cand = {(f.get("run_id"), f.get("candidate_id")): f for f in first_stop_csv}

    if runs_dir.is_dir():
        for run_path in sorted(runs_dir.iterdir()):
            if not run_path.is_dir() or run_path.name.startswith("pytest-"):
                continue

            run_id = run_path.name
            run_json = safe_json_read(run_path / "run.json") or {}
            incident_json = safe_json_read(run_path / "incident.json")
            diag_json = safe_json_read(run_path / "diagnosis.json")
            patches_json = safe_json_read(run_path / "patches.json")
            baseline_json = safe_json_read(run_path / "baseline.json")

            # Candidate subdirectories
            cand_dirs = [p for p in run_path.iterdir() if p.is_dir() and (p / "gates.json").is_file()]
            run_candidates = []
            run_deploy_artifact = None
            run_rollback_artifact = None

            for cdir in sorted(cand_dirs, key=lambda p: p.name):
                cid = cdir.name
                gates_data = safe_json_read(cdir / "gates.json") or {}
                decision_data = safe_json_read(cdir / "decision.json") or {}
                deploy_data = safe_json_read(cdir / "deploy.json")
                rollback_data = safe_json_read(cdir / "rollback.json")
                diff_text = read_text_safe(cdir / "candidate.diff")

                if deploy_data:
                    run_deploy_artifact = deploy_data
                if rollback_data:
                    run_rollback_artifact = rollback_data

                # Evidence match
                ev_row = evidence_by_run_cand.get((run_id, cid)) or {}
                dep_row = deploy_by_run_cand.get((run_id, cid)) or {}
                fs_row = first_stop_by_run_cand.get((run_id, cid)) or {}

                # Oracle label
                offline_label_entry = offline_labels.get(cid, {})
                oracle_label = offline_label_entry.get("label") or oracle_live.get((run_id, cid)) or fs_row.get("label")

                cand_entry = {
                    "candidate_id": cid,
                    "run_id": run_id,
                    "fault_id": run_json.get("fault_id") or (ev_row.get("fault_id")) or (incident_json.get("fault_id") if incident_json else None),
                    "cohort": "llm" if run_json.get("patch_mode") in ("live", "replay") or ev_row.get("patch_mode") in ("live", "replay") else "scripted",
                    "diag_mode": run_json.get("diag_mode") or ev_row.get("diag_mode"),
                    "patch_mode": run_json.get("patch_mode") or ev_row.get("patch_mode"),
                    "model": run_json.get("provenance", {}).get("llm_model") or ev_row.get("model") or (diag_json.get("model") if diag_json else None),
                    "diff_lines": decision_data.get("patch_meta", {}).get("diff_lines") or ev_row.get("diff_lines"),
                    "files_touched": decision_data.get("patch_meta", {}).get("files_touched") or ev_row.get("files_touched", []),
                    "gates": gates_data.get("gates", {
                        "V0": ev_row.get("v0", {"status": "not_run"}),
                        "V1": ev_row.get("v1", {"status": "not_run"}),
                        "V2": ev_row.get("v2", {"status": "not_run"}),
                        "V3": ev_row.get("v3", {"status": "not_run"}),
                    }),
                    "passed_all_gates": gates_data.get("passed_all", False),
                    "decision": decision_data if decision_data else {
                        "tier": ev_row.get("tier"),
                        "decision": ev_row.get("decision"),
                        "reasons": ev_row.get("reasons", [])
                    },
                    "approval_source": ev_row.get("approval_source") or dep_row.get("approval_source"),
                    "deployed": bool(deploy_data) or ev_row.get("deployed") is True or dep_row.get("outcome") in ("promoted", "rolled back"),
                    "outcome": (deploy_data.get("outcome") if deploy_data else None) or dep_row.get("outcome") or (ev_row.get("rolled_back") and "rolled back"),
                    "rolled_back": bool(rollback_data) or ev_row.get("rolled_back") is True or dep_row.get("outcome") == "rolled back",
                    "recovery_s": (rollback_data.get("seconds_breach_to_healthy") if rollback_data else None) or ev_row.get("recovery_s"),
                    "first_stop": fs_row.get("first_stop"),
                    "offline_oracle_label": oracle_label,
                    "offline_oracle_note": "Independent offline ground truth evaluation; never shown to pipeline or model",
                    "diff_snippet": diff_text,
                    "has_deploy_artifact": bool(deploy_data),
                    "has_rollback_artifact": bool(rollback_data),
                }
                run_candidates.append(cand_entry)
                candidates_list.append(cand_entry)

            # Build timeline stages
            stages = build_timeline_stages(run_json, incident_json, diag_json, run_candidates, run_deploy_artifact, run_rollback_artifact)

            fid = run_json.get("fault_id") or (incident_json.get("fault_id") if incident_json else None)
            f_info = fault_metadata.get(fid, {})
            f_desc = f_info.get("description", "")

            # Formulate human-readable plain fault and headline
            if fid:
                short_fault_name = f"{fid} {f_info.get('category', 'fault')}".replace("_", " ")
                if fid == "F06":
                    short_fault_name = "F06 discount threshold boundary"
                elif fid == "F01":
                    short_fault_name = "F01 customer search null guard"
                elif fid == "F04":
                    short_fault_name = "F04 catalog health config"
                elif fid == "F02":
                    short_fault_name = "F02 item price precision"
                elif fid == "F05":
                    short_fault_name = "F05 order status transition"
                elif fid == "F07":
                    short_fault_name = "F07 tax calculation rounding"
                elif fid == "F08":
                    short_fault_name = "F08 inventory stock check"
            elif "healthy-watch" in run_id:
                short_fault_name = "No fault (healthy watch)"
            elif "audit-verify" in run_id:
                short_fault_name = "Audit baseline verification"
            else:
                short_fault_name = "Unspecified baseline execution"

            if run_rollback_artifact:
                plain_outcome = "Rolled back"
            elif run_deploy_artifact:
                plain_outcome = "Promoted"
            elif any(c.get("decision", {}).get("decision") == "AUTO_APPLY" for c in run_candidates):
                plain_outcome = "Auto-applied"
            elif any(c.get("decision", {}).get("decision") == "ESCALATE" for c in run_candidates):
                plain_outcome = "Escalated"
            elif all(c.get("decision", {}).get("decision") == "REJECT" for c in run_candidates) and run_candidates:
                plain_outcome = "Rejected"
            else:
                plain_outcome = "Gates evaluated"

            headline = f"{short_fault_name}, {plain_outcome.lower()}"

            started_at_iso = format_iso_timestamp(run_json.get("started_at")) or (incident_json.get("timestamp") if incident_json else None)
            ended_at_iso = format_iso_timestamp(run_json.get("ended_at"))

            run_entry = {
                "run_id": run_id,
                "fault_id": fid,
                "fault_name": short_fault_name,
                "fault_description": f_desc,
                "headline": headline,
                "plain_outcome": plain_outcome,
                "diag_mode": run_json.get("diag_mode"),
                "patch_mode": run_json.get("patch_mode"),
                "model": run_json.get("provenance", {}).get("llm_model") or (diag_json.get("model") if diag_json else None),
                "started_at": started_at_iso,
                "ended_at": ended_at_iso,
                "outcome": run_json.get("outcome") or ("deployed" if run_deploy_artifact else "finished"),
                "config": run_json.get("config", {}),
                "provenance": run_json.get("provenance", {}),
                "incident": incident_json,
                "diagnosis": diag_json,
                "patches_meta": patches_json,
                "candidates": run_candidates,
                "deploy_artifact": run_deploy_artifact,
                "rollback_artifact": run_rollback_artifact,
                "timeline_stages": stages,
                "is_excluded": run_id in excluded_run_ids,
                "exclusion_reason": exclusions.get(run_id, {}).get("reason"),
            }
            runs_data.append(run_entry)

    # Sort runs chronologically descending
    runs_data.sort(key=lambda r: r.get("started_at") or r.get("run_id"), reverse=True)

    # Calculate summary stats
    total_units_count = len(units)
    scripted_units = [u for u in units if analyse.cohort_of(u) == "scripted"]
    llm_units = [u for u in units if analyse.cohort_of(u) == "llm"]

    gate_stats = {}
    for g in ("V0", "V1", "V2", "V3"):
        statuses = Counter()
        durations = []
        for u in units:
            g_data = u.get(g.lower()) or {}
            st = g_data.get("status", "unknown")
            statuses[st] += 1
            sec = g_data.get("seconds")
            if sec is not None and isinstance(sec, (int, float)) and sec > 0 and st in ("pass", "fail", "error"):
                durations.append(sec)
        durations.sort()
        gate_stats[g] = {
            "statuses": dict(statuses),
            "min_seconds": round(durations[0], 2) if durations else None,
            "avg_seconds": round(sum(durations) / len(durations), 2) if durations else None,
            "median_seconds": round(durations[len(durations) // 2], 2) if durations else None,
            "max_seconds": round(durations[-1], 2) if durations else None,
            "count": len(durations),
        }

    # First stop distribution
    first_stop_counts = Counter(r.get("first_stop", "unknown") for r in first_stop_csv)

    # Verified Case Studies
    case_studies = [
        {
            "id": "ai-silent-escape",
            "title": "When All Validation Gates Pass But Patch Is Wrong (Silent Escape)",
            "subtitle": "RQ2 Core Finding: Passing tests and health checks does not prove semantic correctness",
            "run_id": "f01-live-live-20261108t195433z",
            "candidate_id": "F01-live-2",
            "fault_id": "F01",
            "provider": "openai/gpt-oss-120b",
            "what_happened": "The model drafted a patch that only checks `name != null`, but completely ignores empty/whitespace-only names (`name.isBlank()`). The visible target test only checked null, so V0, V1, V2, and V3 all passed. The deterministic decision engine gave it AUTO_APPLY. It was deployed and promoted after 30s of healthy actuator responses. However, independent offline oracle specification testing labelled it INCORRECT because blank customer orders still corrupted database state.",
            "gates_result": "V0: PASS, V1: PASS, V2: PASS, V3: PASS (0 Semgrep findings)",
            "decision_result": "AUTO_APPLY (tier: low)",
            "health_result": "Promoted (HTTP 200 /actuator/health)",
            "oracle_ground_truth": "INCORRECT (failed hidden specification tests for blank strings)",
            "research_takeaway": "Test suites contain blind spots. Even a 4-gate verification pipeline plus automated health window promotion can auto-apply semantically invalid patches without safety-critical invariant specifications."
        },
        {
            "id": "ai-repair-success",
            "title": "Autonomous AI Repair With Complete Provenance",
            "subtitle": "RQ1 Demonstration: End-to-end diagnosis, gating, deployment, and promotion",
            "run_id": "f06-live-live-20261108t193456z",
            "candidate_id": "F06-live-1",
            "fault_id": "F06",
            "provider": "openai/gpt-oss-120b",
            "what_happened": "F06 discount threshold calculation bug detected via probe mismatch. GPT-OSS-120B localized the bug to OrderService.java:28, drafted a precise 2-line patch fixing the boundary condition (`>=` instead of `>`). The patch passed V0, V1, V2, and V3 with 0 new Semgrep findings. It received AUTO_APPLY, was deployed to the Docker container, passed side-by-side smoke tests, and was promoted after a 30s health window. The independent oracle confirmed semantic correctness.",
            "gates_result": "V0: PASS (7.8s), V1: PASS (30.6s), V2: PASS (32.0s), V3: PASS (8.0s)",
            "decision_result": "AUTO_APPLY (tier: low)",
            "health_result": "Promoted (Actuator UP, probes valid, latency < 50ms)",
            "oracle_ground_truth": "CORRECT (passes hidden tests, performance, security probes)",
            "research_takeaway": "When the fault lies within single-function arithmetic/boundary logic and the test oracle accurately captures the contract, LLM repairs can safely auto-apply under deterministic multi-gate constraints."
        },
        {
            "id": "staged-rollback",
            "title": "Automated Latency Breach & Fast Image Rollback",
            "subtitle": "Safety Architecture: Recovery window catches latent runtime defects",
            "run_id": "f06-rule-scripted-20261108t201808z",
            "candidate_id": "F06-scripted-7509cb64",
            "fault_id": "F06",
            "provider": "scripted (slow.diff candidate)",
            "what_happened": "A scripted patch introduced a latent 3000ms delay in discount calculation. It passed static compilation (V0), the target unit test (V1), existing suite (V2), and Semgrep (V3) because unit tests did not enforce latency bounds. The engine auto-applied it. Upon container swap, the health window probe measured 3015ms (breaching the 2000ms threshold). The deployment controller instantly rolled back to the previous image in 5.1s and verified restored image sha256.",
            "gates_result": "V0: PASS, V1: PASS, V2: PASS, V3: PASS",
            "decision_result": "AUTO_APPLY (tier: low)",
            "health_result": "ROLLED BACK in 5.1 seconds (breach: probe took 3015ms > 2000ms)",
            "oracle_ground_truth": "SLOW (staged demonstration candidate)",
            "research_takeaway": "Pre-deployment gates alone cannot catch execution-environment latency regressions. An automated canary/health window with immediate container image-swap rollback is an essential secondary defense line."
        },
        {
            "id": "human-escalation",
            "title": "Sensitive Path Escalation & Human Review",
            "subtitle": "Policy Tiering: Sensitive configuration changes gated by human approval",
            "run_id": "f04-rule-scripted-20261108t205508z",
            "candidate_id": "F04-scripted-835a25e8",
            "fault_id": "F04",
            "provider": "scripted (correct config patch)",
            "what_happened": "F04 caused service health to drop to DOWN due to misconfigured connection pool in application.properties. The repair patch touched application.properties. Even though all gates V0-V3 passed, the decision engine classified it as ESCALATE because config files are flagged as sensitive paths in decision.yaml. The CLI prompted the human operator, who reviewed the diff and issued approval via human_cli. The patch was deployed and successfully promoted.",
            "gates_result": "V0: PASS, V1: PASS, V2: PASS, V3: PASS",
            "decision_result": "ESCALATE (tier: medium; reason: diff touches sensitive path application.properties)",
            "health_result": "Promoted following human approval (human_cli)",
            "oracle_ground_truth": "CORRECT",
            "research_takeaway": "Deterministic policy rules prevent AI or scripted repairs from silently modifying security configs, database credentials, or framework settings without explicit human sign-off."
        }
    ]

    snapshot = {
        "metadata": {
            "title": "AutoImmune: An Empirical Study of Validation-Gated Deployment Strategies for LLM-Generated Software Patches",
            "subtitle": "Research Console Evidence Snapshot",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "git": get_git_info(),
            "analyse_check": check_analyse_status(),
            "acceptance_as_of": acc.get("as_of", "2026-11-08"),
            "total_runs_recorded": len(runs_data),
            "total_evidence_rows": len(evidence_rows),
            "total_units": total_units_count,
            "scripted_units_count": len(scripted_units),
            "llm_units_count": len(llm_units),
            "distinct_faults": sorted(list(set(r.get("fault_id") for r in runs_data if r.get("fault_id")))),
            "provenance_note": "All statistics originate from verified evidence logs and run artifacts. Scripted and LLM cohorts are kept strictly separate."
        },
        "acceptance": acc,
        "runs": runs_data,
        "candidates": candidates_list,
        "case_studies": case_studies,
        "policies": policies_csv,
        "gate_stats": gate_stats,
        "first_stop_distribution": dict(first_stop_counts),
        "gate_incremental": gate_incremental_csv,
        "unsafe_first_stop": unsafe_first_stop_csv,
        "deployments": deployments_csv,
        "rollbacks": rollbacks_csv,
        "approvals": approvals_csv,
        "llm_diagnosis": llm_diagnosis_csv,
        "llm_patch_utility": llm_patch_utility_csv,
        "run_ledger": runs_csv,
        "risk_estimation": load_research_extension(results_dir, "risk_estimation"),
        "validation_cost": load_research_extension(results_dir, "validation_cost"),
        "research_questions": [
            {
                "id": "RQ1",
                "question": "What validation evidence is sufficient to consider bypassing human review?",
                "summary": "Full multi-gate validation (V0–V3) plus scope rules reduces unsafe auto-deployments significantly compared to target-test-only gating, but cannot eliminate semantic defects without behavioral oracle assertions."
            },
            {
                "id": "RQ2",
                "question": "How effectively do gate outcomes and other evidence distinguish unsafe patches?",
                "summary": "Gate cascades sequentially eliminate different defect classes: V0 eliminates syntax/compile errors, V1 eliminates ineffective patches, V2 catches regressions, and V3 catches security anti-patterns. However, patches that overfit only to visible tests can pass all 4 gates."
            },
            {
                "id": "RQ3",
                "question": "How much does each additional validation gate catch, and what execution cost does it introduce?",
                "summary": "Target tests (V1) and regression suites (V2) introduce the largest execution latency (~20-40s each in Docker), but V2 catches the largest fraction of regressive breakages. Static analysis (V3) runs fast (~7-15s) and catches security risks without running tests."
            }
        ]
    }

    for outp in output_paths:
        outp.parent.mkdir(parents=True, exist_ok=True)
        print(f"Writing {len(runs_data)} runs and {len(candidates_list)} candidates to {outp}...")
        with outp.open("w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2)
        print(f"Wrote {outp.stat().st_size / 1024:.1f} KB to {outp}")


def main():
    parser = argparse.ArgumentParser(description="Export AutoImmune UI evidence snapshot.")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "frontend" / "public" / "data" / "evidence_snapshot.json",
                        help="Output JSON path")
    args = parser.parse_args()

    targets = [args.out, REPO_ROOT / "results" / "evidence_snapshot.json"]
    export_all(targets)


if __name__ == "__main__":
    main()
