"""Unit tests for tools/validation_cost.py."""

import json

import pytest

from tools import validation_cost as vc

REPO = vc.REPO


def _row(cohort="llm", **gates):
    st = {g: gates.get(g, ("pass", 10.0)) for g in ("v0", "v1", "v2", "v3")}
    return {"patch_mode": "live" if cohort == "llm" else "scripted",
            **{g: {"status": s, "seconds": sec} for g, (s, sec) in st.items()}}


def test_median_and_nearest_rank_p95():
    assert vc.median([3.0, 1.0, 2.0]) == 2.0
    assert vc.median([1.0, 2.0, 3.0, 4.0]) == 2.5
    assert vc.median([]) is None
    vals = [float(i) for i in range(1, 21)]          # 1..20
    assert vc.p95(vals) == 19.0                      # ceil(0.95 * 20) = 19th value
    assert vc.p95([5.0]) == 5.0
    assert vc.p95([]) is None


def test_timing_uses_recorded_durations_and_skips_unexecuted_gates():
    rows = [
        _row(v1=("pass", 20.0), v2=("pass", 30.0), v3=("pass", 8.0)),
        _row(v1=("fail", 40.0), v2=("not_run", 0.0), v3=("not_run", 0.0)),
        _row(v0=("fail", 0.0), v1=("not_run", 0.0), v2=("not_run", 0.0), v3=("not_run", 0.0)),
        _row(cohort="scripted", v1=("pass", 999.0)),   # other cohort: never mixed in
    ]
    t = {r["gate"]: r for r in vc.gate_timing(rows, "llm")}
    assert t["V0"]["executions"] == 3 and t["V0"]["timed"] == 2 and t["V0"]["untimed"] == 1
    assert t["V1"]["executions"] == 2 and t["V1"]["median_s"] == 30.0 and t["V1"]["total_s"] == 60.0
    assert t["V2"]["executions"] == 1 and t["V2"]["median_s"] == 30.0     # the not_run 0.0 s rows are excluded
    assert t["V3"]["outcomes"] == {"pass": 1}


def _patch(unsafe, statuses, seconds=None, cohort="llm"):
    gates = ("V0", "V1", "V2", "V3")
    return {"cohort": cohort, "unsafe": unsafe, "statuses": dict(zip(gates, statuses)),
            "seconds": dict(zip(gates, seconds or [5.0, 30.0, 30.0, 6.0]))}


def test_incremental_attributes_first_stop_and_counts_reach():
    data = [
        _patch(1, ["pass", "fail", "not_run", "not_run"]),
        _patch(1, ["pass", "pass", "pass", "fail"]),
        _patch(0, ["pass", "pass", "pass", "pass"]),
        _patch(1, ["pass", "pass", "pass", "pass"]),
    ]
    g = {r["gate"]: r for r in vc.incremental(data, "llm")["gates"]}
    assert (g["V1"]["reached"], g["V1"]["unsafe_stopped"]) == (4, 1)
    assert (g["V2"]["reached"], g["V2"]["unsafe_stopped"]) == (3, 0)
    assert (g["V3"]["reached"], g["V3"]["unsafe_stopped"]) == (3, 1)
    assert g["V3"]["unsafe_escaping_after"] == 1
    assert g["V1"]["seconds"] == 120.0                              # 4 patches x 30 s
    assert g["V1"]["catches_per_gate_minute"] == pytest.approx(1 / 2)   # 1 catch / 2 gate-minutes
    assert g["V3"]["cumulative_unsafe_stopped"] == 2


def test_tool_error_is_not_a_safety_catch():
    data = [_patch(1, ["pass", "pass", "error", "not_run"])]
    g = {r["gate"]: r for r in vc.incremental(data, "llm")["gates"]}
    assert g["V2"]["unsafe_stopped"] == 0 and g["V2"]["tool_error_stopped"] == 1


def test_ratio_undefined_when_no_time_recorded():
    data = [_patch(1, ["fail", "not_run", "not_run", "not_run"], seconds=[0.0, 0.0, 0.0, 0.0])]
    g = {r["gate"]: r for r in vc.incremental(data, "llm")["gates"]}
    assert g["V0"]["catches_per_gate_minute"] is None
    assert g["V1"]["reached"] == 0 and g["V1"]["catches_per_gate_minute"] is None


def test_conclusions_flag_unestablished_gates():
    data = [_patch(1, ["pass", "pass", "pass", "pass"]), _patch(0, ["pass", "pass", "pass", "pass"])]
    text = " ".join(vc.conclusions(vc.incremental(data, "llm")))
    assert "V3 stopped no unsafe AI-written patch" in text and "cannot be established" in text


@pytest.mark.skipif(not (REPO / "results" / "evidence.jsonl").is_file(), reason="no local evidence")
def test_real_evidence_balances():
    files = vc.run(REPO / "results" / "evidence.jsonl", REPO / "faults", REPO / "config" / "decision.yaml",
                   REPO / "results")
    doc = json.loads(files["validation_cost.json"])
    for c, body in doc["cohorts"].items():
        b = body["benefit"]
        stopped = sum(r["unsafe_stopped"] for r in b["gates"])
        assert stopped + b["gates"][-1]["unsafe_escaping_after"] == b["unsafe_patches"]
        reached = [r["reached"] for r in b["gates"]]
        assert reached == sorted(reached, reverse=True)
        assert b["path_anomalies"] == 0
        for t in body["timing"]:
            assert t["timed"] + t["untimed"] == t["executions"]
    # the cross-reference is analyse.py's table on the current inputs, never a stale copy
    import csv
    import io
    from analyse import analyse as analyse_results
    current, _ = analyse_results(REPO / "results" / "evidence.jsonl", REPO / "faults", REPO / "runs")
    assert doc["cross_reference"]["rows"] == list(csv.DictReader(io.StringIO(current["gate_incremental.csv"])))
    # and the per-cohort unsafe catches agree with it once its unit (not distinct patches) is accounted for:
    # the LLM cohort has no repeated diffs, so the marginal catches must be identical there
    llm_marginal = [int(r["unsafe_stopped_marginal"]) for r in doc["cross_reference"]["rows"] if r["cohort"] == "llm"]
    assert llm_marginal == [g["unsafe_stopped"] for g in doc["cohorts"]["llm"]["benefit"]["gates"]]
