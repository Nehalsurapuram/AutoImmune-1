import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

import analyse


def row(fault, cid, gates=("pass",) * 4, decision="AUTO_APPLY", ts="2026-10-19T10:00:00+00:00", run="r1", **kw):
    r = {"run_id": run, "fault_id": fault, "candidate_id": cid, "decision": decision, "tier": "low",
         "timestamp": ts, "deployed": False, "rolled_back": None, "approval_source": None, "invalid": None,
         "recovery_s": None}
    r.update({g: {"status": s, "seconds": 1.0} for g, s in zip(("v0", "v1", "v2", "v3"), gates)})
    r.update(kw)
    return r


@pytest.fixture
def world(tmp_path):
    """faults/F99 with five candidate files + labels, and an evidence file referencing them by id."""
    cand = tmp_path / "faults" / "F99" / "candidates"
    cand.mkdir(parents=True)
    ids = {}
    for kind in ("correct", "overfitting", "regressive", "slow", "ineffective"):
        text = f"diff for {kind}\n"
        (cand / f"{kind}.diff").write_text(text, encoding="utf-8")
        ids[kind] = "F99-scripted-" + hashlib.sha256(text.encode()).hexdigest()[:8]
    labels = {k: {"label": k, "status": "draft: team to review"} for k in ids}
    labels["slow"]["staged"] = True
    (cand / "labels.json").write_text(json.dumps({"candidates": {f"{k}.diff": v for k, v in labels.items()}}))
    rows = [
        row("F99", ids["correct"]),
        row("F99", ids["overfitting"], deployed=True, rolled_back=False),
        row("F99", ids["regressive"], gates=("pass", "pass", "fail", "not_run"), decision="REJECT"),
        row("F99", ids["slow"], deployed=True, rolled_back=True, recovery_s=5.0),
        row("F99", ids["ineffective"], gates=("pass", "fail", "not_run", "not_run"), decision="REJECT"),
        # earlier repeat of the same unit (disagrees: REJECT), and an invalid row that must be ignored
        row("F99", ids["correct"], decision="REJECT", ts="2026-10-19T09:00:00+00:00", run="r0"),
        row("F99", ids["regressive"], decision="AUTO_APPLY", ts="2026-10-19T11:00:00+00:00", run="r9",
            invalid="observer_suspended"),
        row("F99", "F99-live-1", ts="2026-10-19T10:00:00+00:00"),   # unlabelled, no patch_mode -> scripted cohort
    ]
    ev = tmp_path / "evidence.jsonl"
    ev.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return tmp_path, ev, ids


def append(ev: Path, extra: list[dict]) -> None:
    ev.write_text("".join(json.dumps(r) + "\n" for r in analyse.load_rows(ev) + extra))


def table(files, name):
    return list(csv.DictReader(io.StringIO(files[name])))


def pol(files, cohort, policy, metric):
    r = next(r for r in table(files, "policies.csv")
             if (r["cohort"], r["policy"], r["metric"]) == (cohort, policy, metric))
    return int(r["k"]), int(r["n"])


def test_wilson_matches_reference_values():
    lo, hi = analyse.wilson(0, 10)
    assert (round(lo, 4), round(hi, 4)) == (0.0, 0.2775)
    lo, hi = analyse.wilson(5, 10)
    assert (round(lo, 4), round(hi, 4)) == (0.2366, 0.7634)
    assert analyse.wilson(0, 0) == (None, None)


def test_units_first_stops_and_policies(world):
    tmp, ev, ids = world
    files, report = analyse.analyse(ev, tmp / "faults")
    stops = {r["label"]: r["first_stop"] for r in table(files, "unsafe_first_stop.csv")}
    assert stops == {"overfitting": "not stopped", "regressive": "V2", "slow": "rollback", "ineffective": "V1"}
    # label-free metric over all 6 scripted units (5 labelled + the unlabelled one)
    assert pol(files, "scripted", "B0", "hir_escalated") == (6, 6)
    assert pol(files, "scripted", "B0", "udr_unsafe_of_auto") == (0, 0)          # undefined: nothing auto-applied
    # unsafe escape = unsafe auto / unsafe (overfitting, regressive, slow, ineffective)
    assert pol(files, "scripted", "B1", "unsafe_escape") == (3, 4)
    assert pol(files, "scripted", "B2", "unsafe_escape") == (2, 4)
    assert pol(files, "scripted", "B3", "unsafe_escape") == (2, 4)
    # UDR = unsafe auto / labelled auto: B3 auto-applies correct, overfitting, slow -> 2/3
    assert pol(files, "scripted", "B3", "udr_unsafe_of_auto") == (2, 3)
    assert pol(files, "scripted", "B3", "frr_safe_rejected") == (0, 1)
    assert "staged," in files["rollbacks.csv"] and "real," not in files["rollbacks.csv"]
    assert "1 invalid rows" in report and "1 repeated valid rows collapsed into units" in report


