"""Unit tests for terminal presentation and ANSI formatting."""
import io
from pipeline.terminal import (
    Style,
    format_status,
    print_approval_section,
    print_execution_summary,
    print_gate_table,
    print_header,
    print_stage,
)


def test_style_enabled_and_disabled():
    s_on = Style(enabled=True)
    assert s_on.CYAN == "\033[36m"
    assert s_on.RESET == "\033[0m"

    s_off = Style(enabled=False)
    assert s_off.CYAN == ""
    assert s_off.RESET == ""


def test_format_status():
    st_pass = format_status("pass")
    assert "PASS" in st_pass
    st_fail = format_status("fail")
    assert "FAIL" in st_fail
    st_esc = format_status("escalate")
    assert "ESCALATE" in st_esc


def test_print_header(capsys):
    print_header("run-123", "F06", "rule", "scripted")
    out = capsys.readouterr().out
    assert "AUTOIMMUNE" in out
    assert "AUTOMATED SOFTWARE REPAIR ENGINE" in out
    assert "Run ID:         run-123" in out
    assert "Fault:          F06" in out
    assert "Diagnosis Mode: rule" in out
    assert "Patch Mode:     scripted" in out


def test_print_stage(capsys):
    print_stage(1, 10, "Baseline Initialization", elapsed_s=0.5)
    out = capsys.readouterr().out
    assert "[01/10] BASELINE INITIALIZATION" in out
    assert "Stage [1/10]" in out


def test_print_gate_table(capsys):
    candidates = [
        {
            "candidate_id": "cand-1",
            "gates": {"V0": "pass", "V1": "pass", "V2": "pass", "V3": "pass"},
            "decision": "AUTO_APPLY",
        },
        {
            "candidate_id": "cand-2",
            "gates": {"V0": "pass", "V1": "fail", "V2": "-", "V3": "-"},
            "decision": "REJECT",
        },
    ]
    print_gate_table(candidates)
    out = capsys.readouterr().out
    assert "CANDIDATE ID" in out
    assert "cand-1" in out
    assert "AUTO_APPLY" in out
    assert "cand-2" in out
    assert "REJECT" in out


def test_print_approval_section():
    buf = []
    print_approval_section(
        candidate_id="cand-esc-1",
        tier="MEDIUM",
        reasons=["diff touches a sensitive path"],
        diff="--- a/x\n+++ b/x\n",
        out=buf.append,
    )
    full = "\n".join(buf)
    assert "HUMAN APPROVAL REQUIRED" in full
    assert "Candidate:  cand-esc-1" in full
    assert "Risk Level: MEDIUM" in full
    assert "diff touches a sensitive path" in full
    assert "--- a/x\n+++ b/x" in full
    assert "[APPROVE / REJECT]" in full


def test_print_execution_summary(capsys):
    print_execution_summary(
        run_id="run-test",
        fault="F01",
        candidates_count=3,
        val_passed_count=1,
        val_failed_count=2,
        auto_apply_count=1,
        escalated_count=0,
        rejected_count=2,
        deployment_status="Promoted",
        baseline_status="Restored & Healthy",
        evidence_saved="results/evidence.jsonl",
        final_status="SUCCESS",
        seconds=12.4,
    )
    out = capsys.readouterr().out
    assert "AUTOIMMUNE EXECUTION SUMMARY" in out
    assert "Run ID:               run-test" in out
    assert "Fault:                F01" in out
    assert "Candidates Generated: 3" in out
    assert "Validation Passed:    1" in out
    assert "Validation Failed:    2" in out
    assert "Auto Apply:           1" in out
    assert "Rejected:             2" in out
    assert "Final Status:         SUCCESS" in out
