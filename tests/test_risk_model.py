"""Unit tests for tools/risk_model.py."""

import json
import math

import pytest

from tools import risk_model as rm

SENSITIVE = ["application.properties", "security/"]


def _unit(**over):
    u = {"_cohort": "llm", "candidate_id": "c1", "run_id": "r1", "fault_id": "F01", "diff_lines": 4,
         "files_touched": ["app/src/main/java/A.java"], "new_findings": {"count": 0},
         "v0": {"status": "pass"}, "v1": {"status": "pass"}, "v2": {"status": "pass"}, "v3": {"status": "pass"}}
    u.update(over)
    return u


# ---------------------------------------------------------------- features

def test_features_all_pass():
    x = rm.features_of(_unit(), SENSITIVE)
    assert x == {"gate_fail": 0.0, "new_findings": 0.0, "log_diff_lines": pytest.approx(math.log(5)),
                 "multi_file": 0.0, "sensitive_path": 0.0}


@pytest.mark.parametrize("gate,st", [("v1", "fail"), ("v2", "error"), ("v3", "timeout"), ("v2", "not_run")])
def test_any_non_pass_gate_is_a_failure(gate, st):
    assert rm.features_of(_unit(**{gate: {"status": st}}), SENSITIVE)["gate_fail"] == 1.0


def test_scope_and_findings_features():
    x = rm.features_of(_unit(files_touched=["a/A.java", "src/main/resources/application.properties"],
                             new_findings={"count": 2}), SENSITIVE)
    assert x["multi_file"] == 1.0 and x["sensitive_path"] == 1.0 and x["new_findings"] == 1.0


def test_leaky_and_post_deploy_fields_are_ignored():
    base = rm.features_of(_unit(), SENSITIVE)
    leaky = rm.features_of(_unit(top1_hit=True, top3_hit=True, oracle_localisation=True, deployed=True,
                                 rolled_back=True, recovery_s=4.2), SENSITIVE)
    assert base == leaky


# ---------------------------------------------------------------- model

def test_logistic_learns_direction_and_stays_in_range():
    xs = [[0.0]] * 10 + [[1.0]] * 10
    ys = [0] * 8 + [1] * 2 + [1] * 9 + [0] * 1
    m = rm.Logistic().fit(xs, ys)
    lo, hi = m.predict([[0.0], [1.0]])
    assert 0 < lo < hi < 1
    assert m.w[1] > 0


def test_logistic_separable_data_is_finite_with_l2():
    m = rm.Logistic().fit([[0.0], [0.0], [1.0], [1.0]], [0, 0, 1, 1])
    assert all(math.isfinite(w) for w in m.w)


def test_logistic_constant_feature_does_not_break():
    m = rm.Logistic().fit([[1.0, 0.0], [1.0, 1.0], [1.0, 1.0]], [0, 1, 1])
    assert all(0 < p < 1 for p in m.predict([[1.0, 0.0], [1.0, 1.0]]))


def test_laplace():
    assert rm.laplace(0, 0) == 0.5
    assert rm.laplace(3, 3) == pytest.approx(0.8)


# ---------------------------------------------------------------- metrics

def test_brier_and_log_loss():
    assert rm.brier([1.0, 0.0], [1, 0]) == 0.0
    assert rm.brier([0.5, 0.5], [1, 0]) == 0.25
    assert rm.log_loss([0.5, 0.5], [1, 0]) == pytest.approx(math.log(2))


def test_auc():
    assert rm.auc([0.9, 0.1], [1, 0]) == 1.0
    assert rm.auc([0.1, 0.9], [1, 0]) == 0.0
    assert rm.auc([0.5, 0.5], [1, 0]) == 0.5
    assert rm.auc([0.3, 0.4], [1, 1]) is None


def test_reliability_bins():
    rows = rm.reliability([0.1, 0.15, 0.9, 1.0], [0, 1, 1, 1])
    assert rows[0][:3] == (0.0, 0.2, 2) and rows[0][4] == 0.5
    assert rows[-1][:3] == (0.8, 1.0, 2) and rows[-1][4] == 1.0


def test_brier_skill_against_baseline():
    s = rm.score([0.9, 0.1], [1, 0], [0.5, 0.5])
    assert s["brier_skill"] == pytest.approx(1 - 0.01 / 0.25)


# ---------------------------------------------------------------- evaluation

_SEQ = iter(range(10 ** 6))


def _item(fault, unsafe, gate_fail, cohort="scripted", pid=None, group=None, decision=None):
    return {"cohort": cohort, "fault": fault, "patch_id": pid or f"{fault}-{unsafe}-{gate_fail}-{next(_SEQ)}",
            "unsafe": unsafe,
            "decision": decision or ("AUTO_APPLY" if not gate_fail else "REJECT"),
            "group": group or ("later_gate_failed" if gate_fail else "all_passed"),
            "x": {"gate_fail": float(gate_fail), "new_findings": 0.0, "log_diff_lines": 1.0, "multi_file": 0.0,
                  "sensitive_path": 0.0}}


