import json
import re

import pytest

from pipeline.decide import Decision
from pipeline.record import InvalidEvidenceRow, append_row, build_row, max_severity, validate_row

SVC = "app/src/main/java/com/autoimmune/orders/OrderService.java"


def _gates(v3_findings):
    g = {n: {"status": "pass", "seconds": 1.5, "exit_code": 0, "log_tail": ""} for n in ("V0", "V1", "V2", "V3")}
    g["V3"]["new_findings"] = v3_findings
    return {"gates": g}


def _row(**overrides):
    row = build_row(
        run_id="r1", fault_id="F06",
        gates=_gates([{"rule_id": "x", "file": SVC, "line": 3, "severity": "WARNING"}]),
        diagnosis={"provider_mode": "rule", "oracle_localisation": True, "causes": []},
        patch={"candidate_id": "F06-scripted-abc", "candidate_kind": "correct", "provider_mode": "scripted"},
        patch_meta={"files_touched": [SVC], "diff_lines": 2},
        decision=Decision("medium", "ESCALATE", ("reason",), "decide-v1+abc"),
        timestamp="2026-10-19T12:00:00+00:00",
        # Phase 3 fields default to None for backward-compatible rows
        diag_samples=None, samples_disagree=None,
        top1_hit=None, top3_hit=None,
        model=None, llm_attempts=None, apply_error=None)
    row.update(overrides)
    return row


def test_valid_row_is_appended_as_one_json_line(tmp_path):
    path = tmp_path / "evidence.jsonl"
    append_row(_row(), path)
    append_row(_row(candidate_id="F06-scripted-def"), path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    row = json.loads(lines[0])
    assert row["v0"] == {"status": "pass", "seconds": 1.5}
    assert row["new_findings"] == {"count": 1, "max_severity": "WARNING"}
    assert (row["diag_mode"], row["patch_mode"], row["oracle_localisation"]) == ("rule", "scripted", True)
    assert row["deployed"] is None and row["recovery_s"] is None


@pytest.mark.parametrize("bad, where", [
    ({"label": "correct"}, "(row)"),                              # no labels allowed in evidence
    ({"v2": {"status": "passed", "seconds": 1}}, "v2/status"),
    ({"decision": "MAYBE"}, "decision"),
    ({"reasons": []}, "reasons"),
    ({"diag_mode": "llm"}, "diag_mode"),
    ({"fault_id": "F6"}, "fault_id"),
    ({"timestamp": "yesterday"}, "timestamp"),
    ({"recovery_s": -1}, "recovery_s"),
    ({"approval_source": "human"}, "approval_source"),
    ({"invalid": "maybe"}, "invalid"),
])
def test_invalid_row_is_refused_and_nothing_is_written(tmp_path, bad, where):
    path = tmp_path / "evidence.jsonl"
    with pytest.raises(InvalidEvidenceRow, match=re.escape(f"refused at {where}")):
        append_row(_row(**bad), path)
    assert not path.exists()


def test_missing_field_is_refused():
    row = _row()
    del row["rolled_back"]
    with pytest.raises(InvalidEvidenceRow, match="rolled_back"):
        validate_row(row)


def test_v3_without_findings_list_records_null_count():
    row = build_row(run_id="r", fault_id="F01", gates=_gates(None),
                    diagnosis={"provider_mode": "live"}, patch={"candidate_id": "c", "provider_mode": "live"},
                    patch_meta={"files_touched": [], "diff_lines": 0},
                    decision={"tier": "high", "decision": "REJECT", "reasons": ["x"]})
    validate_row(row)
    assert row["new_findings"] == {"count": None, "max_severity": None} and row["candidate_kind"] is None


@pytest.mark.parametrize("approval, source", [(None, None), ({"answer": "approve", "approval_source": "human_cli"}, "human_cli"),
                                              ({"answer": "approve", "approval_source": "human_relayed"}, "human_relayed"),
                                              ({"answer": "approve", "approval_source": "scripted_test"}, "scripted_test")])
def test_approval_source_and_invalid_are_recorded(approval, source):
    row = build_row(run_id="r", fault_id="F04", gates=_gates([]), diagnosis={"provider_mode": "rule"},
                    patch={"candidate_id": "c", "provider_mode": "scripted"},
                    patch_meta={"files_touched": [], "diff_lines": 1},
                    decision={"tier": "medium", "decision": "ESCALATE", "reasons": ["x"]},
                    approval=approval, invalid="observer_suspended")
    validate_row(row)
    assert row["approval_source"] == source and row["invalid"] == "observer_suspended"


def test_max_severity():
    assert max_severity([{"severity": "INFO"}, {"severity": "ERROR"}, {"severity": "WARNING"}]) == "ERROR"
    assert max_severity([]) is None


# ---------------------------------------------------------------- Phase 3 schema additions

def test_phase3_fields_are_accepted_when_set(tmp_path):
    """New nullable fields must be accepted by the schema when set to valid non-null values."""
    path = tmp_path / "evidence.jsonl"
    row = _row(diag_samples=3, samples_disagree=True, top1_hit=True, top3_hit=True,
               model="qwen2.5-coder:7b", llm_attempts=1, apply_error=None)
    append_row(row, path)
    validate_row(_row(diag_samples=1, samples_disagree=False, top1_hit=False, top3_hit=False,
                      model="test-model", llm_attempts=2, apply_error="patch does not apply"))


def test_phase3_null_fields_pass_schema():
    """Phase 3 fields default to null and must validate for backward-compatible scripted rows."""
    row = _row()  # all Phase 3 fields are None
    assert row["diag_samples"] is None
    assert row["top1_hit"] is None
    assert row["samples_disagree"] is None
    validate_row(row)


def test_rows_carry_schema_version_and_patch_hash():
    import hashlib
    row = build_row(run_id="r", fault_id="F06", gates=_gates([]), diagnosis={"provider_mode": "rule"},
                    patch={"candidate_id": "F06-live-1", "diff": "--- a\n+++ b\n", "provider_mode": "live"},
                    patch_meta={"diff_lines": 2, "files_touched": ["a"]},
                    decision={"tier": "high", "decision": "REJECT", "reasons": ["V1 failed"]})
    validate_row(row)
    assert row["schema_version"] == 2
    assert row["patch_sha256"] == hashlib.sha256(b"--- a\n+++ b\n").hexdigest()


def test_extra_field_still_rejected():
    """additionalProperties is still False: no unlisted field may enter the evidence row."""
    with pytest.raises(InvalidEvidenceRow, match="refused at"):
        validate_row(_row(**{"label": "correct"}))
