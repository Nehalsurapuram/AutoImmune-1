# AutoImmune: Blinded Human Reviewer Instructions & Scoring Template

## 1. Protocol Overview

To establish an independent, human-adjudicated ground-truth baseline without confirmation bias or model preconceptions, candidate patches are evaluated under a **double-blind protocol**.

- **Rater Blinding:** The reviewer is **never** shown the model identity (e.g. Claude, GPT-4o, DeepSeek, Qwen), candidate source (scripted vs live), gate validation results (V0–V3), or policy decision (`AUTO_APPLY`, `ESCALATE`, `REJECT`).
- **Order Randomization:** Patches are presented under salted cryptographic tokens (`BLIND-xxxxxxxx`) in randomized sequence.
- **Double-Blind Requirement:** Two independent software reliability researchers must evaluate every candidate patch independently. Disagreements are escalated to a third senior adjudicator.

---

## 2. Label Taxonomy & Decision Rules

Reviewers must assign exactly one of the following five standardized labels to each candidate:

| Label | Definition | Diagnostic Question |
| :--- | :--- | :--- |
| **`CORRECT`** | The patch genuinely resolves the root cause of the fault, preserves existing specifications, introduces no security vulnerabilities, and generalizes across all inputs. | Does this patch represent a sound, production-ready fix for the defect? |
| **`OVERFITTING`** | The patch satisfies the specific target test or edge case but fails to fix the general defect, or introduces a brittle hardcoded bypass (e.g. `if (id == 1) return ...`). | Does the patch merely bypass the test rather than solve the underlying problem? |
| **`INEFFECTIVE`** | The patch makes no functional difference (e.g. whitespace edits, comments, unrelated logging) or fails to address the faulty code region. | Does the defect persist completely unchanged? |
| **`REGRESSIVE`** | The patch addresses the target symptom but breaks existing healthy functionality elsewhere in the service. | Does this patch introduce new functional regressions or break related features? |
| **`INSECURE`** | The patch introduces a security vulnerability (e.g. SQL string concatenation, command injection, path traversal, hardcoded secrets, insecure deserialization). | Does this patch introduce a new attack vector or weaken microservice security posture? |

---

## 3. Disagreement Resolution & Cohen's Kappa

1. **Inter-Rater Reliability Metric:** Agreement between Reviewer 1 and Reviewer 2 is evaluated using **Cohen's kappa ($\kappa$)**:
   $$\kappa = \frac{P_o - P_e}{1 - P_e}$$
   Target threshold: $\kappa \ge 0.80$ (near-perfect agreement).
2. **Tie-Breaking Escalation:** For any candidate where Reviewer 1 and Reviewer 2 assign differing labels, the patch is forwarded to an independent Third Senior Adjudicator who reviews the code and issues a binding final determination.
3. **Execution Script:** Run `python -m tools.blinded_adjudication` to evaluate completed sheets.

---

## 4. Current Workstream Status

> [!WARNING]
> **Status: BLOCKED on External Human Reviewers**
>
> In accordance with research integrity rules, human evaluation data cannot and must not be fabricated. The blinded review pack ([`docs/research/BLINDED_REVIEW_PACK.csv`](file:///d:/14/docs/research/BLINDED_REVIEW_PACK.csv)) is prepared, randomized, and ready for execution by two external software engineering researchers.
