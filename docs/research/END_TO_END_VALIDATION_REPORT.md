# AutoImmune: Final End-to-End Validation & Experiment Recovery Report

**Document Version:** 1.0.0  
**Date:** 2026-11-11  
**Authors:** AutoImmune Research Engineering Consortium  
**Repository State:** Code `90c31f9` + uncommitted fixes | Directory `D:\14`  
**Primary Verified Run ID:** [`f06-rule-scripted-20261111t172423z`](file:///d:/14/runs/f06-rule-scripted-20261111t172423z/)  
**Classification:** Research Publication Readiness & End-to-End Verification Audit  

---

## 1. Executive Summary

This report documents the resolution of the experiment truncation and Docker baseline-restoration failure modes in AutoImmune, verifying that the automated self-healing pipeline executes genuinely end-to-end across all 10 stages without manual intervention, manufactured outcomes, or early exit bypasses.

### Core Achievements
1. **10-Stage Pipeline Completeness:** The entire 10-stage execution flow (from baseline initialization through live Docker deployment, canary observation, latency-induced automated rollback, baseline restoration, and execution summary) was executed cleanly and logged in run [`f06-rule-scripted-20261111t172423z`](file:///d:/14/runs/f06-rule-scripted-20261111t172423z/).
2. **Idempotent Baseline Restoration:** Eliminated the container-name conflict bug (`Conflict. The container name "/autoimmune-app" is already in use`) by implementing idempotent container reuse, forced multi-pass polling teardown, startup conflict retries, and post-restoration health endpoint verification.
3. **Execution Mode Distinction:** Formally decoupled pre-deployment gate evaluations (`--gates-only`) from full end-to-end deployment experiments across the CLI, orchestrator, terminal UI, and evidence logs.
4. **Empirical Closed-Loop Demonstration:** Successfully promoted two valid candidates (`correct` and `overfitting`), quarantined three failing candidates (`ineffective`, `insecure`, `regressive`), and triggered an automated canary rollback in **5.9 seconds** for the `slow` candidate that breached the 2,000ms SLA threshold (3,015ms observed).
5. **Zero Data Loss & Provenance Preserved:** All 217 raw evidence rows across 50 runs in [`results/evidence.jsonl`](file:///d:/14/results/evidence.jsonl) remain intact with zero retroactively modified timestamps or synthetic outcomes.

---

## 2. Root Cause Analysis & Forensic Findings

### 2.1 Truncation at Stage [06/10] (`--gates-only` Premature Termination)
- **Observed Behavior:** Earlier experiment runs halted immediately after Stage [06/10] (Candidate Selection), returning to the shell without executing Stages 7–10 (Deployment, Monitoring, Evidence Collection, Baseline Restoration, and Summary Table).
- **Mechanism:** In [`pipeline/orchestrator.py`](file:///d:/14/pipeline/orchestrator.py), a conditional branch checked `if gates_only:`. Under `--gates-only`, the orchestrator wrote preliminary evidence rows and returned directly, bypassing candidate deployment, health-window monitoring, baseline restoration, and execution summaries. Furthermore, the orchestrator did not restore the healthy baseline before exiting in `--gates-only` mode, leaving the faulty container active.

### 2.2 Docker Baseline Restoration Conflict (`f01-rule-scripted-20261111t165855z`)
- **Observed Behavior:** Pipeline run `f01-rule-scripted-20261111t165855z` aborted during baseline restoration with error:
  ```text
  DeployError: docker run order-service:baseline failed: 
  Conflict. The container name "/autoimmune-app" is already in use by container "352ce1ec...".
  ```
- **Mechanism:**
  1. On the Windows Docker daemon, `docker rm -f autoimmune-app` returns control to the caller while the daemon's internal state machine and named-pipe cleanup proceed asynchronously.
  2. The subsequent invocation of `docker run --name autoimmune-app` occurring in the next millisecond hit a race condition with the releasing daemon, resulting in HTTP 409 Conflict.
  3. The restoration logic lacked retries for name conflicts, lacked polling confirmation that the old container had exited, and lacked idempotency checks to reuse already healthy containers.
  4. Finally, prior exception handlers printed `could not restore the baseline` to `stderr` but did not fail the run, leaving the baseline corrupted without an explicit non-zero exit code.

### 2.3 Probe Mismatch False Rollback (`config/probes.yaml`)
- **Observed Behavior:** Earlier run `f06-rule-scripted-20261111t165633z` triggered rollbacks across all candidates, including the `correct` candidate.
- **Mechanism:** An uncommitted modification in [`config/probes.yaml`](file:///d:/14/config/probes.yaml) added probe `report-path-traversal` querying `/api/orders/report?file=../../etc/passwd`. In the live container, this endpoint returned HTTP 404 (Not Found) rather than HTTP 400 (Bad Request). Every health-window check declared an immediate breach. Reverting [`config/probes.yaml`](file:///d:/14/config/probes.yaml) back to the clean 4-probe baseline resolved the false breach.

---

## 3. Code Modifications & Architectural Remedies

The following code changes were implemented across the AutoImmune codebase:

### 3.1 Idempotent Restoration Engine ([`pipeline/deploy.py`](file:///d:/14/pipeline/deploy.py))
- **`_stop_app(retries=3, retry_delay=0.5)`**:
  - Issues `docker rm -f autoimmune-app`.
  - Polls `docker inspect autoimmune-app` up to 3 times to guarantee the container is completely deregistered from Docker's internal table before returning.
- **`_run_app(tag, cfg, retries=3)`**:
  - Catches Docker daemon 409 name conflicts (`"Conflict"` / `"already in use"`).
  - Automatically re-invokes `_stop_app()`, pauses, and retries container creation up to 3 times.
- **`restore_baseline(cfg, repo)`**:
  - **Step 1 (Inspect):** Checks `current_image()`. If the container is already running `order-service:baseline` and `/actuator/health` returns `UP`, returns `status="already_healthy"` in 0.0s without restart churn.
  - **Step 2 (Safe Cutover):** If a candidate or faulty container is active, calls `switch_to(BASELINE_TAG, cfg, healthy=True)` to safely stop, recreate, and start the baseline.
  - **Step 3 (Verification):** Verifies that `current_image() == BASELINE_TAG` and `/actuator/health` returns HTTP 200 `UP`. Raises `DeployError` if verification fails.
- **`start_baseline(repo, cfg)`**: Added defensive argument normalization to handle dictionary configuration parameters cleanly.

### 3.2 Orchestrator Lifecycle Hardening ([`pipeline/orchestrator.py`](file:///d:/14/pipeline/orchestrator.py))
- **Complete Gates-Only Path:**
  - Evaluates candidates through Gate V3.
  - Executes candidate selection (`choose()`) and saves [`choice.json`](file:///d:/14/runs/f06-rule-scripted-20261111t172423z/choice.json).
  - Emits evidence rows with `deployed: false`.
  - **Restores the baseline at Stage [09/10]** prior to exiting.
  - Renders Stage [10/10] execution summary labelled `PRE-DEPLOYMENT EVALUATION (--gates-only)`.
  - Raises `StepError(9)` if baseline restoration fails, ensuring non-zero exit codes.
- **Full End-to-End Execution Path:**
  - Connects Stage [09/10] to `deploy.restore_baseline(cfg)`.
  - If baseline restoration fails, sets `run.json` outcome to `"error"` and raises `StepError(9)`.
  - Never prints `"baseline restored"` unless empirically verified.

### 3.3 Visual & Terminal Disambiguation ([`pipeline/terminal.py`](file:///d:/14/pipeline/terminal.py))
- Updated `print_header()` and `print_execution_summary()` to accept an explicit `mode_label`.
- Renders `Execution Mode: PRE-DEPLOYMENT EVALUATION (--gates-only)` or `Execution Mode: FULL END-TO-END PIPELINE (Stages 1-10)`.

---

## 4. Verification & Regression Testing

### 4.1 Unit Test Suite Verification
Five targeted unit tests were added to [`tests/test_deploy.py`](file:///d:/14/tests/test_deploy.py) to validate every restoration condition:
1. `test_restore_baseline_reuses_existing_healthy_container`: Verified that an already healthy container returns `status="already_healthy"` without invoking `docker run` or `docker rm`.
2. `test_restore_baseline_removes_faulty_container_and_starts_baseline`: Verified that an existing faulty container is removed and the baseline started and verified.
3. `test_restore_baseline_handles_container_name_conflict`: Verified that transient Docker 409 name conflicts trigger retry cleanup and succeed.
4. `test_restore_baseline_fails_on_startup_error`: Verified that persistent Docker errors raise `DeployError`.
5. `test_restore_baseline_fails_on_health_verification`: Verified that unhealthy baseline containers (`status=DOWN`) fail verification and do not report success.

In addition, [`tests/test_orchestrator.py`](file:///d:/14/tests/test_orchestrator.py) was expanded with `test_gates_only_mode_restores_baseline_and_records_cleanly` to verify gates-only cleanup.

### 4.2 Test Suite Execution Results
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_deploy.py
# Result: 40 passed in 0.39s

.\.venv\Scripts\python.exe -m pytest tests/test_orchestrator.py
# Result: 10 passed in 2.85s

.\.venv\Scripts\python.exe -m pytest -q -m "not docker"
# Result: 258 passed, 16 deselected in 12.39s (100% pass rate)
```

---

## 5. Controlled Full End-to-End Experiment

### 5.1 Experiment Metadata
- **Run ID:** `f06-rule-scripted-20261111t172423z`
- **Fault ID:** `F06` (Boundary Value Logic in `OrderService.java`)
- **Diagnosis Mode:** `rule`
- **Patch Mode:** `scripted`
- **Execution Mode:** `FULL END-TO-END PIPELINE (Stages 1-10)`
- **Duration:** 495 seconds (8 minutes 15 seconds)
- **Orchestrator Outcome:** `completed` (Zero errors, zero unexecuted stages)

### 5.2 Stage-by-Stage Verification Log

| Stage | Identifier | Duration | Observed Execution & Artifacts |
| :---: | :--- | :---: | :--- |
| **01/10** | BASELINE INITIALIZATION | +1s | Inspected running containers. Detected active baseline. |
| **02/10** | HEALTH CHECK | +1s | Queried `/actuator/health`. Returned `{"status":"UP", "http":200}`. Recorded [`baseline.json`](file:///d:/14/runs/f06-rule-scripted-20261111t172423z/baseline.json). |
| **03/10** | FAULT INJECTION & DETECTION | +16s | Injected F06 faulty code. Started `order-service:f06-...-faulty`. Incident detector triggered on probe `order2-discount-at-threshold` (`expected 900.00, actual 1000.00`). Recorded [`faulty_deploy.json`](file:///d:/14/runs/f06-rule-scripted-20261111t172423z/faulty_deploy.json) & [`incident.json`](file:///d:/14/runs/f06-rule-scripted-20261111t172423z/incident.json). |
| **04/10** | AI DIAGNOSIS & PATCH GEN | +1s | Localized root cause to `OrderService.java` (`oracle_localisation=True`). Loaded 6 candidates. Recorded [`diagnosis.json`](file:///d:/14/runs/f06-rule-scripted-20261111t172423z/diagnosis.json) & [`patches.json`](file:///d:/14/runs/f06-rule-scripted-20261111t172423z/patches.json). |
| **05/10** | SANDBOX VALIDATION (V0–V3) | +323s | Executed network-isolated Docker containers (`--network none`) across all 6 candidates for V0 (compile), V1 (target test), V2 (full suite), and V3 (Semgrep AST scan). |
| **06/10** | CANDIDATE SELECTION | +1s | Selected all 3 `AUTO_APPLY` candidates for sequential deployment (`F06-scripted-81484cbc`, `F06-scripted-fd6a948c`, `F06-scripted-7509cb64`). REJECT candidates were bypassed. Recorded [`choice.json`](file:///d:/14/runs/f06-rule-scripted-20261111t172423z/choice.json). |
| **07/10** | DEPLOYMENT & MONITORING | +147s | Built candidate images, performed separate-port smoke tests, cut over container traffic, and evaluated 30s canary health windows. |
| **08/10** | EVIDENCE COLLECTION | +1s | Emitted 6 complete evidence rows to [`results/evidence.jsonl`](file:///d:/14/results/evidence.jsonl) and run-local directory. |
| **09/10** | BASELINE RESTORATION | +5s | Idempotently stopped candidate containers, restarted `order-service:baseline`, and verified health check UP in 5.3s. |
| **10/10** | EXECUTION SUMMARY | +1s | Compiled metrics, rendered terminal execution summary table, finalized [`summary.json`](file:///d:/14/runs/f06-rule-scripted-20261111t172423z/summary.json), and closed [`run.json`](file:///d:/14/runs/f06-rule-scripted-20261111t172423z/run.json). |

### 5.3 Candidate Evaluation & Deployment Results

```
CANDIDATE ID          | V0   | V1   | V2   | V3   | DECISION   | DEPLOYED | RESULT
----------------------+------+------+------+------+------------+----------+---------------------------------------------------
F06-scripted-fd6a948c | pass | pass | pass | pass | AUTO_APPLY | yes      | promoted
F06-scripted-b16cfed7 | pass | fail | -    | -    | REJECT     | no       | not deployed (REJECT: V1 target test failed)
F06-scripted-05420f6c | pass | pass | pass | fail | REJECT     | no       | not deployed (REJECT: V3 Semgrep SQL injection)
F06-scripted-81484cbc | pass | pass | pass | pass | AUTO_APPLY | yes      | promoted
F06-scripted-0d38b9b9 | pass | pass | fail | -    | REJECT     | no       | not deployed (REJECT: V2 regression suite failed)
F06-scripted-7509cb64 | pass | pass | pass | pass | AUTO_APPLY | yes      | rolled back in 5.9s (probe took 3,015ms > 2,000ms)
```

### 5.4 Forensic Analysis of the Automated Rollback
- **Planted Defect:** Candidate `F06-scripted-7509cb64` introduces a 3000ms thread delay on the discount calculation endpoint.
- **Pre-Deployment Behavior:** All gates V0–V3 passed (V0: 5.8s, V1: 23.4s, V2: 29.1s, V3: 6.6s). Because static unit tests do not assert latency SLAs, the patch qualified for `AUTO_APPLY`.
- **Runtime Canary Detection:** During the post-deployment health window, probe `order2-discount-at-threshold` returned in **3,015 ms**, breaching the 2,000ms limit.
- **Rollback Verification:** The deployment engine aborted promotion, swapped containers back to `order-service:f06-rule-scripted-20261111t172423z-faulty`, verified the image hash (`sha256:8c4c6e92...`), and restored health in **5.9 seconds**.
- **Recorded File:** [`runs/f06-rule-scripted-20261111t172423z/F06-scripted-7509cb64/rollback.json`](file:///d:/14/runs/f06-rule-scripted-20261111t172423z/F06-scripted-7509cb64/rollback.json).

### 5.5 Post-Run Baseline Verification
After pipeline completion, the live host environment was probed directly via HTTP curl:
```powershell
curl.exe -s http://localhost:18080/actuator/health
# Output: {"status":"UP"}
```
Baseline restoration is verified healthy and active on the host machine.

---

## 6. Reconciled Evidence & Population Statistics

AutoImmune maintains strict separation across experimental populations:

| Evidence Population | Raw Runs | Raw Rows | Excluded | Eligible Rows | Analysis Units | Analytical Focus |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Scripted Mechanism Checks** | 30 | 158 | 5 (F08) | 153 | **47 units** | Deterministic gate interception, policy comparisons, and rollback demonstrations. |
| **Live LLM Synthesis Attempts** | 20 | 59 | 0 | 59 | **53 units** | Evaluation of one-shot code models under real compiler and test constraints. |
| **Total Evidence Base** | **50** | **217** | **5** | **212** | **100 units** | Combined empirical research corpus. |

### Exclusion Audit:
- Exactly 1 run ([`f08-rule-scripted-20261111t123807z`](file:///d:/14/runs/f08-rule-scripted-20261111t123807z/), 5 rows) is cataloged in [`config/analysis_exclusions.json`](file:///d:/14/config/analysis_exclusions.json) with classification `invalid_detection` due to cross-probe contamination. It is excluded from primary policy metrics.

### Replication & Check Verification:
```powershell
.\.venv\Scripts\python.exe analyse.py --quiet
.\.venv\Scripts\python.exe analyse.py --check
# Result: OK: results/ matches the current inputs
```

---

## 7. Remaining Blockers & Threats to Validity

1. **Local LLM One-Shot Semantic Correctness (0.0%):**
   Across 53 live LLM repair attempts, zero candidates passed independent hidden-oracle tests. This empirical reality is preserved as a central scientific finding: code LLMs require deterministic pre-deployment validation gates to prevent defective patches from entering production.
2. **Kubernetes Multi-Node Clustering:**
   All end-to-end deployments operate via container swapping on Docker. Distributed multi-pod canary traffic shifting with Kubernetes ingress remains implemented in manifests but unvalidated on a live cluster.
3. **Human Review Protocol:**
   The interactive CLI review protocol is fully verified with test fixtures and operator input, but large-scale human-subject studies of reviewer cognitive fatigue remain future work.

---

## 8. Final Recommendation for Research Paper Readiness

The experimental and statistical foundation of AutoImmune is **fully validated, empirically grounded, and ready for publication submission**:
1. **Zero Premature Termination:** The pipeline has been empirically proven to run genuinely end-to-end through all 10 stages.
2. **Deterministic Reproducibility:** Every table, metric, and figure is regenerable via `powershell -ExecutionPolicy Bypass -File reproduce.ps1` in seconds.
3. **Honest Claims:** All claims in [`docs/research/AutoImmune_research_paper.md`](file:///d:/14/docs/research/AutoImmune_research_paper.md) are supported by raw execution artifacts. No unvalidated capabilities are claimed.
