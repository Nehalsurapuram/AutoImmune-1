"""Build docs/claim_ledger.csv from the saved claim-audit results.

Input:  docs/audit/claim_audit.json  (every factual claim extracted from the submission documents, each checked
        against raw evidence by an independent checker; every flagged claim re-checked by two more checkers).
Output: docs/claim_ledger.csv with one row per claim: document, location, claim, audit verdict, resolution,
        evidence files named by the checker that exist in the repository, and their SHA-256 (first 16 hex).

Resolutions:
  supported            the checker found the claim supported by the cited evidence
  flag_refuted         flagged, but both re-checkers found the claim correct
  corrected            flagged and confirmed (or disputed and accepted); the document was edited
  kept                 flagged but kept after review (reason in the resolution note)
  pending              not re-checked

Usage: python tools/claim_ledger.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "docs" / "audit" / "claim_audit.json"
OUT = ROOT / "docs" / "claim_ledger.csv"
DOCS = {"README": "README.md", "REPORT": "docs/PROJECT_REPORT.md", "DEMO": "docs/DEMO.md",
        "SUBMISSION": "SUBMISSION.md", "ACCEPTANCE": "docs/audit/acceptance.json", "PROTOCOL": "docs/protocol_v1.md"}
PATH_RE = re.compile(r"(?:runs|results|pipeline|tools|tests|faults|config|docs|app|cache)/[A-Za-z0-9_.\-/<>*]+")


def evidence_files(text: str, limit: int = 4) -> list[str]:
    found: list[str] = []
    for m in PATH_RE.findall(text or ""):
        m = m.rstrip(".,;:)'\"")
        if any(ch in m for ch in "<>*"):
            continue
        p = ROOT / m
        if p.is_file() and m not in found:
            found.append(m)
        if len(found) >= limit:
            break
    return found


def sha16(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()[:16]


def resolution(item: dict, resolutions: dict) -> tuple[str, str]:
    if item.get("verdict") == "supported":
        return "supported", ""
    st = item.get("_status")
    note = resolutions.get(item.get("_id"), "")
    if st == "refuted":
        return "flag_refuted", "both re-checkers found the claim correct"
    if st == "pending":
        return "pending", ""
    if note.startswith("kept"):
        return "kept", note
    return "corrected", note or "document edited after the audit (see git log)"


def main() -> None:
    data = json.loads(AUDIT.read_text(encoding="utf-8"))
    resolutions = data.get("resolutions", {})
    rows = []
    for i, (doc, item) in enumerate(data["claims"], 1):
        res, note = resolution(item, resolutions)
        files = evidence_files(item.get("evidence", ""))
        rows.append({
            "claim_id": f"C{i:03d}", "document": DOCS.get(doc, doc), "location": item.get("location", ""),
            "claim": item.get("quote", ""), "audit_verdict": item.get("verdict", ""),
            "recheck": item.get("_status", "") if item.get("verdict") != "supported" else "",
            "resolution": res, "resolution_note": note,
            "evidence_files": ";".join(files), "evidence_sha256_16": ";".join(sha16(f) for f in files),
        })
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["resolution"]] = counts.get(r["resolution"], 0) + 1
    print(f"{len(rows)} claims -> {OUT.relative_to(ROOT)}: {counts}")


if __name__ == "__main__":
    main()