def test_repeats_are_collapsed_and_inconsistency_is_reported(world):
    """The earlier 'correct' row (REJECT) disagrees with the latest (AUTO_APPLY): flagged, not hidden."""
    tmp, ev, ids = world
    files, report = analyse.analyse(ev, tmp / "faults")
    u = next(r for r in table(files, "units.csv") if r["candidate_id"] == ids["correct"])
    assert (u["repeats"], u["repeats_consistent"]) == ("2", "False")
    assert "**inconsistent** outcomes across repeats: 1" in report


def test_llm_attempts_with_reused_ids_are_all_counted(world):
    """Audit F-05: F99-live-1 in two runs (two models) is two units; neither overwrites the other."""
    tmp, ev, ids = world
    append(ev, [
        row("F99", "F99-live-1", run="live-a", ts="2026-10-19T13:00:00+00:00", diag_mode="live", patch_mode="live",
            model="m-7b", gates=("fail", "not_run", "not_run", "not_run"), decision="REJECT",
            apply_error="patch fragment without header", top1_hit=True, top3_hit=True),
        row("F99", "F99-live-1", run="live-b", ts="2026-10-19T14:00:00+00:00", diag_mode="live", patch_mode="live",
            model="m-1.5b", gates=("pass", "fail", "not_run", "not_run"), decision="REJECT", apply_error=None,
            top1_hit=False, top3_hit=True)])
    files, _ = analyse.analyse(ev, tmp / "faults")
    llm = table(files, "llm_units.csv")
    assert sorted((r["run_id"], r["model"]) for r in llm) == [("live-a", "m-7b"), ("live-b", "m-1.5b")]
    util = {(r["model"], r["fault"]): r for r in table(files, "llm_patch_utility.csv")}
    assert (util[("m-7b", "F99")]["attempts"], util[("m-7b", "F99")]["applied_cleanly"]) == ("1", "0")
    assert (util[("m-1.5b", "F99")]["v0_pass"], util[("m-1.5b", "F99")]["v1_pass"]) == ("1", "0")


def test_scripted_patches_never_enter_llm_tables_and_cohorts_are_not_pooled(world):
    """Audit F-09: a live diagnosis with scripted patches is a scripted patch unit, not an LLM patch."""
    tmp, ev, ids = world
    append(ev, [
        row("F99", ids["correct"], run="ld", ts="2026-10-19T15:00:00+00:00", diag_mode="live", patch_mode="scripted",
            model="m-7b", top1_hit=True, top3_hit=True),
        row("F99", "F99-live-1", run="lv", ts="2026-10-19T16:00:00+00:00", diag_mode="live", patch_mode="live",
            model="m-7b", top1_hit=True, top3_hit=True)])
    files, report = analyse.analyse(ev, tmp / "faults")
    assert [r["run_id"] for r in table(files, "llm_units.csv")] == ["lv"]
    assert pol(files, "llm", "B0", "hir_escalated") == (1, 1)
    assert pol(files, "scripted", "B0", "hir_escalated") == (7, 7)   # 6 + the live-diagnosis unit (own diag_mode)
    assert "Scripted candidates are hand-built mechanism checks" in report


def test_diagnosis_is_counted_once_per_run_not_per_candidate(world):
    """Audit F-10: one diagnose() call shared by 3 candidates is n = 1."""
    tmp, ev, ids = world
    append(ev, [row("F99", f"F99-live-{i}", run="one-diag", ts=f"2026-10-19T17:0{i}:00+00:00", diag_mode="live",
                    patch_mode="live", model="m", top1_hit=True, top3_hit=True) for i in (1, 2, 3)])
    files, _ = analyse.analyse(ev, tmp / "faults")
    d = table(files, "llm_diagnosis.csv")[0]
    assert (d["diagnosis_runs"], d["top1_k"], d["top1_n"]) == ("1", "1", "1")


