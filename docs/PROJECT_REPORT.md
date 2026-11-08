# AutoImmune: Evidence-Gated Self-Healing for a Java Microservice

**B.Tech Final Year Project Report**
**Team:** Agni M N, Pradeep S, S Nehal  **Guide:** Mrs. M. Shona
**Date:** 9 November 2026  **Code:** git history in this folder (protocol frozen in `docs/protocol_v1.md`)

---

## Abstract

AI models can now draft code fixes, but a fix that passes its own test is not necessarily safe to deploy. AutoImmune
is a hybrid self-healing pipeline for a Java Spring Boot service. It detects a production fault, diagnoses it,
collects candidate patches, validates each one in an isolated Docker sandbox through four evidence gates, and then
decides by fixed rules whether to reject, escalate to a human, or auto-apply:
- **V0:** the patch applies and compiles.
- **V1:** the target test passes.
- **V2:** the full regression suite passes.
- **V3:** a Semgrep scan finds no new security issues.

Deployed patches are smoke-tested side by side, watched over a health window that includes p95 latency, and promoted
or rolled back with image-ID verification. An AI model is used only for diagnosis and patch drafting. Every patch is
labelled afterwards by an independent offline oracle the pipeline never sees: hidden specification tests, a
performance test, the full suite, and a separate security probe.

On three seeded faults:
- **Detection** takes 5–6 s, with no false alarm in 5 minutes of healthy traffic.
- **Hand-built patches (32 evaluations):** adding gates cut unsafe patches that would be auto-applied from 20/26
  (target test only) to 13/26 (plus full suite) to 7/26 (full policy), with 0/6 correct patches rejected.
- **Real AI patches (gpt-oss-120b, 15 attempts):** the model produced a correct, oracle-verified repair that was
  deployed and promoted automatically.
- **But under the full policy, 2 of the 5 auto-applied AI patches were wrong.** One guarded only against `null`. The
  other made the health check always report UP after a misdiagnosis, while the correct fix was escalated and never
  reached a human.

**Passing tests and health checks is not evidence of correctness.** With three faults and small samples, these are
pilot results: confidence intervals are wide and policy differences are not statistically established.

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
- A controlled research prototype on one laptop.
- One service, three seeded faults.
- **No** production claims, **no** calibrated probabilities, **no** novelty claimed for repair, verification or
  rollback on their own.

---

## 2. Related work
Closely related work, as listed in the project roadmap (to be checked against the full texts before publication):
- **ORCA** (Gao et al., 2026): observability-grounded microservice repair.
- **Abstain and Validate** (Cambronero et al.): filtering repair attempts before review.
- **Meta Diff Risk Score** (2025): risk scoring for code changes.
- **HealBench/HealGuard** (Tan et al., 2026): guardrails for runtime healing.
- **Sajadi et al.** (2025): security of AI-generated patches.

Our narrower contribution is a reproducible comparison of deployment policies on the *same* independently labelled
candidates, including real AI patches.

---

## 3. System design

