import csv
import tempfile
from pathlib import Path
import pytest

from tools.blinded_adjudication import (
    generate_blinded_packages,
    evaluate_human_adjudication,
)


def test_generate_blinded_packages():
    with tempfile.TemporaryDirectory() as tmp:
        res = generate_blinded_packages(handoff_dir=Path(tmp))
        assert res["candidate_count"] == 61
        assert res["reviewer_a_sheet"].exists()
        assert res["reviewer_b_sheet"].exists()
        assert (Path(tmp) / "REVIEWER_INSTRUCTIONS.md").exists()
        ctx_files = list(res["context_dir"].glob("*.md"))
        assert len(ctx_files) == 61


def test_evaluate_adjudication_perfect_agreement():
    with tempfile.TemporaryDirectory() as tmp:
        path_a = Path(tmp) / "sheet_a.csv"
        path_b = Path(tmp) / "sheet_b.csv"

        rows = [
            {"blind_id": f"BLIND-{i:03d}", "deployment_verdict": "ACCEPT", "fixes_defect": "YES", "introduces_regression": "NO", "introduces_security_issue": "NO"}
            for i in range(10)
        ]

        def write(p, data):
            with open(p, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["blind_id", "deployment_verdict", "fixes_defect", "introduces_regression", "introduces_security_issue"])
                w.writeheader()
                w.writerows(data)

        write(path_a, rows)
        write(path_b, rows)

        kappa_res, raw_agree, disagreements = evaluate_human_adjudication(path_a, path_b)
        assert raw_agree == 1.0
        assert len(disagreements) == 0


def test_evaluate_adjudication_with_disagreements():
    with tempfile.TemporaryDirectory() as tmp:
        path_a = Path(tmp) / "sheet_a.csv"
        path_b = Path(tmp) / "sheet_b.csv"

        rows_a = [
            {"blind_id": "BLIND-001", "deployment_verdict": "ACCEPT"},
            {"blind_id": "BLIND-002", "deployment_verdict": "REJECT"},
            {"blind_id": "BLIND-003", "deployment_verdict": "ESCALATE"},
            {"blind_id": "BLIND-004", "deployment_verdict": "ACCEPT"},
        ]
        rows_b = [
            {"blind_id": "BLIND-001", "deployment_verdict": "ACCEPT"},
            {"blind_id": "BLIND-002", "deployment_verdict": "ACCEPT"},  # disagreement
            {"blind_id": "BLIND-003", "deployment_verdict": "ESCALATE"},
            {"blind_id": "BLIND-004", "deployment_verdict": "REJECT"},  # disagreement
        ]

        def write(p, data):
            with open(p, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["blind_id", "deployment_verdict"])
                w.writeheader()
                w.writerows(data)

        write(path_a, rows_a)
        write(path_b, rows_b)

        kappa_res, raw_agree, disagreements = evaluate_human_adjudication(path_a, path_b)
        assert raw_agree == 0.5
        assert len(disagreements) == 2
        assert {d["blind_id"] for d in disagreements} == {"BLIND-002", "BLIND-004"}


def test_evaluate_adjudication_incomplete_raises():
    with tempfile.TemporaryDirectory() as tmp:
        path_a = Path(tmp) / "sheet_a.csv"
        path_b = Path(tmp) / "sheet_b.csv"

        rows_a = [{"blind_id": "BLIND-001", "deployment_verdict": ""}]
        rows_b = [{"blind_id": "BLIND-001", "deployment_verdict": "ACCEPT"}]

        def write(p, data):
            with open(p, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["blind_id", "deployment_verdict"])
                w.writeheader()
                w.writerows(data)

        write(path_a, rows_a)
        write(path_b, rows_b)

        with pytest.raises(ValueError, match="Incomplete reviews"):
            evaluate_human_adjudication(path_a, path_b)
