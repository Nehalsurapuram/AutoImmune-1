"""tools/audit_baseline.py: read-only manifest. No Docker, no network."""
import builtins
import hashlib
import json
from pathlib import Path

from tools import audit_baseline as ab


def row(run, cid, model=None, **kw):
    base = {"run_id": run, "fault_id": "F06", "candidate_id": cid, "model": model, "diag_mode": "live",
            "patch_mode": "live", "decision": "REJECT", "approval_source": None, "deployed": False,
            "rolled_back": None}
    return {**base, **kw}


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    rows = [row("r1", "F06-live-1", "m7b"), row("r2", "F06-live-1", "m1.5b"), row("r2", "F06-live-2", "m1.5b")]
    write_jsonl(repo / "results" / "evidence.jsonl", rows)
    write_jsonl(repo / "runs" / "r1" / "evidence.jsonl", rows[:1])
    write_jsonl(repo / "runs" / "r2" / "evidence.jsonl", rows[1:])
    (repo / "runs" / "r3").mkdir(parents=True)
    (repo / "runs" / "r3" / "error.json").write_text(json.dumps(
        {"step": 4, "title": "diagnose", "type": "ProviderError",
         "error": "replay cache miss: D:\\Auto Immune\\cache\\x.json not found"}), encoding="utf-8")
    (repo / "runs" / "pytest-1").mkdir()
    cand = repo / "faults" / "F06" / "candidates"
    cand.mkdir(parents=True)
    (cand / "correct.diff").write_text("diff\n", encoding="utf-8")
    (cand / "labels.json").write_text("SECRET-LABELS", encoding="utf-8")
    (repo / "faults" / "F06" / "hidden_tests").mkdir()
    (repo / "faults" / "F06" / "hidden_tests" / "H.java").write_text("SECRET-TEST", encoding="utf-8")
    return repo


def test_sha256_file_matches_hashlib(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc" * 1000)
    assert ab.sha256_file(p) == hashlib.sha256(b"abc" * 1000).hexdigest()


def test_evidence_summary_flags_reused_ids_and_models(tmp_path):
    repo = make_repo(tmp_path)
    s = ab.evidence_summary(repo / "results" / "evidence.jsonl")
    assert s["rows"] == 3 and s["distinct_fault_candidate"] == 2 and s["rows_superseded_by_latest_row_rule"] == 1
    assert s["candidate_ids_reused_across_runs"] == {"F06-live-1": ["r1", "r2"]}
    assert s["candidate_ids_with_multiple_models"] == {"F06-live-1": ["m1.5b", "m7b"]}
    assert s["has_patch_sha256_field"] is False


def test_runs_summary_reconciles_and_strips_local_paths(tmp_path):
    repo = make_repo(tmp_path)
    runs = {r["run_id"]: r for r in ab.runs_summary(repo / "runs", repo / "results" / "evidence.jsonl")}
    assert "pytest-1" not in runs
    assert (runs["r1"]["evidence_rows"], runs["r1"]["rows_in_aggregate"]) == (1, 1)
    assert (runs["r2"]["evidence_rows"], runs["r2"]["rows_in_aggregate"]) == (2, 2)
    assert runs["r3"]["evidence_rows"] is None and runs["r3"]["error"]["step"] == 4
    assert "Auto Immune" not in runs["r3"]["error"]["message"]


def test_report_staleness_detects_mismatch(tmp_path):
    ev = tmp_path / "evidence.jsonl"
    write_jsonl(ev, [row("r1", "c1")])
    rep = tmp_path / "pilot_report.md"
    rep.write_text("- `results/evidence.jsonl` sha256 `000000000000`: 31 rows, 0 excluded", encoding="utf-8")
    s = ab.report_staleness(rep, ev)
    assert s["checked"] and s["stale"] and (s["report_rows"], s["current_rows"]) == (31, 1)
    rep.write_text(f"- `results/evidence.jsonl` sha256 `{ab.sha256_file(ev)[:12]}`: 1 rows", encoding="utf-8")
    assert ab.report_staleness(rep, ev)["stale"] is False


def test_manifest_never_opens_hidden_tests_or_labels(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    opened = []
    real_open, real_read_text, real_read_bytes = builtins.open, Path.read_text, Path.read_bytes
    real_path_open = Path.open

    def spy_open(file, *a, **k):
        opened.append(str(file))
        return real_open(file, *a, **k)

    def spy_path_open(self, *a, **k):
        opened.append(str(self))
        return real_path_open(self, *a, **k)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(Path, "open", spy_path_open)
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: (opened.append(str(self)), real_read_text(self, *a, **k))[1])
    monkeypatch.setattr(Path, "read_bytes", lambda self: (opened.append(str(self)), real_read_bytes(self))[1])
    m = ab.build_manifest(repo, with_env=False)
    text = json.dumps(m)
    assert opened and not [p for p in opened if "hidden_tests" in p or "labels.json" in p]
    assert "SECRET" not in text
    assert not [k for k in m["files_sha256"] if "hidden_tests" in k or "labels.json" in k]
    assert m["oracle_presence"] == {"hidden_tests_dirs": ["faults/F06/hidden_tests"],
                                    "labels_files": ["faults/F06/candidates/labels.json"]}
    assert "faults/F06/candidates/correct.diff" in m["files_sha256"]


def test_missing_tool_is_recorded_as_missing_not_ok():
    assert ab.run_cmd(["definitely-not-a-real-tool-xyz", "--version"])["status"] == "missing"
