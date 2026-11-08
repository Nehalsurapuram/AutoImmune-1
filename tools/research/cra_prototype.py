"""Causal Ripple Analysis (CRA) — Isolated Research Prototype v0.1.

Offline, read-only analyzer that identifies guard-condition regressions in unified diffs,
derives boundary inputs from predicate differences, grounds contracts in source annotations,
and emits an evidence-disciplined JSON report with strict separation between static
predictions and runtime observations.

Supported Syntax Subset:
- Java methods containing String validation guards:
    `if (<param> == null || <param>.isBlank()) { throw new <ExceptionClass>(...); }`
    `if (<param> == null || <param>.isEmpty()) { throw new <ExceptionClass>(...); }`
- Compared against candidate diffs retaining only:
    `if (<param> == null) { throw new <ExceptionClass>(...); }`
- Grounded against exceptions carrying Spring `@ResponseStatus` annotations.

Standard library only. No external parser or runtime execution dependencies.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class HunkLine:
    tag: str                            # "+", "-", " "
    content: str


@dataclass
class DiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str
    lines: list[HunkLine] = field(default_factory=list)
    added_lines: list[str] = field(default_factory=list)
    removed_lines: list[str] = field(default_factory=list)
    context_lines: list[str] = field(default_factory=list)

    @property
    def first_change_old_line(self) -> int:
        """Calculate line number in the old file where the first +/- change occurs."""
        curr = self.old_start
        for hl in self.lines:
            if hl.tag in ("+", "-"):
                return curr
            if hl.tag == " ":
                curr += 1
        return self.old_start


@dataclass
class ParsedDiff:
    old_path: str | None
    new_path: str | None
    hunks: list[DiffHunk] = field(default_factory=list)
    raw_text: str = ""


class DiffParseError(ValueError):
    """Raised when unified diff text is corrupted or unparseable."""


def parse_unified_diff(diff_text: str) -> ParsedDiff:
    """Parse a single-file unified diff into structured hunks with strict validation."""
    if not diff_text or not diff_text.strip():
        raise DiffParseError("Empty diff text supplied")

    raw_lines = diff_text.splitlines()
    old_path: str | None = None
    new_path: str | None = None
    hunks: list[DiffHunk] = []
    current_hunk: DiffHunk | None = None
    file_headers_count = 0

    hunk_header_re = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)$")

    for line in raw_lines:
        if line.startswith("--- "):
            file_headers_count += 1
            raw = line[4:].strip()
            old_path = raw[2:] if raw.startswith(("a/", "b/")) else raw
        elif line.startswith("+++ "):
            raw = line[4:].strip()
            new_path = raw[2:] if raw.startswith(("a/", "b/")) else raw
        elif line.startswith("@@ "):
            m = hunk_header_re.match(line)
            if not m:
                raise DiffParseError(f"Malformed hunk header: {line}")
            old_start = int(m.group(1))
            old_count = int(m.group(2)) if m.group(2) is not None else 1
            new_start = int(m.group(3))
            new_count = int(m.group(4)) if m.group(4) is not None else 1
            header = m.group(5).strip()
            current_hunk = DiffHunk(old_start, old_count, new_start, new_count, header)
            hunks.append(current_hunk)
        elif current_hunk is not None:
            if line.startswith("+"):
                current_hunk.lines.append(HunkLine("+", line[1:]))
                current_hunk.added_lines.append(line[1:])
            elif line.startswith("-"):
                current_hunk.lines.append(HunkLine("-", line[1:]))
                current_hunk.removed_lines.append(line[1:])
            elif line.startswith(" "):
                current_hunk.lines.append(HunkLine(" ", line[1:]))
                current_hunk.context_lines.append(line[1:])

    if file_headers_count > 1:
        raise DiffParseError("Multi-file diffs are not supported by prototype v0.1")

    if not hunks:
        raise DiffParseError("No valid @@ hunk headers found in diff")

    return ParsedDiff(old_path=old_path, new_path=new_path, hunks=hunks, raw_text=diff_text)


@dataclass
class JavaMethodScope:
    name: str
    return_type: str
    parameter_name: str
    parameter_type: str
    start_line: int
    end_line: int
    signature: str
    method_text: str


def _clean_java_code(source_text: str) -> list[str]:
    """Mask string literals and comments with spaces while preserving line structure."""
    lines = source_text.splitlines()
    cleaned_lines = []
    in_block_comment = False

    for line in lines:
        out = []
        i = 0
        n = len(line)
        in_string = False
        in_char = False

        while i < n:
            c = line[i]
            nxt = line[i + 1] if i + 1 < n else ""

            if in_block_comment:
                if c == "*" and nxt == "/":
                    in_block_comment = False
                    out.append("  ")
                    i += 2
                else:
                    out.append(" ")
                    i += 1
                continue

            if in_string:
                if c == "\\":
                    out.append("  ")
                    i += 2
                elif c == '"':
                    in_string = False
                    out.append(" ")
                    i += 1
                else:
                    out.append(" ")
                    i += 1
                continue

            if in_char:
                if c == "\\":
                    out.append("  ")
                    i += 2
                elif c == "'":
                    in_char = False
                    out.append(" ")
                    i += 1
                else:
                    out.append(" ")
                    i += 1
                continue

            if c == "/" and nxt == "/":
                out.append(" " * (n - i))
                break
            elif c == "/" and nxt == "*":
                in_block_comment = True
                out.append("  ")
                i += 2
                continue
            elif c == '"':
                in_string = True
                out.append(" ")
                i += 1
                continue
            elif c == "'":
                in_char = True
                out.append(" ")
                i += 1
                continue
            else:
                out.append(c)
                i += 1

        cleaned_lines.append("".join(out))

    return cleaned_lines


def extract_declared_type_names(source_text: str) -> list[str]:
    """Extract declared top-level and nested class, interface, enum, and record names."""
    cleaned = "\n".join(_clean_java_code(source_text))
    pattern = re.compile(r"\b(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)")
    return pattern.findall(cleaned)


def extract_all_methods(source_text: str) -> list[JavaMethodScope]:
    """Extract all method scopes from a Java source file, supporting multiline headers."""
    orig_lines = source_text.splitlines()
    cleaned_lines = _clean_java_code(source_text)
    methods: list[JavaMethodScope] = []

    depth = 0
    header_chars: list[str] = []
    header_start_line = 1
    current_method_header: tuple[str, str, list[tuple[str, str]], int, str] | None = None

    MODIFIERS = {"public", "protected", "private", "static", "final", "synchronized", "default", "abstract"}

    for idx, (clean_line, orig_line) in enumerate(zip(cleaned_lines, orig_lines), start=1):
        for char in clean_line:
            if char == "{":
                if depth == 1 and not current_method_header:
                    header_str = " ".join("".join(header_chars).split())
                    # Strip annotations like @Override, @GetMapping(...)
                    header_no_ann = re.sub(r"@\w+(?:\([^)]*\))?", "", header_str).strip()
                    words = header_no_ann.split()
                    w_idx = 0
                    while w_idx < len(words) and words[w_idx] in MODIFIERS:
                        w_idx += 1
                    sig_no_mods = " ".join(words[w_idx:])
                    m = re.search(
                        r"([\w<>\[\],]+)\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*(?:throws\s+[\w,\s]+)?$",
                        sig_no_mods,
                    )
                    if m and not any(k in words for k in ("class", "interface", "record", "enum")):
                        ret_type = m.group(1).strip()
                        m_name = m.group(2).strip()
                        raw_params = m.group(3).strip()
                        params: list[tuple[str, str]] = []
                        if raw_params:
                            for p in raw_params.split(","):
                                parts = p.strip().split()
                                if len(parts) >= 2:
                                    params.append((parts[-2], parts[-1]))
                        current_method_header = (m_name, ret_type, params, header_start_line, header_str)
                    header_chars = []
                elif depth == 0:
                    header_chars = []
                    header_start_line = idx + 1
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 1 and current_method_header:
                    m_name, ret_type, params, m_start, sig = current_method_header
                    p_type = params[0][0] if params else "unknown"
                    p_name = params[0][1] if params else "unknown"
                    body_text = "\n".join(orig_lines[m_start - 1 : idx])
                    methods.append(
                        JavaMethodScope(
                            name=m_name,
                            return_type=ret_type,
                            parameter_name=p_name,
                            parameter_type=p_type,
                            start_line=m_start,
                            end_line=idx,
                            signature=sig,
                            method_text=body_text,
                        )
                    )
                    current_method_header = None
                    header_chars = []
                    header_start_line = idx + 1
            elif char == ";":
                if depth == 1 and not current_method_header:
                    header_chars = []
                    header_start_line = idx + 1
            else:
                if depth == 1 and not current_method_header:
                    if not header_chars and char.strip():
                        header_start_line = idx
                    header_chars.append(char)

    return methods


def find_enclosing_method(source_text: str, target_line: int) -> JavaMethodScope | None:
    """Find the specific method strictly enclosing target_line [start_line, end_line].
    
    Returns None if target_line is outside all methods (e.g. class fields, header).
    No fallbacks are used.
    """
    methods = extract_all_methods(source_text)
    matching = [m for m in methods if m.start_line <= target_line <= m.end_line]
    if len(matching) == 1:
        return matching[0]
    return None


@dataclass
class ContractOracle:
    status: str                         # "AVAILABLE" | "UNAVAILABLE"
    exception_class: str | None = None
    expected_http_status: int | None = None
    reason: str | None = None
    grounding_file: str | None = None


def resolve_contract_oracle(
    exception_name: str | None,
    contract_file_path: Path | None = None,
    search_dir: Path | None = None,
) -> ContractOracle:
    """Ground expected failure behavior by inspecting exception class for @ResponseStatus."""
    if not exception_name:
        return ContractOracle(status="UNAVAILABLE")

    target_file: Path | None = None
    if contract_file_path and contract_file_path.exists():
        target_file = contract_file_path
    elif search_dir and search_dir.exists():
        direct = search_dir / f"{exception_name}.java"
        if direct.exists():
            target_file = direct
        else:
            candidates = list(search_dir.glob(f"**/{exception_name}.java"))
            if candidates:
                target_file = candidates[0]

    if not target_file or not target_file.is_file():
        return ContractOracle(status="UNAVAILABLE", exception_class=exception_name)

    content = target_file.read_text(encoding="utf-8", errors="replace")

    status_re = re.compile(
        r"@ResponseStatus\s*\(\s*(?:(?:code|value)\s*=\s*)?(?:HttpStatus\.)?([A-Z_]+|\d+)",
        re.MULTILINE,
    )
    m = status_re.search(content)
    if not m:
        return ContractOracle(
            status="UNAVAILABLE",
            exception_class=exception_name,
            grounding_file=str(target_file),
        )

    val = m.group(1)
    status_code: int | None = None
    if val.isdigit():
        status_code = int(val)
    elif val == "BAD_REQUEST":
        status_code = 400
    elif val == "NOT_FOUND":
        status_code = 404
    elif val in ("UNAUTHORIZED", "FORBIDDEN"):
        status_code = 401 if val == "UNAUTHORIZED" else 403
    elif val == "INTERNAL_SERVER_ERROR":
        status_code = 500

    reason: str | None = None
    reason_re = re.compile(r'super\s*\(\s*"([^"]+)"\s*\)')
    rm = reason_re.search(content)
    if rm:
        reason = rm.group(1)
    else:
        ann_reason_re = re.compile(r'reason\s*=\s*"([^"]+)"')
        arm = ann_reason_re.search(content)
        if arm:
            reason = arm.group(1)

    return ContractOracle(
        status="AVAILABLE" if status_code is not None else "UNAVAILABLE",
        exception_class=exception_name,
        expected_http_status=status_code,
        reason=reason,
        grounding_file=str(target_file),
    )


@dataclass
class BoundaryFinding:
    finding_type: str                   # "PREDICTED_STATIC"
    verified_at_runtime: bool           # False
    boundary_input: dict[str, Any]      # {"parameter": str, "value": Any, "category": str}
    expected_behavior: dict[str, Any]   # {"action": "THROW_EXCEPTION", "exception": str, "expected_http_status": int}
    predicted_behavior: dict[str, Any]  # {"guard_action": "GUARD_BYPASSED", "downstream_behavior": "UNKNOWN_WITHOUT_RUNTIME_OBSERVATION", ...}
    verdict: str                        # "CONTRACT_VIOLATION"
    divergence_explanation: str
    runtime_execution: dict[str, Any] = field(default_factory=lambda: {
        "status": "NOT_EXECUTED",
        "observed_http_code": None,
        "observed_body": None,
    })


@dataclass
class CRAReport:
    analysis_timestamp: str
    status: str                         # "COMPLETED" | "UNSUPPORTED_DIFF" | "INCONCLUSIVE"
    diff_target_file: str | None
    target_method: str | None
    target_parameter: dict[str, str] | None
    predicate_analysis: dict[str, Any]
    contract_oracle: dict[str, Any]
    findings: list[dict[str, Any]]
    overall_verdict: str                # "CONTRACT_VIOLATION" | "NO_RIPPLE_DETECTED" | "INCONCLUSIVE"
    recommendation: str                 # "ESCALATE" | "REVIEW_REQUIRED"
    recommendation_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def analyze_causal_ripple(
    diff_text: str,
    baseline_source_text: str | None = None,
    candidate_source_text: str | None = None,
    contract_file_path: Path | None = None,
    search_dir: Path | None = None,
) -> CRAReport:
    """Perform static Causal Ripple Analysis on a candidate diff and baseline source."""
    now_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # 1. Parse unified diff
    try:
        parsed = parse_unified_diff(diff_text)
    except DiffParseError as err:
        return CRAReport(
            analysis_timestamp=now_ts,
            status="UNSUPPORTED_DIFF",
            diff_target_file=None,
            target_method=None,
            target_parameter=None,
            predicate_analysis={"error": f"Failed to parse unified diff: {err}"},
            contract_oracle={"status": "UNAVAILABLE"},
            findings=[],
            overall_verdict="INCONCLUSIVE",
            recommendation="ESCALATE",
            recommendation_reason=f"Diff validation error: {err}. Human escalation required.",
        )

    target_file = parsed.new_path if parsed.new_path != "/dev/null" else parsed.old_path
    if not target_file or target_file == "/dev/null":
        target_file = parsed.old_path

    if not target_file:
        return CRAReport(
            analysis_timestamp=now_ts,
            status="UNSUPPORTED_DIFF",
            diff_target_file=None,
            target_method=None,
            target_parameter=None,
            predicate_analysis={"error": "Unified diff specifies no valid target file path"},
            contract_oracle={"status": "UNAVAILABLE"},
            findings=[],
            overall_verdict="INCONCLUSIVE",
            recommendation="ESCALATE",
            recommendation_reason="No target file path found in diff headers. Human escalation required.",
        )

    if not target_file.endswith(".java"):
        return CRAReport(
            analysis_timestamp=now_ts,
            status="UNSUPPORTED_DIFF",
            diff_target_file=target_file,
            target_method=None,
            target_parameter=None,
            predicate_analysis={"error": f"Target file '{target_file}' is not a Java source file (.java)"},
            contract_oracle={"status": "UNAVAILABLE"},
            findings=[],
            overall_verdict="INCONCLUSIVE",
            recommendation="ESCALATE",
            recommendation_reason=f"Target file '{target_file}' is non-Java. Prototype v0.1 only supports Java diffs.",
        )

    # 2. Scope extraction: Must locate method strictly enclosing the change
    if not baseline_source_text:
        return CRAReport(
            analysis_timestamp=now_ts,
            status="INCONCLUSIVE",
            diff_target_file=target_file,
            target_method=None,
            target_parameter=None,
            predicate_analysis={"error": "Baseline source text is required for method scope resolution"},
            contract_oracle={"status": "UNAVAILABLE"},
            findings=[],
            overall_verdict="INCONCLUSIVE",
            recommendation="ESCALATE",
            recommendation_reason="Baseline source text missing. Scope resolution inconclusive.",
        )

    # Validate that diff target file corresponds to the class in baseline source
    expected_class = Path(target_file).stem
    declared_classes = extract_declared_type_names(baseline_source_text)
    if declared_classes and expected_class not in declared_classes:
        return CRAReport(
            analysis_timestamp=now_ts,
            status="INCONCLUSIVE",
            diff_target_file=target_file,
            target_method=None,
            target_parameter=None,
            predicate_analysis={
                "error": f"Diff target '{target_file}' (expected class '{expected_class}') does not match declared classes in baseline source: {declared_classes}"
            },
            contract_oracle={"status": "UNAVAILABLE"},
            findings=[],
            overall_verdict="INCONCLUSIVE",
            recommendation="ESCALATE",
            recommendation_reason=f"Diff target file path '{target_file}' does not match baseline source class '{expected_class}'. Human escalation required.",
        )

    if candidate_source_text:
        cand_declared = extract_declared_type_names(candidate_source_text)
        if cand_declared and expected_class not in cand_declared:
            return CRAReport(
                analysis_timestamp=now_ts,
                status="INCONCLUSIVE",
                diff_target_file=target_file,
                target_method=None,
                target_parameter=None,
                predicate_analysis={
                    "error": f"Diff target '{target_file}' (expected class '{expected_class}') does not match declared classes in candidate source: {cand_declared}"
                },
                contract_oracle={"status": "UNAVAILABLE"},
                findings=[],
                overall_verdict="INCONCLUSIVE",
                recommendation="ESCALATE",
                recommendation_reason=f"Diff target file path '{target_file}' does not match candidate source class '{expected_class}'. Human escalation required.",
            )

    # Verify enclosing method for ALL hunks in the diff
    hunk_scopes: list[JavaMethodScope] = []
    for idx, hunk in enumerate(parsed.hunks, start=1):
        change_line = hunk.first_change_old_line
        hunk_scope = find_enclosing_method(baseline_source_text, change_line)
        if not hunk_scope:
            return CRAReport(
                analysis_timestamp=now_ts,
                status="INCONCLUSIVE",
                diff_target_file=target_file,
                target_method=None,
                target_parameter=None,
                predicate_analysis={
                    "error": f"Hunk #{idx} at line {change_line} is outside any resolved method scope"
                },
                contract_oracle={"status": "UNAVAILABLE"},
                findings=[],
                overall_verdict="INCONCLUSIVE",
                recommendation="ESCALATE",
                recommendation_reason=f"Hunk #{idx} at line {change_line} falls outside proven method scopes. Human escalation required.",
            )
        hunk_scopes.append(hunk_scope)

    distinct_method_names = {s.name for s in hunk_scopes}
    if len(distinct_method_names) > 1:
        sorted_methods = sorted(distinct_method_names)
        return CRAReport(
            analysis_timestamp=now_ts,
            status="INCONCLUSIVE",
            diff_target_file=target_file,
            target_method=None,
            target_parameter=None,
            predicate_analysis={
                "error": f"Multi-hunk diff affects multiple distinct methods: {', '.join(sorted_methods)}. Prototype v0.1 does not support cross-method hunks."
            },
            contract_oracle={"status": "UNAVAILABLE"},
            findings=[],
            overall_verdict="INCONCLUSIVE",
            recommendation="ESCALATE",
            recommendation_reason=(
                f"Multi-hunk diff modifies multiple separate methods ({', '.join(sorted_methods)}). "
                "Scope cannot be safely isolated to a single target method. Human escalation required."
            ),
        )

    scope = hunk_scopes[0]
    method_name = scope.name
    param_name = scope.parameter_name
    param_type = scope.parameter_type

    # 3. Restrict analysis strictly to the enclosing method's slice
    baseline_method_text = scope.method_text

    # Extract diff modifications strictly belonging to this method
    method_added_lines: list[str] = []
    method_removed_lines: list[str] = []
    for h in parsed.hunks:
        if scope.start_line <= h.first_change_old_line <= scope.end_line:
            method_added_lines.extend(h.added_lines)
            method_removed_lines.extend(h.removed_lines)

    added_text = "\n".join(method_added_lines)
    removed_text = "\n".join(method_removed_lines)

    # 4. Require positive evidence of baseline predicate strictly in baseline_method_text
    blank_check_re = re.compile(
        rf"if\s*\(\s*(?:{param_name}\s*==\s*null\s*\|\|\s*{param_name}\.isBlank\s*\(\s*\)|"
        rf"{param_name}\.isBlank\s*\(\s*\)\s*\|\|\s*{param_name}\s*==\s*null)\s*\)"
    )
    empty_check_re = re.compile(
        rf"if\s*\(\s*(?:{param_name}\s*==\s*null\s*\|\|\s*{param_name}\.isEmpty\s*\(\s*\)|"
        rf"{param_name}\.isEmpty\s*\(\s*\)\s*\|\|\s*{param_name}\s*==\s*null)\s*\)"
    )
    null_only_re = re.compile(rf"if\s*\(\s*{param_name}\s*==\s*null\s*\)")

    # Detect baseline predicate kind
    baseline_predicate_kind: str | None = None
    if blank_check_re.search(baseline_method_text) or blank_check_re.search(removed_text):
        baseline_predicate_kind = "isBlank"
    elif empty_check_re.search(baseline_method_text) or empty_check_re.search(removed_text):
        baseline_predicate_kind = "isEmpty"

    if not baseline_predicate_kind:
        return CRAReport(
            analysis_timestamp=now_ts,
            status="INCONCLUSIVE",
            diff_target_file=target_file,
            target_method=method_name,
            target_parameter={"name": param_name, "type": param_type},
            predicate_analysis={
                "pattern": "UNSUPPORTED_OR_MISSING_BASELINE_GUARD",
                "delta": "No positive evidence of baseline String null-and-blank/empty guard in target method",
            },
            contract_oracle={"status": "UNAVAILABLE"},
            findings=[],
            overall_verdict="INCONCLUSIVE",
            recommendation="ESCALATE",
            recommendation_reason="No positive evidence of baseline guard in target method slice. Escalation required.",
        )

    # 5. Require positive evidence of candidate predicate strictly in added text or candidate method
    candidate_method_text = ""
    if candidate_source_text:
        cand_methods = extract_all_methods(candidate_source_text)
        cand_matching = [m for m in cand_methods if m.name == method_name]
        if cand_matching:
            candidate_method_text = cand_matching[0].method_text

    candidate_search_corpus = added_text + ("\n" + candidate_method_text if candidate_method_text else "")

    candidate_has_full_guard = False
    candidate_has_null_only = False

    if baseline_predicate_kind == "isBlank":
        candidate_has_full_guard = bool(blank_check_re.search(candidate_search_corpus))
    elif baseline_predicate_kind == "isEmpty":
        candidate_has_full_guard = bool(empty_check_re.search(candidate_search_corpus))

    candidate_has_null_only = bool(null_only_re.search(candidate_search_corpus))

    # Identify exception name strictly within the method slice
    exc_re = re.compile(r"throw\s+new\s+(\w+Exception)\s*\(")
    exc_match = (
        exc_re.search(added_text)
        or exc_re.search(removed_text)
        or exc_re.search(baseline_method_text)
        or (exc_re.search(candidate_method_text) if candidate_method_text else None)
    )
    exception_name = exc_match.group(1) if exc_match else None

    # Resolve contract oracle
    oracle = resolve_contract_oracle(exception_name, contract_file_path=contract_file_path, search_dir=search_dir)

    pattern_name = "STRING_NULL_AND_BLANK_GUARD" if baseline_predicate_kind == "isBlank" else "STRING_NULL_AND_EMPTY_GUARD"

    # Case A: Candidate preserves or restores the full guard -> Safe patch control
    if candidate_has_full_guard:
        return CRAReport(
            analysis_timestamp=now_ts,
            status="COMPLETED",
            diff_target_file=target_file,
            target_method=method_name,
            target_parameter={"name": param_name, "type": param_type},
            predicate_analysis={
                "baseline_predicate": f"{param_name} == null || {param_name}.{baseline_predicate_kind}()",
                "candidate_predicate": f"{param_name} == null || {param_name}.{baseline_predicate_kind}()",
                "pattern": pattern_name,
                "delta": "NONE",
            },
            contract_oracle=asdict(oracle),
            findings=[],
            overall_verdict="NO_RIPPLE_DETECTED",
            recommendation="REVIEW_REQUIRED",
            recommendation_reason="Baseline guard conditions are preserved in candidate. Standard review required.",
        )

    # Case B: Candidate has positive evidence of weakening to null-only
    if candidate_has_null_only and not candidate_has_full_guard:
        # Check contract oracle availability
        if oracle.status != "AVAILABLE":
            return CRAReport(
                analysis_timestamp=now_ts,
                status="COMPLETED",
                diff_target_file=target_file,
                target_method=method_name,
                target_parameter={"name": param_name, "type": param_type},
                predicate_analysis={
                    "baseline_predicate": f"{param_name} == null || {param_name}.{baseline_predicate_kind}()",
                    "candidate_predicate": f"{param_name} == null",
                    "pattern": pattern_name,
                    "delta": f"{param_name}.{baseline_predicate_kind}() guard omitted in candidate",
                },
                contract_oracle=asdict(oracle),
                findings=[],
                overall_verdict="INCONCLUSIVE",
                recommendation="ESCALATE",
                recommendation_reason="Guard was weakened, but contract oracle is unavailable. Safety cannot be established.",
            )

        # Derive boundary inputs according to precise predicate semantics:
        # - isBlank(): "" and whitespace-only both evaluate to true in baseline guard
        # - isEmpty(): "" evaluates to true; whitespace-only evaluates to false (not covered by isEmpty)
        uncovered_inputs = [{"value": "", "category": "empty_string"}]
        if baseline_predicate_kind == "isBlank":
            uncovered_inputs.append({"value": "   ", "category": "whitespace_only"})

        findings: list[dict[str, Any]] = []
        for inp in uncovered_inputs:
            bf = BoundaryFinding(
                finding_type="PREDICTED_STATIC",
                verified_at_runtime=False,
                boundary_input={"parameter": param_name, "value": inp["value"], "category": inp["category"]},
                expected_behavior={
                    "action": "THROW_EXCEPTION",
                    "exception": oracle.exception_class,
                    "expected_http_status": oracle.expected_http_status,
                },
                predicted_behavior={
                    "guard_action": "GUARD_BYPASSED",
                    "downstream_behavior": "UNKNOWN_WITHOUT_RUNTIME_OBSERVATION",
                    "predicted_http_status": None,
                    "predicted_return_value": None,
                    "note": "Downstream return value and HTTP status are unknown without runtime execution.",
                },
                verdict="CONTRACT_VIOLATION",
                divergence_explanation=(
                    f"Input '{inp['value']}' satisfies baseline guard ({baseline_predicate_kind}) and is expected to raise "
                    f"{oracle.exception_class} (HTTP {oracle.expected_http_status}), but bypasses candidate null-only guard. "
                    "Downstream response is unverified without runtime execution."
                ),
                runtime_execution={
                    "status": "NOT_EXECUTED",
                    "observed_http_code": None,
                    "observed_body": None,
                },
            )
            findings.append(asdict(bf))

        return CRAReport(
            analysis_timestamp=now_ts,
            status="COMPLETED",
            diff_target_file=target_file,
            target_method=method_name,
            target_parameter={"name": param_name, "type": param_type},
            predicate_analysis={
                "baseline_predicate": f"{param_name} == null || {param_name}.{baseline_predicate_kind}()",
                "candidate_predicate": f"{param_name} == null",
                "pattern": pattern_name,
                "delta": f"{param_name}.{baseline_predicate_kind}() guard omitted in candidate",
            },
            contract_oracle=asdict(oracle),
            findings=findings,
            overall_verdict="CONTRACT_VIOLATION",
            recommendation="ESCALATE",
            recommendation_reason=(
                f"Candidate patch introduces predicted contract violation on boundary inputs: "
                f"{', '.join(inp['category'] for inp in uncovered_inputs)}. Human escalation required."
            ),
        )

    # Case C: Unrelated or unproven changes
    return CRAReport(
        analysis_timestamp=now_ts,
        status="INCONCLUSIVE",
        diff_target_file=target_file,
        target_method=method_name,
        target_parameter={"name": param_name, "type": param_type},
        predicate_analysis={"pattern": "UNSUPPORTED_OR_UNKNOWN_SYNTAX", "delta": "Diff does not match positive guard weakening patterns"},
        contract_oracle=asdict(oracle),
        findings=[],
        overall_verdict="INCONCLUSIVE",
        recommendation="ESCALATE",
        recommendation_reason="Diff syntax is outside the supported CRA prototype subset. Human escalation required.",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AutoImmune Causal Ripple Analysis (CRA) — Isolated Research Prototype v0.1"
    )
    parser.add_argument("--diff", required=True, help="Path to unified diff file (or '-' for stdin)")
    parser.add_argument("--baseline-source", required=False, help="Path to baseline Java source file")
    parser.add_argument("--candidate-source", required=False, help="Path to candidate Java source file")
    parser.add_argument("--contract-file", required=False, help="Path to contract exception Java file")
    parser.add_argument("--search-dir", required=False, help="Search directory for contract exceptions")

    args = parser.parse_args()

    # Read diff
    if args.diff == "-":
        diff_text = sys.stdin.read()
    else:
        diff_path = Path(args.diff)
        if not diff_path.exists():
            sys.stderr.write(f"Error: Diff file not found: {diff_path}\n")
            return 2
        diff_text = diff_path.read_text(encoding="utf-8", errors="replace")

    # Read baseline source
    baseline_text: str | None = None
    if args.baseline_source:
        b_path = Path(args.baseline_source)
        if not b_path.exists():
            sys.stderr.write(f"Error: Baseline source not found: {b_path}\n")
            return 2
        baseline_text = b_path.read_text(encoding="utf-8", errors="replace")

    # Read candidate source
    candidate_text: str | None = None
    if args.candidate_source:
        c_path = Path(args.candidate_source)
        if not c_path.exists():
            sys.stderr.write(f"Error: Candidate source not found: {c_path}\n")
            return 2
        candidate_text = c_path.read_text(encoding="utf-8", errors="replace")

    contract_path = Path(args.contract_file) if args.contract_file else None
    search_dir = Path(args.search_dir) if args.search_dir else None

    report = analyze_causal_ripple(
        diff_text=diff_text,
        baseline_source_text=baseline_text,
        candidate_source_text=candidate_text,
        contract_file_path=contract_path,
        search_dir=search_dir,
    )

    sys.stdout.write(report.to_json() + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
