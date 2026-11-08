"""One end-to-end run for one fault. Fixed pipeline, no agent loop:

     1 banner                       6 choose one candidate (no candidate_kind, no labels)
     2 baseline running + healthy   7 deploy + health window -> promote or roll back
     3 faulty build + detector      8 one evidence row per candidate
     4 diagnose + draft patches     9 restore the baseline
     5 gates + decide per candidate 10 summary table

    python -m pipeline run --fault F06 --diag-mode rule --patch-mode scripted [--candidate ID] [--deploy-each]

Every step writes into runs/<run_id>/. A failing step stops the run with the real error (error.json);
the baseline is restored in any case.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pipeline import deploy, detector, provenance, record, sandbox, terminal
from pipeline.decide import decide, patch_meta
from pipeline.providers import get_provider

REPO = Path(__file__).resolve().parents[1]
GATES = sandbox.GATES


class StepError(RuntimeError):
    def __init__(self, step: int, title: str, cause: BaseException):
        super().__init__(f"step {step} ({title}) failed: {type(cause).__name__}: {cause}")
        self.step, self.title, self.cause = step, title, cause


@dataclass
class Selection:
    chosen: list[dict]      # entries to deploy, in order
    note: str


def _rank(e: dict) -> tuple:
    return (e["diff_lines"], e["candidate_id"])


def choose(entries: list[dict], override: str | None = None, deploy_each: bool = False) -> Selection:
    """Pick what to deploy from {candidate_id, decision, diff_lines} entries; no other field is read.

    AUTO_APPLY with the fewest diff lines (tie: candidate_id); --deploy-each: every AUTO_APPLY in that order.
    No AUTO_APPLY: the first ESCALATE in the same order goes to human review. Neither: no safe candidate.
    override (--candidate) picks one id for demos; deploy.release still refuses REJECT and unapproved ESCALATE.
    """
    view = [{"candidate_id": e["candidate_id"], "decision": e["decision"], "diff_lines": e["diff_lines"]}
            for e in entries]
    if override:
        match = [e for e in view if e["candidate_id"] == override]
        if not match:
            raise ValueError(f"--candidate {override} is not one of {[e['candidate_id'] for e in view]}")
        return Selection(match, f"--candidate {override} chosen by the operator ({match[0]['decision']})")
    auto = sorted((e for e in view if e["decision"] == "AUTO_APPLY"), key=_rank)
    if auto:
        if deploy_each:
            return Selection(auto, f"--deploy-each: all {len(auto)} AUTO_APPLY candidates, fewest diff lines first")
        return Selection(auto[:1], f"AUTO_APPLY with the fewest diff lines ({auto[0]['diff_lines']})")
    esc = sorted((e for e in view if e["decision"] == "ESCALATE"), key=_rank)
    if esc:
        return Selection(esc[:1], "no AUTO_APPLY candidate; the first ESCALATE candidate goes to human review")
    return Selection([], "no safe candidate: every candidate was REJECTED")


def keep_awake() -> None:
    """Windows: keep the host from idle-sleeping while this process runs (process-scoped, no settings change)."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _source_files(app_dir: Path) -> dict[str, str]:
    """Production sources of the deployed (faulty) build, keyed by repo path. Never tests, never faults/."""
    files = {}
    for p in sorted((app_dir / "src" / "main").rglob("*")):
        if p.is_file() and p.suffix in (".java", ".properties"):
            files["app/" + p.relative_to(app_dir).as_posix()] = p.read_text(encoding="utf-8")
    return files


def _hit_flags(diagnosis, fault_id: str, repo: Path) -> tuple[bool | None, bool | None]:
    """Compute top1_hit and top3_hit by comparing diagnosis causes against fault.json diagnosed_file.
    Returns (top1_hit, top3_hit). Both are None when oracle_localisation=True (the answer came from
    fault.json itself, so the comparison is not informative).
    Evaluator-only: the result is written to artifacts; it never enters the model prompt or decide()."""
    if getattr(diagnosis, "oracle_localisation", False):
        return None, None
    fault_path = repo / "faults" / fault_id / "fault.json"
    if not fault_path.is_file():
        return None, None
    diagnosed_file = json.loads(fault_path.read_text(encoding="utf-8")).get("diagnosed_file", "")
    if not diagnosed_file:
        return None, None
    causes = getattr(diagnosis, "causes", []) or []
    sorted_causes = sorted(causes, key=lambda c: getattr(c, "rank", 99) if hasattr(c, "rank") else c.get("rank", 99))
    files = [getattr(c, "file", None) or c.get("file") for c in sorted_causes]
    top1_hit = (files[0] == diagnosed_file) if files else False
    top3_hit = any(f == diagnosed_file for f in files[:3])
    return top1_hit, top3_hit


