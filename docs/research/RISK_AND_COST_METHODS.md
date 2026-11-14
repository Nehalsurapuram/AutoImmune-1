# Risk estimation (RQ2) and validation cost (RQ3): methods

Offline analyses of recorded evidence. Neither changes the gates or the decision engine, which remains a
rule-based tier (`pipeline/decide.py`, `config/decision.yaml`). Results are pilot-scale.

| Analysis | Code | Output | Tests |
|---|---|---|---|
| Risk estimation | `tools/risk_model.py` | `results/risk/` (`risk_estimation.json`, `risk_report.md`, CSVs) | `tests/test_risk_model.py` |
| Validation cost | `tools/validation_cost.py` | `results/cost/` (`validation_cost.json`, `validation_cost.md`) | `tests/test_validation_cost.py` |
| Console export | `tools/export_ui_data.py` | `risk_estimation`, `validation_cost` keys of the evidence snapshot | `tests/test_export_ui_data.py` |

Regenerate: `python -m tools.risk_model`, `python -m tools.validation_cost`, then `python tools/export_ui_data.py`.

## Unit of analysis

Raw evidence rows (`results/evidence.jsonl`) -> eligible rows (`analyse.eligible_rows`: not invalid, run not in
`config/analysis_exclusions.json`) -> research units (`analyse.units_of`) -> labelled units -> **distinct judged
patches**: units collapsed by patch identity (scripted: content-hash candidate id; live: `patch_sha256`). The same
diff evaluated under two diagnosis modes or in several runs is one observation. Scripted (hand-built) and LLM
(model-written) patches are estimated and reported separately.

## Labels

Scripted: `faults/*/candidates/labels.json`, assigned when the candidates were built. LLM: `results/oracle_report.jsonl`
from `tools/oracle.py` (hidden specification tests, hidden performance test, full existing suite, security probe).
Unsafe = `analyse.UNSAFE`; safe = `analyse.SAFE`. Labels `invalid`, `unknown` and unlabelled units are excluded and
counted, never treated as safe. Independent two-person adjudication (`docs/research/LABEL_ADJUDICATION.md`) is
**pending**: `docs/label_adjudication.csv` has no completed rows.

Known circularity: the oracle reuses the full existing suite (the same suite as V2) and a security probe that
overlaps V3, so "a gate failed, therefore unsafe" is partly true by construction.

## Risk estimation

**Empirical conditional rate.** Patches are grouped by gate outcome: V0 failed; passed V0 and failed V1, V2 or V3;
passed V0-V3; and the subset of the last decided AUTO_APPLY.

    P(unsafe | E) = N(unsafe and E) / N(labelled and E)

with a Wilson score 95% interval (z = 1.96). This is an interval for the group's rate, not a prediction interval
for one patch. A group with fewer than 5 labelled distinct patches is reported as counts only (a presentation
rule); a group with none has no estimate.

**Logistic model** (`logistic-l2-v1`). Features, fixed before results were seen and all available before deploy:
`gate_fail`, `new_findings`, `log_diff_lines`, `multi_file`, `sensitive_path`. Standardised on the training set;
L2 penalty 1.0 on slopes, intercept unpenalised; fitted by Newton's method.

    p = 1 / (1 + exp(-(b0 + sum_j b_j * z_j)))

Not used: `top1_hit`/`top3_hit` (computed from the known fault location), `oracle_localisation`, deploy and
rollback fields (post-deploy), the rule tier and decision, gate durations, labels of any kind.

**Evaluation.** Every scored probability is out of sample: leave-one-fault-out within scripted; fit on scripted,
score LLM; leave-one-fault-out on both cohorts with scores reported per cohort. Metrics: Brier score, Brier skill
against the base rate, log loss, ROC AUC, reliability table. A separate AUC is computed among patches that passed all
four gates, the case the decision actually depends on. A candidate's model probability in the console is its
out-of-fold prediction and exists only for judged patches.

## Validation cost

**Timing** uses every eligible row in which the gate executed (status other than `not_run`), per cohort, including
repeats. Durations recorded as 0.0 s (the V0 apply check that runs on the host is not timed) are counted as executed
and untimed, and left out of median, p95 (nearest rank) and mean.

**Benefit** uses the distinct judged patches of the risk analysis. The pipeline stops at the first non-passing gate,
so each unsafe patch is attributed to the first gate that stopped it; whether a later gate would also have caught it
is unknown. Tool errors and timeouts are counted separately, never as a catch.

    catches per gate-minute (g) = unsafe first stopped at g / (sum of g's seconds over judged patches reaching g / 60)

Undefined when the gate recorded no time. `results/gate_incremental.csv` (from `analyse.py`) covers a different
population: research units, with units labelled invalid counted as labelled, and gates that did not run counted as
0 s in its per-unit medians.
