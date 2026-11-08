"""Evidence: one JSON row per candidate, appended to results/evidence.jsonl.

    row = build_row(...); append_row(row)

Rows are validated against EVIDENCE_SCHEMA before writing; an invalid row raises and nothing is written.
additionalProperties is false, so no label or other unexpected field can enter the file.
candidate_kind is what a scripted candidate was built as (its file name); it is null for live/replay patches.
Ground-truth labels (labels.json) and hidden-test results are never part of a row.
deployed / rolled_back / awaiting_review / recovery_s are null until deploy.py has acted on the candidate;
awaiting_review means the patch was set aside for human review (ESCALATE) instead of being deployed.
("staged" exists only in labels.json: a candidate planted for a demo, e.g. slow.diff.)
approval_source says who answered approve_cli: "human_cli" (a person typed it at the prompt),
"human_relayed" (a person decided elsewhere, e.g. in an assistant's question box, and a tool relayed the
answer) or "scripted_test" (a script supplied the answer); null when no approval was asked.
Reports keep the three apart and must never count scripted_test approvals as human ones.
invalid is "observer_suspended" when the health window could not be trusted (host was frozen); analysis
excludes such rows.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

REPO = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = REPO / "results" / "evidence.jsonl"
SEVERITY_ORDER = ["INFO", "LOW", "WARNING", "MEDIUM", "ERROR", "HIGH", "CRITICAL"]

_GATE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "seconds"],
    "properties": {
        "status": {"enum": ["pass", "fail", "error", "timeout", "not_run"]},
        "seconds": {"type": "number", "minimum": 0},
    },
}
_MODES = {"enum": ["rule", "scripted", "replay", "live"]}
_OPT_BOOL = {"type": ["boolean", "null"]}

EVIDENCE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "AutoImmune evidence row (one per candidate)",
    "type": "object",
    "additionalProperties": False,
    "required": ["run_id", "fault_id", "candidate_id", "candidate_kind", "diag_mode", "patch_mode",
                 "oracle_localisation", "v0", "v1", "v2", "v3", "new_findings", "diff_lines", "files_touched",
                 "tier", "decision", "reasons", "deployed", "rolled_back", "awaiting_review", "recovery_s",
                 "approval_source", "invalid", "timestamp",
                 # Phase 3 additions (nullable for backward compatibility with scripted rows)
                 "diag_samples", "samples_disagree", "top1_hit", "top3_hit", "model", "llm_attempts", "apply_error",
                 "schema_version", "patch_sha256"],
    "properties": {
        "run_id": {"type": "string", "minLength": 1},
        "fault_id": {"type": "string", "pattern": "^F[0-9]{2}$"},
        "candidate_id": {"type": "string", "minLength": 1},
        "candidate_kind": {"type": ["string", "null"]},
        "diag_mode": _MODES,
        "patch_mode": _MODES,
        "oracle_localisation": {"type": "boolean"},
        "v0": _GATE, "v1": _GATE, "v2": _GATE, "v3": _GATE,
        "new_findings": {
            "type": "object",
            "additionalProperties": False,
            "required": ["count", "max_severity"],
            "properties": {
                "count": {"type": ["integer", "null"], "minimum": 0},     # null: V3 did not produce findings
                "max_severity": {"type": ["string", "null"]},
            },
        },
        "diff_lines": {"type": "integer", "minimum": 0},
        "files_touched": {"type": "array", "items": {"type": "string"}},
        "tier": {"enum": ["low", "medium", "high"]},
        "decision": {"enum": ["AUTO_APPLY", "ESCALATE", "REJECT"]},
        "reasons": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
        "deployed": _OPT_BOOL,
        "rolled_back": _OPT_BOOL,
        "awaiting_review": _OPT_BOOL,
        "recovery_s": {"type": ["number", "null"], "minimum": 0},
        "approval_source": {"enum": ["human_cli", "human_relayed", "scripted_test", None]},
        "invalid": {"enum": ["observer_suspended", None]},
        "timestamp": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"},
        # Phase 3 additions
        # diag_samples: number of diagnosis samples requested (null = rule/scripted/pre-Phase-3 rows)
        "diag_samples": {"type": ["integer", "null"], "minimum": 1},
        # samples_disagree: True if rank-1 files differed across samples; null if 1 sample or not LLM mode
        "samples_disagree": {"type": ["boolean", "null"]},
        # top1_hit/top3_hit: evaluator-side comparison vs fault.json diagnosed_file
        # null when oracle_localisation=True (answer was copied from fault.json itself)
        "top1_hit": {"type": ["boolean", "null"]},
        "top3_hit": {"type": ["boolean", "null"]},
        # model: LLM model string (null for rule/scripted)
        "model": {"type": ["string", "null"]},
        # llm_attempts: number of LLM HTTP attempts for this diagnosis (null for rule/scripted)
        "llm_attempts": {"type": ["integer", "null"], "minimum": 1},
        # apply_error: first non-null patch apply_error (null if patch applied cleanly or not checked)
        "apply_error": {"type": ["string", "null"]},
        # S0 additions (audit F-05/F-06). Rows written before schema_version 2 lack both fields.
        # schema_version: 2 from S0 on. patch_sha256: SHA-256 of the candidate diff text (UTF-8, as drafted),
        # so the same id with different content, or the same content under different ids, is detectable.
        "schema_version": {"const": 2},
        "patch_sha256": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"},
    },
}
SCHEMA_VERSION = 2


class InvalidEvidenceRow(ValueError):
    pass


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def max_severity(findings: list[dict]) -> str | None:
    sev = [str(f.get("severity", "")).upper() for f in findings]
    ranked = [s for s in SEVERITY_ORDER if s in sev]
    return ranked[-1] if ranked else (sev[0] if sev else None)


def build_row(*, run_id: str, fault_id: str, gates: dict, diagnosis, patch, patch_meta: dict, decision,
              deployed: bool | None = None, rolled_back: bool | None = None, awaiting_review: bool | None = None,
              recovery_s: float | None = None, approval: dict | None = None, invalid: str | None = None,
              timestamp: str | None = None,
              # Phase 3 additions (all nullable; None is the correct default for pre-Phase-3 rows)
              diag_samples: int | None = None, samples_disagree: bool | None = None,
              top1_hit: bool | None = None, top3_hit: bool | None = None,
              model: str | None = None, llm_attempts: int | None = None,
              apply_error: str | None = None) -> dict:
    g = gates.get("gates", gates)
    findings = (g.get("V3") or {}).get("new_findings")
    d = decision.to_dict() if hasattr(decision, "to_dict") else dict(decision)
    return {
        "run_id": run_id,
        "fault_id": fault_id,
        "candidate_id": _get(patch, "candidate_id"),
        "candidate_kind": _get(patch, "candidate_kind"),
        "diag_mode": _get(diagnosis, "provider_mode"),
        "patch_mode": _get(patch, "provider_mode"),
        "oracle_localisation": bool(_get(diagnosis, "oracle_localisation", False)),
        **{k.lower(): {"status": g[k]["status"], "seconds": g[k]["seconds"]} for k in ("V0", "V1", "V2", "V3")},
        "new_findings": {"count": None if findings is None else len(findings),
                         "max_severity": max_severity(findings or [])},
        "diff_lines": patch_meta["diff_lines"],
        "files_touched": list(patch_meta["files_touched"]),
        "tier": d["tier"],
        "decision": d["decision"],
        "reasons": list(d["reasons"]),
        "deployed": deployed,
        "rolled_back": rolled_back,
        "awaiting_review": awaiting_review,
        "recovery_s": recovery_s,
        "approval_source": approval.get("approval_source") if approval else None,
        "invalid": invalid,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # Phase 3 additions
        "diag_samples": diag_samples,
        "samples_disagree": samples_disagree,
        "top1_hit": top1_hit,
        "top3_hit": top3_hit,
        "model": model,
        "llm_attempts": llm_attempts,
        "apply_error": apply_error,
        "schema_version": SCHEMA_VERSION,
        "patch_sha256": patch_sha256(_get(patch, "diff")),
    }


def patch_sha256(diff: str | None) -> str | None:
    return None if diff is None else hashlib.sha256(diff.encode("utf-8")).hexdigest()


def validate_row(row: dict) -> None:
    try:
        jsonschema.validate(row, EVIDENCE_SCHEMA)
    except jsonschema.ValidationError as e:
        where = "/".join(str(p) for p in e.absolute_path) or "(row)"
        raise InvalidEvidenceRow(f"evidence row refused at {where}: {e.message}") from None


def append_row(row: dict, path: Path = EVIDENCE_PATH) -> None:
    validate_row(row)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
