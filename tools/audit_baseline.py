"""Read-only baseline manifest for the reproducibility audit (ticket AI-R0-001).

    python tools/audit_baseline.py --out docs/audit/baseline_manifest.json [--zip PATH_TO_ARCHIVE]

Records, without changing anything in the repository:
  - git HEAD, branch and the working-tree / index changes;
  - SHA-256 of the source archive (if given), code, config, fault assets, evidence, reports and cache files;
  - toolchain versions (a missing tool is recorded as "missing", never as a pass);
  - evidence row counts, duplicate candidate ids and candidate ids reused across runs;
  - per-run artifact status (evidence rows, error.json step and message);
  - whether results/pilot_report.md was generated from the current results/evidence.jsonl.

Integrity: hidden_tests/ directories and labels.json files are never opened or hashed. Only their presence
is counted, so the manifest itself cannot leak oracle content. Paths are repo-relative; the archive is
recorded by file name only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1
FORBIDDEN_PARTS = ("hidden_tests", "labels.json")
WIN_DIR = re.compile(r"[A-Za-z]:\\(?:[^\\\n]*\\)+")   # local absolute directory prefix (may contain spaces)
HASHED_GLOBS = (
    "AGENTS.md", "README.md", "requirements.txt", "pytest.ini", "analyse.py", ".gitignore", ".gitattributes",
    "config/*.yaml", "pipeline/*.py", "tools/*.py", "faults/**/*", "app/pom.xml", "app/Dockerfile",
    "results/*", "cache/*.json",
)
TOOLS = {
    "git": ["git", "--version"],
    "java": ["java", "-version"],
    "mvn": ["mvn", "-v"],
    "docker_client": ["docker", "version", "--format", "{{.Client.Version}}"],
    "docker_server": ["docker", "version", "--format", "{{.Server.Version}}"],
    "semgrep": ["semgrep", "--version"],
    "ollama": ["ollama", "--version"],
}


# --------------------------------------------------------------------------- helpers

def is_forbidden(path: Path) -> bool:
    return any(part in FORBIDDEN_PARTS for part in path.parts)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cmd(argv: list[str], cwd: Path | None = None, timeout: float = 20) -> dict:
    """{"status": ok|error|missing|timeout, "output": first non-empty line of stdout/stderr}."""
    try:
        r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {"status": "missing", "output": None}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "output": None}
    text = (r.stdout or "") + (r.stderr or "")
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return {"status": "ok" if r.returncode == 0 else "error", "output": first[:300]}


# --------------------------------------------------------------------------- sections

def git_info(repo: Path) -> dict:
    head = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo)
    branch = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    try:
        porcelain = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True,
                                   text=True, timeout=20).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        porcelain = ""
    changes = [{"xy": ln[:2], "path": ln[3:]} for ln in porcelain.splitlines() if ln.strip()]
    try:
        listed = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True, text=True, timeout=20).stdout
        forbidden = sorted(p for p in listed.splitlines() if is_forbidden(Path(p)))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        forbidden = None   # unknown, not "none tracked"
    return {
        "head": head["output"] if head["status"] == "ok" else None,
        "branch": branch["output"] if branch["status"] == "ok" else None,
        "dirty": bool(changes),
        "changes": changes,
        "tracked_hidden_or_label_files": forbidden,
    }


def environment() -> dict:
    return {
        "os": platform.platform(),
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "tools": {name: run_cmd(argv) for name, argv in TOOLS.items()},
    }


def file_hashes(repo: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for pattern in HASHED_GLOBS:
        for p in sorted(repo.glob(pattern)):
            if p.is_file() and not is_forbidden(p.relative_to(repo)) and "__pycache__" not in p.parts:
                out[p.relative_to(repo).as_posix()] = sha256_file(p)
    return dict(sorted(out.items()))


def oracle_presence(repo: Path) -> dict:
    """Counts only. Nothing under these paths is opened."""
    faults = repo / "faults"
    return {
        "hidden_tests_dirs": sorted(p.relative_to(repo).as_posix() for p in faults.glob("*/hidden_tests") if p.is_dir()),
        "labels_files": sorted(p.relative_to(repo).as_posix() for p in faults.glob("*/candidates/labels.json")),
    }


def evidence_summary(path: Path) -> dict:
    rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    per_key = Counter((r.get("fault_id"), r.get("candidate_id")) for r in rows)
    runs_per_id: dict[str, set] = defaultdict(set)
    models_per_id: dict[str, set] = defaultdict(set)
    for r in rows:
        runs_per_id[r.get("candidate_id")].add(r.get("run_id"))
        models_per_id[r.get("candidate_id")].add(r.get("model"))
    reused = {cid: sorted(runs) for cid, runs in sorted(runs_per_id.items()) if len(runs) > 1}
    multi_model = {cid: sorted(m or "null" for m in ms) for cid, ms in sorted(models_per_id.items()) if len(ms) > 1}
    return {
        "sha256": sha256_file(path),
        "rows": len(rows),
        "distinct_fault_candidate": len(per_key),
        "rows_superseded_by_latest_row_rule": len(rows) - len(per_key),
        "candidate_ids_reused_across_runs": reused,
        "candidate_ids_with_multiple_models": multi_model,
        "has_patch_sha256_field": any("patch_sha256" in r for r in rows),
        "modes": {f"{d}/{p}": n for (d, p), n in sorted(Counter((r.get("diag_mode"), r.get("patch_mode"))
                                                                for r in rows).items(), key=str)},
        "decisions": dict(sorted(Counter(r.get("decision") for r in rows).items(), key=str)),
        "approval_sources": dict(sorted(Counter(r.get("approval_source") for r in rows).items(), key=str)),
        "deployed_rows": sum(1 for r in rows if r.get("deployed")),
        "rolled_back_rows": sum(1 for r in rows if r.get("rolled_back")),
        "run_ids": sorted({r.get("run_id") for r in rows}),
    }


def runs_summary(runs_dir: Path, aggregate: Path | None) -> list[dict]:
    agg_lines: set[str] = set()
    if aggregate and aggregate.exists():
        agg_lines = {ln for ln in aggregate.read_text(encoding="utf-8").splitlines() if ln.strip()}
    out = []
    for d in sorted(p for p in runs_dir.iterdir() if p.is_dir()) if runs_dir.exists() else []:
        if d.name.startswith("pytest-"):
            continue
        entry: dict = {"run_id": d.name, "files": sorted(p.name for p in d.iterdir() if p.is_file())}
        ev = d / "evidence.jsonl"
        if ev.exists():
            lines = [ln for ln in ev.read_text(encoding="utf-8").splitlines() if ln.strip()]
            entry["evidence_rows"] = len(lines)
            entry["rows_in_aggregate"] = sum(ln in agg_lines for ln in lines)
        else:
            entry["evidence_rows"] = None
        err = d / "error.json"
        if err.exists():
            try:
                e = json.loads(err.read_text(encoding="utf-8"))
                msg = next((ln for ln in str(e.get("error", "")).splitlines() if ln.strip()), "")
                entry["error"] = {"step": e.get("step"), "title": e.get("title"), "type": e.get("type"),
                                  "message": WIN_DIR.sub(lambda _: "<path>/", msg)[:200]}
            except (json.JSONDecodeError, OSError) as exc:
                entry["error"] = {"unreadable": str(exc)}
        run_json = d / "run.json"
        if run_json.exists():
            try:
                rj = json.loads(run_json.read_text(encoding="utf-8"))
                entry["run_json_keys"] = sorted(rj.keys())
            except json.JSONDecodeError:
                entry["run_json_keys"] = None
        out.append(entry)
    return out


def report_staleness(report: Path, evidence: Path) -> dict:
    """pilot_report.md prints the first 12 hex chars of the evidence sha256 it was generated from."""
    if not report.exists() or not evidence.exists():
        return {"checked": False}
    m = re.search(r"evidence\.jsonl` sha256 `([0-9a-f]{6,64})`: (\d+) rows", report.read_text(encoding="utf-8"))
    actual = sha256_file(evidence)
    if not m:
        return {"checked": False, "reason": "no evidence hash line found in report"}
    rows_now = sum(1 for ln in evidence.read_text(encoding="utf-8").splitlines() if ln.strip())
    return {"checked": True, "report_evidence_sha_prefix": m.group(1), "report_rows": int(m.group(2)),
            "current_evidence_sha_prefix": actual[:len(m.group(1))], "current_rows": rows_now,
            "stale": not actual.startswith(m.group(1))}


# --------------------------------------------------------------------------- main

def build_manifest(repo: Path = REPO, archive: Path | None = None, with_env: bool = True) -> dict:
    results = repo / "results"
    evidence = results / "evidence.jsonl"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "tools/audit_baseline.py",
        "git": git_info(repo),
        "archive": ({"name": archive.name, "bytes": archive.stat().st_size, "sha256": sha256_file(archive)}
                    if archive else None),
        "environment": environment() if with_env else None,
        "oracle_presence": oracle_presence(repo),
        "files_sha256": file_hashes(repo),
        "evidence": {"results/evidence.jsonl": evidence_summary(evidence)} if evidence.exists() else {},
        "pilot_report_vs_evidence": report_staleness(results / "pilot_report.md", evidence),
        "runs": runs_summary(repo / "runs", evidence),
    }
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, help="write JSON here (default: stdout)")
    ap.add_argument("--zip", type=Path, help="source archive to hash (recorded by file name only)")
    ap.add_argument("--repo", type=Path, default=REPO)
    args = ap.parse_args(argv)
    manifest = build_manifest(args.repo.resolve(), args.zip)
    text = json.dumps(manifest, indent=2, sort_keys=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
