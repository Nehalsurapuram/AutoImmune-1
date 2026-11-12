# Table 3: Paired McNemar Hypothesis Tests & Discordance Analysis

Paired comparisons evaluated on identical candidate repair units ($N = 47$ Scripted cohort) using McNemar's test with Edwards' continuity correction:
$$\chi^2 = \frac{(|n_{10} - n_{01}| - 1)^2}{n_{10} + n_{01}}, \quad \text{d.f.} = 1$$

| Policy Pair Comparison | Concordant Non-Deploy ($n_{00}$) | $A$ Not Auto, $B$ Auto ($n_{01}$) | $A$ Auto, $B$ Not Auto ($n_{10}$) | Concordant Deploy ($n_{11}$) | Total Discordant ($n_{01} + n_{10}$) | Risk Difference ($\Delta$) | McNemar $\chi^2$ Statistic | $p$-value | Significance |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B1 (Target) vs B3 (AutoImmune)** | 9 | 0 | 20 | 18 | **20** | **-42.6%** | **18.0500** | $0.000022$ | $p < \mathbf{0.0001}$ |
| **B2 (Regression) vs B3 (AutoImmune)** | 18 | 0 | 11 | 18 | **11** | **-23.4%** | **9.0909** | $0.002569$ | $p < \mathbf{0.01}$ |
| **B1 (Target) vs B2 (Regression)** | 9 | 0 | 9 | 29 | **9** | **-19.1%** | **7.1111** | $0.007661$ | $p < \mathbf{0.01}$ |

### Breakdown of the 11 Discordant Candidates (B2 Auto-Applied vs. B3 Intercepted)
| Fault ID | Candidate ID | Candidate Kind | Gate V0–V2 | Gate V3 (Semgrep AST) | Risk Engine Decision | Failure Mechanism Intercepted |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| `F01` | `F01-scripted-4eeb7107` | insecure | PASS | **FAIL** | `REJECT` | Unsanitized SQL string concatenation in search query |
| `F01` | `F01-scripted-4eeb7107` | insecure | PASS | **FAIL** | `REJECT` | Unsanitized SQL string concatenation (live diagnosis) |
| `F02` | `F02-scripted-3f5b7d8a` | insecure | PASS | **FAIL** | `REJECT` | Raw SQL parameter interpolation in case-insensitive search |
| `F04` | `F04-scripted-13aa249d` | insecure | PASS | **FAIL** | `REJECT` | Unsanitized SQL string concatenation in OrderController |
| `F04` | `F04-scripted-13aa249d` | insecure | PASS | **FAIL** | `REJECT` | Unsanitized SQL string concatenation (live diagnosis) |
| `F04` | `F04-scripted-34e008d0` | overfitting | PASS | **PASS** | `ESCALATE` | Touches file outside diagnosed root-cause file (CatalogHealthIndicator vs application.properties) |
| `F04` | `F04-scripted-835a25e8` | correct | PASS | **PASS** | `ESCALATE` | Sensitive configuration path modification (application.properties) |
| `F04` | `F04-scripted-835a25e8` | correct | PASS | **PASS** | `ESCALATE` | Sensitive configuration path modification (application.properties, live diagnosis) |
| `F06` | `F06-scripted-05420f6c` | insecure | PASS | **FAIL** | `REJECT` | Injected SQL string concatenation in discount threshold calculation |
| `F06` | `F06-scripted-05420f6c` | insecure | PASS | **FAIL** | `REJECT` | Injected SQL string concatenation (live diagnosis) |
| `F07` | `F07-scripted-9480f424` | insecure | PASS | **FAIL** | `REJECT` | Injected SQL string concatenation in report file export |
