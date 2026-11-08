# AutoImmune: Evidence-Gated Self-Healing for a Java Microservice

**B.Tech Final Year Project Report**
**Team:** Agni M N, Pradeep S, S Nehal  **Guide:** Mrs. M. Shona
**Date:** 9 November 2026  **Code:** git history in this folder (protocol frozen at commit 6e1d2ac in
`docs/protocol_v1.md`, written during the pilot; not a preregistration. The later gpt-oss-120b runs and code changes
were logged in its section 9 as deviations only afterwards.)

---

## Abstract

AI models can now draft code fixes, but a fix that passes its own test is not necessarily safe to deploy. AutoImmune
is a hybrid self-healing pipeline for a Java Spring Boot service. It detects a seeded fault in the running service
(a local Docker deployment), diagnoses it, collects candidate patches, validates each one through four sequential
evidence gates that stop at the first failure (a patch-apply check, then compile, tests and Semgrep in network-isolated
Docker containers), and then decides by fixed rules whether to reject, escalate to a human, or auto-apply:
- **V0:** the patch applies and compiles.
- **V1:** the target test passes.
- **V2:** the full regression suite passes.
- **V3:** a Semgrep scan (5 local rules) finds no new high-severity finding compared with the unpatched code. A new
  lower-severity finding does not fail V3, but it forces escalation.

In the current pipeline, deployed patches are smoke-tested side by side, watched over a health window that includes
p95 latency, and promoted or rolled back with image-ID verification. These checks were added after the first 7
scripted deployments; they are recorded for the last 5 of 12 deployments (the 3 AI deployments and 2 scripted reruns).
An AI model is used only for diagnosis and patch drafting. Every patch is
labelled afterwards by an independent offline oracle the pipeline never sees: hidden specification tests, a
performance test, the full suite, and a separate security probe.

On three seeded faults:
- **Detection** takes 5–6 s in every run but one (7 s; timestamps have 1 s resolution), with no false alarm in 5
  minutes of healthy traffic.
- **Hand-built patches (32 evaluations):** adding gates cut unsafe patches that would be auto-applied from 20/26
  (target test only) to 13/26 (plus full suite) to 7/26 (full policy), with 0/6 correct patches rejected.
- **Real AI patches (gpt-oss-120b, 15 attempts):** the model produced a correct, oracle-verified repair that was
  deployed and promoted automatically.
- **But under the full policy, 2 of the 5 AI patches approved for auto-apply were wrong, and both were deployed and
  promoted (2 of the 3 AI patches actually deployed).** One guarded only against `null`. The
  other made the health check always report UP after a misdiagnosis, while the correct fix was escalated and never
  reached a human.

**Passing tests and health checks is not sufficient evidence of correctness.** With three faults and small samples,
these are pilot results: confidence intervals are wide and policy differences are not statistically established.

---

## 1. Introduction

### 1.1 Problem
LLMs can draft fixes for a failing service in seconds. Deploying them unreviewed is risky:
- a patch may pass the visible test while being wrong in general (overfitting);
- it may break other features;
- it may add a vulnerability;
- it may be correct but slow.

Reviewing every patch by hand removes the speed benefit.

### 1.2 Research questions (`docs/protocol_v1.md`)
- **RQ1:** On the same candidates, how do unsafe auto-apply (UDR) and human-review (HIR) rates change across policies
  B0–B3?
- **RQ2:** Can gate patterns rank unsafe patches? *Not attempted: too little data. Reported as insufficient evidence.*
- **RQ3:** Which gate first stops each unsafe patch, and what does each gate cost in time?

### 1.3 Scope
- A controlled research prototype: the pipeline, Docker gates and deployments ran locally on a Windows 11 laptop
  (no machine ID is recorded). Live AI diagnosis and patches came from a hosted model (openai/gpt-oss-120b via the
  Groq API).
- One service, three seeded faults.
- **No** production claims, **no** calibrated probabilities, **no** novelty claimed for repair, verification or
  rollback on their own.

---

## 2. Related work
Closely related work named in the project plan (`docs/masterPlan.md` §4.3; not all read in full yet, so to be checked
against the full texts before publication):
- **Abstain and Validate** (Google, arXiv 2510.03217, ICSE-SEIP 2026): agentic repair that filters bugs and patches
  before review; a human still reviews each patch.
