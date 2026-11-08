"""Tests for the evidence dashboard generator.

They build their own evidence + results + acceptance.json in tmp_path, so they never depend on the mutable
contents of results/ (audit F-03), and they check that no hand-typed claim survives in the page.
"""
import json
from pathlib import Path

import pytest

import analyse
from tools.make_dashboard import build_dashboard_data, determine_first_stop, generate_dashboard

REPO = Path(__file__).resolve().parents[1]


def row(cid, run, gates=("pass",) * 4, decision="AUTO_APPLY", patch_mode="scripted", diag_mode="rule", **kw):
    r = {"run_id": run, "fault_id": "F06", "candidate_id": cid, "decision": decision, "tier": "low",
         "timestamp": f"2026-11-01T10:00:0{len(run) % 10}+00:00", "deployed": False, "rolled_back": None,
         "approval_source": None, "invalid": None, "recovery_s": None, "patch_mode": patch_mode,
         "diag_mode": diag_mode, "model": None, "reasons": ["r"], "candidate_kind": None, "apply_error": None,
         "top1_hit": None, "top3_hit": None}
    r.update({g: {"status": s, "seconds": 1.0} for g, s in zip(("v0", "v1", "v2", "v3"), gates)})
    r.update(kw)
    return r


@pytest.fixture
def site(tmp_path):
    rows = [
        row("F06-scripted-aaaa0001", "s1", candidate_kind="correct", deployed=True, rolled_back=False),
        row("F06-scripted-aaaa0002", "s1", gates=("pass", "fail", "not_run", "not_run"), decision="REJECT",
            candidate_kind="ineffective"),
        row("F06-scripted-aaaa0003", "s1", gates=("pass", "pass", "pass", "fail"), decision="REJECT",
            candidate_kind="insecure"),
        # same live id in two runs: two units
        row("F06-live-1", "l1", gates=("fail", "not_run", "not_run", "not_run"), decision="REJECT", patch_mode="live",
            diag_mode="live", model="m-7b", apply_error="patch fragment without header", top1_hit=True, top3_hit=True),
        row("F06-live-1", "l2", gates=("pass", "fail", "not_run", "not_run"), decision="REJECT", patch_mode="live",
            diag_mode="live", model="m-1.5b", top1_hit=False, top3_hit=False),
    ]
    ev = tmp_path / "results" / "evidence.jsonl"
    ev.parent.mkdir()
    ev.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (tmp_path / "faults").mkdir()
    analyse.main(ev, tmp_path / "faults", tmp_path / "results", runs_dir=None, quiet=True)
    docs = tmp_path / "docs"
    (docs / "audit").mkdir(parents=True)
    (docs / "audit" / "acceptance.json").write_text(json.dumps({
        "as_of": "2099-01-01",
        "test_suite": {"badge": "x", "text": "FIXTURE-SUITE-TEXT"},
        "acceptance_checks": [
            {"id": "A5", "name": "Isolated sandbox", "criterion": "c", "status": "NOT YET TESTED", "evidence": "e",
             "limitation": "FIXTURE-LIMIT"},
            {"id": "A9", "name": "Rollback", "criterion": "c", "status": "FAIL", "evidence": "e", "limitation": ""}],
        "known_limitations": [{"title": "FIXTURE-LIMITATION-TITLE", "category": "c", "severity": "info",
                               "badge": "b", "description": "d"}]}), encoding="utf-8")
    return tmp_path, ev, docs


def test_build_dashboard_data_uses_the_same_units_as_analyse(site):
    tmp, ev, docs = site
    data = build_dashboard_data(tmp, ev, tmp / "results", docs)
    assert len(data["evidence_rows"]) == 5
    assert len(data["units"]) == 5                       # both F06-live-1 attempts kept (audit F-05)
    assert len(data["units"]) == len(analyse.units_of(analyse.load_rows(ev)))
    assert data["decision_counts"]["AUTO_APPLY"] == 1 and data["decision_counts"]["REJECT"] == 4
    assert data["deployed_count"] == 1 and data["rollback_count"] == 0


def test_first_stop_distribution(site):
    tmp, ev, docs = site
    stops = build_dashboard_data(tmp, ev, tmp / "results", docs)["first_stop_counts"]
    assert dict(stops) == {"SURVIVED": 1, "V1": 2, "V3": 1, "V0": 1}
    assert determine_first_stop({"v0": {"status": "error"}}) == "V0"   # an error is never a pass


def test_acceptance_checks_and_limitations_come_from_the_data_file(site):
    tmp, ev, docs = site
    out = tmp / "dash.html"
    generate_dashboard(tmp, ev, tmp / "results", docs, out)
    html = out.read_text(encoding="utf-8")
    assert "FIXTURE-SUITE-TEXT" in html and "FIXTURE-LIMIT" in html and "FIXTURE-LIMITATION-TITLE" in html
    assert "NOT YET TESTED" in html and "badge-reject\">FAIL" in html


def test_page_is_offline_and_carries_no_hand_typed_claims(site):
    tmp, ev, docs = site
    out = tmp / "dash.html"
    generate_dashboard(tmp, ev, tmp / "results", docs, out)
    html = out.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>") and "<title>AutoImmune — Evidence Dashboard</title>" in html
    assert "http://" not in html and "https://" not in html
    for section in ("Executive Overview", "Validation Gates", "Policy Comparison", "Acceptance Checks",
                    "Known Limitations"):
        assert section in html, section
    for stale in ("158 Unit Tests", "170 passed", "0 of 9", "Localization failure (0/8)", "PASS &bull; PROVEN",
                  "DONE AND PROVEN", "All 25 units", "test_no_network"):
        assert stale not in html, stale


def test_policy_and_llm_numbers_are_rendered_from_results(site):
    tmp, ev, docs = site
    out = tmp / "dash.html"
    generate_dashboard(tmp, ev, tmp / "results", docs, out)
    html = out.read_text(encoding="utf-8")
    assert "scripted cohort" in html and "llm cohort" in html
    assert "<td>1/3 (33.3%)</td>" in html                      # scripted B3 auto-applied 1 of 3
    assert "<code>m-7b</code>: 0/1 applied cleanly" in html and "<code>m-1.5b</code>: 1/1 applied cleanly" in html


def test_real_repository_dashboard_builds(tmp_path):
    """Smoke test on the real results/ (no totals asserted: they change with every run)."""
    ev = REPO / "results" / "evidence.jsonl"
    if not ev.is_file():
        pytest.skip("no results/evidence.jsonl in this checkout")
    out = tmp_path / "dash.html"
    generate_dashboard(REPO, ev, REPO / "results", REPO / "docs", out)
    assert out.stat().st_size > 10000