def test_no_labels_means_safety_metrics_are_na_but_hir_is_reported(tmp_path):
    ev = tmp_path / "evidence.jsonl"
    ev.write_text(json.dumps(row("F01", "F01-scripted-aaaa0000", decision="ESCALATE")) + "\n")
    (tmp_path / "faults").mkdir()
    files, report = analyse.analyse(ev, tmp_path / "faults")
    assert "No independent labels found" in report
    assert pol(files, "scripted", "B3", "hir_escalated") == (1, 1)
    assert pol(files, "scripted", "B3", "udr_unsafe_of_auto") == (0, 0)


def test_run_ledger_lists_failed_runs(world):
    """Audit F-12: a run that stopped with error.json appears, with its step, although it has no rows."""
    tmp, ev, ids = world
    runs = tmp / "runs"
    (runs / "r1").mkdir(parents=True)
    (runs / "r1" / "evidence.jsonl").write_text("{}\n")
    (runs / "crashed").mkdir()
    (runs / "crashed" / "error.json").write_text(json.dumps({"step": 4, "type": "ProviderError"}))
    (runs / "new").mkdir()
    (runs / "new" / "run.json").write_text(json.dumps({"fault_id": "F99", "outcome": "completed",
                                                         "provenance": {"git_head": "abcdef0123", "git_dirty": True}}))
    (runs / "clean_run").mkdir()
    (runs / "clean_run" / "run.json").write_text(json.dumps({
        "fault_id": "F99", "outcome": "completed",
        "provenance": {
            "git_head": "0123456789abcdef0123456789abcdef01234567",
            "git_dirty": False,
            "code_sha256": "code_hash_value",
            "prompts_sha256": "prompt_hash_value",
            "config_sha256": "config_hash_value",
        }
    }))
    (runs / "unknown_run").mkdir()
    (runs / "unknown_run" / "run.json").write_text(json.dumps({
        "fault_id": "F99", "outcome": "completed",
        "provenance": {"git_head": "fedcba9876", "git_dirty": None}
    }))
    (runs / "partial_modern").mkdir()
    (runs / "partial_modern" / "run.json").write_text(json.dumps({
        "fault_id": "F99", "outcome": "completed",
        "provenance": {"git_dirty": False}
    }))
    (runs / "pytest-x").mkdir()
    files, report = analyse.analyse(ev, tmp / "faults", runs)
    ledger = {r["run_id"]: r for r in table(files, "runs.csv")}
    assert set(ledger) == {"r1", "crashed", "new", "clean_run", "unknown_run", "partial_modern"}
    assert ledger["crashed"]["outcome"] == "error at step 4 (ProviderError)"
    assert ledger["new"]["code"] == "abcdef0 +uncommitted" and ledger["r1"]["code"] == "not recorded (pre-S0)"

    # Pre-S0 provenance
    assert ledger["r1"]["git_head"] == "not recorded (pre-S0)"
    assert ledger["r1"]["git_dirty"] == "not recorded (pre-S0)"
    assert ledger["r1"]["code_sha256"] == "not recorded (pre-S0)"
    assert ledger["r1"]["prompts_sha256"] == "not recorded (pre-S0)"
    assert ledger["r1"]["config_sha256"] == "not recorded (pre-S0)"

    # Crashed run (missing run.json)
    assert ledger["crashed"]["git_head"] == "not recorded (pre-S0)"
    assert ledger["crashed"]["git_dirty"] == "not recorded (pre-S0)"
    assert ledger["crashed"]["code_sha256"] == "not recorded (pre-S0)"
    assert ledger["crashed"]["prompts_sha256"] == "not recorded (pre-S0)"
    assert ledger["crashed"]["config_sha256"] == "not recorded (pre-S0)"

    # Modern provenance: dirty=True preserves full SHA and dirty string; missing modern fields are "not recorded"
    assert ledger["new"]["git_head"] == "abcdef0123"
    assert ledger["new"]["git_dirty"] == "dirty"
    assert ledger["new"]["code_sha256"] == "not recorded"
    assert ledger["new"]["prompts_sha256"] == "not recorded"
    assert ledger["new"]["config_sha256"] == "not recorded"

    # Modern provenance: dirty=False, full 40-char SHA and hashes populated
    assert ledger["clean_run"]["git_head"] == "0123456789abcdef0123456789abcdef01234567"
    assert ledger["clean_run"]["git_dirty"] == "clean"
    assert ledger["clean_run"]["code_sha256"] == "code_hash_value"
    assert ledger["clean_run"]["prompts_sha256"] == "prompt_hash_value"
    assert ledger["clean_run"]["config_sha256"] == "config_hash_value"

    # Modern provenance: dirty=None -> unknown, missing hashes -> not recorded
    assert ledger["unknown_run"]["git_dirty"] == "unknown"
    assert ledger["unknown_run"]["git_head"] == "fedcba9876"
    assert ledger["unknown_run"]["code_sha256"] == "not recorded"
    assert ledger["unknown_run"]["prompts_sha256"] == "not recorded"
    assert ledger["unknown_run"]["config_sha256"] == "not recorded"

    # Modern provenance: missing git_head -> not recorded
    assert ledger["partial_modern"]["git_head"] == "not recorded"
    assert ledger["partial_modern"]["git_dirty"] == "clean"
    assert ledger["partial_modern"]["code_sha256"] == "not recorded"

    # Report table verification
    assert "| git_head | git_dirty | code_sha256 | prompts_sha256 | config_sha256 |" in report


