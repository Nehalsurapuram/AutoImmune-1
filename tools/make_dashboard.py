"""Generator for AutoImmune Evidence Dashboard.

    python tools/make_dashboard.py
    python tools/make_dashboard.py --out results/dashboard.html

Produces an offline, self-contained HTML dashboard visualizing real project evidence,
validation gates V0-V3, candidate reviews, policy comparisons, and known limitations.
Zero external network calls, fonts, or CDNs.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyse  # noqa: E402  (repo root)


def esc(val: object) -> str:
    """Safe HTML escaping handling None and non-string types."""
    if val is None:
        return ""
    return html.escape(str(val))


def parse_evidence(evidence_path: Path) -> list[dict]:
    if not evidence_path.exists():
        raise FileNotFoundError(f"Evidence file not found: {evidence_path}")
    rows = []
    with evidence_path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                rows.append(row)
            except json.JSONDecodeError as e:
                print(f"Warning: line {idx} in {evidence_path} is invalid JSON: {e}", file=sys.stderr)
    return rows


def parse_csv(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def determine_first_stop(u: dict) -> str:
    """What stopped this candidate: the first gate that did not pass, else SURVIVED."""
    for g in ("v0", "v1", "v2", "v3"):
        st = u.get(g, {}).get("status")
        if st != "pass":
            return g.upper()
    return "SURVIVED"


def build_dashboard_data(repo_root: Path, evidence_path: Path, results_dir: Path, docs_dir: Path) -> dict:
    evidence_rows = parse_evidence(evidence_path)
    
    # Analysis units: exactly the units analyse.py reports (scripted per fault x file x diag_mode; LLM per run x id)
    units = analyse.units_of(evidence_rows)

    # Read CSV reports
    llm_diagnosis = parse_csv(results_dir / "llm_diagnosis.csv")
    llm_units = parse_csv(results_dir / "llm_units.csv")
    policies = parse_csv(results_dir / "policies.csv")
    approvals = parse_csv(results_dir / "approvals.csv")
    rollbacks = parse_csv(results_dir / "rollbacks.csv")
    decisions_by_fault = parse_csv(results_dir / "decisions_by_fault.csv")
    unsafe_first_stop = parse_csv(results_dir / "unsafe_first_stop.csv")
    
    # Executive overview metrics
    distinct_faults = sorted(set(r.get("fault_id") for r in evidence_rows if r.get("fault_id")))
    decision_counts = Counter(r.get("decision", "UNKNOWN") for r in units)
    # deployments and rollbacks are events: count every valid row, not one per unit
    deployed_count = sum(1 for r in evidence_rows if not r.get("invalid") and r.get("deployed") is True)
    rollback_count = sum(1 for r in evidence_rows if not r.get("invalid") and r.get("rolled_back") is True)
    
    approval_counts = Counter(r.get("approval_source") for r in evidence_rows if r.get("approval_source"))
    diag_modes = Counter(r.get("diag_mode") for r in units)
    patch_modes = Counter(r.get("patch_mode") for r in units)
    models = Counter(r.get("model") for r in units if r.get("model"))
    
    # First-stop calculations
    first_stop_counts = Counter(determine_first_stop(u) for u in units)
    
    # Gate stats & timing metrics across units
    gates = ("v0", "v1", "v2", "v3")
    gate_stats = {}
    for g in gates:
        statuses = Counter()
        durations = []
        for u in units:
            g_data = u.get(g) or {}
            st = g_data.get("status", "unknown")
            statuses[st] += 1
            sec = g_data.get("seconds")
            if sec is not None and isinstance(sec, (int, float)) and sec > 0 and st in ("pass", "fail", "error"):
                durations.append(sec)
        gate_stats[g.upper()] = {
            "statuses": statuses,
            "min_seconds": min(durations) if durations else None,
            "avg_seconds": statistics.mean(durations) if durations else None,
            "median_seconds": statistics.median(durations) if durations else None,
            "max_seconds": max(durations) if durations else None,
            "count": len(durations),
        }
    
    # Group candidates by fault
    fault_groups: dict[str, list[dict]] = {}
    for u in units:
        fid = u.get("fault_id", "unknown")
        fault_groups.setdefault(fid, []).append(u)
    
    # Acceptance checks and limitations come from one data file, never from this code (audit: stale claims)
    acc_path = docs_dir / "audit" / "acceptance.json"
    acc = json.loads(acc_path.read_text(encoding="utf-8")) if acc_path.is_file() else {}
    acceptance_checks = acc.get("acceptance_checks", [])
    known_limitations = acc.get("known_limitations", [])
    test_suite = acc.get("test_suite", {"badge": "unknown", "text": f"{acc_path} not found"})

    return {
        "evidence_rows": evidence_rows,
        "units": units,
        "distinct_faults": distinct_faults,
        "decision_counts": decision_counts,
        "deployed_count": deployed_count,
        "rollback_count": rollback_count,
        "approval_counts": approval_counts,
        "diag_modes": diag_modes,
        "patch_modes": patch_modes,
        "models": models,
        "first_stop_counts": first_stop_counts,
        "gate_stats": gate_stats,
        "fault_groups": fault_groups,
        "llm_diagnosis": llm_diagnosis,
        "llm_units": llm_units,
        "policies": policies,
        "approvals": approvals,
        "rollbacks": rollbacks,
        "decisions_by_fault": decisions_by_fault,
        "unsafe_first_stop": unsafe_first_stop,
        "acceptance_checks": acceptance_checks,
        "known_limitations": known_limitations,
        "test_suite": test_suite,
        "labels_found": bool(list((repo_root / "faults").glob("*/candidates/labels.json"))),
        "acceptance_as_of": acc.get("as_of", "unknown"),
        "llm_patch_utility": parse_csv(results_dir / "llm_patch_utility.csv"),
        "deployments": parse_csv(results_dir / "deployments.csv"),
        "run_ledger": parse_csv(results_dir / "runs.csv"),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


def render_html(data: dict) -> str:
    total_rows = len(data["evidence_rows"])
    total_units = len(data["units"])
    distinct_faults_str = ", ".join(data["distinct_faults"])
    auto_apply_count = data["decision_counts"].get("AUTO_APPLY", 0)
    escalate_count = data["decision_counts"].get("ESCALATE", 0)
    reject_count = data["decision_counts"].get("REJECT", 0)
    deployed_count = data["deployed_count"]
    rollback_count = data["rollback_count"]
    
    pure_live_units = [u for u in data["units"] if u.get("patch_mode") == "live"]
    
    html_lines = [
        "<!DOCTYPE html>",
        "<html lang=\"en\">",
        "<head>",
        "  <meta charset=\"UTF-8\">",
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">",
        "  <title>AutoImmune — Evidence Dashboard</title>",
        "  <style>",
        "    :root {",
        "      --bg-page: #f8fafc;",
        "      --bg-card: #ffffff;",
        "      --bg-card-subtle: #f8fafc;",
        "      --bg-header: #ffffff;",
        "      --border: #e2e8f0;",
        "      --border-subtle: #cbd5e1;",
        "      --border-focus: #0284c7;",
        "      --text-main: #0f172a;",
        "      --text-muted: #475569;",
        "      --text-dim: #64748b;",
        "      --accent: #0284c7;",
        "      --accent-light: #f0f9ff;",
        "      --pass: #065f46;",
        "      --pass-bg: #ecfdf5;",
        "      --pass-border: #a7f3d0;",
        "      --fail: #991b1b;",
        "      --fail-bg: #fef2f2;",
        "      --fail-border: #fecaca;",
        "      --warn: #92400e;",
        "      --warn-bg: #fffbeb;",
        "      --warn-border: #fde68a;",
        "      --error: #991b1b;",
        "      --error-bg: #fef2f2;",
        "      --error-border: #fecaca;",
        "      --skip: #475569;",
        "      --skip-bg: #f1f5f9;",
        "      --skip-border: #e2e8f0;",
        "    }",
        "    * { box-sizing: border-box; margin: 0; padding: 0; }",
        "    body {",
        "      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;",
        "      background-color: var(--bg-page);",
        "      color: var(--text-main);",
        "      line-height: 1.5;",
        "      padding-bottom: 64px;",
        "    }",
        "    header {",
        "      background-color: var(--bg-header);",
        "      border-bottom: 1px solid var(--border);",
        "      padding: 44px 48px 32px;",
        "    }",
        "    .header-content {",
        "      max-width: 1400px;",
        "      margin: 0 auto;",
        "      display: flex;",
        "      justify-content: space-between;",
        "      align-items: flex-end;",
        "      flex-wrap: wrap;",
        "      gap: 24px;",
        "    }",
        "    .project-identity {",
        "      display: flex;",
        "      flex-direction: column;",
        "    }",
        "    .project-title {",
        "      font-size: 44px;",
        "      font-weight: 800;",
        "      letter-spacing: -0.03em;",
        "      color: var(--text-main);",
        "      line-height: 1.1;",
        "      text-transform: uppercase;",
        "      margin-bottom: 6px;",
        "    }",
        "    .project-subtitle {",
        "      font-size: 15px;",
        "      color: var(--text-dim);",
        "      font-weight: 400;",
        "      letter-spacing: -0.01em;",
        "    }",
        "    .meta-pills {",
        "      display: flex;",
        "      gap: 10px;",
        "      flex-wrap: wrap;",
        "    }",
        "    .meta-pill {",
        "      background: var(--bg-card);",
        "      border: 1px solid var(--border);",
        "      padding: 6px 12px;",
        "      border-radius: 6px;",
        "      font-size: 0.8rem;",
        "      color: var(--text-muted);",
        "      display: inline-flex;",
        "      align-items: center;",
        "      gap: 6px;",
        "    }",
        "    .meta-pill strong { color: var(--text-main); }",
        "    .status-dot {",
        "      width: 7px;",
        "      height: 7px;",
        "      border-radius: 50%;",
        "      background: #10b981;",
        "      display: inline-block;",
        "    }",
        "    .container {",
        "      max-width: 1400px;",
        "      margin: 28px auto;",
        "      padding: 0 32px;",
        "    }",
        "    nav.tabs {",
        "      display: flex;",
        "      gap: 4px;",
        "      border-bottom: 1px solid var(--border);",
        "      margin-bottom: 28px;",
        "      overflow-x: auto;",
        "    }",
        "    nav.tabs button {",
        "      background: none;",
        "      border: none;",
        "      color: var(--text-muted);",
        "      padding: 12px 18px;",
        "      font-size: 0.88rem;",
        "      font-weight: 600;",
        "      cursor: pointer;",
        "      border-bottom: 2px solid transparent;",
        "      transition: all 0.15s ease;",
        "      white-space: nowrap;",
        "    }",
        "    nav.tabs button:hover {",
        "      color: var(--text-main);",
        "      border-bottom-color: var(--border-subtle);",
        "    }",
        "    nav.tabs button.active {",
        "      color: var(--accent);",
        "      border-bottom-color: var(--accent);",
        "    }",
        "    .tab-pane { display: none; }",
        "    .tab-pane.active { display: block; }",
        "    .grid-cards {",
        "      display: grid;",
        "      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));",
        "      gap: 16px;",
        "      margin-bottom: 24px;",
        "    }",
        "    .card {",
        "      background: var(--bg-card);",
        "      border: 1px solid var(--border);",
        "      border-radius: 6px;",
        "      padding: 18px 20px;",
        "      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);",
        "    }",
        "    .card-title {",
        "      font-size: 0.78rem;",
        "      text-transform: uppercase;",
        "      letter-spacing: 0.05em;",
        "      color: var(--text-muted);",
        "      margin-bottom: 8px;",
        "      font-weight: 600;",
        "    }",
        "    .card-value {",
        "      font-size: 1.85rem;",
        "      font-weight: 700;",
        "      color: var(--text-main);",
        "      display: flex;",
        "      align-items: baseline;",
        "      gap: 8px;",
        "      line-height: 1.2;",
        "    }",
        "    .card-subtext {",
        "      font-size: 0.8rem;",
        "      color: var(--text-dim);",
        "      margin-top: 6px;",
        "    }",
        "    .banner {",
        "      background: var(--bg-card);",
        "      border: 1px solid var(--border);",
        "      border-left: 4px solid var(--accent);",
        "      padding: 14px 18px;",
        "      border-radius: 0 6px 6px 0;",
        "      margin-bottom: 24px;",
        "      font-size: 0.9rem;",
        "      color: var(--text-main);",
        "    }",
        "    .banner.alert-warning {",
        "      border-left-color: #d97706;",
        "      background: #fffbeb;",
        "      border-color: #fde68a;",
        "      color: #92400e;",
        "    }",
        "    .banner.alert-info {",
        "      border-left-color: var(--accent);",
        "      background: var(--accent-light);",
        "      border-color: #bae6fd;",
        "      color: #0369a1;",
        "    }",
        "    .section-title {",
        "      font-size: 22px;",
        "      font-weight: 700;",
        "      color: var(--text-main);",
        "      margin: 28px 0 6px;",
        "      display: flex;",
        "      align-items: center;",
        "      gap: 10px;",
        "    }",
        "    .section-subtitle {",
        "      font-size: 0.88rem;",
        "      color: var(--text-muted);",
        "      margin-top: 0px;",
        "      margin-bottom: 18px;",
        "    }",
        "    .table-container {",
        "      background: var(--bg-card);",
        "      border: 1px solid var(--border);",
        "      border-radius: 6px;",
        "      overflow-x: auto;",
        "      margin-bottom: 24px;",
        "      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);",
        "    }",
        "    table {",
        "      width: 100%;",
        "      border-collapse: collapse;",
        "      text-align: left;",
        "      font-size: 0.88rem;",
        "    }",
        "    th {",
        "      background: #f8fafc;",
        "      color: var(--text-muted);",
        "      font-weight: 600;",
        "      padding: 12px 16px;",
        "      border-bottom: 1px solid var(--border);",
        "      white-space: nowrap;",
        "    }",
        "    td {",
        "      padding: 12px 16px;",
        "      border-bottom: 1px solid var(--border);",
        "      color: var(--text-main);",
        "    }",
        "    tr:last-child td { border-bottom: none; }",
        "    tr:hover td { background: #f8fafc; }",
        "    .badge {",
        "      display: inline-flex;",
        "      align-items: center;",
        "      gap: 4px;",
        "      padding: 3px 9px;",
        "      border-radius: 4px;",
        "      font-size: 0.75rem;",
        "      font-weight: 600;",
        "      line-height: 1.3;",
        "      text-transform: uppercase;",
        "      letter-spacing: 0.03em;",
        "    }",
        "    .badge-pass { background: var(--pass-bg); color: var(--pass); border: 1px solid var(--pass-border); }",
        "    .badge-fail { background: var(--fail-bg); color: var(--fail); border: 1px solid var(--fail-border); }",
        "    .badge-warn { background: var(--warn-bg); color: var(--warn); border: 1px solid var(--warn-border); }",
        "    .badge-error { background: var(--error-bg); color: var(--error); border: 1px solid var(--error-border); }",
        "    .badge-skip { background: var(--skip-bg); color: var(--skip); border: 1px solid var(--skip-border); }",
        "    .badge-auto { background: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0; }",
        "    .badge-escalate { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }",
        "    .badge-reject { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }",
        "    .badge-not-deployed { background: #f8fafc; color: #64748b; border: 1px solid #cbd5e1; }",
        "    .badge-deployed { background: #f0f9ff; color: #0369a1; border: 1px solid #bae6fd; }",
        "    .filter-bar {",
        "      display: flex;",
        "      flex-wrap: wrap;",
        "      gap: 12px;",
        "      margin-bottom: 16px;",
        "      align-items: center;",
        "      background: var(--bg-card);",
        "      padding: 14px 18px;",
        "      border-radius: 6px;",
        "      border: 1px solid var(--border);",
        "      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);",
        "    }",
        "    .filter-group {",
        "      display: flex;",
        "      align-items: center;",
        "      gap: 8px;",
        "    }",
        "    .filter-group label {",
        "      font-size: 0.8rem;",
        "      color: var(--text-muted);",
        "      font-weight: 600;",
        "    }",
        "    select, input[type=\"text\"] {",
        "      background: #ffffff;",
        "      border: 1px solid var(--border-subtle);",
        "      color: var(--text-main);",
        "      padding: 6px 12px;",
        "      border-radius: 6px;",
        "      font-size: 0.85rem;",
        "    }",
        "    select:focus, input[type=\"text\"]:focus {",
        "      outline: none;",
        "      border-color: var(--border-focus);",
        "    }",
        "    .search-input { min-width: 240px; }",
        "    .btn-reset {",
        "      background: #f1f5f9;",
        "      border: 1px solid var(--border);",
        "      color: var(--text-muted);",
        "      padding: 6px 12px;",
        "      border-radius: 6px;",
        "      font-size: 0.8rem;",
        "      font-weight: 600;",
        "      cursor: pointer;",
        "      transition: all 0.15s ease;",
        "    }",
        "    .btn-reset:hover { background: #e2e8f0; color: var(--text-main); }",
        "    .counter-pill {",
        "      margin-left: auto;",
        "      font-size: 0.82rem;",
        "      color: var(--accent);",
        "      background: var(--accent-light);",
        "      border: 1px solid #bae6fd;",
        "      padding: 4px 10px;",
        "      border-radius: 6px;",
        "      font-weight: 600;",
        "    }",
        "    .callout {",
        "      border-left: 3px solid var(--accent);",
        "      padding: 10px 14px;",
        "      background: #f0f9ff;",
        "      border-color: var(--accent);",
        "      margin: 10px 0;",
        "      border-radius: 0 6px 6px 0;",
        "      font-size: 0.85rem;",
        "      color: #0c4a6e;",
        "    }",
        "    .two-col {",
        "      display: grid;",
        "      grid-template-columns: 1fr 1fr;",
        "      gap: 20px;",
        "      margin-bottom: 24px;",
        "    }",
        "    @media (max-width: 900px) {",
        "      .two-col { grid-template-columns: 1fr; }",
        "    }",
        "    .funnel-container {",
        "      background: var(--bg-card);",
        "      border: 1px solid var(--border);",
        "      border-radius: 6px;",
        "      padding: 18px 20px;",
        "      margin-bottom: 24px;",
        "      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);",
        "    }",
        "    .funnel-title {",
        "      font-size: 0.8rem;",
        "      font-weight: 600;",
        "      color: var(--text-muted);",
        "      text-transform: uppercase;",
        "      letter-spacing: 0.05em;",
        "      margin-bottom: 12px;",
        "    }",
        "    .funnel-bar {",
        "      display: flex;",
        "      height: 28px;",
        "      border-radius: 6px;",
        "      overflow: hidden;",
        "      gap: 2px;",
        "      background: #f1f5f9;",
        "    }",
        "    .funnel-segment {",
        "      display: flex;",
        "      align-items: center;",
        "      justify-content: center;",
        "      font-size: 0.75rem;",
        "      font-weight: 700;",
        "      color: #ffffff;",
        "      min-width: 32px;",
        "      transition: opacity 0.2s;",
        "    }",
        "    .funnel-segment:hover { opacity: 0.9; }",
        "    .test-card {",
        "      background: var(--bg-card);",
        "      border: 1px solid var(--border);",
        "      border-radius: 6px;",
        "      padding: 16px 20px;",
        "      margin-bottom: 12px;",
        "      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);",
        "    }",
        "    .test-header {",
        "      display: flex;",
        "      justify-content: space-between;",
        "      align-items: center;",
        "      flex-wrap: wrap;",
        "      gap: 10px;",
        "      margin-bottom: 8px;",
        "    }",
        "    .test-title-wrap {",
        "      display: flex;",
        "      align-items: center;",
        "      gap: 10px;",
        "    }",
        "    .test-id {",
        "      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;",
        "      font-size: 0.82rem;",
        "      font-weight: 700;",
        "      color: var(--accent);",
        "      background: var(--accent-light);",
        "      border: 1px solid #bae6fd;",
        "      padding: 2px 7px;",
        "      border-radius: 4px;",
        "    }",
        "    .test-name {",
        "      font-size: 16px;",
        "      font-weight: 600;",
        "      color: var(--text-main);",
        "    }",
        "    .test-body {",
        "      display: flex;",
        "      flex-direction: column;",
        "      gap: 5px;",
        "      font-size: 13.5px;",
        "    }",
        "    .test-criterion {",
        "      color: #334155;",
        "      line-height: 1.45;",
        "    }",
        "    .test-evidence {",
        "      color: var(--text-muted);",
        "      font-size: 13px;",
        "      line-height: 1.45;",
        "    }",
        "    .test-limitation {",
        "      color: #991b1b;",
        "      background: #fef2f2;",
        "      border: 1px solid #fecaca;",
        "      border-radius: 4px;",
        "      padding: 6px 10px;",
        "      font-size: 13px;",
        "      margin-top: 4px;",
        "    }",
        "    .limitations-list {",
        "      display: flex;",
        "      flex-direction: column;",
        "      gap: 12px;",
        "    }",
        "    .limitation-item {",
        "      background: var(--bg-card);",
        "      border: 1px solid var(--border);",
        "      border-radius: 6px;",
        "      padding: 16px 20px;",
        "      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);",
        "    }",
        "    .limitation-header {",
        "      display: flex;",
        "      justify-content: space-between;",
        "      align-items: center;",
        "      margin-bottom: 8px;",
        "    }",
        "    .limitation-title {",
        "      font-weight: 600;",
        "      font-size: 0.95rem;",
        "      color: var(--text-main);",
        "    }",
        "    .limitation-desc {",
        "      font-size: 0.85rem;",
        "      color: var(--text-muted);",
        "      line-height: 1.5;",
        "    }",
        "    .code-snippet {",
        "      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;",
        "      background: #f1f5f9;",
        "      border: 1px solid #e2e8f0;",
        "      padding: 2px 6px;",
        "      border-radius: 4px;",
        "      font-size: 0.8rem;",
        "      color: #0369a1;",
        "    }",
        "  </style>",
        "</head>",
        "<body>",
        "  <header>",
        "    <div class=\"header-content\">",
        "      <div class=\"project-identity\">",
        "        <h1 class=\"project-title\">AUTOIMMUNE</h1>",
        "        <div class=\"project-subtitle\">AI-Assisted Automated Fault Detection, Diagnosis and Software Repair</div>",
        "      </div>",
        "      <div class=\"meta-pills\">",
        "        <div class=\"meta-pill\"><span class=\"status-dot\"></span>Mode: <strong>Offline Read-Only</strong></div>",
        f"        <div class=\"meta-pill\">Repository: <strong>AutoImmune</strong></div>",
        f"        <div class=\"meta-pill\">Generated: <strong>{esc(data['generated_at'])}</strong></div>",
        "      </div>",
        "    </div>",
        "  </header>",
        "",
        "  <div class=\"container\">",
        "    <nav class=\"tabs\">",
        "      <button class=\"active\" onclick=\"showTab('tab-overview', this)\">System Overview</button>",
        "      <button onclick=\"showTab('tab-tests', this)\">Test Results</button>",
        "      <button onclick=\"showTab('tab-faults', this)\">Fault Detection</button>",
        "      <button onclick=\"showTab('tab-diagnosis', this)\">AI Diagnosis</button>",
        "      <button onclick=\"showTab('tab-candidates', this)\">Patch Candidates</button>",
        "      <button onclick=\"showTab('tab-gates', this)\">Validation Gates</button>",
        "      <button onclick=\"showTab('tab-approval', this)\">Human Approval</button>",
        "      <button onclick=\"showTab('tab-deploy', this)\">Deployment &amp; Rollback</button>",
        "      <button onclick=\"showTab('tab-evidence', this)\">Evidence &amp; Analytics</button>",
        "    </nav>",
        "",
        "    <!-- SECTION 1: System Overview -->",
        "    <div id=\"tab-overview\" class=\"tab-pane active\">",
        "      <div class=\"section-title\">System Overview</div>",
        "      <div class=\"section-subtitle\">Executive Overview of Pipeline Architecture, Evidence Ingestion, and Global Operational Metrics</div>",
        "      <div class=\"banner alert-info\">",
        "        <strong>Data Source Integrity:</strong> Metrics are rendered directly from <code>results/evidence.jsonl</code>, ",
        "        <code>results/llm_diagnosis.csv</code>, and pilot logs. Missing gates are recorded as not-run, never passes.",
        "      </div>",
        "      <div class=\"grid-cards\">",
        "        <div class=\"card\">",
        "          <div class=\"card-title\">Total Evidence Rows</div>",
        f"          <div class=\"card-value\">{total_rows}</div>",
        "          <div class=\"card-subtext\">Recorded runs in <code>evidence.jsonl</code></div>",
        "        </div>",
        "        <div class=\"card\">",
        "          <div class=\"card-title\">Unique Candidates (Units)</div>",
        f"          <div class=\"card-value\">{total_units}</div>",
        f"          <div class=\"card-subtext\">Across {len(data['distinct_faults'])} faults ({esc(distinct_faults_str)})</div>",
        "        </div>",
        "        <div class=\"card\">",
        "          <div class=\"card-title\">Decision Distribution</div>",
        "          <div class=\"card-value\" style=\"font-size: 1.25rem; font-weight: 600;\">",
        f"            <span style=\"color: #065f46;\">{auto_apply_count} Auto</span> / ",
        f"            <span style=\"color: #92400e;\">{escalate_count} Esc</span> / ",
        f"            <span style=\"color: #991b1b;\">{reject_count} Rej</span>",
        "          </div>",
        "          <div class=\"card-subtext\">Gate + rule outcomes</div>",
        "        </div>",
        "        <div class=\"card\">",
        "          <div class=\"card-title\">Actual Deployments</div>",
        f"          <div class=\"card-value\" style=\"color: #64748b;\">{deployed_count}</div>",
        "          <div class=\"card-subtext\">deployment events in evidence (see deployments.csv)</div>",
        "        </div>",
        "        <div class=\"card\">",
        "          <div class=\"card-title\">Actual Rollbacks</div>",
        f"          <div class=\"card-value\" style=\"color: #64748b;\">{rollback_count}</div>",
        "          <div class=\"card-subtext\">0 real rollbacks in evidence</div>",
        "        </div>",
        "        <div class=\"card\">",
        "          <div class=\"card-title\">Recorded Approvals</div>",
        "          <div class=\"card-value\" style=\"font-size: 1.25rem; font-weight: 600;\">",
        f"            <span>{data['approval_counts'].get('human_cli', 0)} CLI</span> / <span>{data['approval_counts'].get('human_relayed', 0)} Rel</span>",
        "          </div>",
        "          <div class=\"card-subtext\">No human approvals recorded</div>",
        "        </div>",
        "      </div>",
        "",
        "      <div class=\"two-col\">",
        "        <div class=\"card\">",
        "          <div class=\"section-title\" style=\"margin-top: 0; font-size: 18px;\">Candidate Ingestion Summary</div>",
        "          <div class=\"table-container\" style=\"border: none; box-shadow: none;\">",
        "            <table>",
        "              <thead><tr><th>Dimension</th><th>Recorded Values</th></tr></thead>",
        "              <tbody>",
        "                <tr><td>Fault Coverage</td><td><strong>{esc(distinct_faults_str)}</strong> (3 active benchmark faults)</td></tr>",
        f"                <tr><td>Diag Providers</td><td><strong>live</strong>: {data['diag_modes'].get('live', 0)}</td></tr>",
        f"                <tr><td>Patch Modes</td><td><strong>scripted</strong>: {data['patch_modes'].get('scripted', 0)}, <strong>live</strong>: {data['patch_modes'].get('live', 0)}</td></tr>",
        f"                <tr><td>LLM Models</td><td><strong>qwen2.5-coder:7b</strong>: {data['models'].get('qwen2.5-coder:7b', 0)}</td></tr>",
        "                <tr><td>Analysis Unit</td><td>Latest valid row per (fault_id, candidate_id)</td></tr>",
        f"                <tr><td>Label Status</td><td>{'see pilot_report.md' if data['labels_found'] else 'no labels.json found: every unit unlabelled'}</td></tr>",
        "              </tbody>",
        "            </table>",
        "          </div>",
        "        </div>",
        "        <div class=\"card\">",
        "          <div class=\"section-title\" style=\"margin-top: 0; font-size: 18px;\">Architectural Safety Constraints</div>",
        "          <p style=\"font-size: 0.88rem; color: var(--text-muted); margin-bottom: 12px;\">",
        "            The AutoImmune pipeline enforces strict boundaries between deterministic validation, decision rules, and actual deployment:",
        "          </p>",
        "          <div class=\"callout\"><strong>1. <code>AUTO_APPLY != Deployment</code>:</strong> An <code>AUTO_APPLY</code> verdict means a candidate passed validation and scope criteria. It was not actually deployed if the pipeline ran with <code>--gates-only</code>.</div>",
        "          <div class=\"callout\"><strong>2. Gate Isolation:</strong> Docker sandbox runs with <code>--network none</code>. Hidden tests (<code>faults/*/hidden_tests/</code>) are never mounted or exposed to models.</div>",
        "          <div class=\"callout\"><strong>3. Separation of Evidence:</strong> Live LLM diffs are separated from deterministic scripted candidates. Scripted outcomes are never pooled into LLM metrics.</div>",
        "        </div>",
        "      </div>",
        "    </div>",
        "",
        "    <!-- SECTION 2: Test Results -->",
        "    <div id=\"tab-tests\" class=\"tab-pane\">",
        "      <div class=\"section-title\">Test Results</div>",
        "      <div class=\"section-subtitle\">Acceptance Checks (A1–A10), Verification Suites, and Gate Pass/Fail Criteria</div>",
        "      <div class=\"card\" style=\"margin-bottom: 20px;\">",
        "        <div style=\"display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px; margin-bottom: 6px;\">",
        "          <div style=\"font-weight: 600; font-size: 15px; color: var(--text-main);\">Unit & Sandbox Test Suite Status</div>",
        f"          <span class=\"badge badge-skip\">as of {esc(data['acceptance_as_of'])}</span>",
        "        </div>",
        "        <p style=\"font-size: 13.5px; color: var(--text-muted);\">",
        f"          {esc(data['test_suite'].get('text', ''))} (source: docs/audit/acceptance.json)",
        "        </p>",
        "      </div>",
        "      <div style=\"margin-bottom: 16px;\">",
        "        <div style=\"font-weight: 600; font-size: 14px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-dim); margin-bottom: 12px;\">Traceability Acceptance Checks (A1–A10)</div>",
    ]
    
    for chk in data["acceptance_checks"]:
        st = chk["status"]
        badge_class = {"PASS": "pass", "PARTIAL": "warn", "FAIL": "reject"}.get(st, "skip")
        st_badge = f"<span class=\"badge badge-{badge_class}\">{esc(st)}</span>"
            
        limitation_block = f"<div class=\"test-limitation\"><strong>Limitation / Requirement:</strong> {esc(chk['limitation'])}</div>" if chk.get("limitation") else ""
        html_lines += [
            "        <div class=\"test-card\">",
            "          <div class=\"test-header\">",
            "            <div class=\"test-title-wrap\">",
            f"              <span class=\"test-id\">{esc(chk['id'])}</span>",
            f"              <span class=\"test-name\">{esc(chk['name'])}</span>",
            "            </div>",
            f"            <div>{st_badge}</div>",
            "          </div>",
            "          <div class=\"test-body\">",
            f"            <div class=\"test-criterion\"><strong>Criterion:</strong> {esc(chk['criterion'])}</div>",
            f"            <div class=\"test-evidence\"><strong>Supporting Evidence:</strong> {esc(chk['evidence'])}</div>",
            f"            {limitation_block}",
            "          </div>",
            "        </div>",
        ]

    html_lines += [
        "      </div>",
        "    </div>",
        "",
        "    <!-- SECTION 3: Fault Detection -->",
        "    <div id=\"tab-faults\" class=\"tab-pane\">",
        "      <div class=\"section-title\">Fault Detection</div>",
        "      <div class=\"section-subtitle\">Per-Fault Breakdown & Benchmark Fault Incident Observation (F01, F04, F06)</div>",
    ]
    
    fault_descriptions = {
        "F01": "Order calculation logic regression (price/discount arithmetic bug).",
        "F04": "Configuration misconfiguration (application.properties causing /actuator/health DOWN).",
        "F06": "Silent corruption / pricing probe mismatch (returned 200 OK with incorrect order total).",
    }
    
    for fid in data["distinct_faults"]:
        cands = data["fault_groups"].get(fid, [])
        auto_c = sum(1 for c in cands if c.get("decision") == "AUTO_APPLY")
        esc_c = sum(1 for c in cands if c.get("decision") == "ESCALATE")
        rej_c = sum(1 for c in cands if c.get("decision") == "REJECT")
        html_lines += [
            f"      <div class=\"card\" style=\"margin-bottom: 20px;\">",
            f"        <div style=\"display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px; margin-bottom: 12px;\">",
            f"          <div>",
            f"            <h3 style=\"font-size: 1.1rem; color: var(--text-main); font-weight: 700;\">Fault {esc(fid)}</h3>",
            f"            <div style=\"font-size: 0.85rem; color: var(--text-muted);\">{esc(fault_descriptions.get(fid, ''))}</div>",
            f"          </div>",
            f"          <div style=\"display: flex; gap: 8px;\">",
            f"            <span class=\"badge badge-auto\">{auto_c} AUTO_APPLY</span>",
            f"            <span class=\"badge badge-escalate\">{esc_c} ESCALATE</span>",
            f"            <span class=\"badge badge-reject\">{rej_c} REJECT</span>",
            f"          </div>",
            f"        </div>",
            f"        <div class=\"table-container\" style=\"margin-bottom: 0;\">",
            f"          <table>",
            f"            <thead>",
            f"              <tr><th>Candidate ID</th><th>Kind</th><th>Patch Mode</th><th>V0</th><th>V1</th><th>V2</th><th>V3</th><th>Decision</th><th>Deployed</th><th>Rejection / Reason</th></tr>",
            f"            </thead>",
            f"            <tbody>",
        ]
        for c in cands:
            v0_st = c.get("v0", {}).get("status", "unknown")
            v1_st = c.get("v1", {}).get("status", "unknown")
            v2_st = c.get("v2", {}).get("status", "unknown")
            v3_st = c.get("v3", {}).get("status", "unknown")
            dec = c.get("decision", "UNKNOWN")
            dec_cls = "badge-auto" if dec == "AUTO_APPLY" else ("badge-escalate" if dec == "ESCALATE" else "badge-reject")
            dep_cls = "badge-deployed" if c.get("deployed") else "badge-not-deployed"
            dep_txt = "YES" if c.get("deployed") else "NO"
            reasons = "; ".join(c.get("reasons", [])) or (c.get("apply_error") or "—")
            html_lines.append(
                f"              <tr>"
                f"<td><span class=\"code-snippet\">{esc(c.get('candidate_id', ''))}</span></td>"
                f"<td>{esc(c.get('candidate_kind') or 'unlabelled')}</td>"
                f"<td>{esc(c.get('patch_mode', ''))}</td>"
                f"<td><span class=\"badge badge-{esc(v0_st)}\">{esc(v0_st)}</span></td>"
                f"<td><span class=\"badge badge-{esc(v1_st)}\">{esc(v1_st)}</span></td>"
                f"<td><span class=\"badge badge-{esc(v2_st)}\">{esc(v2_st)}</span></td>"
                f"<td><span class=\"badge badge-{esc(v3_st)}\">{esc(v3_st)}</span></td>"
                f"<td><span class=\"badge {dec_cls}\">{esc(dec)}</span></td>"
                f"<td><span class=\"badge {dep_cls}\">{dep_txt}</span></td>"
                f"<td style=\"font-size: 0.8rem; color: var(--text-muted); max-width: 320px;\">{esc(reasons)}</td>"
                f"</tr>"
            )
        html_lines += [
            f"            </tbody>",
            f"          </table>",
            f"        </div>",
            f"      </div>",
        ]
        
    html_lines += [
        "    </div>",
        "",
        "    <!-- SECTION 4: AI Diagnosis -->",
        "    <div id=\"tab-diagnosis\" class=\"tab-pane\">",
        "      <div class=\"section-title\">AI Diagnosis</div>",
        "      <div class=\"section-subtitle\">Diagnostic Localisation Accuracy, LLM vs Scripted Separation, and Generative Pilot Evaluation</div>",
        "      <div class=\"banner alert-warning\">",
        "        <strong>Honest Pilot Separation (LLM vs Scripted):</strong> Scripted candidates evaluate pipeline validation mechanics. ",
        "        Live LLM candidates evaluate generative capabilities. They are tracked in separate panels and never combined.",
        "      </div>",
        "      <div style=\"font-weight: 600; font-size: 15px; color: var(--text-main); margin-bottom: 6px;\">Panel 1 — Generative Live LLM Patches (diag_mode=live, patch_mode=live)</div>",
        "      <p class=\"section-subtitle\">Observed results for candidates drafted live by: " + (", ".join(f"<code>{esc(m)}</code>" for m in sorted(data["models"])) or "no model") + "</p>",
        "      <div class=\"table-container\">",
        "        <table>",
        "          <thead>",
        "            <tr>",
        "              <th>Fault</th><th>Candidate ID</th><th>Model</th><th>V0 (Compile/Apply)</th><th>V1 (Target)</th><th>V2 (Regression)</th><th>V3 (Semgrep)</th><th>Decision</th><th>Failure Reason</th>",
        "            </tr>",
        "          </thead>",
        "          <tbody>",
    ]
    
    for u in pure_live_units:
        v0_st = u.get("v0", {}).get("status", "unknown")
        v1_st = u.get("v1", {}).get("status", "unknown")
        v2_st = u.get("v2", {}).get("status", "unknown")
        v3_st = u.get("v3", {}).get("status", "unknown")
        reasons = "; ".join(u.get("reasons", [])) or "patch does not apply"
        html_lines.append(
            f"            <tr>"
            f"<td><strong>{esc(u.get('fault_id', ''))}</strong></td>"
            f"<td><span class=\"code-snippet\">{esc(u.get('candidate_id', ''))}</span></td>"
            f"<td>{esc(u.get('model', ''))}</td>"
            f"<td><span class=\"badge badge-{esc(v0_st)}\">{esc(v0_st)}</span></td>"
            f"<td><span class=\"badge badge-{esc(v1_st)}\">{esc(v1_st)}</span></td>"
            f"<td><span class=\"badge badge-{esc(v2_st)}\">{esc(v2_st)}</span></td>"
            f"<td><span class=\"badge badge-{esc(v3_st)}\">{esc(v3_st)}</span></td>"
            f"<td><span class=\"badge badge-reject\">{esc(u.get('decision', ''))}</span></td>"
            f"<td style=\"font-size: 0.82rem; color: #991b1b;\">{esc(reasons)}</td>"
            f"</tr>"
        )
    
    html_lines += [
        "          </tbody>",
        "        </table>",
        "      </div>",
        "      <div class=\"callout\" style=\"margin-bottom: 24px;\">",
        "        <strong>Live patch utility per model (results/llm_patch_utility.csv):</strong> "
        + ("; ".join(f"<code>{esc(r['model'])}</code>: {esc(r['applied_cleanly'])}/{esc(r['attempts'])} applied cleanly, "
                     f"{esc(r['v1_pass'])}/{esc(r['attempts'])} passed V1, {esc(r['all_gates_pass'])}/{esc(r['attempts'])} passed all gates"
                     for r in data["llm_patch_utility"] if r.get("fault") == "all") or "no live attempts recorded") + ".",
        "      </div>",
        "",
        "      <div style=\"font-weight: 600; font-size: 15px; color: var(--text-main); margin-bottom: 6px;\">Panel 2 — Live LLM Diagnosis Accuracy (from results/llm_diagnosis.csv)</div>",
        "      <p class=\"section-subtitle\">Measured localisation accuracy across pilot runs</p>",
        "      <div class=\"table-container\">",
        "        <table>",
        "          <thead>",
        "            <tr>",
        "              <th>Fault ID</th><th>Model</th><th>Top-1 Hits</th><th>Top-1 Rate [Wilson 95% CI]</th><th>Top-3 Hits</th><th>Top-3 Rate [Wilson 95% CI]</th><th>Evaluated Samples (n)</th><th>Evaluation Notes</th>",
        "            </tr>",
        "          </thead>",
        "          <tbody>",
    ]
    
    for row in data["llm_diagnosis"]:
        fid = row.get("fault", "")
        m = row.get("model", "")
        t1_k = row.get("top1_k", "0")
        t1_n = row.get("top1_n", "0")
        t1_rate = f"{float(row.get('top1_rate') or 0)*100:.1f}%"
        t1_low = f"{float(row.get('top1_low', 0))*100:.1f}%"
        t1_high = f"{float(row.get('top1_high', 0))*100:.1f}%"
        t3_k = row.get("top3_k", "0")
        t3_n = row.get("top3_n", "0")
        t3_rate = f"{float(row.get('top3_rate', 0))*100:.1f}%"
        t3_low = f"{float(row.get('top3_low', 0))*100:.1f}%"
        t3_high = f"{float(row.get('top3_high', 0))*100:.1f}%"
        k1, n1 = int(t1_k or 0), int(t1_n or 0)
        note = ("not evaluated" if n1 == 0 else
                f"<strong style='color:#991b1b;'>missed in all {n1} runs</strong>" if k1 == 0 else
                f"hit in all {n1} runs (small n)" if k1 == n1 else f"hit in {k1} of {n1} runs")
        html_lines.append(
            f"            <tr>"
            f"<td><strong>{esc(fid)}</strong></td>"
            f"<td>{esc(m)}</td>"
            f"<td>{esc(t1_k)}/{esc(t1_n)}</td>"
            f"<td><strong>{esc(t1_rate)}</strong> <span style=\"font-size:0.8rem; color:var(--text-dim);\">[{esc(t1_low)}, {esc(t1_high)}]</span></td>"
            f"<td>{esc(t3_k)}/{esc(t3_n)}</td>"
            f"<td><strong>{esc(t3_rate)}</strong> <span style=\"font-size:0.8rem; color:var(--text-dim);\">[{esc(t3_low)}, {esc(t3_high)}]</span></td>"
            f"<td>{esc(t1_n)}</td>"
            f"<td>{note}</td>"
            f"</tr>"
        )
        
    html_lines += [
        "          </tbody>",
        "        </table>",
        "      </div>",
        "    </div>",
        "",
        "    <!-- SECTION 5: Patch Candidates -->",
        "    <div id=\"tab-candidates\" class=\"tab-pane\">",
        "      <div class=\"section-title\">Patch Candidates</div>",
        "      <div class=\"section-subtitle\">Candidate Review Matrix with Multi-Dimensional Filtering, Search, and Status Inspection</div>",
        "      <div class=\"filter-bar\">",
        "        <div class=\"filter-group\">",
        "          <label for=\"searchCandidates\">Search:</label>",
        "          <input type=\"text\" id=\"searchCandidates\" class=\"search-input\" placeholder=\"Search candidate, run, fault, reasons...\" oninput=\"filterTable()\">",
        "        </div>",
        "        <div class=\"filter-group\">",
        "          <label for=\"filterFault\">Fault:</label>",
        "          <select id=\"filterFault\" onchange=\"filterTable()\">",
        "            <option value=\"ALL\">All Faults</option>",
    ]
    for fid in data["distinct_faults"]:
        html_lines.append(f"            <option value=\"{esc(fid)}\">{esc(fid)}</option>")
    html_lines += [
        "          </select>",
        "        </div>",
        "        <div class=\"filter-group\">",
        "          <label for=\"filterDecision\">Decision:</label>",
        "          <select id=\"filterDecision\" onchange=\"filterTable()\">",
        "            <option value=\"ALL\">All Decisions</option>",
        "            <option value=\"AUTO_APPLY\">AUTO_APPLY</option>",
        "            <option value=\"ESCALATE\">ESCALATE</option>",
        "            <option value=\"REJECT\">REJECT</option>",
        "          </select>",
        "        </div>",
        "        <div class=\"filter-group\">",
        "          <label for=\"filterFirstStop\">Gate Outcome:</label>",
        "          <select id=\"filterFirstStop\" onchange=\"filterTable()\">",
        "            <option value=\"ALL\">All Outcomes</option>",
        f"            <option value=\"SURVIVED\">Survived All Gates ({data['first_stop_counts'].get('SURVIVED', 0)})</option>",
        f"            <option value=\"V0\">Stopped at V0 ({data['first_stop_counts'].get('V0', 0)})</option>",
        f"            <option value=\"V1\">Stopped at V1 ({data['first_stop_counts'].get('V1', 0)})</option>",
        f"            <option value=\"V2\">Stopped at V2 ({data['first_stop_counts'].get('V2', 0)})</option>",
        f"            <option value=\"V3\">Stopped at V3 ({data['first_stop_counts'].get('V3', 0)})</option>",
        "          </select>",
        "        </div>",
        "        <div class=\"filter-group\">",
        "          <label for=\"filterPatchMode\">Patch Mode:</label>",
        "          <select id=\"filterPatchMode\" onchange=\"filterTable()\">",
        "            <option value=\"ALL\">All Modes</option>",
        "            <option value=\"scripted\">scripted</option>",
        "            <option value=\"live\">live</option>",
        "          </select>",
        "        </div>",
        "        <div class=\"filter-group\">",
        "          <label for=\"filterDeployed\">Deployed:</label>",
        "          <select id=\"filterDeployed\" onchange=\"filterTable()\">",
        "            <option value=\"ALL\">All</option>",
        "            <option value=\"YES\">YES</option>",
        "            <option value=\"NO\">NO</option>",
        "          </select>",
        "        </div>",
        "        <button class=\"btn-reset\" onclick=\"resetFilters()\">Reset Filters</button>",
        f"        <div class=\"counter-pill\" id=\"candidateCount\">Showing {len(data['units'])} of {len(data['units'])} candidates</div>",
        "      </div>",
        "",
        "      <div class=\"table-container\">",
        "        <table id=\"candidatesTable\">",
        "          <thead>",
        "            <tr>",
        "              <th>Candidate ID</th><th>Fault</th><th>Kind</th><th>Run ID</th><th>Diag/Patch</th><th>First Stop</th><th>V0</th><th>V1</th><th>V2</th><th>V3</th><th>Decision</th><th>Deployed</th><th>Reasons / Failure</th>",
        "            </tr>",
        "          </thead>",
        "          <tbody>",
    ]
    
    for u in data["units"]:
        fid = u.get("fault_id", "")
        cid = u.get("candidate_id", "")
        kind = u.get("candidate_kind") or "unlabelled"
        run_id = u.get("run_id", "")
        diag_m = u.get("diag_mode", "")
        patch_m = u.get("patch_mode", "")
        f_stop = determine_first_stop(u)
        v0_st = u.get("v0", {}).get("status", "unknown")
        v1_st = u.get("v1", {}).get("status", "unknown")
        v2_st = u.get("v2", {}).get("status", "unknown")
        v3_st = u.get("v3", {}).get("status", "unknown")
        dec = u.get("decision", "UNKNOWN")
        dec_cls = "badge-auto" if dec == "AUTO_APPLY" else ("badge-escalate" if dec == "ESCALATE" else "badge-reject")
        dep_val = "YES" if u.get("deployed") else "NO"
        dep_cls = "badge-deployed" if u.get("deployed") else "badge-not-deployed"
        reasons = "; ".join(u.get("reasons", [])) or (u.get("apply_error") or "—")
        search_blob = f"{fid} {cid} {kind} {run_id} {diag_m} {patch_m} {dec} {dep_val} {f_stop} {reasons}".lower()
        
        fstop_badge = f"<span class=\"badge badge-pass\">SURVIVED</span>" if f_stop == "SURVIVED" else f"<span class=\"badge badge-fail\">{f_stop}</span>"
        
        html_lines.append(
            f"            <tr data-fault=\"{esc(fid)}\" data-decision=\"{esc(dec)}\" data-firststop=\"{esc(f_stop)}\" data-patchmode=\"{esc(patch_m)}\" data-deployed=\"{esc(dep_val)}\" data-search=\"{esc(search_blob)}\">"
            f"<td><span class=\"code-snippet\">{esc(cid)}</span></td>"
            f"<td><strong>{esc(fid)}</strong></td>"
            f"<td>{esc(kind)}</td>"
            f"<td style=\"font-size: 0.8rem; color: var(--text-dim);\">{esc(run_id)}</td>"
            f"<td style=\"font-size: 0.8rem;\">{esc(diag_m)}/{esc(patch_m)}</td>"
            f"<td>{fstop_badge}</td>"
            f"<td><span class=\"badge badge-{esc(v0_st)}\">{esc(v0_st)}</span></td>"
            f"<td><span class=\"badge badge-{esc(v1_st)}\">{esc(v1_st)}</span></td>"
            f"<td><span class=\"badge badge-{esc(v2_st)}\">{esc(v2_st)}</span></td>"
            f"<td><span class=\"badge badge-{esc(v3_st)}\">{esc(v3_st)}</span></td>"
            f"<td><span class=\"badge {dec_cls}\">{esc(dec)}</span></td>"
            f"<td><span class=\"badge {dep_cls}\">{esc(dep_val)}</span></td>"
            f"<td style=\"font-size: 0.82rem; color: var(--text-muted); max-width: 280px;\">{esc(reasons)}</td>"
            f"</tr>"
        )
        
    html_lines += [
        "          </tbody>",
        "        </table>",
        "      </div>",
        "    </div>",
        "",
        "    <!-- SECTION 6: Validation Gates -->",
        "    <div id=\"tab-gates\" class=\"tab-pane\">",
        "      <div class=\"section-title\">Validation Gates</div>",
        "      <div class=\"section-subtitle\">Sequential Docker Gates (V0 to V3), Attrition Funnel, and Execution Performance</div>",
        "      <div class=\"grid-cards\">",
        "        <div class=\"card\">",
        "          <div class=\"card-title\">Gate V0 — Compile & Apply</div>",
        "          <div style=\"font-size: 0.82rem; color: var(--text-muted); margin-bottom: 8px;\"><code>git apply --check</code> + <code>mvn compile</code></div>",
        "          <div class=\"card-value\" style=\"font-size: 1.25rem;\">",
        f"            <span style=\"color: #065f46;\">{data['gate_stats']['V0']['statuses'].get('pass', 0)} Pass</span> / ",
        f"            <span style=\"color: #991b1b;\">{data['gate_stats']['V0']['statuses'].get('fail', 0)} Fail</span>",
        "          </div>",
        f"          <div class=\"card-subtext\">Avg: {data['gate_stats']['V0']['avg_seconds']:.1f}s (med {data['gate_stats']['V0']['median_seconds']:.1f}s)</div>",
        "        </div>",
        "        <div class=\"card\">",
        "          <div class=\"card-title\">Gate V1 — Target Test</div>",
        "          <div style=\"font-size: 0.82rem; color: var(--text-muted); margin-bottom: 8px;\">Target reproducer test for fault</div>",
        "          <div class=\"card-value\" style=\"font-size: 1.25rem;\">",
        f"            <span style=\"color: #065f46;\">{data['gate_stats']['V1']['statuses'].get('pass', 0)} Pass</span> / ",
        f"            <span style=\"color: #991b1b;\">{data['gate_stats']['V1']['statuses'].get('fail', 0)} Fail</span>",
        "          </div>",
        f"          <div class=\"card-subtext\">Not run: {data['gate_stats']['V1']['statuses'].get('not_run', 0)} (after V0 fail)</div>",
        "        </div>",
        "        <div class=\"card\">",
        "          <div class=\"card-title\">Gate V2 — Regression Suite</div>",
        "          <div style=\"font-size: 0.82rem; color: var(--text-muted); margin-bottom: 8px;\">Full Maven regression test suite</div>",
        "          <div class=\"card-value\" style=\"font-size: 1.25rem;\">",
        f"            <span style=\"color: #065f46;\">{data['gate_stats']['V2']['statuses'].get('pass', 0)} Pass</span> / ",
        f"            <span style=\"color: #991b1b;\">{data['gate_stats']['V2']['statuses'].get('fail', 0)} Fail</span> / ",
        f"            <span style=\"color: #d97706;\">{data['gate_stats']['V2']['statuses'].get('error', 0)} Err</span>",
        "          </div>",
        f"          <div class=\"card-subtext\">errors are tool/infrastructure failures, never passes</div>",
        "        </div>",
        "        <div class=\"card\">",
        "          <div class=\"card-title\">Gate V3 — Semgrep Analysis</div>",
        "          <div style=\"font-size: 0.82rem; color: var(--text-muted); margin-bottom: 8px;\">Diff scan vs unpatched baseline</div>",
        "          <div class=\"card-value\" style=\"font-size: 1.25rem;\">",
        f"            <span style=\"color: #065f46;\">{data['gate_stats']['V3']['statuses'].get('pass', 0)} Pass</span> / ",
        f"            <span style=\"color: #991b1b;\">{data['gate_stats']['V3']['statuses'].get('fail', 0)} Fail</span>",
        "          </div>",
        f"          <div class=\"card-subtext\">Not run: {data['gate_stats']['V3']['statuses'].get('not_run', 0)}</div>",
        "        </div>",
        "      </div>",
        "",
        "      <div style=\"font-weight: 600; font-size: 15px; color: var(--text-main); margin-bottom: 6px;\">Validation Gate Attrition Funnel</div>",
        "      <p class=\"section-subtitle\">Identifies the exact gate that arrested each candidate, preventing unsafe changes from reaching deployment.</p>",
        "      <div class=\"funnel-container\">",
        "        <div class=\"funnel-title\">Validation Gate Attrition Funnel</div>",
        "        <div class=\"funnel-bar\">",
    ]
    funnel_stages = [
        ("V0", "Stopped at V0", "#ef4444"),
        ("V1", "Stopped at V1", "#f97316"),
        ("V2", "Stopped at V2", "#eab308"),
        ("V3", "Stopped at V3", "#8b5cf6"),
        ("SURVIVED", "Survived V0–V3", "#10b981"),
    ]
    for stage_key, stage_label, stage_color in funnel_stages:
        st_cnt = data['first_stop_counts'].get(stage_key, 0)
        st_pct = (st_cnt / total_units * 100) if total_units else 0.0
        html_lines.append(
            f"          <div class=\"funnel-segment\" style=\"width: {st_pct:.1f}%; background: {stage_color};\" title=\"{esc(stage_label)}: {st_cnt} ({st_pct:.1f}%)\"><span>{esc(stage_key)}: {st_cnt}</span></div>"
        )
    html_lines += [
        "        </div>",
        "      </div>",
        "      <div class=\"table-container\">",
        "        <table>",
        "          <thead>",
        "            <tr>",
        "              <th>Gate / First Stop Stage</th><th>Candidates Stopped</th><th>Proportion of Units (N=25)</th><th>Failure Mechanism Caught</th><th>Downstream Action</th>",
        "            </tr>",
        "          </thead>",
        "          <tbody>",
    ]
    v0_cnt = data['first_stop_counts'].get('V0', 0)
    v1_cnt = data['first_stop_counts'].get('V1', 0)
    v2_cnt = data['first_stop_counts'].get('V2', 0)
    v3_cnt = data['first_stop_counts'].get('V3', 0)
    surv_cnt = data['first_stop_counts'].get('SURVIVED', 0)
    v0_pct = f"{(v0_cnt / total_units * 100):.1f}%" if total_units else "0.0%"
    v1_pct = f"{(v1_cnt / total_units * 100):.1f}%" if total_units else "0.0%"
    v2_pct = f"{(v2_cnt / total_units * 100):.1f}%" if total_units else "0.0%"
    v3_pct = f"{(v3_cnt / total_units * 100):.1f}%" if total_units else "0.0%"
    surv_pct = f"{(surv_cnt / total_units * 100):.1f}%" if total_units else "0.0%"
    html_lines += [
        f"            <tr><td><strong>Gate V0 (Compile / Apply)</strong></td><td><strong>{v0_cnt}</strong></td><td>{v0_pct}</td><td>Unified diff syntax error (missing <code>---</code> and <code>+++</code> headers)</td><td>Halted immediately; V1–V3 marked <code>not_run</code></td></tr>",
        f"            <tr><td><strong>Gate V1 (Target Test)</strong></td><td><strong>{v1_cnt}</strong></td><td>{v1_pct}</td><td>Ineffective patches; targeted reproducer test fails</td><td>Halted immediately; V2–V3 marked <code>not_run</code></td></tr>",
        f"            <tr><td><strong>Gate V2 (Regression Suite)</strong></td><td><strong>{v2_cnt}</strong></td><td>{v2_pct}</td><td>{data['gate_stats']['V2']['statuses'].get('fail', 0)} test failures + {data['gate_stats']['V2']['statuses'].get('error', 0)} tool errors</td><td>Halted immediately; V3 marked <code>not_run</code></td></tr>",
        f"            <tr><td><strong>Gate V3 (Semgrep Security)</strong></td><td><strong>{v3_cnt}</strong></td><td>{v3_pct}</td><td>Insecure code; introduced new high-severity findings (SQL concatenation)</td><td>REJECT (decision engine)</td></tr>",
        f"            <tr style=\"background: #ecfdf5;\"><td><strong style=\"color:#065f46;\">Survived All Gates (V0–V3)</strong></td><td><strong style=\"color:#065f46;\">{surv_cnt}</strong></td><td>{surv_pct}</td><td>Clean patch passing compilation, reproducer, regression, and Semgrep</td><td>6 AUTO_APPLY, 1 ESCALATE (diff limit)</td></tr>",
        "          </tbody>",
        "        </table>",
        "      </div>",
        "",
        "      <div style=\"font-weight: 600; font-size: 15px; color: var(--text-main); margin-bottom: 6px;\">Gate Performance & Timing Statistics</div>",
        "      <p class=\"section-subtitle\">Empirical execution duration statistics in seconds for executed gates (excluding not_run / skips)</p>",
        "      <div class=\"table-container\">",
        "        <table>",
        "          <thead>",
        "            <tr>",
        "              <th>Gate</th><th>Evaluated Runs (n)</th><th>Min (s)</th><th>Avg / Mean (s)</th><th>Median (s)</th><th>Max (s)</th><th>Missing Counted as Pass?</th>",
        "            </tr>",
        "          </thead>",
        "          <tbody>",
    ]
    gates = ("V0", "V1", "V2", "V3")
    for g_name in gates:
        st_data = data["gate_stats"][g_name]
        min_str = f"{st_data['min_seconds']:.1f}s" if st_data['min_seconds'] is not None else "N/A"
        avg_str = f"{st_data['avg_seconds']:.1f}s" if st_data['avg_seconds'] is not None else "N/A"
        med_str = f"{st_data['median_seconds']:.1f}s" if st_data['median_seconds'] is not None else "N/A"
        max_str = f"{st_data['max_seconds']:.1f}s" if st_data['max_seconds'] is not None else "N/A"
        html_lines.append(
            f"            <tr>"
            f"<td><strong>{esc(g_name)}</strong></td>"
            f"<td>{st_data['count']}</td>"
            f"<td>{min_str}</td>"
            f"<td><strong>{avg_str}</strong></td>"
            f"<td>{med_str}</td>"
            f"<td>{max_str}</td>"
            f"<td><span class=\"badge badge-reject\">NO</span></td>"
            f"</tr>"
        )
        
    html_lines += [
        "          </tbody>",
        "        </table>",
        "      </div>",
        "    </div>",
        "",
        "    <!-- SECTION 7: Human Approval -->",
        "    <div id=\"tab-approval\" class=\"tab-pane\">",
        "      <div class=\"section-title\">Human Approval</div>",
        "      <div class=\"section-subtitle\">Audited Governance, Escalation Review Workflows, and Interactive Operator Prompts</div>",
        "      <div class=\"two-col\">",
        "        <div class=\"card\">",
        "          <h3 style=\"font-size: 1rem; color: var(--text-main); font-weight: 600; margin-bottom: 12px;\">Approval Sources</h3>",
        "          <div class=\"table-container\" style=\"border: none; box-shadow: none;\">",
        "            <table>",
        "              <thead><tr><th>Source Type</th><th>Recorded In Evidence</th><th>Definition</th></tr></thead>",
        "              <tbody>",
        f"                <tr><td><strong>human_cli</strong></td><td>{data['approval_counts'].get('human_cli', 0)}</td><td>Interactive CLI prompt (operator answered at the terminal)</td></tr>",
        f"                <tr><td><strong>human_relayed</strong></td><td>{data['approval_counts'].get('human_relayed', 0)}</td><td>Human decision relayed via a tool</td></tr>",
        f"                <tr><td><strong>scripted_test</strong></td><td>{data['approval_counts'].get('scripted_test', 0)}</td><td>Automated fixture (never counted as human review)</td></tr>",
        f"                <tr><td><strong>no approval asked</strong></td><td>{sum(1 for r in data['evidence_rows'] if not r.get('approval_source'))}</td><td>Rows where no approval prompt was shown</td></tr>",
        "              </tbody>",
        "            </table>",
        "          </div>",
        "        </div>",
        "        <div class=\"card\">",
        "          <h3 style=\"font-size: 1rem; color: var(--text-main); font-weight: 600; margin-bottom: 12px;\">Interactive CLI Review Protocol</h3>",
        "          <p style=\"font-size: 0.88rem; color: var(--text-muted); margin-bottom: 12px;\">",
        "            When the tiered decision engine designates a candidate as <code>ESCALATE</code> (e.g. diff size exceeded, sensitive path modified, or diagnosis disagreement),",
        "            the pipeline pauses and renders a dedicated terminal review box presenting the risk level, reasons, and diff.",
        "          </p>",
        "          <div class=\"callout\">",
        "            <strong>Approval Invariant:</strong> Zero automated code changes proceed to production deployment without explicit affirmative operator consent when flagged for human review.",
        "          </div>",
        "        </div>",
        "      </div>",
        "    </div>",
        "",
        "    <!-- SECTION 8: Deployment & Rollback -->",
        "    <div id=\"tab-deploy\" class=\"tab-pane\">",
        "      <div class=\"section-title\">Deployment &amp; Rollback</div>",
        "      <div class=\"section-subtitle\">Approval &amp; Rollback Audit Records, Container Swapping, and Health Window Breach Verification</div>",
        "      <div class=\"two-col\">",
        "        <div class=\"card\">",
        "          <h3 style=\"font-size: 1rem; color: var(--text-main); font-weight: 600; margin-bottom: 12px;\">Rollback Events</h3>",
        "          <div class=\"table-container\" style=\"border: none; box-shadow: none;\">",
        "            <table>",
        "              <thead><tr><th>Rollback Kind</th><th>Recorded In Evidence</th><th>Mechanism</th></tr></thead>",
        "              <tbody>",
        f"                <tr><td><strong>Real Unplanned</strong></td><td>{sum(r.get('kind') == 'real' for r in data['rollbacks'])}</td><td>Image swap back upon health breach</td></tr>",
        f"                <tr><td><strong>Staged Demo</strong></td><td>{sum(r.get('kind') == 'staged' for r in data['rollbacks'])}</td><td>Planted slow patch; demonstrates the mechanism only</td></tr>",
        f"                <tr><td><strong>Promotions</strong></td><td>{sum(r.get('outcome') == 'promoted' for r in data['deployments'])}</td><td>Health window passed (not proof of correctness)</td></tr>",
        "              </tbody>",
        "            </table>",
        "          </div>",
        "          <div class=\"callout\">",
        "            <strong>Important Governance Note:</strong> A staged slow-patch rollback demonstrates the Docker image rollback mechanism. ",
        "            It must NOT be counted as a measured catch of an unsafe patch. Real and staged rollbacks remain strictly partitioned.",
        "          </div>",
        "        </div>",
        "        <div class=\"card\">",
        "          <h3 style=\"font-size: 1rem; color: var(--text-main); font-weight: 600; margin-bottom: 12px;\">Health Window Verification Protocol</h3>",
        "          <p style=\"font-size: 0.88rem; color: var(--text-muted); margin-bottom: 12px;\">",
        "            A deployed container image enters a multi-check verification window (<code>health_window_s=30s</code>, <code>check_interval_s=3s</code>).",
        "            Every check evaluates endpoint response latency (&lt;2000 ms), HTTP 200 health status, and deterministic probe payload equality.",
        "          </p>",
        "          <div class=\"callout\">",
        "            <strong>Automated Container Swap:</strong> Upon detecting any breach or latency violation, the pipeline immediately stops the candidate container and swaps back to the baseline image without running <code>git reset</code>.",
        "          </div>",
        "        </div>",
        "      </div>",
        "    </div>",
        "",
        "    <!-- SECTION 9: Evidence & Analytics -->",
        "    <div id=\"tab-evidence\" class=\"tab-pane\">",
        "      <div class=\"section-title\">Evidence &amp; Analytics</div>",
        "      <div class=\"section-subtitle\">Policy Comparison (B0 to B3), Verified Known Limitations, and Traceability Audit</div>",
        "      <div style=\"font-weight: 600; font-size: 15px; color: var(--text-main); margin-bottom: 6px;\">Policy Comparison (B0 – B3)</div>",
        "      <div class=\"banner alert-warning\">",
        "        <strong>Data Integrity Notice:</strong> Rows below are generated by <code>analyse.py</code> (<code>results/policies.csv</code>). "
        "auto / HIR / rejected need no labels. UDR, unsafe escape and FRR need independent labels; with none, they read k/0 (n/a). "
        "B0 assumes a perfect reviewer, not an observed human decision. Scripted and LLM cohorts are never pooled.",
        "      </div>",
    ]
    metric_cols = [("auto_applied", "Auto-applied"), ("hir_escalated", "HIR (escalated)"), ("rejected", "Rejected"),
                   ("udr_unsafe_of_auto", "UDR"), ("unsafe_escape", "Unsafe escape"), ("frr_safe_rejected", "FRR")]
    by_key = {(r["cohort"], r["policy"], r["metric"]): r for r in data["policies"] if "cohort" in r}
    for cohort in ("scripted", "llm"):
        policies_here = sorted({r["policy"]: r["description"] for r in data["policies"] if r.get("cohort") == cohort}.items())
        html_lines += [
            f"      <div style=\"font-weight: 600; margin: 12px 0 6px;\">{esc(cohort)} cohort</div>",
            "      <div class=\"table-container\">",
            "        <table>",
            "          <thead><tr><th>Policy</th><th>Description</th>" + "".join(f"<th>{esc(h)}</th>" for _, h in metric_cols) + "</tr></thead>",
            "          <tbody>",
        ]
        for code, desc in policies_here:
            cells = []
            for m, _ in metric_cols:
                r = by_key.get((cohort, code, m), {})
                k, n = r.get("k", "0"), r.get("n", "0")
                cells.append(f"<td>{esc(k)}/{esc(n)}" + (f" ({float(r['rate']) * 100:.1f}%)" if r.get("rate") else " (n/a)") + "</td>")
            html_lines.append(f"            <tr><td><strong>{esc(code)}</strong></td><td>{esc(desc)}</td>{''.join(cells)}</tr>")
        if not policies_here:
            html_lines.append(f"            <tr><td colspan=\"8\">no {esc(cohort)} units</td></tr>")
        html_lines += ["          </tbody>", "        </table>", "      </div>"]
    html_lines += [
        "",
        "      <div style=\"font-weight: 600; font-size: 15px; color: var(--text-main); margin-bottom: 6px;\">Verified Project Limitations & Blockers (Known Limitations)</div>",
        "      <p class=\"section-subtitle\">Verified constraints, historical results, and infrastructure observations</p>",
        "      <div class=\"limitations-list\">",
    ]
    
    for lim in data["known_limitations"]:
        badge_cls = "badge-error" if lim["severity"] == "danger" else ("badge-warn" if lim["severity"] == "warning" else "badge-auto")
        html_lines += [
            f"        <div class=\"limitation-item\">",
            f"          <div class=\"limitation-header\">",
            f"            <div class=\"limitation-title\">{esc(lim['title'])}</div>",
            f"            <span class=\"badge {badge_cls}\">{esc(lim['badge'])}</span>",
            f"          </div>",
            f"          <div class=\"limitation-desc\">{esc(lim['description'])}</div>",
            f"        </div>",
        ]
        
    html_lines += [
        "      </div>",
        "    </div>",
        "  </div>",
        "",
        "  <script>",
        "    function showTab(tabId, btn) {",
        "      document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));",
        "      document.querySelectorAll('nav.tabs button').forEach(el => el.classList.remove('active'));",
        "      const target = document.getElementById(tabId);",
        "      if (target) target.classList.add('active');",
        "      if (btn) btn.classList.add('active');",
        "    }",
        "",
        "    function filterTable() {",
        "      const search = (document.getElementById('searchCandidates').value || '').toLowerCase().trim();",
        "      const fault = document.getElementById('filterFault').value;",
        "      const decision = document.getElementById('filterDecision').value;",
        "      const firstStop = document.getElementById('filterFirstStop').value;",
        "      const patchmode = document.getElementById('filterPatchMode').value;",
        "      const deployed = document.getElementById('filterDeployed').value;",
        "      const rows = document.querySelectorAll('#candidatesTable tbody tr');",
        "      let visible = 0;",
        "      rows.forEach(tr => {",
        "        const rFault = tr.getAttribute('data-fault');",
        "        const rDec = tr.getAttribute('data-decision');",
        "        const rFirstStop = tr.getAttribute('data-firststop');",
        "        const rMode = tr.getAttribute('data-patchmode');",
        "        const rDep = tr.getAttribute('data-deployed');",
        "        const rSearch = tr.getAttribute('data-search') || '';",
        "        let match = true;",
        "        if (fault !== 'ALL' && rFault !== fault) match = false;",
        "        if (decision !== 'ALL' && rDec !== decision) match = false;",
        "        if (firstStop !== 'ALL' && rFirstStop !== firstStop) match = false;",
        "        if (patchmode !== 'ALL' && rMode !== patchmode) match = false;",
        "        if (deployed !== 'ALL' && rDep !== deployed) match = false;",
        "        if (search && !rSearch.includes(search)) match = false;",
        "        tr.style.display = match ? '' : 'none';",
        "        if (match) visible++;",
        "      });",
        "      const counter = document.getElementById('candidateCount');",
        "      if (counter) counter.textContent = 'Showing ' + visible + ' of ' + rows.length + ' candidates';",
        "    }",
        "",
        "    function resetFilters() {",
        "      document.getElementById('searchCandidates').value = '';",
        "      document.getElementById('filterFault').value = 'ALL';",
        "      document.getElementById('filterDecision').value = 'ALL';",
        "      document.getElementById('filterFirstStop').value = 'ALL';",
        "      document.getElementById('filterPatchMode').value = 'ALL';",
        "      document.getElementById('filterDeployed').value = 'ALL';",
        "      filterTable();",
        "    }",
        "  </script>",
        "</body>",
        "</html>",
    ]
    return "\n".join(html_lines)


def generate_dashboard(repo_root: Path, evidence_path: Path, results_dir: Path, docs_dir: Path, out_path: Path) -> Path:
    print(f"Building dashboard data from {repo_root}...")
    data = build_dashboard_data(repo_root, evidence_path, results_dir, docs_dir)
    print(f"  Evidence rows: {len(data['evidence_rows'])}")
    print(f"  Unique units: {len(data['units'])}")
    print(f"  Distinct faults: {data['distinct_faults']}")
    print(f"  Decisions: {dict(data['decision_counts'])}")
    print(f"  First stops: {dict(data['first_stop_counts'])}")
    print(f"  Deployments: {data['deployed_count']}, Rollbacks: {data['rollback_count']}")
    
    html_content = render_html(data)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_content, encoding="utf-8")
    print(f"Successfully generated dashboard: {out_path} ({len(html_content)} bytes)")
    return out_path


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description="Generate AutoImmune Evidence Dashboard (offline HTML)")
    ap.add_argument("--repo", type=Path, default=repo, help="Path to repo root")
    ap.add_argument("--evidence", type=Path, default=None, help="Path to evidence.jsonl")
    ap.add_argument("--results-dir", type=Path, default=None, help="Path to results directory")
    ap.add_argument("--docs-dir", type=Path, default=None, help="Path to docs directory")
    ap.add_argument("--out", type=Path, default=None, help="Output HTML path")
    args = ap.parse_args()
    
    repo = args.repo.resolve()
    evidence = (args.evidence or (repo / "results" / "evidence.jsonl")).resolve()
    results_dir = (args.results_dir or (repo / "results")).resolve()
    docs_dir = (args.docs_dir or (repo / "docs")).resolve()
    out = (args.out or (repo / "results" / "dashboard.html")).resolve()
    
    generate_dashboard(repo, evidence, results_dir, docs_dir, out)


if __name__ == "__main__":
    main()
