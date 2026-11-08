# AutoImmune: Evidence-Gated Self-Healing for a Java Microservice

**B.Tech Final Year Project Report**
**Team:** Agni M N, Pradeep S, S Nehal  **Guide:** Mrs. M. Shona
**Date:** 9 November 2026  **Code version:** git `cfb0237` (tag `baseline-s0` = audited baseline `2bc12e2`)

---

## Abstract

AI models can now draft code fixes, but a fix that passes its own test is not necessarily safe to deploy. AutoImmune
is a hybrid self-healing pipeline for a Java Spring Boot service ("order-service"). It detects a production fault,
diagnoses it, collects candidate patches, and validates each one in an isolated Docker sandbox through four
**evidence gates**:
- **V0:** the patch applies and compiles.
- **V1:** the target test passes.
- **V2:** the full regression suite passes.
- **V3:** a Semgrep scan finds no new security issues.

A rule-based risk tier then decides to **REJECT**, **ESCALATE** to a human, or **AUTO_APPLY**. Approved patches are
deployed as a new container image, watched over a health window, and promoted or rolled back. An AI model is used only
for diagnosis and patch drafting; every decision is deterministic code.

We demonstrate the full loop with recorded, traceable evidence on three seeded faults:
- **Detection:** within 5–6 s of the faulty build going live.
- **Human review:** a real human approval, followed by deployment.
- **Rollback:** a staged rollback, restoring the previous image in 4.0 s.

On 32 scripted candidate evaluations (16 hand-built patches, each evaluated under two diagnosis modes), adding gates
reduced the number of unsafe-by-construction patches that would be auto-applied:
- **Target test only:** 20 of 26.
- **Full suite added:** 13 of 26.
- **Full AutoImmune policy:** 7 of 26.

No correct patch was rejected. However, **overfitting patches passed every gate and one was promoted three times**, so
test-based gates and health checks alone cannot certify correctness. Local LLMs (qwen2.5-coder 7b and 1.5b) produced
0 of 17 patches that passed the target test.

This is a **pilot mechanism study**: one service, three seeded faults, no independent ground-truth labels yet. All
numbers are counts with stated denominators, not general safety guarantees.

---

## 1. Introduction

### 1.1 Problem
When a production service misbehaves, engineers must find the cause, write a fix, test it and deploy it. LLMs can draft
fixes quickly, but deploying an AI-written patch without review is risky:
- it may pass the visible test while being wrong in general (overfitting);
- it may break other features (regression);
- it may introduce a vulnerability;
- it may be correct but slow.

Reviewing every AI patch by hand removes most of the speed benefit.

### 1.2 Research question
*How much execution evidence lets an AI-drafted patch deploy without human review, and what does each validation gate
catch?*

### 1.3 Objectives
1. Build a fixed (non-agentic) pipeline: observe → detect → diagnose → candidate patches → validate (V0–V3) → risk tier
   → decide → deploy → health window → promote or roll back → record evidence.
2. Run every gate inside an isolated Docker sandbox; treat a timeout or tool error as a failure, never a pass.
3. Compare deployment policies of increasing evidence depth on the same candidates.
4. Record complete, reproducible evidence for every candidate and run.

### 1.4 Scope and honest limits
- This is a **controlled research prototype on a laptop**, not a production system.
- It covers three seeded faults, scripted candidate patches (to exercise the gates), and a small pilot of live LLM
  patches.
- We claim **no** calibrated probabilities, **no** general safety guarantee, and **no** novelty for repair,
  verification or rollback as individual techniques.

---

## 2. Related work

Closely related work, as listed in the project roadmap (to be verified against the full texts before publication):
- **ORCA** (Gao et al., 2026): observability-grounded microservice repair and telemetry-based patch verification.
- **Abstain and Validate** (Cambronero et al.): policies that filter repair attempts before human review.
- **Meta Diff Risk Score** (2025): risk scoring for code changes.
- **HealBench/HealGuard** (Tan et al., 2026): benchmarking and guardrails for runtime healing.
- **Sajadi et al.** (2025): a large-scale security analysis of AI-generated patches.

