# AutoImmune: Research Reproduction Guide & Replication Protocol

**Author:** AutoImmune Research Engineering Consortium  
**Date:** 2026-11-11  
**Target Venue Artifact Evaluation:** Badges for *Artifacts Available*, *Artifacts Evaluated & Functional*, and *Results Reproduced*.  
**One-Click Reproduction Script:** [`tools/reproduce_research.py`](file:///d:/14/tools/reproduce_research.py)

---

## 1. Reproduction Overview & Core Principles

AutoImmune is architected for **zero-variance deterministic reproducibility**. To eliminate the "it worked on my machine" reproducibility crisis in empirical software engineering:
1. **Raw Evidence Immutability:** Raw experimental records in [`results/evidence.jsonl`](file:///d:/14/results/evidence.jsonl) and [`runs/`](file:///d:/14/runs/) are never overwritten, edited, or suppressed.
2. **Deterministic Exclusion Manifest:** All filtering of contaminated or invalid runs is governed by a versioned JSON manifest ([`config/analysis_exclusions.json`](file:///d:/14/config/analysis_exclusions.json)).
3. **Offline Ground Truth:** Independent oracle evaluations ([`results/oracle_report.jsonl`](file:///d:/14/results/oracle_report.jsonl)) are generated offline and joined strictly during evaluation, ensuring zero leakage into model prompts or pipeline decisions.
4. **Frozen Docker Environments:** All compilation, test suites, and security scans execute in pinned, air-gapped Docker images (`maven:3.9-eclipse-temurin-17` and `semgrep/semgrep:1.100.0`).

---

## 2. Software Requirements & System Environment

### 2.1 Host Environment
- **Operating System:** Windows 10/11, Ubuntu 22.04 LTS, or macOS (tested on Windows 11).
- **Python Runtime:** Python 3.10, 3.11, or 3.12 (verified on Python 3.12.6).
- **Container Engine:** Docker Desktop or Docker CE $\ge 24.0$ (with Linux containers enabled).
- **Disk Space:** $\ge 15\text{ GB}$ available space (for container layers and local Maven repository cache).
- **Memory:** $\ge 8\text{ GB}$ RAM (Docker allocated $\ge 4\text{ GB}$).

### 2.2 Python Dependencies
The virtual environment requirements are frozen in `requirements.txt`:
```text
pytest>=8.0.0
pyyaml>=6.0.1
requests>=2.31.0
jsonschema>=4.21.0
scipy>=1.11.0
```

---

## 3. One-Click Reproduction Instructions

To reproduce every table, metric, paired test, and visual artifact presented in the research paper from the raw evidence:

### 3.1 Full Analysis & Artifact Regeneration
Execute from the repository root:
```powershell
python tools/reproduce_research.py
```
This single command executes in $\approx 5\text{ seconds}$ and performs:
1. **Environment Verification:** Validates Python version and workspace paths.
2. **Input Hashing:** Verifies SHA-256 hashes of `evidence.jsonl`, `analysis_exclusions.json`, and all 12 `labels.json` files.
3. **Pilot Analysis Generation:** Executes `analyse.py` to regenerate all 11 CSV files and [`results/pilot_report.md`](file:///d:/14/results/pilot_report.md).
4. **Dashboard Compilation:** Executes `tools/make_dashboard.py` to generate the interactive standalone HTML visualization ([`results/dashboard.html`](file:///d:/14/results/dashboard.html)).
5. **Statistical Recalculation:** Recomputes paired McNemar discordance tests ($\chi^2 = 9.0909, p = 0.002569$), Wilson 95% confidence intervals, and exports [`docs/research/final_results.csv`](file:///d:/14/docs/research/final_results.csv), [`docs/research/policy_comparison.csv`](file:///d:/14/docs/research/policy_comparison.csv), and [`docs/research/fault_level_results.csv`](file:///d:/14/docs/research/fault_level_results.csv).
6. **Self-Verification:** Runs `analyse.py --check` to guarantee byte-for-byte consistency.

### 3.2 Non-Destructive Verification Check
To verify that existing results match the raw inputs without altering any files:
```powershell
python tools/reproduce_research.py --check
```
Exit code `0` confirms that all published artifacts are 100% current and uncorrupted.

### 3.3 Full Test Suite Execution
To verify the entire 250-test regression suite covering orchestrators, sandboxes, detectors, and statistical estimators:
```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
**Expected Output:** `258 passed, 16 deselected in ~12-15s` (using `-m "not docker"`). All unit tests including the 5 baseline restoration idempotency tests and orchestrator regression tests pass cleanly.

---

## 4. Audit Trail & Cryptographic Provenance

Every generated report embeds input hashes to guarantee traceability:

| Artifact Description | File Path | Current SHA-256 (Truncated) |
| :--- | :--- | :---: |
| **Raw Experimental Evidence** | `results/evidence.jsonl` | `30889cbf6bb1...` |
| **Analysis Exclusion Manifest** | `config/analysis_exclusions.json` | `07809b21c3d4...` |
| **F01 Oracle Labels** | `faults/F01/candidates/labels.json` | `f2f2dcb9564c...` |
| **F02 Oracle Labels** | `faults/F02/candidates/labels.json` | `d1a4148b758b...` |
| **F03 Oracle Labels** | `faults/F03/candidates/labels.json` | `86bc5281e398...` |
| **F04 Oracle Labels** | `faults/F04/candidates/labels.json` | `f8d9619bd7d7...` |
| **F05 Oracle Labels** | `faults/F05/candidates/labels.json` | `0683a3fa1296...` |
| **F06 Oracle Labels** | `faults/F06/candidates/labels.json` | `fe0202f46b53...` |
| **F07 Oracle Labels** | `faults/F07/candidates/labels.json` | `98fcee1db5f7...` |
| **F08 Oracle Labels** | `faults/F08/candidates/labels.json` | `57ebd2455d16...` |
| **F09 Oracle Labels** | `faults/F09/candidates/labels.json` | `9ab837b8302d...` |
| **F11 Oracle Labels** | `faults/F11/candidates/labels.json` | `72f3045f4735...` |
| **F12 Oracle Labels** | `faults/F12/candidates/labels.json` | `83948c72bebb...` |
| **F13 Oracle Labels** | `faults/F13/candidates/labels.json` | `365813c6ef6f...` |

---

## 5. Re-running End-to-End Pipeline Experiments (Optional)

*Note: Rerunning live Docker experiments rebuilds containers and requires the Docker daemon. It is NOT required for statistical analysis reproduction.*

To execute an end-to-end self-healing run on fault `F06` under rule-based diagnosis and scripted patching:
```powershell
python -m pipeline run --fault F06 --diag-mode rule --patch-mode scripted
```
To evaluate against a live local Ollama model:
```powershell
$env:LLM_BASE_URL = "http://localhost:11434/v1"
$env:LLM_MODEL = "qwen2.5-coder:7b"
python -m pipeline run --fault F06 --diag-mode live --patch-mode live
```
Every execution emits a complete audit package to `runs/<run_id>/` and appends candidate rows to `results/evidence.jsonl`.
