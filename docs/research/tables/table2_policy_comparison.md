# Table 2: Policy Safety Comparison (Scripted Cohort, N = 47)

Evaluated across the 47 primary candidate units in `results/evidence.jsonl` across 6 fault clusters (`F01`, `F02`, `F04`, `F05`, `F06`, `F07`). All 47 units are verified by ground truth oracle tests (38 unsafe, 9 safe applicable):

| Policy Configuration | Policy Definition | Auto-Apply Rate [95% Wilson CI] | Escalate Rate [95% Wilson CI] | Reject Rate [95% Wilson CI] | Unsafe Decision Rate (UDR) | Unsafe Escape Rate | False Rejection Rate (FRR) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **B0** | Review-All Baseline | 0.0% (0/47)<br/>[0.0%, 7.6%] | **100.0%** (47/47)<br/>[92.4%, 100.0%] | 0.0% (0/47)<br/>[0.0%, 7.6%] | *0/0 (Undefined)* | **0.0%** (0/38)<br/>[0.0%, 9.2%] | **0.0%** (0/9)<br/>[0.0%, 29.9%] |
| **B1** | Target Test (V0+V1) | **80.9%** (38/47)<br/>[67.5%, 89.6%] | 0.0% (0/47)<br/>[0.0%, 7.6%] | 19.1% (9/47)<br/>[10.4%, 32.5%] | **76.3%** (29/38)<br/>[60.8%, 87.0%] | **76.3%** (29/38)<br/>[60.8%, 87.0%] | **0.0%** (0/9)<br/>[0.0%, 29.9%] |
| **B2** | Full Regression (V0–V2) | **61.7%** (29/47)<br/>[47.4%, 74.2%] | 0.0% (0/47)<br/>[0.0%, 7.6%] | 38.3% (18/47)<br/>[25.8%, 52.6%] | **69.0%** (20/29)<br/>[50.8%, 82.7%] | **52.6%** (20/38)<br/>[37.3%, 67.5%] | **0.0%** (0/9)<br/>[0.0%, 29.9%] |
| **B3** | **AutoImmune (V0–V3 + Risk)** | **38.3%** (18/47)<br/>[25.8%, 52.6%] | **6.4%** (3/47)<br/>[2.2%, 17.2%] | **55.3%** (26/47)<br/>[41.2%, 68.6%] | **61.1%** (11/18)<br/>[38.6%, 79.7%] | **28.9%** (11/38)<br/>[17.0%, 44.8%] | **0.0%** (0/9)<br/>[0.0%, 29.9%] |

**Definitions:**
- **Auto-Apply Rate:** Proportions of candidates automatically deployed ($\frac{\text{Auto-Applied}}{N}$).
- **UDR (Unsafe Decision Rate):** Proportion of auto-applied candidates that are semantically incorrect or unsafe ($\frac{\text{Unsafe Auto-Applied}}{\text{Labelled Auto-Applied}}$).
- **Unsafe Escape Rate:** Proportion of all unsafe candidates that escape into production ($\frac{\text{Unsafe Auto-Applied}}{\text{Total Unsafe Candidates}}$).
- **FRR (False Rejection Rate):** Proportion of viable, correct candidates rejected by gates ($\frac{\text{Safe Applicable Rejected}}{\text{Safe Applicable Candidates}}$).