def test_lofo_never_trains_on_the_held_out_fault(monkeypatch):
    seen = []
    real = rm.fit_predict

    def spy(train, test):
        seen.append(({t["fault"] for t in train}, {t["fault"] for t in test}))
        return real(train, test)

    monkeypatch.setattr(rm, "fit_predict", spy)
    data = [_item(f, u, g) for f in ("F01", "F02", "F03") for u, g in ((1, 1), (0, 0), (1, 0))]
    out = rm.lofo(data)
    assert len(out) == len(data)
    for train_faults, test_faults in seen:
        assert not (train_faults & test_faults)


def test_gate_table_uses_training_group_rate():
    train = [_item("F01", 1, 1, pid="a"), _item("F01", 1, 1, pid="b"), _item("F01", 0, 0, pid="c")]
    p = rm.fit_predict(train, [_item("F02", 1, 1, pid="d"), _item("F02", 0, 0, pid="e")])
    assert p["gate_table"] == [pytest.approx(3 / 4), pytest.approx(1 / 3)]
    assert p["base_rate"] == [pytest.approx(3 / 5)] * 2


def _independent_wilson(k, n, z=1.959963984540054):
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z / (1 + z * z / n) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return centre - half, centre + half


def test_group_estimate_numerator_denominator_and_wilson():
    data = [_item("F01", 1, 0) for _ in range(3)] + [_item("F01", 0, 0) for _ in range(4)]
    est = rm.group_estimate(data, "all_passed")
    assert (est["unsafe"], est["labelled"], est["status"]) == (3, 7, "ok")
    assert est["estimate"] == pytest.approx(3 / 7)
    lo, hi = _independent_wilson(3, 7)
    assert (est["ci95_low"], est["ci95_high"]) == (pytest.approx(lo), pytest.approx(hi))
    assert (round(est["ci95_low"], 3), round(est["ci95_high"], 3)) == (0.158, 0.750)


def test_zero_denominator_gives_no_estimate():
    est = rm.group_estimate([_item("F01", 1, 0)], "v0_failed")
    assert est["status"] == "no_labelled_support"
    assert est["estimate"] is None and est["ci95_low"] is None and est["ci95_high"] is None


def test_small_group_is_counts_only():
    est = rm.group_estimate([_item("F01", 1, 1) for _ in range(rm.MIN_GROUP_N - 1)], "later_gate_failed")
    assert est["status"] == "insufficient"
    assert (est["unsafe"], est["labelled"]) == (rm.MIN_GROUP_N - 1, rm.MIN_GROUP_N - 1)
    assert est["estimate"] is None


def test_profile_rates_keep_cohorts_separate():
    data = ([_item("F01", 1, 0, cohort="scripted") for _ in range(6)]
            + [_item("F01", 0, 0, cohort="llm") for _ in range(5)])
    rows = {(r["cohort"], r["group"]): r for r in rm.profile_rates(data)}
    assert rows[("scripted", "all_passed")]["estimate"] == 1.0
    assert rows[("llm", "all_passed")]["estimate"] == 0.0
    assert rows[("llm", "all_passed")]["labelled"] == 5


def test_auto_apply_is_a_subset_of_all_passed():
    data = [_item("F01", 1, 0, decision="AUTO_APPLY"), _item("F01", 0, 0, decision="ESCALATE")]
    assert rm.group_estimate(data, "auto_apply", min_n=1)["labelled"] == 1
    assert rm.group_estimate(data, "all_passed", min_n=1)["labelled"] == 2


def test_group_of_uses_gate_outcomes_only():
    assert rm.group_of(_unit(v0={"status": "fail"}, v1={"status": "not_run"})) == "v0_failed"
    assert rm.group_of(_unit(v2={"status": "error"})) == "later_gate_failed"
    assert rm.group_of(_unit()) == "all_passed"
    # the rule tier and decision never move a candidate between groups
    assert rm.group_of(_unit(tier="high", decision="REJECT")) == rm.group_of(_unit(tier="low", decision="AUTO_APPLY"))


def test_tier_and_decision_are_not_model_features():
    assert "tier" not in rm.FEATURES and "decision" not in rm.FEATURES
    assert rm.features_of(_unit(tier="high"), SENSITIVE) == rm.features_of(_unit(tier="low"), SENSITIVE)


# ---------------------------------------------------------------- dataset

def _row(run, cid, sha, ts, **gates):
    st = {g: gates.get(g, "pass") for g in ("v0", "v1", "v2", "v3")}
    return {"run_id": run, "candidate_id": cid, "fault_id": "F06", "patch_mode": "live", "diag_mode": "live",
            "timestamp": ts, "decision": "AUTO_APPLY", "patch_sha256": sha, "diff_lines": 2,
            "files_touched": ["A.java"], "new_findings": {"count": 0}, "invalid": None,
            **{g: {"status": s, "seconds": 1.0} for g, s in st.items()}}