def _result(rel: dict | None, decision: str) -> str:
    if rel is None:
        return {"REJECT": "not deployed (REJECT)", "ESCALATE": "awaiting review"}.get(decision, "not chosen")
    if not rel["deployed"]:
        return "awaiting review (not approved)" if rel.get("awaiting_review") else rel.get("reason", "not deployed")
    if rel["outcome"] == "promoted":
        return "promoted"
    if rel["outcome"] == "rolled_back":
        return f"rolled back in {rel['recovery_s']}s: {rel['reason']}"
    return rel["outcome"]


def print_table(rows: list[dict]) -> None:
    head = ["candidate", "V0", "V1", "V2", "V3", "tier", "decision", "deployed", "result"]
    body = [[r["candidate_id"], *[r["gates"][g] for g in GATES], r["tier"], r["decision"],
             "yes" if r["deployed"] else "no", r["result"]] for r in rows]
    widths = [max(len(str(x)) for x in col) for col in zip(head, *body)]
    line = lambda cells: "| " + " | ".join(str(c).ljust(w) for c, w in zip(cells, widths)) + " |"  # noqa: E731
    print(line(head))
    print("|" + "|".join("-" * (w + 2) for w in widths) + "|")
    for b in body:
        print(line(b))


def run(fault: str, diag_mode: str, patch_mode: str, *, candidate: str | None = None, deploy_each: bool = False,
        run_id: str | None = None, input_fn=input, approval_source: str = "human_cli",
        diag_samples: int | None = None, gates_only: bool = False) -> dict:
    """approval_source: "human_cli" when a person answers approve_cli at the terminal; callers that feed the
    answer through input_fn from a script must pass "scripted_test".
    diag_samples: override config diag_samples (number of diagnosis samples for H1; None = use config).
    gates_only: stop after step 5 (gates + decisions); do not deploy, record, or print summary table."""
    cfg = deploy.load_config()
    # Resolve n_samples: CLI flag > config value > default 1
    n_samples = diag_samples if diag_samples is not None else int(cfg.get("diag_samples", 1))
    sample_temperature = float(cfg.get("diag_temperature", 0.7))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = (run_id or f"{fault}-{diag_mode}-{patch_mode}-{stamp}").lower()
    run_dir = REPO / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    keep_awake()
    t0 = time.monotonic()
    state = {"step": 1, "title": "BASELINE INITIALIZATION"}

    def step(n: int, title: str) -> None:
        state.update(step=n, title=title)
        elapsed = time.monotonic() - t0
        terminal.print_stage(n, 10, title, elapsed)

    extra_note = "" if {diag_mode, patch_mode} & {"live", "replay"} else "(no LLM: rule/scripted results)"
    terminal.print_header(run_id, fault, diag_mode, patch_mode, extra_note)

    run_meta = {"run_id": run_id, "fault_id": fault, "diag_mode": diag_mode,
                "patch_mode": patch_mode, "candidate": candidate, "deploy_each": deploy_each,
                "diag_samples": n_samples, "gates_only": gates_only,
                "started_at": stamp, "ended_at": None, "outcome": "running", "config": cfg,
                "provenance": provenance.collect(cfg)}
    _write(run_dir / "run.json", run_meta)

    def finish(outcome: str, error: str | None = None) -> None:
        """Close run.json: every run ends as completed, gates_only or error, never silently."""
        run_meta.update(ended_at=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), outcome=outcome,
                        error=error, n_candidates=len(candidates))
        _write(run_dir / "run.json", run_meta)

    candidates: list[dict] = []
    releases: dict[str, dict] = {}
    approvals: dict[str, dict] = {}
    try:
        step(1, "BASELINE INITIALIZATION")
        with tempfile.TemporaryDirectory(prefix="autoimmune-run-") as tmp:
            step(2, "HEALTH CHECK")
            if deploy.current_image() == deploy.BASELINE_TAG and deploy._health(cfg)["ok"]:
                info = {"image": deploy.BASELINE_TAG, "already_running": True}
            else:
                info = deploy.start_baseline(cfg=cfg)
            _write(run_dir / "baseline.json", info)
            print(f"  {info}")

            step(3, "FAULT INJECTION & INCIDENT DETECTION")
            faulty_src = sandbox.prepare_patched_app(fault, None, Path(tmp) / "faulty")
            faulty = deploy.deploy(faulty_src, f"{run_id}-faulty", cfg)
            _write(run_dir / "faulty_deploy.json", {k: v for k, v in faulty.items() if k != "swap_clock"})
            print(f"  running {faulty['new_image']} (answering after {faulty['swap_to_answer_s']}s)", flush=True)
            incident = detector.watch(cfg.get("detect_timeout_s", 60), run_id=run_id, fault_id=fault)
            if incident is None:
                raise RuntimeError(f"no incident within {cfg.get('detect_timeout_s', 60)}s")
            if incident.get("status") == "invalid":
                raise RuntimeError(f"detector invalid: {incident['invalid']} ({incident['sign']})")
            print(f"  incident: rule={incident['rule']} endpoint={incident['endpoint']} "
                  f"status={incident['status']} -> runs/{run_id}/incident.json")

            step(4, "AI DIAGNOSIS & PATCH GENERATION")
            sources = _source_files(faulty_src)
            # Build provider kwargs for LLM modes: thread in n_samples and sample_temperature
            diag_kwargs = ({"n_samples": n_samples, "sample_temperature": sample_temperature}
                           if diag_mode in ("live", "replay") else {})
            diagnosis = get_provider(diag_mode, **diag_kwargs).diagnose(incident, sources)
            # Evaluator-side top-3 hit: compare causes against fault.json diagnosed_file
            # (never shown to model or decide(); stored in artifacts for analysis only)
            top1_hit, top3_hit = _hit_flags(diagnosis, fault, REPO)
            diag_dict = diagnosis.to_dict()
            diag_dict["top1_hit"] = top1_hit
            diag_dict["top3_hit"] = top3_hit
            _write(run_dir / "diagnosis.json", diag_dict)
            top = diagnosis.causes[0]
            print(f"  diagnosis: {top.file}:{top.line} (oracle_localisation={diagnosis.oracle_localisation}, "
                  f"top1_hit={top1_hit}, top3_hit={top3_hit}, "
                  f"samples={len(diagnosis.samples)}, samples_disagree={diagnosis.samples_disagree})")
            patches = get_provider(patch_mode).draft_patches(diagnosis, sources, fault,
                                                             n=None if patch_mode == "scripted" else 3)
            _write(run_dir / "patches.json", [p.to_dict() for p in patches])
            print(f"  {len(patches)} candidates: {', '.join(p.candidate_id for p in patches)}")

            step(5, "SANDBOX VALIDATION — V0 TO V3")
            for p in patches:
                gates = sandbox.run_gates(fault, p, run_id)
                meta = patch_meta(p.diff)
                dec = decide(gates, diagnosis, meta, cfg)
                _write(run_dir / p.candidate_id / "decision.json", {**dec.to_dict(), "patch_meta": meta})
                candidates.append({"patch": p, "gates": gates, "meta": meta, "decision": dec})

            # Present clean aligned validation gate table
            terminal.print_gate_table([
                {"candidate_id": c["patch"].candidate_id, "gates": c["gates"], "decision": c["decision"].decision}
                for c in candidates
            ])

            if gates_only:
                step(6, "CANDIDATE SELECTION")
                for c in candidates:
                    cid = c["patch"].candidate_id
                    llm_attempts = (len(diagnosis.attempts) // max(1, n_samples)
                                    if diag_mode in ("live", "replay") else None)
                    row = record.build_row(
                        run_id=run_id, fault_id=fault, gates=c["gates"], diagnosis=diagnosis, patch=c["patch"],
                        patch_meta=c["meta"], decision=c["decision"],
                        deployed=False,
                        rolled_back=None,
                        awaiting_review=(c["decision"].decision == "ESCALATE"),
                        recovery_s=None,
                        approval=None,
                        invalid=None,
                        top1_hit=top1_hit, top3_hit=top3_hit,
                        diag_samples=n_samples if diag_mode in ("live", "replay") else None,
                        samples_disagree=diagnosis.samples_disagree,
                        model=diagnosis.model,
                        llm_attempts=llm_attempts,
                        apply_error=c["patch"].apply_error)
                    record.append_row(row)
                    record.append_row(row, run_dir / "evidence.jsonl")
                print(f"  {len(candidates)} rows -> results/evidence.jsonl and runs/{run_id}/evidence.jsonl")
                finish("gates_only")
                return {"run_id": run_id, "fault_id": fault, "diag_mode": diag_mode, "patch_mode": patch_mode,
                        "gates_only": True, "candidates": [
                            {"candidate_id": c["patch"].candidate_id,
                             "gates": {g: c["gates"]["gates"][g]["status"] for g in GATES},
                             "tier": c["decision"].tier, "decision": c["decision"].decision}
                            for c in candidates]}

            step(6, "CANDIDATE SELECTION")
            sel = choose([{"candidate_id": c["patch"].candidate_id, "decision": c["decision"].decision,
                           "diff_lines": c["meta"]["diff_lines"]} for c in candidates], candidate, deploy_each)
            _write(run_dir / "choice.json", {"note": sel.note, "chosen": sel.chosen})
            print(f"  {sel.note}: {[e['candidate_id'] for e in sel.chosen] or 'none'}")

            step(7, "DEPLOYMENT & HEALTH MONITORING")
            by_id = {c["patch"].candidate_id: c for c in candidates}
            for i, e in enumerate(sel.chosen):
                c = by_id[e["candidate_id"]]
                cid, dec = e["candidate_id"], c["decision"]
                if i and deploy.current_image() != faulty["new_image"]:
                    print(f"  restoring the faulty build {faulty['new_image']} before the next candidate", flush=True)
                    deploy.switch_to(faulty["new_image"], cfg, healthy=False)
                approval = None
                if dec.decision == "ESCALATE":
                    approval = deploy.approve_cli(dec, c["patch"].diff, input_fn=input_fn, run_dir=run_dir / cid,
                                                  source=approval_source, candidate_id=cid)
                    approvals[cid] = approval
                    print(f"  approval: {approval['answer']} by {approval['user']} at {approval['time']} "
                          f"({approval['approval_source']})")
                print(f"  {cid}: deploying ({dec.decision})", flush=True)
                src = sandbox.prepare_patched_app(fault, c["patch"].diff, Path(tmp) / cid)
                rel = deploy.release(dec, src, f"{run_id}-{cid}", approval=approval, run_dir=run_dir / cid, cfg=cfg)
                releases[cid] = rel
                print(f"  {cid}: {_result(rel, dec.decision)}", flush=True)

            step(8, "EVIDENCE COLLECTION")
            for c in candidates:
                cid, rel = c["patch"].candidate_id, releases.get(c["patch"].candidate_id)
                # derive per-patch fields for the evidence row
                llm_attempts = (len(diagnosis.attempts) // max(1, n_samples)
                                if diag_mode in ("live", "replay") else None)
                row = record.build_row(
                    run_id=run_id, fault_id=fault, gates=c["gates"], diagnosis=diagnosis, patch=c["patch"],
                    patch_meta=c["meta"], decision=c["decision"],
                    deployed=bool(rel and rel["deployed"]),
                    rolled_back=rel.get("rolled_back") if rel else None,
                    awaiting_review=(rel.get("awaiting_review") if rel else c["decision"].decision == "ESCALATE"),
                    recovery_s=rel.get("recovery_s") if rel else None,
                    approval=approvals.get(cid),
                    invalid="observer_suspended" if rel and str(rel.get("outcome", "")).startswith("invalid") else None,
                    top1_hit=top1_hit, top3_hit=top3_hit,
                    diag_samples=n_samples if diag_mode in ("live", "replay") else None,
                    samples_disagree=diagnosis.samples_disagree,
                    model=diagnosis.model,
                    llm_attempts=llm_attempts,
                    apply_error=c["patch"].apply_error)
                record.append_row(row)
                record.append_row(row, run_dir / "evidence.jsonl")
            print(f"  {len(candidates)} rows -> results/evidence.jsonl and runs/{run_id}/evidence.jsonl")
    except Exception as exc:
        err = StepError(state["step"], state["title"], exc)
        _write(run_dir / "error.json", {"step": state["step"], "title": state["title"], "error": str(exc),
                                        "type": type(exc).__name__, "traceback": traceback.format_exc()})
        finish("error", str(err))
        _restore_baseline(cfg, step)
        raise err from exc

    baseline_state = _restore_baseline(cfg, step)
    step(10, "EXECUTION SUMMARY")
    rows = []
    for c in candidates:
        cid, rel = c["patch"].candidate_id, releases.get(c["patch"].candidate_id)
        rows.append({"candidate_id": cid, "gates": {g: c["gates"]["gates"][g]["status"] for g in GATES},
                     "tier": c["decision"].tier, "decision": c["decision"].decision,
                     "deployed": bool(rel and rel["deployed"]), "result": _result(rel, c["decision"].decision)})
    summary = {"run_id": run_id, "fault_id": fault, "diag_mode": diag_mode, "patch_mode": patch_mode,
               "incident_rule": incident["rule"], "diagnosed_file": diagnosis.causes[0].file,
               "oracle_localisation": diagnosis.oracle_localisation, "choice": sel.note,
               "seconds": round(time.monotonic() - t0), "candidates": rows}
    _write(run_dir / "summary.json", summary)
    finish("completed")

    # Detailed counts for execution summary
    val_passed = sum(1 for c in candidates if all(c["gates"]["gates"][g]["status"] == "pass" for g in GATES))
    val_failed = len(candidates) - val_passed   # any gate not "pass" (fail, error, timeout, not_run)
    auto_count = sum(1 for c in candidates if c["decision"].decision == "AUTO_APPLY")
    esc_count = sum(1 for c in candidates if c["decision"].decision == "ESCALATE")
    rej_count = sum(1 for c in candidates if c["decision"].decision == "REJECT")
    dep_status, final_status = summary_status(releases)

    terminal.print_execution_summary(
        run_id=run_id,
        fault=fault,
        candidates_count=len(candidates),
        val_passed_count=val_passed,
        val_failed_count=val_failed,
        auto_apply_count=auto_count,
        escalated_count=esc_count,
        rejected_count=rej_count,
        deployment_status=dep_status,
        baseline_status=baseline_state,
        evidence_saved=f"results/evidence.jsonl & runs/{run_id}/evidence.jsonl",
        final_status=final_status,
        seconds=time.monotonic() - t0,
    )

    print_table(rows)
    return summary


