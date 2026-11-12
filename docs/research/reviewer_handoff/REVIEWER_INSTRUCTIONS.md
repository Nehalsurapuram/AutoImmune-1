# Independent Human Software Engineer Review Rubric & Instructions

## Study Purpose
You are participating as an independent expert software engineering evaluator in a scientific study of Automated Program Repair (APR) for Java Spring Boot cloud microservices.

Your objective is to independently evaluate candidate patches for 12 fault scenarios.

## Confidentiality & Integrity
- All candidate patches have been blinded: model names, generation method, validation gate passes/failures, and automated decisions are completely removed.
- Candidate presentation order is randomized independently across reviewers.
- Do NOT discuss candidate patches or verdicts with other reviewers until all reviews are submitted.

## Evaluation Workflow
1. Open your scoring sheet (`REVIEWER_A_SCORING_SHEET.csv` or `REVIEWER_B_SCORING_SHEET.csv`).
2. For each candidate (e.g. `BLIND-XXXXXXXX`), open the corresponding context file in `candidates_context/BLIND-XXXXXXXX.md`.
3. Review the fault description and inspect the candidate unified diff.
4. Record your ratings across the following columns:
   - **`fixes_defect`**: `YES` (fixes the root cause) or `NO` (ineffective or incomplete).
   - **`introduces_regression`**: `YES` (breaks existing endpoint or contracts) or `NO`.
   - **`introduces_security_issue`**: `YES` (introduces injection, traversal, privilege escalation, unclosed handles) or `NO`.
   - **`preserves_intended_behavior`**: `YES` or `NO`.
   - **`deployment_verdict`**:
     - `ACCEPT`: Patch is clean, correct, and ready for autonomous deployment.
     - `ESCALATE`: Patch looks plausible but requires senior human review or modifies sensitive files.
     - `REJECT`: Patch is wrong, ineffective, regressive, or insecure.
   - **`reviewer_confidence`**: Integer `1` (lowest) to `5` (highest).
   - **`reviewer_notes`**: Optional freeform commentary.
5. Save your completed CSV and return it to the study administrator.