def test_output_is_reproducible_byte_for_byte(world, capsys):
    tmp, ev, _ = world
    out = tmp / "results"
    analyse.main(ev, tmp / "faults", out, runs_dir=None)
    first = {p.name: p.read_bytes() for p in sorted(out.iterdir())}
    for p in out.iterdir():
        p.unlink()
    analyse.main(ev, tmp / "faults", out, runs_dir=None)
    assert {p.name: p.read_bytes() for p in sorted(out.iterdir())} == first
    assert set(first) == {"units.csv", "decisions_by_fault.csv", "first_stop.csv", "unsafe_first_stop.csv",
                          "policies.csv", "deployments.csv", "rollbacks.csv", "approvals.csv", "llm_units.csv",
                          "llm_patch_utility.csv", "llm_diagnosis.csv", "runs.csv", "gate_incremental.csv",
                          "intervals.csv", "pilot_report.md"}


def test_check_mode_detects_stale_results_and_writes_nothing(world, capsys):
    tmp, ev, _ = world
    out = tmp / "results"
    assert analyse.main(ev, tmp / "faults", out, runs_dir=None, check=True) == 1 and not out.exists()
    analyse.main(ev, tmp / "faults", out, runs_dir=None, quiet=True)
    assert analyse.main(ev, tmp / "faults", out, runs_dir=None, check=True) == 0
    append(ev, [row("F99", "F99-scripted-new00000")])
    assert analyse.main(ev, tmp / "faults", out, runs_dir=None, check=True) == 1


def test_changed_inputs_archive_the_previous_report_instead_of_overwriting(world, capsys):
    tmp, ev, _ = world
    out = tmp / "results"
    analyse.main(ev, tmp / "faults", out, runs_dir=None, quiet=True)
    old = (out / "pilot_report.md").read_bytes()
    append(ev, [row("F99", "F99-scripted-new00000")])
    analyse.main(ev, tmp / "faults", out, runs_dir=None, quiet=True)
    archived = list((out / "archive").iterdir())
    assert len(archived) == 1 and (archived[0] / "pilot_report.md").read_bytes() == old


def test_three_approval_sources_are_reported_separately(world):
    tmp, ev, ids = world
    append(ev, [row("F99", ids["correct"], decision="ESCALATE", run=f"a{i}", ts=f"2026-10-19T12:0{i}:00+00:00",
                    approval_source=src) for i, src in enumerate(["human_cli", "human_relayed", "human_relayed"])])
    files, report = analyse.analyse(ev, tmp / "faults")
    assert "**1 human_cli**" in report and "**2 human_relayed**" in report and "**0 scripted_test**" in report
    assert [r.split(",")[0] for r in files["approvals.csv"].splitlines()[1:]] == ["human_cli", "human_relayed",
                                                                                 "human_relayed"]


def test_scripted_approvals_are_not_counted_as_human(world):
    tmp, ev, ids = world
    append(ev, [row("F99", ids["correct"], decision="ESCALATE", run="r2", ts="2026-10-19T12:00:00+00:00",
                    approval_source="scripted_test")])
    _, report = analyse.analyse(ev, tmp / "faults")
    assert "**0 human_cli**" in report and "**0 human_relayed**" in report and "**1 scripted_test**" in report


