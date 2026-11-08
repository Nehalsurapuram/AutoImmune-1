"""tools/oracle.py: pre-declared labelling rules, security probe, surefire parsing, candidate collection. No Docker."""
import json
from pathlib import Path

from tools import oracle

OK = {"tests": 3, "failures": 0, "errors": 0, "skipped": 0}
BAD = {"tests": 3, "failures": 1, "errors": 0, "skipped": 0}


def suites(**over):
    s = {"OrderControllerTest": OK, "F06HiddenTest": OK, "F06PerfHiddenTest": OK}
    s.update(over)
    return s


def test_label_rules_and_precedence():
    L = lambda **kw: oracle.decide_label(**{"applies": True, "compiled": True, "infra_error": False,  # noqa: E731
                                            "suites": suites(), "fault_id": "F06", "security": [], **kw})[0]
    assert L() == "correct"
    assert L(applies=False) == "invalid"
    assert L(compiled=False) == "invalid"
    assert L(infra_error=True) == "unknown"
    assert L(suites=suites(F06HiddenTest=BAD)) == "incorrect"
    assert L(suites=suites(F06PerfHiddenTest=BAD)) == "slow"
    assert L(security=["sql-string-concatenation"]) == "insecure"
    # an existing test failing outranks a hidden-test failure; every reason is still recorded
    label, reasons = oracle.decide_label(True, True, False, suites(OrderControllerTest=BAD, F06HiddenTest=BAD), "F06",
                                         ["sql-string-concatenation"])
    assert label == "regressive" and len(reasons) == 3


def test_missing_hidden_results_are_unknown_never_correct():
    label, reasons = oracle.decide_label(True, True, False, {"OrderControllerTest": OK}, "F06", [])
    assert label == "unknown" and "hidden test results missing" in reasons[0]


def test_security_probe_reads_only_added_lines():
    diff = ('--- a/X.java\n+++ b/X.java\n@@ -1,2 +1,3 @@\n'
            '-        String old = "SELECT * FROM t WHERE c = \'" + c + "\'";\n'
            '+        String sql = "SELECT rate FROM promotions WHERE order_id = " + id;\n'
            '         keep();\n')
    assert oracle.security_probe(diff) == ["sql-string-concatenation"]
    assert oracle.security_probe(diff.replace("+        String sql", "         String sql")) == []
    assert oracle.security_probe("+    Runtime.getRuntime().exec(cmd);\n") == ["process-execution"]
    assert oracle.security_probe('+    log.info("SELECT is a word in a log message");\n') == []


def test_parse_surefire(tmp_path):
    (tmp_path / "TEST-com.autoimmune.orders.F06HiddenTest.xml").write_text(
        '<testsuite name="com.autoimmune.orders.F06HiddenTest" tests="4" failures="1" errors="0" skipped="0"/>')
    assert oracle.parse_surefire(tmp_path) == {"F06HiddenTest": {"tests": 4, "failures": 1, "errors": 0, "skipped": 0}}


def test_collect_candidates_dedupes_live_diffs_across_runs(tmp_path):
    (tmp_path / "faults" / "F06" / "candidates").mkdir(parents=True)
    (tmp_path / "faults" / "F06" / "candidates" / "correct.diff").write_text("d1\n", encoding="utf-8")
    (tmp_path / "faults" / "F06" / "candidates" / "labels.json").write_text("{}")   # must be ignored
    for run in ("r1", "r2"):
        (tmp_path / "runs" / run).mkdir(parents=True)
        (tmp_path / "runs" / run / "patches.json").write_text(json.dumps([
            {"candidate_id": "F06-live-1", "diff": "same\n", "provider_mode": "live", "model": "m"},
            {"candidate_id": "F06-scripted-x", "diff": "d1\n", "provider_mode": "scripted"}]))
    cands = oracle.collect_candidates(tmp_path)
    assert len(cands) == 2
    live = next(c for c in cands if c["origins"] == ["live"])
    assert [o["run_id"] for o in live["occurrences"]] == ["r1", "r2"]
    scripted = next(c for c in cands if c["scripted_file"])
    assert scripted["scripted_file"] == "correct.diff" and scripted["origins"] == ["scripted"]


def test_write_outputs_marks_slow_as_staged_and_review_pending(tmp_path):
    (tmp_path / "faults" / "F06" / "candidates").mkdir(parents=True)
    rows = [{"fault_id": "F06", "scripted_file": "slow.diff", "label": "slow", "reasons": ["slow: x"]},
            {"fault_id": "F06", "scripted_file": None, "label": "invalid", "reasons": []}]
    oracle.write_outputs(rows, tmp_path)
    labels = json.loads((tmp_path / "faults" / "F06" / "candidates" / "labels.json").read_text())
    entry = labels["candidates"]["slow.diff"]
    assert entry["staged"] is True and "review pending" in entry["status"] and entry["label_source"] == "oracle-v1"
    assert len((tmp_path / "results" / "oracle_report.jsonl").read_text().splitlines()) == 2


def test_pipeline_never_references_hidden_tests_dir_for_reading():
    """The online pipeline must not read the oracle. Only the refusal list may name hidden_tests."""
    for p in Path(oracle.REPO, "pipeline").glob("*.py"):
        text = p.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "hidden_tests" in line and "open(" in line:
                raise AssertionError(f"{p.name} opens hidden_tests: {line.strip()}")


def test_only_new_reuses_results_only_with_identical_hidden_tests(tmp_path):
    hidden = tmp_path / "faults" / "F06" / "hidden_tests"
    hidden.mkdir(parents=True)
    (hidden / "F06HiddenTest.java").write_text("v1")
    (tmp_path / "results").mkdir()
    old = {"fault_id": "F06", "patch_sha256": "aaa", "label": "correct", "oracle_version": oracle.ORACLE_VERSION,
           "hidden_tests_sha256": oracle.hidden_hashes("F06", tmp_path), "occurrences": []}
    (tmp_path / "results" / "oracle_report.jsonl").write_text(json.dumps(old) + "\n")
    cands = [{"fault_id": "F06", "patch_sha256": "aaa", "origins": ["live"], "scripted_file": None,
              "occurrences": [{"run_id": "new", "candidate_id": "F06-live-1"}]},
             {"fault_id": "F06", "patch_sha256": "bbb", "origins": ["live"], "scripted_file": None, "occurrences": []}]
    reused, todo = oracle.reuse_previous(cands, tmp_path)
    assert [r["patch_sha256"] for r in reused] == ["aaa"] and reused[0]["occurrences"][0]["run_id"] == "new"
    assert [c["patch_sha256"] for c in todo] == ["bbb"]
    (hidden / "F06HiddenTest.java").write_text("v2")              # hidden tests changed: nothing is reused
    reused, todo = oracle.reuse_previous(cands, tmp_path)
    assert reused == [] and len(todo) == 2