def test_build_dataset_dedupes_by_patch_and_skips_unjudged(tmp_path):
    rows = [_row("r1", "c1", "same", "2026-01-01T00:00:00"),
            _row("r2", "c1", "same", "2026-01-02T00:00:00"),          # same diff, second run: one patch
            _row("r3", "c2", "other", "2026-01-03T00:00:00", v1="fail"),
            _row("r4", "c3", "bad", "2026-01-04T00:00:00", v0="fail")]  # oracle says invalid
    ev = tmp_path / "evidence.jsonl"
    ev.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    oracle = [{"label": "correct", "occurrences": [{"run_id": "r1", "candidate_id": "c1"},
                                                   {"run_id": "r2", "candidate_id": "c1"}]},
              {"label": "incorrect", "occurrences": [{"run_id": "r3", "candidate_id": "c2"}]},
              {"label": "invalid", "occurrences": [{"run_id": "r4", "candidate_id": "c3"}]}]
    (tmp_path / "oracle_report.jsonl").write_text("\n".join(json.dumps(o) for o in oracle), encoding="utf-8")
    (tmp_path / "faults").mkdir()
    data, info = rm.build_dataset(ev, tmp_path / "faults", {"sensitive_paths": SENSITIVE})
    by = {d["patch_id"]: d for d in data}
    assert set(by) == {"same", "other"}
    assert by["same"]["units"] == 2 and by["same"]["unsafe"] == 0
    assert by["other"]["unsafe"] == 1 and by["other"]["x"]["gate_fail"] == 1.0
    assert info["excluded"][("llm", "invalid")] == 1
    f = info["funnel"]["llm"]
    assert (f["raw_rows"], f["research_units"], f["labelled_units"], f["distinct_judged_patches"]) == (4, 4, 3, 2)


def test_missing_label_is_excluded_not_safe(tmp_path):
    rows = [_row("r1", "c1", "a", "2026-01-01T00:00:00"), _row("r2", "c2", "b", "2026-01-02T00:00:00")]
    ev = tmp_path / "evidence.jsonl"
    ev.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    (tmp_path / "oracle_report.jsonl").write_text(
        json.dumps({"label": "incorrect", "occurrences": [{"run_id": "r1", "candidate_id": "c1"}]}), encoding="utf-8")
    (tmp_path / "faults").mkdir()
    data, info = rm.build_dataset(ev, tmp_path / "faults", {"sensitive_paths": SENSITIVE})
    assert [d["patch_id"] for d in data] == ["a"]
    assert info["excluded"][("llm", "unlabelled")] == 1


def test_candidates_get_model_probability_only_when_judged(tmp_path):
    rows = [_row("r1", "c1", "a", "2026-01-01T00:00:00"), _row("r2", "c2", "b", "2026-01-02T00:00:00")]
    ev = tmp_path / "evidence.jsonl"
    ev.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    (tmp_path / "oracle_report.jsonl").write_text(
        json.dumps({"label": "incorrect", "occurrences": [{"run_id": "r1", "candidate_id": "c1"}]}), encoding="utf-8")
    (tmp_path / "faults").mkdir()
    data, info = rm.build_dataset(ev, tmp_path / "faults", {"sensitive_paths": SENSITIVE})
    profiles = rm.profile_rates(data)
    oof = {"llm|a": {"logistic": 0.7}}
    cands = {c["candidate_id"]: c for c in rm.candidate_entries(info["units"], data, profiles, oof, SENSITIVE)}
    assert cands["c1"]["model_probability"] == 0.7 and cands["c1"]["judged"]
    assert cands["c2"]["model_probability"] is None and not cands["c2"]["judged"]
    # an unjudged candidate still shows its group's (cohort-level) rate, labelled as a group rate
    assert cands["c2"]["group_estimate"] == cands["c1"]["group_estimate"]
    assert cands["c2"]["oracle_label"] is None


# ---------------------------------------------------------------- real evidence (integration)

REPO = rm.REPO


@pytest.mark.skipif(not (REPO / "results" / "evidence.jsonl").is_file(), reason="no local evidence")
def test_real_evidence_is_internally_consistent():
    files = rm.run(REPO / "results" / "evidence.jsonl", REPO / "faults", REPO / "config" / "decision.yaml")
    doc = json.loads(files["risk_estimation.json"])
    for e in doc["empirical"]["estimates"]:
        if e["status"] == "ok":
            assert e["estimate"] == pytest.approx(e["unsafe"] / e["labelled"])
            assert e["labelled"] >= doc["min_group_n"]
        else:
            assert e["estimate"] is None
    for c in ("scripted", "llm"):
        est = {e["group"]: e for e in doc["empirical"]["estimates"] if e["cohort"] == c}
        partition = sum(est[g]["labelled"] for g in ("v0_failed", "later_gate_failed", "all_passed"))
        assert partition == doc["funnel"][c]["distinct_judged_patches"]
        assert est["auto_apply"]["labelled"] <= est["all_passed"]["labelled"]
    assert len(doc["candidates"]) == sum(doc["funnel"][c]["research_units"] for c in ("scripted", "llm"))
    for cand in doc["candidates"]:
        if not cand["judged"]:
            assert cand["model_probability"] is None
    for m in doc["model"]["metrics"]:
        assert m["cohort"] in ("scripted", "llm")
