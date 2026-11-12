# AutoImmune: Rigorous Statistical Analysis & Policy Evaluation

**Author:** AutoImmune Research Engineering Consortium  
**Date:** 2026-11-11  
**Dataset:** `results/evidence.jsonl` (217 raw rows, 212 eligible rows, 100 primary analysis units)  
**Artifact Dependencies:** [`docs/research/final_results.csv`](file:///d:/14/docs/research/final_results.csv), [`docs/research/policy_comparison.csv`](file:///d:/14/docs/research/policy_comparison.csv), [`docs/research/fault_level_results.csv`](file:///d:/14/docs/research/fault_level_results.csv)

---

## 1. Methodological & Theoretical Foundation

Empirical research in Automated Program Repair (APR) and autonomous systems often suffers from two methodological flaws:
1. **The Independence Fallacy:** Treating multiple candidate patches generated for the same software bug as independent and identically distributed (i.i.d.) observations. Because candidates for a common defect share identical compiler dependencies, class hierarchies, and execution paths, candidates within a fault cluster exhibit high intra-cluster correlation.
2. **The Unpaired Comparison Fallacy:** Evaluating competing repair policies on the same candidates using two-sample independent tests (e.g. standard two-sample $z$-tests or Fisher's exact tests). Because Policy B1, B2, and B3 evaluate the **exact same candidate units**, observations are inherently paired.

AutoImmune addresses these foundational issues through a mathematically rigorous statistical methodology:

### 1.1 The Candidate Repair Unit
To eliminate bias from repeated pipeline executions, repeated runs of identical scripted candidate diffs are collapsed into unique candidate units:
$$\text{Unit Key}_{\text{scripted}} = (\text{scripted}, \text{fault\_id}, \text{candidate\_id}, \text{diag\_mode})$$
$$\text{Unit Key}_{\text{llm}} = (\text{llm}, \text{fault\_id}, \text{run\_id}, \text{candidate\_id})$$
Every unit represents a distinct candidate evaluation. Across the 212 eligible execution rows (from 217 raw rows in [`results/evidence.jsonl`](file:///d:/14/results/evidence.jsonl)), this yields exactly **100 candidate units** (47 Scripted units, 53 Live LLM attempts). Repeated runs of identical scripted diffs are collapsed into their single unit key.

### 1.2 Paired McNemar Discordance Test
When comparing policies $A$ and $B$, we construct a $2 \times 2$ contingency matrix of deployment decisions:
- $n_{00}$: Both policies reject or escalate.
- $n_{11}$: Both policies auto-apply.
- $n_{10}$: Policy $A$ auto-applies, but Policy $B$ rejects or escalates.
- $n_{01}$: Policy $B$ auto-applies, but Policy $A$ rejects or escalates.

Hypothesis testing is performed using **McNemar's test with Edwards' continuity correction**:
$$\chi^2 = \frac{(|n_{10} - n_{01}| - 1)^2}{n_{10} + n_{01}}, \quad \text{d.f.} = 1$$
This evaluates whether the discordance between policies is statistically significant.

### 1.3 Confidence Intervals (Wilson Score Interval)
For binomial proportions $p = k / n$, normal approximations fail when $k$ is near 0 or $n$. We compute asymmetric **Wilson score 95% confidence intervals**:
$$CI_{95\%} = \frac{k + \frac{z^2}{2}}{n + z^2} \pm \frac{z}{n + z^2} \sqrt{\frac{k(n - k)}{n} + \frac{z^2}{4}}, \quad z = 1.95996$$

---

## 2. Empirical Policy Comparison: Scripted Cohort ($N = 47$)

The scripted cohort comprises 47 candidate units across 6 fault clusters (`F01`, `F02`, `F04`, `F05`, `F06`, `F07`) evaluated under both rule-based and live diagnosis. All 47 units have ground-truth oracle labels (38 unsafe, 9 safe applicable):

| Policy | Definition | Auto-Apply Rate [95% CI] | Escalate Rate [95% CI] | Reject Rate [95% CI] | Unsafe Decision Rate (UDR) | Unsafe Escape Rate | False Rejection Rate (FRR) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **B0** | Review-All Baseline | 0.0% (0/47)<br/>[0.0%, 7.6%] | **100.0%** (47/47)<br/>[92.4%, 100.0%] | 0.0% (0/47)<br/>[0.0%, 7.6%] | *0/0 (Undefined)* | **0.0%** (0/38)<br/>[0.0%, 9.2%] | **0.0%** (0/9)<br/>[0.0%, 29.9%] |
| **B1** | Target Test Only (V0+V1) | **80.9%** (38/47)<br/>[67.5%, 89.6%] | 0.0% (0/47)<br/>[0.0%, 7.6%] | 19.1% (9/47)<br/>[10.4%, 32.5%] | **76.3%** (29/38)<br/>[60.8%, 87.0%] | **76.3%** (29/38)<br/>[60.8%, 87.0%] | **0.0%** (0/9)<br/>[0.0%, 29.9%] |
| **B2** | Full Regression (V0–V2) | **61.7%** (29/47)<br/>[47.4%, 74.2%] | 0.0% (0/47)<br/>[0.0%, 7.6%] | 38.3% (18/47)<br/>[25.8%, 52.6%] | **69.0%** (20/29)<br/>[50.8%, 82.7%] | **52.6%** (20/38)<br/>[37.3%, 67.5%] | **0.0%** (0/9)<br/>[0.0%, 29.9%] |
| **B3** | **AutoImmune (V0–V3 + Risk)** | **38.3%** (18/47)<br/>[25.8%, 52.6%] | **6.4%** (3/47)<br/>[2.2%, 17.0%] | **55.3%** (26/47)<br/>[41.2%, 68.6%] | **61.1%** (11/18)<br/>[38.6%, 79.7%] | **28.9%** (11/38)<br/>[16.9%, 45.2%] | **0.0%** (0/9)<br/>[0.0%, 29.9%] |

---

## 3. Paired Hypothesis Tests & Discordance Analysis

Because policies evaluate identical candidate units, paired McNemar discordance tests establish whether policy differences represent genuine structural filtering:

### 3.1 Policy B1 (Target Test) vs. Policy B3 (AutoImmune)
- **Discordance:** $n_{00} = 9$, $n_{01} = 0$, $n_{10} = 20$, $n_{11} = 18$.
- **Total Discordant Pairs:** $n_{10} + n_{01} = 20$.
- **Test Statistic:** $\chi^2 = \frac{(|20 - 0| - 1)^2}{20} = \frac{361}{20} = \mathbf{18.0500}$.
- **Significance:** $p = 0.000022$ ($p < \mathbf{0.0001}$).
- **Risk Difference:** $\Delta = -42.6\%$ ($p < 0.001$).
- **Finding:** Policy B3 intercepts 20 hazardous patches admitted by naive target-test gating.

### 3.2 Policy B2 (Full Regression) vs. Policy B3 (AutoImmune)
- **Discordance:** $n_{00} = 18$, $n_{01} = 0$, $n_{10} = 11$, $n_{11} = 18$.
- **Total Discordant Pairs:** $n_{10} + n_{01} = 11$.
- **Test Statistic:** $\chi^2 = \frac{(|11 - 0| - 1)^2}{11} = \frac{100}{11} = \mathbf{9.0909}$.
- **Significance:** $p = 0.002569$ ($p = \mathbf{0.0026}$).
- **Risk Difference:** $\Delta = -23.4\%$ ($p < 0.01$).
- **Core Empirical Discovery:** Passing a full regression test suite (V2) is **demonstrably insufficient for autonomous deployment**. AutoImmune's Gate V3 and risk tiering intercept 11 regression-passing candidates that contain security violations or sensitive scope breaches.

### 3.3 Anatomy of the 11 Discordant Candidates (B2 vs B3)
Forensic inspection of the 11 candidates where B2 auto-applies and B3 rejects/escalates reveals two distinct failure mechanisms:
1. **Static AST Security Violations (8 candidates intercepted by Gate V3 Semgrep):**
   - `F01` insecure (`F01-scripted-4eeb7107`, 2 units): Injects unescaped SQL concatenation into search query.
   - `F02` insecure (`F02-scripted-3f5b7d8a`, 1 unit): Injects raw SQL parameter interpolation.
   - `F04` insecure (`F04-scripted-13aa249d`, 2 units): Adds command injection vulnerability.
   - `F06` insecure (`F06-scripted-05420f6c`, 2 units): Injects unsanitized SQL string concatenation.
   - `F07` insecure (`F07-scripted-9480f424`, 1 unit): Injects unsanitized process execution call.
2. **Sensitive Configuration Scope Breaches (3 candidates escalated by Risk Policy):**
   - `F04` correct (`F04-scripted-835a25e8`, 2 units): Modifies `application.properties`. Even though V0–V3 pass, the path is flagged as sensitive infrastructure configuration, escalating to human review.
   - `F04` overfitting (`F04-scripted-34e008d0`, 1 unit): Configuration-level patch escalated for operator signature.

---

## 4. Empirical Evaluation: Live LLM Cohort ($N = 53$)

The live LLM cohort evaluates 53 one-shot patch synthesis attempts generated by local open-weights code models (`qwen2.5-coder:1.5b`, `qwen2.5-coder:7b`) and historical GPT-OSS endpoints:

| LLM Model / Synthesizer | Evaluated Attempts | Applied Cleanly (V0) | Fixed Target Test (V1) | Passed Regression (V2) | Clean Security (V3) | `AUTO_APPLY` Decisions | Verified Correct (Oracle) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `qwen2.5-coder:1.5b` | 8 | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | **0 (0.0%)** |
| `qwen2.5-coder:7b` | 33 | 11 (33.3%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | **0 (0.0%)** |
| `openai/gpt-oss-120b` | 12 | 11 (91.7%) | 7 (58.3%) | 7 (58.3%) | 7 (58.3%) | 5 (41.7%) | **0 (0.0%)** |
| **All LLM Attempts** | **53** | **22 (41.5%)** | **7 (13.2%)** | **7 (13.2%)** | **7 (13.2%)** | **5 (9.4%)** | **0 / 53 (0.0%)** |

### 4.1 Key Findings for LLM Repair
1. **Compilation Bottleneck:** 58.5% of open-weights LLM patches fail at Gate V0. The model frequently synthesizes hallucinated methods, invalid imports, or malformed diff headers.
2. **The 0% Verified Repair Reality:** Across all 53 live attempts evaluated against independent hidden oracle tests (`results/oracle_report.jsonl`), **exactly zero candidates achieved semantic correctness**. 
3. **Safety Interception:** AutoImmune's pre-deployment validation pipeline successfully rejected **86.8% (46/53)** of defective LLM patches, and escalated another **3.8% (2/53)** for human review. Only 5 patches (9.4%) were auto-applied, all of which represented semantic overfitting.

---

## 5. Gate Execution Cost & Latency Analysis

AutoImmune's deterministic gates operate sequentially, halting at the first failure to minimize computational waste:

| Gate Identifier | Target Evaluation | Mean Latency (s) | Median Latency (s) | Intercepted Candidates (First Stop) |
| :--- | :--- | :---: | :---: | :---: |
| **Gate V0** | Syntax, git apply, Maven compilation | 1.1s | 1.0s | **31 candidates** (31 LLM) |
| **Gate V1** | Visible Target Incident Test | 2.4s | 2.1s | **24 candidates** (9 Scripted, 15 LLM) |
| **Gate V2** | Full Regression Suite (`mvn test`) | 3.8s | 3.5s | **9 candidates** (9 Scripted) |
| **Gate V3** | Semgrep Static Security AST Scan | 1.2s | 1.1s | **8 candidates** (8 Scripted) |
| **Decision Scope** | Path allowlist, diff lines, multi-file | <0.01s | <0.01s | **5 candidates escalated** (3 Scripted, 2 LLM) |
| **Canary Window** | Post-deployment HTTP latency probe | 3.0s | 3.0s | **1 candidate rolled back** (F06 slow) |
| **Survived** | Passed all gates and deployed cleanly | — | — | **22 candidates** (17 Scripted, 5 LLM) |

**Total Validation Latency:** The median end-to-end validation latency for a candidate passing all four pre-deployment gates is **8.2 seconds**, providing real-time feedback without delaying incident response.

---

## 6. Runtime Canary Defense & Rollback Metrics

- **Total Production Deployments Executed:** 13 deployment events across the baseline run series.
- **Promoted Workloads:** 11 deployments met SLA criteria and were fully promoted.
- **Automated Rollbacks:** 2 rollback events.
  - 1 staged demonstration rollback (`F06-scripted-7509cb64`): SLA latency breached (3015ms > 2000ms limit); traffic swapped back to baseline in **5.0 seconds**.
  - 1 transient rollback during exploratory configuration testing.
  - **Zero false rollbacks:** The healthy baseline run (`healthy-watch-20261108t182609z`, 300 seconds continuous polling) exhibited **0 false alarms** and **0 spurious rollbacks**.

---

## 7. Limitations & Threats to Validity

1. **Defect Diversity:** The evaluated live benchmark spans 6 faults. Expanding live execution to the remaining 6 exploratory faults is necessary before making broader claims across enterprise Java systems.
2. **Small-Sample Cluster Properties:** With 6 evaluated fault clusters, Liang-Zeger cluster-robust variance estimates should be interpreted alongside exact paired McNemar statistics.
3. **Absence of Real Human Operators:** Human escalation is validated through interactive terminal mechanics and scripted test feeds; operator cognitive load and real-world review accuracy remain to be measured in human-subject trials.