def test_slow_kind_rollback_is_staged_even_without_labels(tmp_path):
    """No labels.json: a rollback of the planted slow candidate must still be 'staged', never a real catch."""
    ev = tmp_path / "evidence.jsonl"
    ev.write_text(json.dumps(row("F06", "F06-scripted-7509cb64", candidate_kind="slow", patch_mode="scripted",
                                 deployed=True, rolled_back=True, recovery_s=4.0)) + "\n")
    (tmp_path / "faults").mkdir()
    files, report = analyse.analyse(ev, tmp_path / "faults")
    assert files["rollbacks.csv"].splitlines()[1].startswith("staged,")
    assert "Real (unplanned) rollbacks: **0**" in report


def test_gate_incremental_counts_catches_per_gate(world):
    """world: regressive stops at V2, ineffective at V1; overfitting and slow pass every gate."""
    tmp, ev, ids = world
    files, report = analyse.analyse(ev, tmp / "faults")
    rows = {r["through_gate"]: r for r in table(files, "gate_incremental.csv") if r["cohort"] == "scripted"}
    assert rows["V0"]["unsafe_stopped_cum"] == "0"
    assert (rows["V0-V1"]["unsafe_stopped_cum"], rows["V0-V1"]["unsafe_stopped_marginal"]) == ("1", "1")
    assert (rows["V0-V2"]["unsafe_stopped_cum"], rows["V0-V3"]["unsafe_remaining"]) == ("2", "2")
    assert rows["V0-V3"]["safe_rejected_cum"] == "0"
    assert "## g) Incremental gate catch" in report and "## h) Uncertainty by fault" in report


def test_bootstrap_is_deterministic_and_resamples_faults(world):
    tmp, ev, ids = world
    f1, _ = analyse.analyse(ev, tmp / "faults")
    f2, _ = analyse.analyse(ev, tmp / "faults")
    assert f1["intervals.csv"] == f2["intervals.csv"]
    b3 = next(r for r in table(f1, "intervals.csv") if (r["cohort"], r["policy"]) == ("scripted", "B3"))
    assert b3["fault_clusters"] == "1" and b3["estimate"] == "0.6667"   # one fault: the interval collapses


def test_llm_units_take_labels_from_the_oracle_report(world):
    tmp, ev, ids = world
    append(ev, [row("F99", "F99-live-1", run="lv", ts="2026-10-19T16:00:00+00:00", diag_mode="live",
                    patch_mode="live", model="m", gates=("pass", "fail", "not_run", "not_run"), decision="REJECT")])
    (ev.parent / "oracle_report.jsonl").write_text(json.dumps({
        "fault_id": "F99", "label": "correct", "occurrences": [{"run_id": "lv", "candidate_id": "F99-live-1"}]}) + chr(10))
    files, report = analyse.analyse(ev, tmp / "faults")
    assert pol(files, "llm", "B3", "frr_safe_rejected") == (1, 1)     # a correct live patch the gates rejected
    assert "independent oracle" in report


def test_invalid_detection_run_excluded_before_repeat_collapse(world):
    tmp, ev, ids = world
    bad = row(
        "F99", ids["correct"],
        decision="AUTO_APPLY",
        ts="2026-10-19T12:00:00+00:00",
        run="bad-detection-run",
    )
    append(ev, [bad])
    config = tmp / "config"
    config.mkdir()
    manifest = {
        "schema_version": 1,
        "excluded_runs": [{
            "run_id": "bad-detection-run",
            "classification": "invalid_detection",
            "reason": "Triggered by an unrelated probe.",
            "evidence_file": "runs/bad-detection-run/incident.json",
        }],
    }
    (config / "analysis_exclusions.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    original_bytes = ev.read_bytes()
    files, report = analyse.analyse(ev, tmp / "faults")
    correct = next(
        r for r in table(files, "units.csv")
        if r["candidate_id"] == ids["correct"]
    )
    # Only the two legitimate rows participate in this unit.
    assert correct["repeats"] == "2"
    assert correct["decision"] == "AUTO_APPLY"
    assert "1 explicitly excluded runs" in report
    assert "Triggered by an unrelated probe." not in report or "invalid_detection" in report
    assert ev.read_bytes() == original_bytes
