"""tools/blinded_adjudication.py: Prepares and scores blinded two-reviewer human adjudication.

Generates:
1. Blinded candidate presentation sheets (strips model names, gates, and decisions).
2. Independent reviewer packages for Reviewer A and Reviewer B with randomized order.
3. Candidate context files for full source/diff inspection without oracle leakage.
4. Inter-rater agreement computation (Cohen's kappa) and disagreement reports.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from tools.cluster_statistics import cohen_kappa, KappaResult

REPO_ROOT = Path(__file__).resolve().parent.parent


def generate_blinded_packages(
    repo: Path = REPO_ROOT,
    handoff_dir: Path | None = None,
) -> dict:
    """Generates complete reviewer handoff folder with blinded packs and context."""
    target_dir = handoff_dir or (repo / "docs" / "research" / "reviewer_handoff")
    context_dir = target_dir / "candidates_context"
    target_dir.mkdir(parents=True, exist_ok=True)
    context_dir.mkdir(parents=True, exist_ok=True)

    candidates = []
    for diff_path in sorted((repo / "faults").glob("F*/candidates/*.diff")):
        fault_id = diff_path.parent.parent.name
        fault_json_path = diff_path.parent.parent / "fault.json"
        desc = "Software defect in order-service microservice"
        if fault_json_path.exists():
            try:
                data = json.loads(fault_json_path.read_text(encoding="utf-8"))
                desc = data.get("description", desc)
            except Exception:
                pass

        diff_text = diff_path.read_text(encoding="utf-8")
        diff_hash = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()[:12]
        
        # Deterministic cryptographic token
        token_hash = hashlib.sha256(f"blind_salt:{fault_id}:{diff_hash}".encode("utf-8")).hexdigest()[:8]
        blind_id = f"BLIND-{token_hash.upper()}"

        candidates.append({
            "blind_id": blind_id,
            "fault_id": fault_id,
            "defect_description": desc,
            "diff_sha12": diff_hash,
            "full_diff": diff_text,
            "source_path": str(diff_path.relative_to(repo)),
        })

    # Sort master list by blind_id
    candidates.sort(key=lambda c: c["blind_id"])

    # Write context file for each candidate
    for c in candidates:
        ctx_file = context_dir / f"{c['blind_id']}.md"
        ctx_content = f"""# Candidate Patch Context: {c['blind_id']}

## Fault Context
- **Fault Scenario:** {c['fault_id']}
- **Defect Description:** {c['defect_description']}

## Proposed Candidate Unified Diff
```diff
{c['full_diff']}
```