These works already cover telemetry-driven repair, layered verification, risk scoring and patch-safety evaluation.
AutoImmune's narrower contribution is a **transparent, reproducible comparison of deployment-decision policies over the
same patch candidates**, measuring what each extra layer of evidence catches and costs.

---

## 3. System design

### 3.1 Architecture

```
 order-service (Docker) ──► detector ──► diagnose (LLM or rule) ──► draft patches (LLM or scripted)
                                                                          │
              ┌───────────────── Docker sandbox, --network none ─────────┘
              ▼
   V0 apply+compile → V1 target test → V2 full suite → V3 Semgrep (new findings only)
              │
              ▼
   decide(): REJECT / ESCALATE (human) / AUTO_APPLY        ← thresholds in config/decision.yaml
              │
              ▼
   build new image → swap → health window (health UP, latency < 2000 ms, probe values)
              │                          │
           promote                  roll back to previous image
              │
              ▼
   evidence row per candidate (results/evidence.jsonl) + run artifacts (runs/<run_id>/)
```

### 3.2 Components (Python 3.12 orchestrator, `pipeline/`)
| Module | Role |
|---|---|
| `detector.py`, `observe.py` | Probe the service and Prometheus metrics; raise an incident on a probe mismatch, an HTTP 5xx, health DOWN or a latency breach |
| `providers.py` | One provider interface with modes `live`, `replay`, `scripted`, `rule`; the **only** place an LLM is used (diagnose, draft patches); bounded retries; responses cached |
| `sandbox.py` | Gates V0–V3 in Docker: `--network none`, 2 GB memory, 2 CPUs, PID limit, `--cap-drop ALL`, non-root, read-only Maven cache |
| `decide.py` | Rule-based risk tier and decision with explicit reasons |
| `deploy.py` | Image build, container swap, health window, rollback to the previous image, CLI human approval |
| `record.py` | Schema-validated evidence row per candidate (schema v2 includes the patch SHA-256) |
| `provenance.py` | Per-run fingerprint: git commit and dirty state, code, prompt and config hashes, model, Python, OS and Docker versions |
| `orchestrator.py` | The fixed 10-step run; writes every artifact; always restores the healthy baseline |
| `analyse.py` | The only module that reads labels; regenerates all tables; `--check` detects stale reports |

### 3.3 Decision rules (`config/decision.yaml`)
- **REJECT** (high risk): V0, V1 or V2 fails, or a new high-severity Semgrep finding.
- **ESCALATE** (medium risk): all gates pass, but there is a new low-severity finding, the diff exceeds 20 lines, a file
  outside the diagnosed file is touched, a sensitive path is touched (`application.properties`, `security/`), or the
  diagnosis samples disagree.
- **AUTO_APPLY** (low risk): all gates pass, no new findings, and the diff stays inside the diagnosed file and within
  the size limit.

### 3.4 Integrity rules
- Hidden tests and labels are never mounted in the sandbox and never shown to the model or the decision engine. A test
  scans prompts for fault ids and oracle words.
- Scripted and rule results are never reported as LLM results; the analysis keeps the two cohorts separate.
- A human approval is recorded as `human_cli` only when typed by a person at the terminal; scripted approvals are
  labelled `scripted_test`.
- Rollback swaps container images and never uses `git reset`.

---

## 4. Experimental setup

### 4.1 Faults (seeded into order-service)
| Fault | Type | What breaks | Observable symptom |
|---|---|---|---|
| F01 | Null handling | Null/blank guard removed in `searchByCustomer` | `GET /api/orders/search` without `customer` returns HTTP 500 (NullPointerException) instead of 400 |
| F04 | Configuration | `orders.catalog.enabled=false` | `/actuator/health` returns 503 DOWN |
| F06 | Business logic | Discount threshold `>= 1000` changed to `> 1000` | `GET /api/orders/2/discount` returns 1000.00 instead of 900.00, with no error logged |

### 4.2 Candidate patches
- **Scripted (mechanism checks):** 16 hand-built patches, one of each kind per fault: `correct`, `overfitting` (passes
  the target test only), `regressive` (breaks another test), `insecure` (adds an SQL-injection pattern) and
  `ineffective`, plus `slow` for F06 (correct, but adds a 3 s delay). The kind is the builder's intent, **not an
  independent label**.
