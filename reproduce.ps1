# Regenerate every table, figure source and manifest from the raw evidence, and log hashes.
#
#   powershell -ExecutionPolicy Bypass -File reproduce.ps1            # analysis only (minutes, no Docker needed)
#   powershell -ExecutionPolicy Bypass -File reproduce.ps1 -Oracle    # also re-run the offline oracle (Docker, ~30+ min)
#   powershell -ExecutionPolicy Bypass -File reproduce.ps1 -Tests     # also run the full test suite (Docker, ~10 min)
#
# Raw inputs (never rewritten): results/evidence.jsonl, runs/*/, faults/*/, cache/.
# Outputs: results/*.csv, results/pilot_report.md, results/dashboard.html, results/oracle_report.jsonl (with -Oracle),
#          docs/audit/baseline_manifest.json, and docs/audit/reproduction_log.txt with SHA-256 of every output.
param([switch]$Oracle, [switch]$Tests)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.12 -m venv .venv
    .\.venv\Scripts\pip install -r requirements.lock
}
$py = ".\.venv\Scripts\python.exe"

if ($Tests)  { & $py -m pytest -rs;           if ($LASTEXITCODE) { throw "tests failed" } }
else         { & $py -m pytest -q -m "not docker"; if ($LASTEXITCODE) { throw "tests failed" } }
if ($Oracle) { & $py tools\oracle.py --workers 3; if ($LASTEXITCODE) { throw "oracle failed" } }

& $py analyse.py --quiet;              if ($LASTEXITCODE) { throw "analyse failed" }
& $py analyse.py --check;              if ($LASTEXITCODE) { throw "results are stale after regeneration" }
& $py tools\make_dashboard.py | Out-Null
& $py tools\audit_baseline.py --out docs\audit\baseline_manifest.json | Out-Null

$log = "docs\audit\reproduction_log.txt"
"Reproduction run $(Get-Date -Format o) on $env:COMPUTERNAME, code $(git rev-parse --short HEAD)" | Out-File $log -Encoding utf8
Get-ChildItem results -File | Where-Object { $_.Extension -in ".csv", ".md", ".jsonl", ".html" } | Sort-Object Name |
    ForEach-Object { "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), "results/$($_.Name)" } |
    Out-File $log -Append -Encoding utf8
Write-Host "Done. Hashes in $log"
