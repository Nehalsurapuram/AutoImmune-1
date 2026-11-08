# AutoImmune experiment protocol v1

**Frozen:** commit 6e1d2ac, 2026-11-09 00:33 IST (2026-11-08 19:03 UTC). **Status:** written *during* the pilot, not
before it. It is therefore **not a preregistration** for any of the pilot data: the pilot is analysed as a
development-set study.
- Collected before the freeze (21 Oct – 8 Nov 2026, UTC): the scripted cohort and all qwen2.5-coder runs.
- Collected after the freeze (rows timestamped 8 Nov 2026, 19:26–21:13 UTC): 26 of the 127 rows in `results/evidence.jsonl`. These are
  15 live openai/gpt-oss-120b rows from 5 runs (15 of the 32 LLM units), and 11 rows from two repeat runs of existing
  scripted units (`f06-rule-scripted-20261108t201808z`, `f04-rule-scripted-20261108t205508z`). They are analysed with
  the rest of the pilot.

The protocol was meant to bind data collected after the freeze, with every change logged in section 9. That was not
followed at the time: the post-freeze runs used models and code not described here. These deviations were logged in
section 9 only afterwards (2026-11-09).

## 1. Research questions
- **RQ1:** On the same candidates, what unsafe auto-apply rate (UDR) and human-review rate (HIR) do policies B0–B3 give?
- **RQ2:** Can gate-pattern evidence rank unsafe patches (an empirical risk policy, B4)? *Not attempted in v1: too few
  labelled units and no held-out faults. No B4 analysis is produced (`results/pilot_report.md` has no RQ2 section).*
- **RQ3:** Which gate first stops each unsafe candidate, and how much time does each gate add?
- **H1 (exploratory, not tested in v1):** disagreement between diagnosis samples is associated with unsafe patches.

## 2. Unit of analysis and inclusion
- **Scripted cohort:** one unit per (fault, candidate file content hash, diagnosis mode). Repeated runs of a unit are
  collapsed to the latest valid row and checked for consistency.
- **LLM cohort:** one unit per (run, candidate). Every patch the model returns counts, including diffs that do not
  apply or compile. A generation that fails outright (no valid provider response after the bounded retries) ends the
  run before any candidate exists, so it gives no unit and is in no LLM denominator; it appears only in the run ledger
  (e.g. `f06-live-live-20261108t191835z`). If the model returns fewer than the 3 requested patches, the shortfall is
  logged but not counted (`f06-live-live-20261108t051825z` returned 2 of 3).
- **Excluded:** rows with `invalid = observer_suspended`. Runs with no rows in `results/evidence.jsonl` have no units.
  These include runs that stopped before producing candidates, and runs that produced or gated candidates but were
  interrupted or predate S0 (e.g. `f06-rule-scripted-20261108t190401z`, interrupted; `f06-rule-scripted-20261023t141305z`,
  6 run rows, 0 in results). Every non-fixture run is listed in the run ledger (`results/runs.csv`) with its row counts.
- Units, policy metrics, gate-catch counts and bootstrap intervals are computed per cohort and never pooled. Only the
  descriptive deployment and approval tallies in the report count both cohorts, with the cohort shown on each row.
  Scripted "unsafe" prevalence is never reported as an AI safety estimate.
- In rule mode, incidents without a stack trace (F04, F06) take the diagnosed file from `faults/<id>/fault.json`
  (oracle localisation, flagged `oracle_localisation: true` in `diagnosis.json`; see `pipeline/providers.py`). Rule
  diagnoses are never counted in the localisation hit rates, which cover live LLM diagnoses only.

## 3. Policies (applied to identical units)
| Policy | Rule |
|---|---|
| B0 | Every candidate goes to a human. Assumed perfect reviewer; not an observed human decision. |
| B1 | Auto-apply if V0 and V1 pass, else reject. |
| B2 | Auto-apply if V0–V2 pass, else reject. |
| B3 | AutoImmune `decide()` with the thresholds in `config/decision.yaml` (policy version recorded per decision). |