- **Live LLM:** qwen2.5-coder:7b and qwen2.5-coder:1.5b via a local Ollama endpoint, 3 patches requested per
  diagnosis.

### 4.3 Policies compared on the same candidates
| Policy | Rule |
|---|---|
| B0 | A human reviews everything (theoretical perfect-reviewer baseline) |
| B1 | Auto-apply if V0 and V1 pass, else reject |
| B2 | Auto-apply if V0–V2 pass, else reject |
| B3 | AutoImmune: V0–V3 plus scope and risk rules (can escalate) |

### 4.4 Environment
Windows 11, Docker Desktop 4.91 (engine 29.8.0), Python 3.12, Maven image `maven:3.9-eclipse-temurin-17`, Semgrep
1.100.0. Exact Python package versions are in `requirements.lock`.

---

## 5. Results

All numbers below are regenerated by `python analyse.py` from `results/evidence.jsonl` (101 rows) and verified by
`python analyse.py --check`. Raw artifacts for every run are in `runs/<run_id>/`.

### 5.1 End-to-end runs with full provenance (code `f5ef81a`; the F01, F04 and rollback runs also had small uncommitted docs/provenance-fix changes, recorded in each `run.json`)
| Run | Fault | Detected after | Gates and decision | Deployment outcome |
|---|---|---|---|---|
| f06-rule-scripted-20261108t173444z | F06 | 5.0 s (probe mismatch) | 3 AUTO_APPLY, 3 REJECT | `overfitting` patch promoted (smallest diff) |
| f01-rule-scripted-20261108t174806z | F01 | 5.0 s (HTTP 500) | 2 AUTO_APPLY, 3 REJECT | `correct` patch promoted |
| f04-rule-scripted-20261108t175754z | F04 | 6.0 s (health 503) | 2 ESCALATE, 3 REJECT | **human approved** (`human_cli`), deployed, promoted |
| f06-rule-scripted-20261108t180955z | F06 | — | planted `slow` patch forced | **rolled back in 4.0 s** (probe 3016 ms > 2000 ms limit) |

Every run wrote all ten step artifacts, recorded its code version, and restored the healthy baseline afterwards.

### 5.2 What each gate catches (32 scripted unit evaluations)
| Candidate kind | First stop |
|---|---|
| ineffective | **V1** (6/6) |
| regressive | **V2** (6/6) |
| insecure | **V3** (5/6); 1 stopped at V2 by a Docker tool **error**, recorded as an error, not a pass |
| correct | passed all gates: AUTO_APPLY (4) or ESCALATE for F04's config file (2) |
| overfitting | **passed all gates**: AUTO_APPLY (5), ESCALATE (1) |
| slow | passed all gates; caught only by the health window (staged rollback) |

Median gate time: V0 5.8 s, V1 26.4 s, V2 28.7 s, V3 5.7 s.

### 5.3 Policy comparison (same 32 scripted units)
"Unsafe" here means unsafe **by construction** (builder intent), not independently labelled.

| Policy | Auto-applied | Unsafe-by-construction auto-applied | Correct patches rejected | Escalated to a human |
|---|---|---|---|---|
| B0 human reviews all | 0/32 | 0 | 0/6 | 32/32 |
| B1 V0+V1 | 26/32 | **20 / 26** | 0/6 | 0 |
| B2 V0–V2 | 19/32 | **13 / 26** | 0/6 | 0 |
| B3 AutoImmune | 11/32 | **7 / 26** (5 overfitting, 2 slow) | 0/6 | 3/32 |

Each added gate removed a distinct class of unsafe patch (regressive at V2, insecure at V3) at no cost in rejected
correct patches. The remaining escapes are overfitting patches, which no gate in the pipeline can detect, and slow
patches, which only the post-deployment health window catches.

### 5.4 Live LLM pilot
| Model | Attempts | Applied cleanly | Passed V1 | Deployed |
|---|---|---|---|---|
| qwen2.5-coder:7b | 9 | 0 (diffs missing `---`/`+++` file headers) | 0 | 0 |
| qwen2.5-coder:1.5b | 8 | 3 | 0 | 0 |