- **Meta Diff Risk Score** (year and link to be confirmed): risk gating for human-written diffs.
- **Spiess et al.**: calibration and correctness of language models for code.
- **Durieux et al.** (2018), Production-Driven Patch Generation: shadow-traffic testing of patches.
- **ORCA** (arXiv 2608.17018): telemetry-grounded patch verification (only the conclusion was read).
- **HealBench** (arXiv 2609.39086): only a snippet was read; it appears close to our trust theme.

Our narrower contribution is a reproducible comparison of deployment policies on the *same* independently labelled
candidates, including real AI patches.

---

## 3. System design

```
service ──► detector ──► diagnose (LLM | rule) ──► draft patches (LLM | scripted) ──► format check + normalizer
                                                                     (LLM patches only; recorded)  │
   V0 git apply --check (host) + compile → V1 target test → V2 full suite → V3 Semgrep (new findings)
   compile, tests and Semgrep run in Docker with --network none; gates stop at the first non-pass
                                                                                     │
   decide(): REJECT | ESCALATE (human) | AUTO_APPLY  (config/decision.yaml)
                                                                                     │
   build image → SMOKE TEST side by side (port 18081) → cutover → health window (health, probes, latency, p95)
                                   │                                         │
                          no cutover if unhealthy              promote (image ID verified) | roll back (verified)
                                                                                     │
   evidence row per candidate + run.json provenance (commit, dirty state, code/prompt/config hashes, model)

   OFFLINE, never seen by the pipeline:  oracle = hidden tests + full suite + performance test + security probe
```

