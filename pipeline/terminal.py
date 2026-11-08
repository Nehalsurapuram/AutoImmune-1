"""Terminal visual presentation and formatting for AutoImmune CLI.

Provides modern, structured engineering terminal output:
- Prominent project header and stage indicators
- Restrained color palette (Cyan, Green, Red, Yellow, Grey)
- ANSI terminal colors with plain-text fallback (Windows PowerShell & CMD compatible)
- Aligned validation gate tables
- Distinct human approval section
- Final execution summary
"""
from __future__ import annotations

import os
import sys
from typing import Sequence


def _supports_color() -> bool:
    """Check if the active terminal supports ANSI colors."""
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    # If stdout is a TTY or explicitly requested
    return sys.stdout.isatty() or bool(os.environ.get("FORCE_COLOR"))


def _init_windows_console() -> None:
    """Enable Windows 10+ Virtual Terminal Processing for ANSI colors."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32
            h_out = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            if h_out and h_out != -1:
                mode = wintypes.DWORD()
                if kernel32.GetConsoleMode(h_out, ctypes.byref(mode)):
                    # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                    kernel32.SetConsoleMode(h_out, mode.value | 0x0004)
        except Exception:
            pass


# Initialize Windows console on module load
_init_windows_console()


class Style:
    """ANSI color and formatting constants with plain-text fallback."""

    def __init__(self, enabled: bool | None = None):
        self.enabled = _supports_color() if enabled is None else enabled

    def _c(self, code: str) -> str:
        return code if self.enabled else ""

    @property
    def RESET(self) -> str:
        return self._c("\033[0m")

    @property
    def BOLD(self) -> str:
        return self._c("\033[1m")

    @property
    def DIM(self) -> str:
        return self._c("\033[90m")

    @property
    def CYAN(self) -> str:
        return self._c("\033[36m")

    @property
    def BOLD_CYAN(self) -> str:
        return self._c("\033[1;36m")

    @property
    def GREEN(self) -> str:
        return self._c("\033[32m")

    @property
    def BOLD_GREEN(self) -> str:
        return self._c("\033[1;32m")

    @property
    def RED(self) -> str:
        return self._c("\033[31m")

    @property
    def BOLD_RED(self) -> str:
        return self._c("\033[1;31m")

    @property
    def YELLOW(self) -> str:
        return self._c("\033[33m")

    @property
    def BOLD_YELLOW(self) -> str:
        return self._c("\033[1;33m")

    @property
    def GREY(self) -> str:
        return self._c("\033[37m")


style = Style()


def _safe_symbol(unicode_char: str, ascii_fallback: str) -> str:
    """Return unicode symbol if encodable by stdout, otherwise ascii fallback."""
    try:
        encoding = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
        unicode_char.encode(encoding)
        return unicode_char
    except (UnicodeEncodeError, LookupError):
        return ascii_fallback


SYM_PASS = _safe_symbol("✓", "PASS")
SYM_FAIL = _safe_symbol("✗", "FAIL")
SYM_WARN = _safe_symbol("!", "WARN")
SYM_RUN = _safe_symbol("→", "->")
SYM_SKIP = _safe_symbol("○", "-")


def format_status(status: str) -> str:
    """Format status with appropriate symbol and color."""
    s = (status or "").upper()
    if s in ("PASS", "HEALTHY", "PROMOTED", "AUTO_APPLY", "AUTO"):
        return f"{style.GREEN}{SYM_PASS} {s}{style.RESET}"
    if s in ("FAIL", "REJECT", "ERROR", "ROLLED_BACK"):
        return f"{style.RED}{SYM_FAIL} {s}{style.RESET}"
    if s in ("WARNING", "ESCALATE", "PENDING", "AWAITING_REVIEW"):
        return f"{style.YELLOW}{SYM_WARN} {s}{style.RESET}"
    if s in ("NOT_RUN", "NOT RUN", "SKIP", "NONE"):
        return f"{style.DIM}{SYM_SKIP} {s}{style.RESET}"
    return status


def print_header(run_id: str, fault: str, diag_mode: str, patch_mode: str, extra_note: str | None = None) -> None:
    """Display the required modern AutoImmune terminal header."""
    w = 78
    sep_heavy = "=" * w
    sep_subtle = "-" * w

    print(sep_heavy)
    print(f"{style.BOLD_CYAN}AUTOIMMUNE{style.RESET}")
    print(f"{style.BOLD}AUTOMATED SOFTWARE REPAIR ENGINE{style.RESET}")
    print(sep_subtle)
    print(f"Run ID:         {style.BOLD}{run_id}{style.RESET}")
    print(f"Fault:          {style.BOLD}{fault}{style.RESET}")
    print(f"Diagnosis Mode: {diag_mode}")
    print(f"Patch Mode:     {patch_mode}")
    if extra_note:
        print(f"{style.DIM}{extra_note}{style.RESET}")
    print(sep_heavy, flush=True)


def print_stage(step_num: int, total_steps: int, title: str, elapsed_s: float | None = None) -> None:
    """Display clean numbered pipeline stage with visual separator.
    
    Includes '[n/10]' in supporting text so existing test suites pass.
    """
    time_str = f"  (+{elapsed_s:.0f}s)" if elapsed_s is not None else ""
    # Main stage banner
    print(f"\n{style.DIM}------------------------------------------------------------------------------{style.RESET}")
    print(f"{style.BOLD_CYAN}[{step_num:02d}/{total_steps:02d}] {title.upper()}{style.RESET}")
    # Supporting detail line with [{step_num}/10] for traceability and backward compatibility
    print(f"{style.DIM}  Stage [{step_num}/{total_steps}]{time_str}{style.RESET}", flush=True)


def print_gate_table(candidates: Sequence[dict]) -> None:
    """Print aligned candidate validation gate table (V0 to V3)."""
    headers = ["CANDIDATE ID", "V0", "V1", "V2", "V3", "DECISION"]
    col_widths = [26, 8, 8, 8, 8, 14]

    def render_row(cells: list[str]) -> str:
        padded = [str(c).ljust(w) for c, w in zip(cells, col_widths)]
        return " | ".join(padded)

    header_line = render_row(headers)
    sep_line = "-+-".join("-" * w for w in col_widths)

    print(f"\n{style.BOLD}{header_line}{style.RESET}")
    print(f"{style.DIM}{sep_line}{style.RESET}")

    for c in candidates:
        cid = c.get("candidate_id", "")
        # Gates dict or subdict
        gates_dict = c.get("gates", {})
        if "gates" in gates_dict:
            gates_dict = gates_dict["gates"]

        v0_raw = gates_dict.get("V0", {})
        v1_raw = gates_dict.get("V1", {})
        v2_raw = gates_dict.get("V2", {})
        v3_raw = gates_dict.get("V3", {})

        v0 = v0_raw.get("status", v0_raw) if isinstance(v0_raw, dict) else str(v0_raw)
        v1 = v1_raw.get("status", v1_raw) if isinstance(v1_raw, dict) else str(v1_raw)
        v2 = v2_raw.get("status", v2_raw) if isinstance(v2_raw, dict) else str(v2_raw)
        v3 = v3_raw.get("status", v3_raw) if isinstance(v3_raw, dict) else str(v3_raw)

        dec = c.get("decision", "")

        def _cell(st: str) -> str:
            st_u = st.upper()
            if st_u == "PASS":
                return f"{style.GREEN}PASS{style.RESET}"
            if st_u in ("FAIL", "ERROR"):
                return f"{style.RED}{st_u}{style.RESET}"
            if st_u in ("NOT_RUN", "-"):
                return f"{style.DIM}-{style.RESET}"
            return st

        def _dec(d: str) -> str:
            d_u = d.upper()
            if d_u == "AUTO_APPLY":
                return f"{style.BOLD_GREEN}AUTO_APPLY{style.RESET}"
            if d_u == "ESCALATE":
                return f"{style.BOLD_YELLOW}ESCALATE{style.RESET}"
            if d_u == "REJECT":
                return f"{style.BOLD_RED}REJECT{style.RESET}"
            return d

        row_text = (
            f"{cid.ljust(col_widths[0])} | "
            f"{_cell(v0).ljust(col_widths[1] + (len(_cell(v0)) - len(v0)))} | "
            f"{_cell(v1).ljust(col_widths[2] + (len(_cell(v1)) - len(v1)))} | "
            f"{_cell(v2).ljust(col_widths[3] + (len(_cell(v2)) - len(v2)))} | "
            f"{_cell(v3).ljust(col_widths[4] + (len(_cell(v3)) - len(v3)))} | "
            f"{_dec(dec)}"
        )
        print(row_text)
    print()


def _safe_out(msg: str, out=print) -> None:
    try:
        out(msg)
    except Exception:
        pass


def print_approval_section(
    candidate_id: str,
    tier: str,
    reasons: Sequence[str],
    diff: str,
    policy_version: str | None = None,
    out=print,
) -> None:
    """Display visually distinct human approval section."""
    sep = "=" * 78
    subsep = "-" * 78

    _safe_out(sep, out)
    _safe_out(f"{style.BOLD_YELLOW}HUMAN APPROVAL REQUIRED{style.RESET}", out)
    _safe_out(subsep, out)
    _safe_out(f"Candidate:  {style.BOLD}{candidate_id}{style.RESET}", out)
    _safe_out(f"Risk Level: {style.BOLD_YELLOW}{tier}{style.RESET}" + (f"   (Policy: {policy_version})" if policy_version else ""), out)
    _safe_out("Reason:", out)
    for r in reasons:
        _safe_out(f"  • {r}", out)
    _safe_out(subsep, out)
    _safe_out(f"{style.DIM}Candidate Unified Diff:{style.RESET}", out)
    _safe_out(diff.rstrip(), out)
    _safe_out(subsep, out)
    _safe_out(f"{style.BOLD}Awaiting reviewer decision:{style.RESET}", out)
    _safe_out("[APPROVE / REJECT]", out)
    _safe_out(sep, out)


def print_execution_summary(
    run_id: str,
    fault: str,
    candidates_count: int,
    val_passed_count: int,
    val_failed_count: int,
    auto_apply_count: int,
    escalated_count: int,
    rejected_count: int,
    deployment_status: str,
    baseline_status: str,
    evidence_saved: str,
    final_status: str,
    seconds: float | None = None,
) -> None:
    """Display final execution summary."""
    sep = "=" * 78
    subsep = "-" * 78

    time_note = f" ({seconds:.0f}s)" if seconds is not None else ""
    print(f"\n{sep}")
    print(f"{style.BOLD_CYAN}AUTOIMMUNE EXECUTION SUMMARY{style.RESET}{time_note}")
    print(subsep)
    print(f"Run ID:               {style.BOLD}{run_id}{style.RESET}")
    print(f"Fault:                {style.BOLD}{fault}{style.RESET}")
    print()
    print(f"Candidates Generated: {candidates_count}")
    print(f"Validation Passed:    {style.GREEN}{val_passed_count}{style.RESET}")
    print(f"Validation Failed:    {style.RED if val_failed_count else style.DIM}{val_failed_count}{style.RESET}")
    print(f"Auto Apply:           {style.GREEN}{auto_apply_count}{style.RESET}")
    print(f"Escalated:            {style.YELLOW if escalated_count else style.DIM}{escalated_count}{style.RESET}")
    print(f"Rejected:             {style.RED if rejected_count else style.DIM}{rejected_count}{style.RESET}")
    print()
    print(f"Deployment Status:    {deployment_status}")
    print(f"Baseline Status:      {baseline_status}")
    print(f"Evidence Saved:       {evidence_saved}")
    print(subsep)
    print(f"Final Status:         {style.BOLD}{final_status}{style.RESET}")
    print(f"{sep}\n", flush=True)