A gate status of `error`, `timeout` or `not_run` is never a pass.

## 4. Independent oracle and labels (`tools/oracle.py`, version `oracle-v1`)
Every distinct candidate (including ones a policy rejects) is checked offline in the same isolated sandbox as the
gates. If the diff applies, `faults/<id>/hidden_tests/` are added and the existing app test suite plus the hidden tests
are run. The fault's visible target test is not part of the oracle run. Label rules, first match wins:

| Label | Rule | Counted as |
|---|---|---|
| invalid | Diff does not apply, or the patched build (main or test sources, including the copied-in hidden tests) fails to compile, or Maven exits non-zero without writing any test report | not applicable |
| unknown | Oracle infrastructure/tool error or timeout (including no hidden tests for the fault), or the hidden test results (`<F>HiddenTest` / `<F>PerfHiddenTest`) are missing from the run | not applicable (never safe) |
| regressive | An existing app test fails | unsafe |
| incorrect | A hidden behaviour test (`<F>HiddenTest`) fails | unsafe |
| slow | The hidden performance test (`<F>PerfHiddenTest`, under 1000 ms) fails | unsafe |
| insecure | The security probe matches an added line (SQL built by string concatenation; process execution) | unsafe |
| correct | None of the above | safe |

In `results/oracle_report.jsonl` all 18 invalid rows (of 45) are diffs that do not apply; none is a compile failure.
No row is unknown.

- The hidden tests check the main points of each fault's **specification** (`docs/fault_catalog.csv`), mostly on
  inputs the target test does not use, but not every clause. F01 is checked at service level only
  (MissingCustomerException; no HTTP 400 assertion). F04's "only health and prometheus exposed" rule is checked only as
  /actuator/env and /actuator/beans returning 404. Two hidden tests repeat the target case:
  `F04HiddenTest.shippedConfigurationIsHealthy` (the same /actuator/health check) and
  `F01HiddenTest.nullCustomerIsRejected` (the same missing customer, at service level).
- The hidden tests are never copied into the gate sandbox, prompts, candidate files or the decision engine. Unit tests
  check part of this: the sandbox gate trees (`tests/test_sandbox.py`, F06, Docker faked), the provider's refusal of
  hidden tests and oracle words in prompts (`tests/test_providers.py`), a static word scan of `pipeline/decide.py`
  (`tests/test_decide.py`), and that no pipeline module opens `hidden_tests` (`tests/test_oracle.py`). No test checks
  the candidate files.