Diagnosis localisation, counted once per diagnosis run: F01 2/2, F06 5/5 (both models), **F04 0/2**. The model missed
the configuration root cause. Two 1.5b runs were produced by code that was never committed, and we report that openly
(see 6.3).

---

## 6. Discussion

### 6.1 Main findings
1. **Layered evidence helps, and each gate catches something different.** V1 stops ineffective fixes, V2 regressions
   and V3 insecure code. With all four, unsafe-by-construction auto-applies fell from 20 to 7 of 26 with no correct
   patch rejected.
2. **Tests cannot certify correctness.** Overfitting patches passed every gate and the health window. When two patches
   both pass, the pipeline cannot tell the overfitting one from the correct one, and it promoted the overfitting patch
   on F06 because it was smaller. Measuring this requires an **independent oracle** (hidden tests), which is the most
   important next step.
3. **Post-deployment monitoring is a separate safety layer.** The slow patch passed all gates and was caught only by
   the health window, which rolled it back automatically in 4 s.
4. **Small local LLMs are not yet usable as patch generators here.** 0 of 17 live patches passed the target test.
   Format failures (missing diff headers) dominated for the 7b model.

### 6.2 Threats to validity
- One service and three seeded faults; scripted candidates were written by the team.
- **No independent ground-truth labels:** "unsafe" means builder intent. Hidden-test oracles and blind two-person
  labelling are future work.
- Small, correlated samples: the 32 scripted units are 16 patches under two diagnosis modes, not 32 independent bugs.
- The deployment is a container swap on a laptop with simulated probes, not a production canary. Latency is checked
  per probe, not as p95.
- The human reviewer was a team member.

### 6.3 Reproducibility and the integrity audit
Before the final runs we audited our own evidence (`docs/audit/AUDIT_BASELINE.md`). We found and fixed:
- a stale pilot report;
- an analysis rule that silently dropped 54 of 79 evidence rows;
- scripted patches shown in LLM tables;
- inflated diagnosis counts;
- dashboard claims not backed by data;
- two live runs produced by uncommitted code.

Every run now records its exact code version, and every report can be regenerated and checked with one command.

---

## 7. Conclusion and future work

AutoImmune shows a complete, traceable self-healing loop: detection in seconds, sandboxed multi-gate validation,
rule-based decisions with human escalation, and deployment with automatic rollback. The evidence shows that each gate
adds distinct protection, but also that passing tests and health checks is not proof of correctness.

**Future work:**
1. Independent hidden-test oracles and blind labels, so the true unsafe-deployment rate (UDR) and false-rejection rate
   (FRR) can be measured.
2. About 10 more faults, split into development and held-out sets.
3. Stronger LLMs, with structured diff output.
4. A side-by-side canary deployment with p95 latency and image digests.
5. Uncertainty analysis clustered by fault.

---

## Appendix A: How to reproduce
```
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -r requirements.lock
.\.venv\Scripts\python -m pytest -rs                       # 205 tests (Docker running)
.\.venv\Scripts\python -m pipeline run --fault F06 --diag-mode rule --patch-mode scripted
.\.venv\Scripts\python analyse.py                          # regenerate results/
.\.venv\Scripts\python analyse.py --check                  # verify results/ is current
.\.venv\Scripts\python tools\make_dashboard.py             # results/dashboard.html
```

## Appendix B: Where the evidence is
| Claim | Evidence |
|---|---|
| End-to-end runs, detection times | `runs/f0*-rule-scripted-20261108t17*/` (`run.json`, `incident.json`, `faulty_deploy.json`) |
| Human approval and deploy | `runs/f04-rule-scripted-20261108t175754z/F04-scripted-835a25e8/approval.json`, `deploy.json` |
| Staged rollback | `runs/f06-rule-scripted-20261108t180955z/F06-scripted-7509cb64/rollback.json` |
| Gate and policy tables | `results/first_stop.csv`, `results/policies.csv`, `results/pilot_report.md` |
| LLM pilot | `results/llm_units.csv`, `results/llm_patch_utility.csv`, `results/llm_diagnosis.csv` |
| Acceptance checks A1–A10 | `docs/audit/acceptance.json`, rendered in `results/dashboard.html` |
| Audit | `docs/audit/AUDIT_BASELINE.md` |
