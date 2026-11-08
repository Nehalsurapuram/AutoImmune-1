"""Run provenance: what code, prompts, config and environment produced a run.

    prov = collect(cfg)        # dict, written into runs/<run_id>/run.json by the orchestrator

Recorded so every evidence row can be traced (through run_id) to an exact code state:
  - git HEAD, branch, and whether the working tree had uncommitted changes (and which files);
  - code_sha256: one hash over pipeline/*.py, so a run made with uncommitted or since-lost code is detectable
    even when git cannot tell (audit finding F-24);
  - prompts_sha256 (DIAGNOSE_SYSTEM + PATCH_SYSTEM), config_sha256, the LLM endpoint and model names
    (never the API key);
  - python, OS and Docker server versions.
A value that could not be collected is null with a reason, never a guess.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROVENANCE_VERSION = 1


def _git(args: list[str], repo: Path) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def code_sha256(repo: Path = REPO) -> str:
    """SHA-256 over (relative path, bytes) of every pipeline/*.py, in sorted order. Line endings normalised to LF
    so a Windows checkout and a Linux checkout of the same commit hash the same."""
    h = hashlib.sha256()
    for p in sorted((repo / "pipeline").glob("*.py")):
        h.update(p.relative_to(repo).as_posix().encode("utf-8") + b"\0")
        h.update(p.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def prompts_sha256() -> str:
    from pipeline.providers import DIAGNOSE_SYSTEM, PATCH_SYSTEM
    return hashlib.sha256(json.dumps([DIAGNOSE_SYSTEM, PATCH_SYSTEM]).encode("utf-8")).hexdigest()


def config_sha256(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def docker_server_version() -> str | None:
    try:
        r = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], capture_output=True,
                           text=True, timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def collect(cfg: dict, repo: Path = REPO, env: dict | None = None) -> dict:
    env = os.environ if env is None else env
    porcelain = _git(["status", "--porcelain"], repo)
    dirty_files = None if porcelain is None else [ln[3:] for ln in porcelain.splitlines() if ln.strip()]
    return {
        "provenance_version": PROVENANCE_VERSION,
        "git_head": _git(["rev-parse", "HEAD"], repo),
        "git_branch": _git(["rev-parse", "--abbrev-ref", "HEAD"], repo),
        "git_dirty": None if dirty_files is None else bool(dirty_files),
        "git_dirty_files": dirty_files,
        "code_sha256": code_sha256(repo),
        "prompts_sha256": prompts_sha256(),
        "config_sha256": config_sha256(cfg),
        "llm_base_url": env.get("LLM_BASE_URL") or None,
        "llm_model": env.get("LLM_MODEL") or None,
        "python": platform.python_version(),
        "os": platform.platform(),
        "docker_server": docker_server_version(),
    }