## Reviewer Inspection Guidelines
1. Inspect whether this patch genuinely resolves the stated defect.
2. Check for regressions or unhandled edge cases in the surrounding method.
3. Check for security vulnerabilities (e.g. injection, unsanitized inputs, traversal, exec).
4. Assign your verdict in the scoring sheet.
"""
        with open(ctx_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(ctx_content)

    # Master pack
    master_csv = repo / "docs" / "research" / "BLINDED_REVIEW_PACK.csv"
    with open(master_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "blind_id", "fault_id", "defect_description", "diff_sha12",
                "fixes_defect", "introduces_regression", "introduces_security_issue",
                "preserves_intended_behavior", "deployment_verdict", "reviewer_confidence", "reviewer_notes"
            ]
        )
        writer.writeheader()
        for c in candidates:
            writer.writerow({
                "blind_id": c["blind_id"],
                "fault_id": c["fault_id"],
                "defect_description": c["defect_description"],
                "diff_sha12": c["diff_sha12"],
                "fixes_defect": "",
                "introduces_regression": "",
                "introduces_security_issue": "",
                "preserves_intended_behavior": "",
                "deployment_verdict": "",
                "reviewer_confidence": "",
                "reviewer_notes": "",
            })

    # Reviewer A: Random permutation with seed 4242
    rnd_a = random.Random(4242)
    cands_a = list(candidates)
    rnd_a.shuffle(cands_a)
    sheet_a = target_dir / "REVIEWER_A_SCORING_SHEET.csv"
    _write_sheet(sheet_a, cands_a)

    # Reviewer B: Random permutation with seed 9876
    rnd_b = random.Random(9876)
    cands_b = list(candidates)
    rnd_b.shuffle(cands_b)
    sheet_b = target_dir / "REVIEWER_B_SCORING_SHEET.csv"
    _write_sheet(sheet_b, cands_b)

    # Write Reviewer Instructions
    instructions_file = target_dir / "REVIEWER_INSTRUCTIONS.md"
    _write_instructions(instructions_file)

    return {
        "candidate_count": len(candidates),
        "reviewer_a_sheet": sheet_a,
        "reviewer_b_sheet": sheet_b,
        "context_dir": context_dir,
    }


def _write_sheet(path: Path, cands: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "presentation_order", "blind_id", "fault_id", "defect_description",
                "fixes_defect", "introduces_regression", "introduces_security_issue",
                "preserves_intended_behavior", "deployment_verdict", "reviewer_confidence", "reviewer_notes"
            ]
        )
        writer.writeheader()
        for idx, c in enumerate(cands, 1):
            writer.writerow({
                "presentation_order": idx,
                "blind_id": c["blind_id"],
                "fault_id": c["fault_id"],
                "defect_description": c["defect_description"],
                "fixes_defect": "",
                "introduces_regression": "",
                "introduces_security_issue": "",
                "preserves_intended_behavior": "",
                "deployment_verdict": "",
                "reviewer_confidence": "",
                "reviewer_notes": "",
            })


def _write_instructions(path: Path) -> None:
    text = """# Independent Human Software Engineer Review Rubric & Instructions

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
"""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def evaluate_human_adjudication(
    reviewer_a_csv: Path,
    reviewer_b_csv: Path,
) -> tuple[KappaResult, float, list[dict]]:
    """Evaluates two completed reviewer CSVs, computing Cohen's kappa, raw agreement, and disagreements."""
    def load_labels(path: Path) -> dict[str, dict]:
        records = {}
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                bid = r["blind_id"].strip()
                verdict = r.get("deployment_verdict", "").strip().upper()
                records[bid] = {
                    "verdict": verdict,
                    "fixes": r.get("fixes_defect", "").strip().upper(),
                    "regression": r.get("introduces_regression", "").strip().upper(),
                    "security": r.get("introduces_security_issue", "").strip().upper(),
                }
        return records

    rec_a = load_labels(reviewer_a_csv)
    rec_b = load_labels(reviewer_b_csv)

    common_ids = sorted(set(rec_a.keys()) & set(rec_b.keys()))
    if not common_ids:
        raise ValueError("No common blind_ids found between reviewer sheets")

    # Check for empty verdicts
    unrated_a = [bid for bid in common_ids if not rec_a[bid]["verdict"]]
    unrated_b = [bid for bid in common_ids if not rec_b[bid]["verdict"]]
    if unrated_a or unrated_b:
        raise ValueError(f"Incomplete reviews: Reviewer A unrated {len(unrated_a)}, Reviewer B unrated {len(unrated_b)}")

    v_a = [rec_a[bid]["verdict"] for bid in common_ids]
    v_b = [rec_b[bid]["verdict"] for bid in common_ids]

    kappa_res = cohen_kappa(v_a, v_b)

    agree_count = sum(1 for a, b in zip(v_a, v_b) if a == b)
    raw_agreement = agree_count / len(common_ids)

    disagreements = []
    for bid in common_ids:
        if rec_a[bid]["verdict"] != rec_b[bid]["verdict"]:
            disagreements.append({
                "blind_id": bid,
                "reviewer_a": rec_a[bid]["verdict"],
                "reviewer_b": rec_b[bid]["verdict"],
                "details_a": rec_a[bid],
                "details_b": rec_b[bid],
            })

    return kappa_res, raw_agreement, disagreements


if __name__ == "__main__":
    res = generate_blinded_packages()
    print(f"Generated blinded packages for {res['candidate_count']} candidates at {res['reviewer_a_sheet'].parent}")
