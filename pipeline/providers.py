"""Provider interface: the only place a model may be used (diagnose and draft_patches).

Modes
-----
rule      diagnose only. Top application stack frame of the incident; for incidents without a stack
          trace (probe mismatch, health DOWN) the fault's diagnosed_file from faults/<id>/fault.json,
          i.e. oracle localisation. Never an LLM result.
scripted  draft_patches only. Patches read from faults/<id>/candidates/*.diff. Never an LLM result.
replay    diagnose and draft_patches from cache/, keyed by sha256(CACHE_KEY_VERSION, provider, model, prompt,
          temperature, sample index). No network. A missing entry is an error; an entry recorded under an older
          key scheme (version 1 had no version in the key and no cache_key_version field) is reported as a
          version mismatch, not as a bare miss. Old entries are never rewritten: re-record them with mode=live.
live      diagnose and draft_patches via an OpenAI-compatible /chat/completions endpoint configured by
          LLM_BASE_URL, LLM_MODEL, LLM_API_KEY (Ollama or a hosted API). Every response is saved to cache/
          with a cache_key_version field.

Each result carries provider_mode, so diag_mode and patch_mode are recorded separately by the caller.
Every patch is checked with `git apply --check` against a temp copy of app/ with the fault injected.

Raw-output audit trail (live/replay only)
-----------------------------------------
Every attempt record holds cache_key and raw_sha256 (SHA-256 of the full, unmodified response text; None
when the transport failed). Each LLM Patch carries raw_output_sha256 (the response it came from) and a
format_status:
  raw_valid   the diff as drafted passes validate_diff_structure(); it is used unchanged.
  normalized  it failed, and normalize_diff() (NORMALIZER_VERSION) produced a diff that passes. Patch.diff is
              the normalized text, Patch.raw_diff keeps the original, normalizer_rules says which rules fired.
  invalid     it failed and normalization did not fix it. Patch.diff stays exactly as drafted.
raw_diff_sha256 and diff_sha256 (of the text actually apply-checked) let analysis report raw-valid and
normalized-valid rates separately. Normalization is deterministic and never calls the model; there is no
repair loop. Scripted patches are not LLM output and keep format_status None.

Integrity: this module never reads faults/<id>/hidden_tests/ or labels.json, and refuses source files
from those paths. candidate_kind (scripted only) is for records and analysis, never for the decision engine.

Incident contract (produced by detector.py):
    {"kind": "exception" | "probe_mismatch" | "health_down" | ..., "fault_id": "F01",
     "stack_trace": "...", "endpoint": "...", "status": 500, "expected": ..., "actual": ..., ...}
fault_id is used for rule-mode fallback and is stripped before any prompt is built.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import jsonschema
import requests

log = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[1]
APP_PACKAGE = "com.autoimmune."
JAVA_ROOT = "app/src/main/java/"
MAX_RETRIES = 2                      # retries after the first attempt
HTTP_TIMEOUT_S = 180
FORBIDDEN_PARTS = ("hidden_tests", "labels.json")
CACHE_KEY_VERSION = 2                # 1 = original scheme, without a version in the key material
NORMALIZER_VERSION = 1               # bump whenever the normalize_diff() rules change


class ProviderError(RuntimeError):
    """A provider could not produce a valid result. The message says why."""


@dataclass
class Cause:
    rank: int
    file: str
    line: int | None
    reason: str
    evidence: str


@dataclass
class Diagnosis:
    causes: list[Cause]
    provider_mode: str
    model: str | None = None
    attempts: list[dict] = field(default_factory=list)
    oracle_localisation: bool = False   # rule mode from fault.json diagnosed_file (ground truth), not from evidence
    # H1 sampling fields (None when only one sample or mode is rule/scripted)
    samples: list[dict] = field(default_factory=list)  # [{"file": ..., "line": ...}, ...] per sample rank-1 cause
    samples_disagree: bool | None = None                # True iff rank-1 files differ across samples

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Patch:
    candidate_id: str
    diff: str
    explanation: str
    provider_mode: str
    candidate_kind: str | None = None   # scripted only: file name stem; never shown to the decision engine
    model: str | None = None
    applies: bool | None = None         # git apply --check on app/ + inject.diff
    apply_error: str | None = None
    attempts: list[dict] = field(default_factory=list)   # live/replay request attempts (bounded retries)
    # Raw-output audit trail (live/replay only; None/[] for scripted). See the module docstring.
    raw_output_sha256: str | None = None    # full model response that contained this patch
    format_status: str | None = None        # "raw_valid" | "normalized" | "invalid"
    format_problems: list[str] = field(default_factory=list)   # validate_diff_structure() of the raw diff
    raw_diff_sha256: str | None = None
    diff_sha256: str | None = None          # of .diff, the text actually apply-checked
    raw_diff: str | None = None             # original diff, kept only when format_status == "normalized"
    normalizer_version: int | None = None   # set when the normalizer was tried (status != raw_valid)
    normalizer_rules: list[str] = field(default_factory=list)  # rules that fired, in order

    def to_dict(self) -> dict:
        return asdict(self)


class Provider(Protocol):
    mode: str

    def diagnose(self, incident: dict, source_files: dict[str, str]) -> Diagnosis: ...

    def draft_patches(self, diagnosis: Diagnosis, source_files: dict[str, str], fault_id: str,
                      n: int | None = 3) -> list[Patch]: ...


def get_provider(mode: str, **kwargs) -> Provider:
    if mode == "rule":
        return RuleProvider(**kwargs)
    if mode == "scripted":
        return ScriptedProvider(**kwargs)
    if mode in ("live", "replay"):
        return LLMProvider(mode, **kwargs)
    raise ValueError(f"unknown provider mode {mode!r}; expected rule, scripted, replay or live")


# --------------------------------------------------------------------------- shared helpers

def _assert_allowed(path: str) -> None:
    norm = path.replace("\\", "/")
    if any(part in norm for part in FORBIDDEN_PARTS):
        raise ProviderError(f"refusing to use {path}: hidden tests and labels are never given to a provider")


def _load_fault(repo: Path, fault_id: str) -> dict:
    path = repo / "faults" / fault_id / "fault.json"
    if not path.is_file():
        raise ProviderError(f"unknown fault {fault_id!r}: {path} not found")
    return json.loads(path.read_text(encoding="utf-8"))


def check_patches(patches: list[Patch], fault_id: str, repo: Path = REPO) -> list[Patch]:
    """Set applies/apply_error on each patch: git apply --check against app/ with inject.diff applied."""
    inject = repo / "faults" / fault_id / "inject.diff"
    with tempfile.TemporaryDirectory(prefix="autoimmune-apply-") as tmp:
        work = Path(tmp)
        shutil.copytree(repo / "app", work / "app", ignore=shutil.ignore_patterns("target"))
        res = subprocess.run(["git", "apply", str(inject)], cwd=work, capture_output=True, text=True)
        if res.returncode != 0:
            raise ProviderError(f"{inject} does not apply to app/: {res.stderr.strip()}")
        for p in patches:
            if not p.diff.strip():
                p.applies, p.apply_error = False, "empty diff"
                continue
            diff = p.diff if p.diff.endswith("\n") else p.diff + "\n"
            # Bytes, not text mode: on Windows text-mode stdin turns \n into \r\n and git apply rejects hunks.
            res = subprocess.run(["git", "apply", "--check", "-"], cwd=work, input=diff.encode("utf-8"),
                                 capture_output=True)
            p.applies = res.returncode == 0
            stderr = res.stderr.decode("utf-8", "replace").strip()
            p.apply_error = None if p.applies else (stderr or f"git apply exited {res.returncode}")
            if not p.applies:
                log.info("patch %s does not apply: %s", p.candidate_id, p.apply_error)
    return patches


# --------------------------------------------------------------------------- diff format check / normalizer

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_file_header(lines: list[str], i: int) -> bool:
    return lines[i].startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ ")


def validate_diff_structure(diff: str) -> list[str]:
    """Structural problems of a unified diff; an empty list means structurally valid.

    Checks: LF line endings and a trailing newline; at least one `--- ` line directly followed by `+++ `;
    no hunk before a file header; every `@@` line well-formed; each hunk body has exactly the old/new
    line counts its header declares. It does not say whether the diff applies: git apply decides that."""
    if not diff.strip():
        return ["empty diff"]
    problems = []
    if "\r" in diff:
        problems.append("CRLF line endings")
    if not diff.endswith("\n"):
        problems.append("no trailing newline")
    lines = diff.replace("\r\n", "\n").split("\n")
    if lines[-1] == "":
        lines.pop()
    have_header, hunk_no, i = False, 0, 0
    while i < len(lines):
        if _is_file_header(lines, i):
            have_header, i = True, i + 2
            continue
        if not lines[i].startswith("@@"):
            i += 1
            continue
        hunk_no += 1
        m = HUNK_RE.match(lines[i])
        i += 1
        if not m:
            problems.append(f"hunk {hunk_no}: malformed header {lines[i - 1][:60]!r}")
            continue
        if not have_header:
            problems.append(f"hunk {hunk_no}: no ---/+++ file header before it")
        old = int(m.group(2)) if m.group(2) is not None else 1
        new = int(m.group(4)) if m.group(4) is not None else 1
        while i < len(lines) and (old > 0 or new > 0):
            tag = lines[i][:1]
            if tag in (" ", ""):                 # git also reads an empty line as empty context
                old, new = old - 1, new - 1
            elif tag == "-":
                old -= 1
            elif tag == "+":
                new -= 1
            elif tag != "\\":                    # "\ No newline at end of file"
                break
            i += 1
        while i < len(lines) and lines[i].startswith("\\"):
            i += 1
        if old != 0 or new != 0:
            problems.append(f"hunk {hunk_no}: body does not match header {m.group(0)!r}")
        elif i < len(lines) and lines[i][:1] in ("+", "-", " ") and not _is_file_header(lines, i):
            problems.append(f"hunk {hunk_no}: more body lines than header {m.group(0)!r} declares")
    if hunk_no == 0:
        problems.append("no hunks")
    if not have_header:
        problems.append("no ---/+++ file header")
    return problems


def normalize_diff(diff: str, target_files: set[str]) -> tuple[str, list[str]]:
    """Deterministic rewrite of a structurally invalid diff (NORMALIZER_VERSION). Returns (text, rules fired).

    Rules, in order: crlf_to_lf; trailing_newline; add_file_headers (only when there are @@ hunks, no
    `--- `, `+++ ` or `diff --git` line at all, and exactly one target file). The caller re-validates the
    result and keeps the raw diff if it is still invalid."""
    text, rules = diff, []
    if "\r" in text:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        rules.append("crlf_to_lf")
    if text.strip() and not text.endswith("\n"):
        text += "\n"
        rules.append("trailing_newline")
    lines = text.split("\n")
    has_hunks = any(line.startswith("@@") for line in lines)
    has_headers = any(line.startswith(("--- ", "+++ ", "diff --git")) for line in lines)
    if has_hunks and not has_headers and len(target_files) == 1:
        target = next(iter(target_files)).replace("\\", "/")
        text = f"--- a/{target}\n+++ b/{target}\n" + text.lstrip("\n")
        rules.append("add_file_headers")
    return text, rules


def apply_format_check(patch: Patch, target_files: set[str]) -> Patch:
    """Set the format/sha/normalizer fields of an LLM patch. .diff changes only when normalization yields a
    structurally valid diff; otherwise the drafted text is left exactly as it was."""
    raw = patch.diff
    patch.raw_diff_sha256 = _sha256(raw)
    patch.format_problems = validate_diff_structure(raw)
    if not patch.format_problems:
        patch.format_status = "raw_valid"
    else:
        patch.normalizer_version = NORMALIZER_VERSION
        fixed, rules = normalize_diff(raw, target_files)
        if rules and not validate_diff_structure(fixed):
            patch.format_status, patch.diff, patch.raw_diff = "normalized", fixed, raw
            patch.normalizer_rules = rules
        else:
            patch.format_status = "invalid"
    patch.diff_sha256 = _sha256(patch.diff)
    return patch


# --------------------------------------------------------------------------- rule mode

FRAME_RE = re.compile(r"at\s+(?:[\w.$-]+/)*([\w$.]+)\.([\w$<>]+)\(([^:()]+\.java):(\d+)\)")
EXC_RE = re.compile(r"^\s*(?:Caused by:\s*)?([\w$.]+(?:Exception|Error)\b.*)$")


def _trace_sections(trace: str) -> list[tuple[str, list[str]]]:
    """Split a stack trace into (exception line, frame lines) sections; later sections are deeper causes."""
    sections: list[tuple[str, list[str]]] = []
    for line in trace.splitlines():
        if FRAME_RE.search(line):
            if not sections:
                sections.append(("", []))
            sections[-1][1].append(line.strip())
        elif EXC_RE.match(line) and "\tat " not in line:
            sections.append((EXC_RE.match(line).group(1).strip(), []))
    return sections


class RuleProvider:
    mode = "rule"

    def __init__(self, repo: Path = REPO):
        self.repo = Path(repo)

    def diagnose(self, incident: dict, source_files: dict[str, str]) -> Diagnosis:
        for path in source_files:
            _assert_allowed(path)
        causes = self._from_stack_trace(incident.get("stack_trace") or "", source_files)
        if causes:
            return Diagnosis(causes=causes, provider_mode=self.mode)
        return Diagnosis(causes=self._from_fault(incident), provider_mode=self.mode, oracle_localisation=True)

    def _from_stack_trace(self, trace: str, source_files: dict[str, str]) -> list[Cause]:
        # Deepest section (root cause) that has application frames.
        for exc_line, frames in reversed(_trace_sections(trace)):
            app = [(f, FRAME_RE.search(f)) for f in frames]
            app = [(f, m) for f, m in app if m.group(1).startswith(APP_PACKAGE)]
            if not app:
                continue
            causes: list[Cause] = []
            seen: set[tuple[str, int]] = set()
            for frame, m in app:
                cls, method, filename, line = m.group(1), m.group(2), m.group(3), int(m.group(4))
                path = self._source_path(cls, filename, source_files)
                if (path, line) in seen:
                    continue
                seen.add((path, line))
                rank = len(causes) + 1
                where = "top application frame" if rank == 1 else f"application frame #{rank} in the stack"
                causes.append(Cause(rank=rank, file=path, line=line,
                                    reason=f"{where}: {cls.rsplit('.', 1)[-1]}.{method}",
                                    evidence=f"{exc_line} | {frame}".strip(" |")))
                if len(causes) == 3:
                    break
            return causes
        return []

    @staticmethod
    def _source_path(cls: str, filename: str, source_files: dict[str, str]) -> str:
        package = cls.split("$")[0].rsplit(".", 1)[0].replace(".", "/")
        suffix = f"{package}/{filename}"
        for path in source_files:
            if path.replace("\\", "/").endswith(suffix):
                return path.replace("\\", "/")
        return JAVA_ROOT + suffix

    def _from_fault(self, incident: dict) -> list[Cause]:
        fault_id = incident.get("fault_id")
        if not fault_id:
            raise ProviderError("rule mode: incident has no stack trace with application frames and no fault_id")
        fault = _load_fault(self.repo, fault_id)
        detail = {k: incident[k] for k in ("kind", "endpoint", "status", "expected", "actual") if k in incident}
        return [Cause(rank=1, file=fault["diagnosed_file"], line=None,
                      reason=f"no stack trace for a {incident.get('kind', 'unknown')} incident; "
                             f"oracle localisation from faults/{fault_id}/fault.json diagnosed_file",
                      evidence=json.dumps(detail, sort_keys=True))]

    def draft_patches(self, diagnosis, source_files, fault_id, n=3):
        raise ProviderError("rule mode only diagnoses; use scripted, replay or live for draft_patches")


# --------------------------------------------------------------------------- scripted mode

class ScriptedProvider:
    mode = "scripted"

    def __init__(self, repo: Path = REPO):
        self.repo = Path(repo)

    def diagnose(self, incident, source_files):
        raise ProviderError("scripted mode only drafts patches; use rule, replay or live for diagnose")

    def draft_patches(self, diagnosis: Diagnosis, source_files: dict[str, str], fault_id: str,
                      n: int | None = 3) -> list[Patch]:
        """All of faults/<id>/candidates/*.diff in file-name order; n caps the count (None = all)."""
        cand_dir = self.repo / "faults" / fault_id / "candidates"
        files = sorted(cand_dir.glob("*.diff"))      # *.diff only: labels.json is never opened
        if not files:
            raise ProviderError(f"scripted mode: no candidates in {cand_dir}")
        if n is not None:
            files = files[:n]
        patches = []
        for f in files:
            diff = f.read_text(encoding="utf-8")
            digest = hashlib.sha256(diff.encode("utf-8")).hexdigest()[:8]
            patches.append(Patch(candidate_id=f"{fault_id}-scripted-{digest}", diff=diff,
                                 explanation=f"scripted candidate {f.name}", provider_mode=self.mode,
                                 candidate_kind=f.stem))
        return check_patches(patches, fault_id, self.repo)


# --------------------------------------------------------------------------- live / replay

DIAGNOSIS_SCHEMA = {
    "type": "object",
    "required": ["causes"],
    "properties": {
        "causes": {
            "type": "array", "minItems": 1, "maxItems": 3,
            "items": {
                "type": "object",
                "required": ["rank", "file", "line", "reason", "evidence"],
                "properties": {
                    "rank": {"type": "integer", "minimum": 1, "maximum": 3},
                    "file": {"type": "string", "minLength": 1},
                    "line": {"type": ["integer", "null"], "minimum": 1},
                    "reason": {"type": "string", "minLength": 1},
                    "evidence": {"type": "string"},
                },
            },
        }
    },
}

PATCHES_SCHEMA = {
    "type": "object",
    "required": ["patches"],
    "properties": {
        "patches": {
            "type": "array", "minItems": 1,
            "items": {
                "type": "object",
                "required": ["diff", "explanation"],
                "properties": {"diff": {"type": "string", "minLength": 1}, "explanation": {"type": "string"}},
            },
        }
    },
}

DIAGNOSE_SYSTEM = (
    "You diagnose faults in order-service, a Java 17 Spring Boot service. "
    "Answer with JSON only, no prose and no code fences, in exactly this shape:\n"
    '{"causes": [{"rank": 1, "file": "<repository-relative path, e.g. app/src/main/java/...>", '
    '"line": <integer or null>, "reason": "<why this is the cause>", '
    '"evidence": "<incident detail or code that supports it>"}]}\n'
    "Give 1 to 3 causes, most likely first, with ranks 1..n."
)

PATCH_SYSTEM = (
    "You fix faults in order-service, a Java 17 Spring Boot service. "
    "Answer with JSON only, no prose and no code fences, in exactly this shape:\n"
    '{"patches": [{"diff": "<unified diff>", "explanation": "<one or two sentences>"}]}\n'
    "Each diff must be a git-style unified diff with paths relative to the repository root "
    "(--- a/app/... +++ b/app/...), apply cleanly to the files shown, and change as little as possible. "
    "Give exactly {n} distinct alternative patches."
)


def _sources_block(source_files: dict[str, str]) -> str:
    parts = []
    for path in sorted(source_files):
        _assert_allowed(path)
        parts.append(f"--- {path}\n{source_files[path]}")
    return "\n".join(parts)


def _parse_json(text: str) -> tuple[object, list[str]]:
    """Parse a model reply as JSON. Returns (data, repairs). Deterministic repairs, each RECORDED in the attempt:
    code_fence_removed, leading_text_ignored (text before the first '{'), trailing_text_ignored:<what> (a complete
    JSON value followed by anything else, e.g. a stray ']'). Anything else raises ValueError."""
    repairs: list[str] = []
    stripped = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1)
        repairs.append("code_fence_removed")
    try:
        return json.loads(stripped), repairs
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    if start < 0:
        raise ValueError("no JSON object in the reply")
    if start > 0:
        repairs.append("leading_text_ignored")
    data, end = json.JSONDecoder().raw_decode(stripped[start:])     # raises ValueError if no complete value
    rest = stripped[start + end:].strip()
    if rest:
        repairs.append(f"trailing_text_ignored:{rest[:40]!r}")
    return data, repairs


RATE_LIMIT_MAX_WAIT_S = 30
_sleep = time.sleep          # patched in tests


def _rate_limit_wait(exc: Exception, attempt: int) -> float | None:
    """On HTTP 429 wait before the next bounded retry: Retry-After if given, else 5 s x attempt, capped. Returns the
    seconds waited (recorded in the attempt), or None if this was not a rate limit."""
    resp = getattr(exc, "response", None)
    if not isinstance(exc, requests.HTTPError) or resp is None or resp.status_code != 429:
        return None
    try:
        wait = float(resp.headers.get("Retry-After", ""))
    except (TypeError, ValueError):
        wait = 5.0 * attempt
    wait = max(0.0, min(wait, RATE_LIMIT_MAX_WAIT_S))
    log.warning("rate limited (HTTP 429); waiting %.0f s before retrying", wait)
    _sleep(wait)
    return wait


class LLMProvider:
    def __init__(self, mode: str, repo: Path = REPO, cache_dir: Path | None = None,
                 temperature: float = 0.2, env: dict | None = None,
                 n_samples: int = 1, sample_temperature: float = 0.7):
        """n_samples: number of diagnosis samples (1 = no agreement check; >1 enables H1).
        sample_temperature: temperature used for sample index >= 1 (first sample uses self.temperature).
        Each sample has its own cache key (base key material includes the sample index).
        Agreement is defined as: the rank-1 cause.file is identical across all samples.
        samples_disagree is set on the returned Diagnosis (True/False for >1 samples; None for 1 sample).
        For n_samples>1 with replay mode every sample must have a pre-recorded cache entry."""
        if mode not in ("live", "replay"):
            raise ValueError(f"LLMProvider mode must be live or replay, not {mode!r}")
        env = os.environ if env is None else env
        self.mode = mode
        self.repo = Path(repo)
        self.cache_dir = Path(cache_dir) if cache_dir else self.repo / "cache"
        self.temperature = temperature
        self.n_samples = max(1, int(n_samples))
        self.sample_temperature = sample_temperature
        self.base_url = (env.get("LLM_BASE_URL") or "").rstrip("/")
        self.model = env.get("LLM_MODEL") or ""
        self._api_key = env.get("LLM_API_KEY") or ""
        missing = [k for k, v in (("LLM_BASE_URL", self.base_url), ("LLM_MODEL", self.model)) if not v]
        if missing:
            raise ProviderError(f"{mode} mode needs environment variable(s) {', '.join(missing)} "
                                f"(they also form the {'cache' if mode == 'replay' else 'request'} key)")

    # ---- prompts

    def diagnosis_messages(self, incident: dict, source_files: dict[str, str]) -> list[dict]:
        shown = {k: v for k, v in incident.items() if k != "fault_id"}
        user = ("Incident:\n" + json.dumps(shown, indent=2, sort_keys=True, default=str)
                + "\n\nSource files:\n" + _sources_block(source_files))
        return [{"role": "system", "content": DIAGNOSE_SYSTEM}, {"role": "user", "content": user}]

    def patch_messages(self, diagnosis: Diagnosis, source_files: dict[str, str], n: int) -> list[dict]:
        causes = [asdict(c) for c in diagnosis.causes]
        user = ("Diagnosis:\n" + json.dumps({"causes": causes}, indent=2, sort_keys=True)
                + "\n\nSource files:\n" + _sources_block(source_files))
        return [{"role": "system", "content": PATCH_SYSTEM.replace("{n}", str(n))},
                {"role": "user", "content": user}]

    # ---- cache

    def cache_key(self, messages: list[dict], sample_index: int = 0,
                  override_temperature: float | None = None, version: int = CACHE_KEY_VERSION) -> str:
        """Stable SHA256 key. sample_index and temperature are part of the key so each sample has a distinct
        entry and replay is deterministic per (version, provider, model, messages, temp, sample).
        version=1 reproduces the original unversioned scheme; it is used only to diagnose old entries."""
        temp = override_temperature if override_temperature is not None else self.temperature
        prompt = json.dumps(messages, sort_keys=True, ensure_ascii=False)
        parts = [self.base_url, self.model, prompt, temp, sample_index]
        if version != 1:
            parts = [version] + parts
        material = json.dumps(parts, ensure_ascii=False)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _fetch(self, messages: list[dict], key: str, temperature: float | None = None,
               sample_index: int = 0) -> str:
        """temperature overrides self.temperature for the HTTP request (and is recorded in the cache entry).
        sample_index is only used to look up an entry recorded under the version-1 key scheme."""
        eff_temp = temperature if temperature is not None else self.temperature
        if self.mode == "replay":
            path = self._cache_path(key)
            if not path.is_file():
                legacy = self._cache_path(self.cache_key(messages, sample_index, temperature, version=1))
                if legacy.is_file():
                    raise ProviderError(
                        f"replay cache version mismatch: this request was recorded as {legacy.name} under "
                        f"cache key version 1, but this code uses cache key version {CACHE_KEY_VERSION}. "
                        f"Old entries are not migrated; re-record with mode=live.")
                raise ProviderError(
                    f"replay cache miss: {path} not found (provider={self.base_url}, model={self.model}, "
                    f"temperature={eff_temp}, cache_key_version={CACHE_KEY_VERSION}). "
                    f"Record it first with mode=live.")
            entry = json.loads(path.read_text(encoding="utf-8"))
            if entry.get("cache_key_version") != CACHE_KEY_VERSION:
                raise ProviderError(
                    f"replay cache version mismatch: {path.name} has cache_key_version="
                    f"{entry.get('cache_key_version')!r}, but this code uses {CACHE_KEY_VERSION}. "
                    f"Re-record with mode=live.")
            return entry["response"]

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        body = {"model": self.model, "messages": messages, "temperature": eff_temp}
        resp = requests.post(f"{self.base_url}/chat/completions", json=body, headers=headers,
                             timeout=HTTP_TIMEOUT_S)
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        entry = {"key": key, "cache_key_version": CACHE_KEY_VERSION, "provider": self.base_url, "model": self.model, "temperature": eff_temp,
                 "messages": messages, "response": text,
                 "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self._cache_path(key).write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
        return text

    # ---- bounded retry loop

    def _request_json(self, messages: list[dict], schema: dict, what: str, extra_check=None,
                      sample_index: int = 0, sample_temp: float | None = None):
        """sample_index and sample_temp are included in the cache key so each sample is stored separately."""
        attempts: list[dict] = []
        for attempt in range(1, MAX_RETRIES + 2):
            key = self.cache_key(messages, sample_index=sample_index, override_temperature=sample_temp)
            try:
                text = self._fetch(messages, key, temperature=sample_temp, sample_index=sample_index)
            except ProviderError:
                raise
            except (requests.RequestException, KeyError, IndexError, ValueError) as e:
                err = f"transport error: {type(e).__name__}: {e}"
                waited = _rate_limit_wait(e, attempt) if attempt <= MAX_RETRIES else None
                attempts.append({"attempt": attempt, "cache_key": key, "raw_sha256": None, "ok": False,
                                 "error": err, "waited_s": waited})
                log.warning("%s attempt %d/%d failed: %s", what, attempt, MAX_RETRIES + 1, err)
                continue
            try:
                data, repairs = _parse_json(text)
                jsonschema.validate(data, schema)
                if extra_check:
                    extra_check(data)
            except (ValueError, jsonschema.ValidationError) as e:
                err = f"invalid response: {e.message if isinstance(e, jsonschema.ValidationError) else e}"
                attempts.append({"attempt": attempt, "cache_key": key, "raw_sha256": _sha256(text), "ok": False,
                                 "error": err})
                log.warning("%s attempt %d/%d failed: %s", what, attempt, MAX_RETRIES + 1, err)
                messages = messages + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": f"That answer was invalid ({err}). "
                                                "Reply again with JSON only, in exactly the requested shape."}]
                continue
            attempts.append({"attempt": attempt, "cache_key": key, "raw_sha256": _sha256(text), "ok": True,
                             "error": None, "parse_repairs": repairs})
            if repairs:
                log.info("%s accepted with recorded parse repairs %s", what, repairs)
            return data, attempts          # attempts[-1] is the accepted response
        summary = "; ".join(f"#{a['attempt']}: {a['error']}" for a in attempts)
        raise ProviderError(f"{what}: no valid response after {MAX_RETRIES + 1} attempts ({summary})")

    # ---- interface

    def _diagnose_one(self, incident: dict, source_files: dict[str, str],
                      sample_index: int = 0) -> tuple[list[Cause], list[dict]]:
        """Run one diagnosis sample. Returns (causes_sorted_by_rank, attempts)."""
        def ranks_are_sequential(data):
            ranks = sorted(c["rank"] for c in data["causes"])
            if ranks != list(range(1, len(ranks) + 1)):
                raise ValueError(f"ranks must be 1..{len(ranks)}, got {ranks}")

        temp = self.sample_temperature if sample_index > 0 else None  # None → uses self.temperature in _fetch
        data, attempts = self._request_json(
            self.diagnosis_messages(incident, source_files), DIAGNOSIS_SCHEMA,
            f"diagnose[sample={sample_index}]", ranks_are_sequential,
            sample_index=sample_index, sample_temp=temp)
        causes = [Cause(**c) for c in sorted(data["causes"], key=lambda c: c["rank"])]
        return causes, attempts

    def diagnose(self, incident: dict, source_files: dict[str, str]) -> Diagnosis:
        """Run self.n_samples diagnosis calls. For n_samples>1 the first sample uses self.temperature;
        subsequent samples use self.sample_temperature (configurable, default 0.7) to introduce variation.
        Agreement is defined as: the rank-1 cause.file is identical across all samples.
        samples_disagree is True when any sample's rank-1 file differs from the first sample's rank-1 file.
        When n_samples==1, samples_disagree is None (no comparison possible).
        All samples' rank-1 {file, line} are recorded in Diagnosis.samples for audit; the full per-sample
        causes list is in diagnosis.json but NOT in the evidence row (keep the row compact)."""
        all_causes, all_attempts, sample_records = [], [], []
        for i in range(self.n_samples):
            causes, attempts = self._diagnose_one(incident, source_files, sample_index=i)
            all_causes.append(causes)
            all_attempts.extend(attempts)
            rank1 = causes[0] if causes else None
            sample_records.append({"sample": i, "file": rank1.file if rank1 else None,
                                   "line": rank1.line if rank1 else None})
            log.info("diagnosis sample %d/%d: rank-1 file=%s", i + 1, self.n_samples,
                     rank1.file if rank1 else None)

        # primary result: first sample's causes (consistent, deterministic)
        primary_causes = all_causes[0]
        # agreement check: all rank-1 files must be the same
        if self.n_samples > 1:
            rank1_files = [s["file"] for s in sample_records]
            samples_disagree = len(set(rank1_files)) > 1
            if samples_disagree:
                log.warning("diagnosis samples disagree: rank-1 files = %s", rank1_files)
            else:
                log.info("diagnosis samples agree: rank-1 file = %s", rank1_files[0])
        else:
            samples_disagree = None

        return Diagnosis(causes=primary_causes, provider_mode=self.mode, model=self.model,
                         attempts=all_attempts, samples=sample_records,
                         samples_disagree=samples_disagree)

    def draft_patches(self, diagnosis: Diagnosis, source_files: dict[str, str], fault_id: str,
                      n: int | None = 3) -> list[Patch]:
        n = 3 if n is None else n

        def at_most_n(data):
            if len(data["patches"]) > n:
                raise ValueError(f"asked for {n} patches, got {len(data['patches'])}")

        data, attempts = self._request_json(self.patch_messages(diagnosis, source_files, n),
                                            PATCHES_SCHEMA, "draft_patches", at_most_n)
        if len(data["patches"]) < n:
            log.warning("draft_patches: asked for %d patches, model returned %d", n, len(data["patches"]))
        raw_sha = attempts[-1]["raw_sha256"]
        targets = {c.file for c in diagnosis.causes}
        patches = []
        for i, p in enumerate(data["patches"], start=1):
            patch = apply_format_check(
                Patch(candidate_id=f"{fault_id}-{self.mode}-{i}", diff=p["diff"], explanation=p["explanation"],
                      provider_mode=self.mode, model=self.model, attempts=attempts, raw_output_sha256=raw_sha),
                targets)
            if patch.format_status != "raw_valid":
                log.info("patch %s format %s (%s; rules %s)", patch.candidate_id, patch.format_status,
                         "; ".join(patch.format_problems), patch.normalizer_rules)
            patches.append(patch)
        return check_patches(patches, fault_id, self.repo)