```
service ──► detector ──► diagnose (LLM | rule) ──► draft patches (LLM | scripted) ──► format check (recorded)
                                                                                     │
   Docker sandbox, --network none:  V0 apply+compile → V1 target test → V2 full suite → V3 Semgrep (new findings)
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
| `pipeline/providers.py` | The only LLM use: diagnose and draft patches (live, replay, scripted, rule). Every raw response is hashed. A deterministic, versioned diff normalizer repairs **format only** (missing headers or line numbers, apply_patch markers), records every rule it fires, and keeps the raw diff. |
| `pipeline/sandbox.py` | Gates in Docker: no network, 2 GB memory, 2 CPUs, PID limit, all capabilities dropped, non-root. Isolation verified (`docs/audit/isolation_test.txt`). |
| `pipeline/decide.py` | Rule-based tier and decision, with written reasons |
| `pipeline/deploy.py` | Side-by-side smoke test before cutover, image IDs, health window with p95, verified rollback, CLI human approval |
| `pipeline/provenance.py` | Per-run fingerprint, so any result traces to exact code |
| `tools/oracle.py` | Independent offline labels: invalid / unknown / regressive / incorrect / slow / insecure / correct |
| `analyse.py` | All tables, Wilson intervals, fault-cluster bootstrap, gate-cost table; `--check` detects stale reports |

**Decision rules:**
- **REJECT** if V0, V1 or V2 fails, or V3 finds a new high-severity issue.
- **ESCALATE** if everything passes but the patch touches a sensitive path or a file outside the diagnosed one, is
  larger than 20 lines, raises a low-severity finding, or the diagnosis samples disagree.
- **AUTO_APPLY** otherwise.
- When several candidates qualify, the smallest AUTO_APPLY patch is deployed; an ESCALATE goes to a human only when no
  AUTO_APPLY exists.

---

## 4. Experimental setup
- **Faults** (`docs/fault_catalog.csv`):
  - F01, null handling: a search without a customer returns 500 instead of 400.
  - F04, configuration: the catalog is disabled, so health is DOWN.
  - F06, business logic: an order of exactly 1000.00 loses its discount.

  All three are seeded faults and **development** faults: there is no held-out set (`docs/data_split.json`).
- **Scripted cohort:** 16 hand-built patches (correct, overfitting, regressive, insecure, ineffective, plus slow for
  F06), each evaluated under two diagnosis modes: 32 units.
- **LLM cohort:** every attempt counts, including failures. That is 32 attempts:
  - qwen2.5-coder 7b: 9 attempts;
  - qwen2.5-coder 1.5b: 8 attempts;
  - **openai/gpt-oss-120b** via Groq: 15 attempts over 5 runs.
- **Oracle** (`tools/oracle.py`, rules fixed in `docs/protocol_v1.md`). For each fault, hidden tests encode the
  specification on inputs the target test does not use. A performance test requires under 1000 ms. A regex security
  probe on added lines is deliberately different from gate V3. **Machine labels; two-person blind review is
  pending** (`docs/label_adjudication.csv`).
- **Policies:**
  - B0: a human reviews everything (an assumed perfect reviewer);
  - B1: V0 + V1;
  - B2: V0–V2;
  - B3: AutoImmune.

---

## 5. Results
All numbers are regenerated by `python analyse.py` from `results/evidence.jsonl` and `results/oracle_report.jsonl`,
and checked by `python analyse.py --check`. `reproduce.ps1` reruns everything.

### 5.1 The full loop (scripted, with provenance)
| Run | Fault | Detected after | Outcome |
|---|---|---|---|
| f06-rule-scripted-20261108t173444z | F06 | 5.0 s | smallest passing patch promoted (the overfitting one) |
| f01-rule-scripted-20261108t174806z | F01 | 5.0 s | correct patch promoted |
| f04-rule-scripted-20261108t175754z | F04 | 6.0 s | escalated, **human approved**, deployed, promoted |
| f06-rule-scripted-20261108t180955z | F06 | — | planted slow patch: 3016 ms over the 2000 ms limit, rolled back in 4.0 s (before the S3 changes; image tracked by tag) |
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

The oracle independently labelled all 16 scripted patches exactly as their builders intended. The 8 that pass every
gate are **overfitting** (labelled incorrect) and **slow** patches. Gate times come from the latest run of each unit on
one laptop and vary between runs (the F06 rerun's V1 took up to 171 s against about 25 s earlier), so treat them as
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

Bootstrap intervals for the AI cohort span [0, 1]: far too few faults to compare policies statistically.

### 5.5 Diagnosis (one count per diagnosis run)
| Fault | gpt-oss-120b | qwen 7b | qwen 1.5b |
|---|---|---|---|
| F01 | 2/2 | 2/2 | — |
| F04 | **0/1** | **0/2** | — |
| F06 | 2/2 | 2/2 | 3/3 |

Every model missed F04's configuration root cause and blamed the health-indicator class instead.

---

## 6. Discussion

### 6.1 Findings
1. **Each gate catches a different class.** V1 catches ineffective patches, V2 regressions and V3 insecure code. With
   all gates, unsafe scripted auto-applies fell from 20 to 7 of 26, with no correct patch rejected.
2. **A real AI repair works end to end.** gpt-oss-120b diagnosed F06, drafted a correct fix that passed every gate,
   and the fix was deployed automatically. The oracle confirms it is correct.
3. **Tests and health checks cannot certify correctness.** Overfitting patches, whether hand-built or AI-written
   (F01-live-2), pass every gate and the health window.
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
- Machine oracle labels: two-person blind review is pending.
- The security probe overlaps in intent with V3.
- Small, clustered samples: the AI cohort has 5 auto-applies over 3 faults.
- Format normalization is a recorded repair. Raw-valid and normalized rates are both stored.
- A laptop container swap with a side-by-side smoke test, not a production canary.
- The reviewer is a team member.
- Hosted model behaviour can change over time.

### 6.3 Integrity
We audited our own evidence (`docs/audit/AUDIT_BASELINE.md`). We fixed stale reports, 54 silently dropped rows, mixed
cohorts and hand-typed dashboard numbers, and we disclosed two runs made with uncommitted code. Every run now records
its code version. Failed runs remain in the run ledger. Two runs that were disturbed by our own mistakes are kept and
annotated (`NOTE.txt`, `INTERRUPTED.txt`), not deleted.

---

## 7. Conclusion and future work
AutoImmune demonstrates a complete, traceable self-healing loop with real AI repairs, layered gates, human escalation,
safe deployment and automatic rollback. Layered evidence reduces unsafe auto-application, but our independent oracle
shows that passing every test is not proof of correctness: 2 of 5 auto-applied AI patches were wrong.

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
powershell -ExecutionPolicy Bypass -File reproduce.ps1 -Tests          # tests + regenerate everything
.\.venv\Scripts\python tools\oracle.py --only-new                       # oracle labels (Docker)
```

## Appendix B: Evidence map
See `docs/claim_ledger.csv`: every number in this report, linked to the file that produces it.