| Module | Role |
|---|---|
| `pipeline/detector.py`, `observe.py` | Probes and Prometheus metrics; incident on probe mismatch, 5xx, health DOWN, or latency/p95 breach |
| `pipeline/providers.py` | The only LLM use: diagnose and draft patches (live, replay, scripted, rule). Every raw response is SHA-256 hashed (the earlier qwen2.5-coder runs predate this and have no hash). A deterministic, versioned diff normalizer repairs **format only** (line endings, trailing newline, missing headers or hunk line numbers, apply_patch markers; it never changes an added or removed line). When the repair succeeds it records the rules that fired and keeps the raw diff. In rule mode, an incident with no stack trace (F04, F06) takes its diagnosed file from `faults/<id>/fault.json`: oracle localisation, flagged `oracle_localisation=true`. |
| `pipeline/sandbox.py` | Gates in Docker: no network, 2 GB memory, 2 CPUs, PID limit, all capabilities dropped, non-root. Network blocking and timeout kill/cleanup were tested in Docker (`docs/audit/isolation_test.txt`); the resource, capability and user limits are configured, not tested at runtime. |
| `pipeline/decide.py` | Rule-based tier and decision, with written reasons |
| `pipeline/deploy.py` | Side-by-side smoke test before cutover, image IDs, health window with p95, verified rollback, CLI human approval |
| `pipeline/provenance.py` | Per-run fingerprint (git commit, dirty flag and files, hashes of pipeline/*.py, prompts and config, model). A clean-tree run traces to an exact commit; for a dirty-tree run the change is detected but cannot be rebuilt. The 28 pre-S0 runs (of 44) have no fingerprint. |
| `tools/oracle.py` | Independent offline labels: invalid / unknown / regressive / incorrect / slow / insecure / correct |
| `analyse.py` | Every `results/` table (CSVs and `pilot_report.md`), Wilson intervals, fault-cluster bootstrap, gate-cost table; `--check` exits 1 if any of those files is stale. It does not compute detection times or check this report. |

**Decision rules:**
- **REJECT** if V0, V1 or V2 does not pass (fail, tool error, timeout or not run), if V3 does not complete, or if V3
  finds a new high-severity issue (Semgrep ERROR/HIGH/CRITICAL).
- **ESCALATE** if everything passes but the patch touches a sensitive path or a file outside the diagnosed one, is
  larger than 20 lines, or raises a new lower-severity V3 finding. A further rule escalates when live/replay diagnosis
  samples disagree, but it needs `diag_samples` > 1. The configured value is now 1, and the rule never fired in any
  run.
- **AUTO_APPLY** otherwise.
- By default, when several candidates are AUTO_APPLY, the one with the fewest diff lines is deployed (ties broken by
  candidate id); an ESCALATE goes to a human only when no AUTO_APPLY exists. An operator override (`--candidate`) can
  pick another candidate; both staged-rollback runs used it to deploy the 7-line slow patch.

---

## 4. Experimental setup
- **Faults** (`docs/fault_catalog.csv`):
  - F01, null handling: a search without a customer returns 500 instead of 400.
  - F04, configuration: the catalog is disabled, so health is DOWN.
  - F06, business logic: an order of exactly 1000.00 loses its discount.

  All three are seeded faults and **development** faults: there is no held-out set (`docs/data_split.json`).
- **Scripted cohort:** 16 hand-built patches (correct, overfitting, regressive, insecure, ineffective, plus slow for
  F06), each evaluated under two diagnosis modes (live model diagnosis and rule): 32 units. In rule mode, F04 and F06
  have no stack trace, so the "diagnosis" is the diagnosed file copied from `faults/<id>/fault.json` (oracle
  localisation). It is excluded from localisation hit rates, but it also feeds decide()'s file-scope rule, so the
  scripted F04/F06 rule-mode policy results assume perfect localisation.
- **LLM cohort:** every candidate a model drafted counts, including diffs that do not apply or compile. That is 32
  attempts:
  - qwen2.5-coder 7b: 9 attempts;
  - qwen2.5-coder 1.5b: 8 attempts;
  - **openai/gpt-oss-120b** via Groq: 15 attempts from the 5 runs that produced candidates.

  Live runs that stopped before producing candidates add no units; they are listed in the run ledger
  (`results/runs.csv`). Two of them failed at diagnosis on Groq: one with llama-3.3-70b-versatile (HTTP 404) and one
  with gpt-oss-120b (invalid JSON, then HTTP 429). A third gpt-oss-120b run saw no incident within 60 s.
- **Oracle** (`tools/oracle.py`, rules fixed in `docs/protocol_v1.md`). For each fault, hidden tests encode the
  specification, mostly on inputs the target test does not use; F01 and F04 each also re-check the target's own case
  once. A performance test requires under 1000 ms. A regex security probe on added lines uses a different technique
  from gate V3, but it checks the same two classes as V3's high-severity rules (SQL string concatenation, process
  execution), so it is not independent of V3. **Machine labels; two-person blind review is pending**
  (`docs/label_adjudication.csv`).
- **Policies:**
  - B0: a human reviews everything (an assumed perfect reviewer);
  - B1: V0 + V1;
  - B2: V0–V2;
  - B3: AutoImmune.

---

## 5. Results
The tables in 5.2–5.5 and the rollback times in 5.1 are regenerated by `python analyse.py` from
`results/evidence.jsonl`, the scripted labels in `faults/*/candidates/labels.json`, the AI-patch labels in
`results/oracle_report.jsonl` and the `runs/` directories, and checked by `python analyse.py --check`. The other 5.1
values (detection times, latencies, smoke-test time, healthy-watch load) are read from each run's `runs/<run_id>/`
artifacts. `reproduce.ps1` regenerates every table, the dashboard and the manifest from this stored evidence; it does
not rerun the pipeline, deployments or live AI runs.

### 5.1 The full loop (scripted candidates; provenance in each run.json, 5 of 7 runs from an uncommitted tree)
| Run | Fault | Detected after | Outcome |
|---|---|---|---|
| f06-rule-scripted-20261108t173444z | F06 | 5.0 s | two passing 2-line patches tied (correct and overfitting); the candidate-id tie-break picked the overfitting one, which was promoted |
| f01-rule-scripted-20261108t174806z | F01 | 5.0 s | correct patch promoted (it tied with the overfitting patch at 3 lines; the tie-break happened to pick the correct one) |
| f04-rule-scripted-20261108t175754z | F04 | 6.0 s | escalated, **human approved**, deployed, promoted |
| f06-rule-scripted-20261108t180955z | F06 | 5.0 s | planted slow patch: 3016 ms over the 2000 ms limit, rolled back in 4.0 s (before the S3 changes; image tracked by tag) |
| f06-rule-scripted-20261108t201808z | F06 | 5.0 s | planted slow patch passed the side-by-side smoke test (11.5 s), then 3015 ms over the 2000 ms limit: **rolled back in 5.1 s**, restored image ID verified |
| f04-rule-scripted-20261108t205508z | F04 | 5.0 s | rerun live: escalated, **human approved**, smoke-tested side by side, promoted (image ID verified) |
| healthy-watch-20261108t182609z | — | — | 300 s of healthy load (about 6000 requests): **no false incident** |

### 5.2 What each gate catches (scripted, oracle-labelled; `results/gate_incremental.csv`)
| Through gate | Unsafe stopped (cumulative, of 26) | Correct rejected (of 6) | Gate time, all 32 units |
|---|---|---|---|
| V0 | 0 | 0 | 363 s |
| V0–V1 | 6 (the incorrect "ineffective" patches) | 0 | 1804 s |
| V0–V2 | 13 (+6 regressive, +1 insecure stopped by a tool error) | 0 | 2885 s |
| V0–V3 | 18 (+5 insecure) | 0 | 3101 s |

The oracle independently labelled all 16 scripted patches exactly as their builders intended. 14 of the 32 units
pass every gate: the 6 correct units and 8 unsafe ones, which are 6 **overfitting** (labelled incorrect) and 2 **slow**
units. Gate times come from the latest run of each unit on one laptop and vary between runs (the F06 rerun's V1 took up to 171 s against about 25 s earlier), so treat them as
rough costs; the counts do not depend on them.

### 5.3 Policy comparison, scripted cohort (32 units)
| Policy | Auto-applied | Unsafe auto-applied (of 26 unsafe) | UDR (unsafe share of auto-applied) | Correct rejected | Escalated |
|---|---|---|---|---|---|
| B1 | 26 | **20** | 20/26 = 77% | 0/6 | 0 |
| B2 | 19 | **13** | 13/19 = 68% | 0/6 | 0 |
| B3 | 11 | **7** | 7/11 = 64% | 0/6 | 3 |

Scripted unsafe prevalence is set by design (26 of 32), so UDR here is **not** an estimate of AI safety. Fault-cluster
bootstrap (3 clusters): the B1−B3 UDR difference is 0.13, 95% interval [−0.25, 0.25], **not established**.

### 5.4 Real AI patches (LLM cohort)
| Model | Attempts | Applied cleanly | Passed all gates | Auto-applied (B3) |
|---|---|---|---|---|
| qwen2.5-coder 7b | 9 | 0 | 0 | 0 |
| qwen2.5-coder 1.5b | 8 | 3 | 0 | 0 |
| **openai/gpt-oss-120b** | 15 | 8 (after recorded format normalization) | 7 | 5 |

The three AI patches that were actually deployed (each one auto-applied, smoke-tested, promoted, image ID verified):

| Run | Patch | What it does | Oracle |
|---|---|---|---|
| f06-live-live-20261108t193456z | F06-live-1 | `> 0` becomes `>= 0` | **correct**: a real AI repair, end to end |
| f01-live-live-20261108t195433z | F01-live-2 | throws only if `customer == null` | **incorrect**: blank customer not rejected (hidden tests 2/5 failed) |
| f04-live-live-20261108t200721z | F04-live-2 | health indicator always reports UP | **incorrect**: hides the fault |

| Policy (AI cohort, 32 attempts) | Auto-applied | UDR | Correct rejected | Escalated |
|---|---|---|---|---|
| B1 / B2 | 7 | **3/7** (43%) | 0/4 | 0 |
| B3 | 5 | **2/5** (40%) | 0/4 | 2 |

Cluster-bootstrap UDR intervals for the AI cohort (3 faults) are [0, 1] for each of B1, B2 and B3, and the B1−B3
difference interval is [−0.50, 0.17], which includes 0: far too few faults to compare policies statistically.

### 5.5 Diagnosis (one count per diagnosis run)
| Fault | gpt-oss-120b | qwen 7b | qwen 1.5b |
|---|---|---|---|
| F01 | 2/2 | 2/2 | — |
| F04 | **0/1** | **0/2** | — |
| F06 | 2/2 | 2/2 | 3/3 |

Both models run on F04 (qwen 1.5b was not) named `CatalogHealthIndicator.java` as the cause instead of
`application.properties`, even though each diagnosis cited the disabled catalog setting as evidence. Rule-mode
diagnoses are not in this table: for F04 and F06 they are oracle localisation (section 4).

---

## 6. Discussion

### 6.1 Findings
1. **Each gate catches a different class.** V1 catches ineffective patches, V2 regressions and V3 insecure code. With
   all gates plus the scope rules (B3), unsafe scripted auto-applies fell from 20 to 7 of 26 units (the gates alone
   leave 8), with no correct patch rejected.
2. **A real AI repair works end to end.** gpt-oss-120b diagnosed F06, drafted a correct fix that passed every gate,
   and the fix was deployed automatically. The oracle confirms it is correct.
3. **Tests and health checks cannot certify correctness.** Overfitting patches, whether hand-built or AI-written
   (F01-live-2, labelled incorrect by the oracle), pass every gate. The two that were deployed (the hand-built F06
   patch and F01-live-2) also passed the health window and were promoted.
4. **A misdiagnosis corrupts the scope rule.** On F04 the AI blamed the wrong file. The patch that hid the symptom
   stayed "inside the diagnosed file" and was auto-applied. The correct config fix was escalated, but never reached a
   human, because the policy prefers an auto-apply candidate over an escalated one. We report this as a policy-design
   finding. We did **not** change the policy after seeing the results. Candidate fixes for future work:
   - escalate when several gate-passing candidates disagree;
   - never let an AUTO_APPLY win over an ESCALATE for the same incident without review;
   - treat health-indicator changes as sensitive.
5. **Post-deployment monitoring is a separate layer.** The slow patch passed all gates and was caught only by the
   health window.

### 6.2 Threats to validity
- Three seeded development faults, one service, no held-out set.
- Rule-mode diagnosis of F04 and F06 is oracle localisation (copied from `fault.json`), so the scripted F04/F06
  rule-mode policy results assume perfect localisation. The live model missed F04.
- Machine oracle labels: two-person blind review is pending.
- The security probe is not independent of V3: its two regex rules cover the same classes as V3's two high-severity
  Semgrep rules; only the technique differs.
- Small, clustered samples: the AI cohort has 5 auto-applies over 3 faults.
- Format normalization is a recorded repair. Each gpt-oss-120b patch's format status, fired rules and raw diff are
  stored in `runs/<run_id>/patches.json`, but rates are not tabulated in `results/`. Of the 15 gpt-oss-120b patches,
  0 were raw-valid, 9 were normalized and 6 were invalid: no AI patch applied without the normalizer.
- A laptop container swap, not a production canary. The side-by-side smoke test was added late and ran for only 5 of
  the 12 deployments.
- Human review decisions were made by team members, not independent reviewers: 3 decisions at the CLI (2 approvals by
  "nehal", 1 rejection by "Agni Mn"; the name is the OS login).
- Hosted model behaviour can change over time.

### 6.3 Integrity
We audited our own evidence (`docs/audit/AUDIT_BASELINE.md`). The audit is still a draft: the code author self-checked
it and it has no independent sign-off yet. We fixed stale reports, 54 silently dropped rows, mixed cohorts and
hand-typed dashboard numbers. We disclosed two early runs whose code exists in no commit. Every run now records its code version and
dirty state; 5 later runs (174806z, 175754z, 180955z, 205508z and the healthy watch) ran on uncommitted changes and
are marked "+uncommitted" in the run ledger. Failed runs remain in the run ledger. Two runs that were disturbed by our
own mistakes are kept and annotated (`NOTE.txt`, `INTERRUPTED.txt`), not deleted.

---

## 7. Conclusion and future work
AutoImmune demonstrates a complete, traceable self-healing loop with real AI repairs, layered gates, human escalation,
staged deployment (side-by-side smoke test, health window, previous image kept) and automatic rollback. A promotion
does not mean the patch is correct. In this pilot, adding gates lowered unsafe auto-applies on the same candidates
(from 20 to 7 of 26 hand-built units, and from 3 to 2 of 7 unsafe AI patches, where the drop came from the scope
rules); with three faults the difference is not statistically established. Our independent oracle shows that passing
every test is not proof of correctness: its hidden tests found 2 of the 5 AI patches rated AUTO_APPLY incorrect, and
both were among the 3 actually deployed and promoted.

**Future work:**
- two-person blind label review;
- about 10 held-out faults;
- the policy changes listed in 6.1;
- more models and trials;
- a production-style canary.

## Appendix A: Reproduce
```
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -r requirements.lock
.\.venv\Scripts\python tools\oracle.py --only-new                       # oracle labels first (Docker; needs faults/*/hidden_tests/)
powershell -ExecutionPolicy Bypass -File reproduce.ps1 -Tests          # full test suite (Docker) + rebuild all tables, dashboard and manifest from recorded evidence
```
`reproduce.ps1 -Tests -Oracle` does both in one step (full oracle relabel, about 30+ min). Neither reruns the
pipeline experiments.

## Appendix B: Evidence map
Every table and count comes from the generated files in `results/`: `pilot_report.md` and its CSVs (`policies.csv`,
`gate_incremental.csv`, `intervals.csv`, `deployments.csv`, `rollbacks.csv`, `approvals.csv`, `llm_units.csv`,
`llm_patch_utility.csv`, `llm_diagnosis.csv`, `runs.csv`, `first_stop.csv`), plus `results/oracle_report.jsonl` for
oracle labels and `runs/<run_id>/` for per-run artifacts. `python tools/claim_ledger.py` builds a per-claim ledger
(`docs/claim_ledger.csv`) from the claim audit in `docs/audit/claim_audit.json`.
