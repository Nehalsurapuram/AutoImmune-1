"""Tests for tools/export_ui_data.py ensuring data integrity and safety."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from tools import export_ui_data

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_export_ui_data_snapshot_validity(tmp_path):
    out_file = tmp_path / "snapshot.json"
    export_ui_data.export_all([out_file])

    assert out_file.is_file()
    data = json.loads(out_file.read_text(encoding="utf-8"))

    # Required top-level keys
    assert "metadata" in data
    assert "runs" in data
    assert "candidates" in data
    assert "case_studies" in data
    assert "policies" in data
    assert "gate_stats" in data
    assert "acceptance" in data

    # Verify metadata
    meta = data["metadata"]
    assert meta["total_runs_recorded"] > 0
    assert meta["total_units"] > 0
    assert meta["scripted_units_count"] > 0
    assert meta["llm_units_count"] > 0
    # Cohorts must be separate
    assert meta["scripted_units_count"] + meta["llm_units_count"] == meta["total_units"]

    # Verify runs structure
    runs = data["runs"]
    assert len(runs) > 0
    for r in runs[:5]:
        assert "run_id" in r
        assert "timeline_stages" in r
        assert len(r["timeline_stages"]) == 10  # 10 pipeline stages

    # Verify candidates
    candidates = data["candidates"]
    assert len(candidates) > 0
    for c in candidates[:10]:
        assert "candidate_id" in c
        assert "run_id" in c
        assert c["cohort"] in ("scripted", "llm")
        assert "gates" in c
        assert "decision" in c
        if c.get("offline_oracle_label"):
            assert "offline_oracle_note" in c


def test_timeline_stages_accuracy():
    run_json = {"run_id": "test-run", "fault_id": "F06"}
    incident = {"rule": "probe_mismatch", "endpoint": "/api/orders/2/discount", "evidence": ["err"]}
    diagnosis = {"provider_mode": "live", "causes": [{"file": "OrderService.java"}]}
    candidates = [{
        "candidate_id": "c1",
        "gates": {"V0": {"status": "pass"}, "V1": {"status": "pass"}},
        "decision": {"decision": "AUTO_APPLY"}
    }]
    deploy = {"new_image": "order-service:test", "outcome": "promoted"}
    rollback = None

    stages = export_ui_data.build_timeline_stages(run_json, incident, diagnosis, candidates, deploy, rollback)
    assert len(stages) == 10
    stage_ids = [s["id"] for s in stages]
    assert stage_ids == [
        "detection", "incident_evidence", "diagnosis", "candidate_generation",
        "validation", "decision", "approval", "deployment", "recovery", "evidence"
    ]
    # Check detection is pass
    assert stages[0]["status"] == "pass"
    # Check deployment is pass
    assert stages[7]["status"] == "pass"
    # Check recovery is pass
    assert stages[8]["status"] == "pass"