def summary_status(releases: dict) -> tuple[str, str]:
    """(deployment status, final status) for the terminal summary, worded only from recorded outcomes.

    A rollback means the health window was breached, not that the candidate is unsafe; a promotion means the
    window passed, not that the patch is correct. Correctness comes only from the offline oracle.
    """
    promoted = [cid for cid, rel in releases.items() if rel.get("outcome") == "promoted"]
    rolled_back = [cid for cid, rel in releases.items() if rel.get("rolled_back")]
    invalid = [cid for cid, rel in releases.items() if str(rel.get("outcome", "")).startswith("invalid")]
    awaiting = [cid for cid, rel in releases.items() if rel.get("awaiting_review")]
    parts = ([f"promoted ({', '.join(promoted)})"] if promoted else []) + \
            ([f"rolled back ({', '.join(rolled_back)})"] if rolled_back else []) + \
            ([f"invalid window ({', '.join(invalid)})"] if invalid else []) + \
            ([f"awaiting review ({', '.join(awaiting)})"] if awaiting else [])
    if not parts:
        return "no candidate deployed", "COMPLETED: no deployment"
    if rolled_back:
        final = "ROLLED BACK: health window breached, previous image restored"
    elif invalid:
        final = "INVALID: observer suspended, health window proves nothing"
    elif promoted:
        final = "PROMOTED: health window passed (correctness not verified by the pipeline)"
    else:
        final = "PENDING: human review required"
    return "; ".join(parts), final


def _restore_baseline(cfg: dict, step) -> str:
    """Put the baseline back. Returns what was observed, for the summary; never claims health it did not check."""
    step(9, "BASELINE RESTORATION")
    try:
        if deploy.current_image() == deploy.BASELINE_TAG and deploy._health(cfg)["ok"]:
            print("  baseline already running and healthy")
            return f"{deploy.BASELINE_TAG} running, health check UP"
        seconds = deploy.switch_to(deploy.BASELINE_TAG, cfg, healthy=True)
        print(f"  {deploy.BASELINE_TAG} running and healthy after {seconds:.1f}s")
        return f"{deploy.BASELINE_TAG} restored, health check UP after {seconds:.1f}s"
    except Exception as exc:   # report, but do not hide the original error
        print(f"  could not restore the baseline: {type(exc).__name__}: {exc}", file=sys.stderr)
        return f"NOT RESTORED ({type(exc).__name__}); check the service manually"