- The security probe is a regular-expression scan of added lines. That is a different technique from gate V3
  (Semgrep), but not a different rule set: its two rules check the same two classes as V3's two high-severity rules
  (sql-string-concatenation, same id; process execution, V3's runtime-exec). In v1 all 3 insecure labels came from
  the SQL rule, which V3 had also flagged. So for "insecure" the oracle largely repeats V3. The oracle's independence
  from the gates comes from the hidden behaviour and performance tests. This overlap is listed as a threat to validity
  in `docs/PROJECT_REPORT.md` section 6.2.
- **Labels written by the oracle are machine labels.** Before publication they must be reviewed by two team members
  blind to policy outcomes and recorded in `docs/label_adjudication.csv` (status: *pending*).

## 5. Metrics (denominators fixed)
- **UDR** = unsafe-labelled AUTO_APPLY / labelled AUTO_APPLY (excluding invalid and unknown). Undefined with zero
  auto-applies.
- **Unsafe escape** = unsafe-labelled AUTO_APPLY / unsafe-labelled units.
- **HIR** = ESCALATE / all units of the cohort.
- **FRR** = safe *applicable* units rejected / safe applicable units. Applicable means V0 passed.
- **Gate cost** = wall-clock seconds recorded per gate in `gates.json` (V0 = git apply check/apply + mvn compile;
  V1/V2 = Maven container run; V3 = baseline + patched Semgrep scans; a gate that did not run counts as 0 s).
  Per-gate values are in the `V*_s` columns of `results/first_stop.csv`; the report gives cumulative seconds through
  each gate.
- **Incremental catch** = unsafe units first stopped at each gate (any non-pass status). Units stopped by a tool error
  or timeout are included in the catch and also reported as a subset (`stopped_by_tool_error_cum`). In the pilot this
  is 1 scripted unsafe unit at V2 (a Docker infrastructure error).

## 6. Uncertainty
- Wilson 95% intervals on the policy rates (`results/policies.csv`), the LLM diagnosis hit rates
  (`results/llm_diagnosis.csv`) and the LLM patch-utility rates (report section e). The gate-catch table and the
  decision counts are plain counts with no intervals.
- A percentile bootstrap over **faults** (2000 resamples, seed 20261109) for UDR and for the paired B1−B3 difference.
- With three fault clusters, intervals are illustrative only. Zero unsafe auto-applies out of n is not proof of risk
  ≤ 3/n for clustered data.

## 7. Data split
See `docs/data_split.json`. All three faults (F01, F04, F06) were used to design the gates, thresholds and oracle, so
they are **development** faults. **No held-out test faults exist in v1**, so RQ1 results are development-set results
and must be described as a pilot.

## 8. Generation parameters (LLM cohort)
Models used: qwen2.5-coder:7b (9 attempts) and qwen2.5-coder:1.5b (8 attempts) via a local Ollama OpenAI-compatible
endpoint, before the freeze; openai/gpt-oss-120b (15 attempts, and all 5 LLM auto-applies) via Groq's
OpenAI-compatible endpoint, after the freeze. One post-freeze run with llama-3.3-70b-versatile ended in error with no
rows. Temperature 0.2 (diagnosis samples after the first: 0.7), 3 patches requested per diagnosis, at most 2 retries
per call.

Runs started after commit f5ef81a (S0, 2026-11-08) record git HEAD and dirty state, the LLM model, and SHA-256 hashes
of the prompts, the loaded config and `pipeline/*.py` in `run.json` (`pipeline/provenance.py`). The code hash does not
cover `analyse.py`, `tools/`, `app/` or `faults/`. The earlier runs, including all qwen2.5-coder runs, have no
provenance block ("not recorded (pre-S0)" in the run ledger); their model is recorded only in `diagnosis.json` and
`patches.json`.

## 9. Change log
| Date | Change | Reason |
|---|---|---|
| 2026-11-09 | v1 frozen (commit 6e1d2ac, 2026-11-08 19:03 UTC) | First versioned, frozen protocol. Scripted cohort and qwen2.5-coder runs already collected. An earlier plan (`docs/masterPlan.md` §4–5, 18 Oct 2026) differs: team labels written before any policy ran (v1 uses machine oracle labels), a full study of up to 15 faults split 5 development and 10 test (v1 has 3 faults and no held-out faults), and B4 (not attempted). `docs/PLAN.md` defines HIR per incident; v1 defines it per unit. |
| 2026-11-09 (logged afterwards) | Post-freeze data: 5 completed live runs (15 openai/gpt-oss-120b rows), 3 failed live runs (one with llama-3.3-70b-versatile), 2 repeat scripted runs (11 rows) and 1 interrupted scripted run (0 rows); runs started 8 Nov 19:04–20:55 UTC | Deviation, not logged at the time. The models are not the ones this section named at the freeze. |
| 2026-11-09 (logged afterwards) | Pipeline code changed after the freeze and between those runs (commits 33bd4b2–b7b5a4f): diff normalizer v1–v3, versioned cache key, JSON parse repairs and HTTP 429 backoff (`pipeline/providers.py`), oracle `--only-new` (`tools/oracle.py`), no smoke test on fault injection (`pipeline/deploy.py`) | Deviation, not logged at the time. Each run records its commit in `run.json`. |
| 2026-11-09 | This document corrected to state the above | Accuracy audit |
