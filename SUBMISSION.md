# AutoImmune: submission guide

**Team:** Agni M N, Pradeep S, S Nehal  **Guide:** Mrs. M. Shona

## Start here
| Read | What it is |
|---|---|
| [docs/PROJECT_REPORT.md](docs/PROJECT_REPORT.md) | The project report: problem, design, results, limitations |
| `results/dashboard.html` | Interactive evidence dashboard; open it in a browser, works offline |
| `results/pilot_report.md` | All result tables, generated from the raw evidence |
| [docs/audit/AUDIT_BASELINE.md](docs/audit/AUDIT_BASELINE.md) | Integrity audit of our own evidence, and what was fixed |
| [README.md](README.md) | Setup, tests, and current pilot status |

## Folder map
| Folder | Contents |
|---|---|
| `app/` | The Java 17 / Spring Boot "order-service" being healed |
| `faults/F01, F04, F06/` | Seeded faults: description, injection diff, target test, scripted candidate patches |
| `pipeline/` | Python orchestrator: detector, LLM/rule providers, Docker sandbox gates, decision engine, deployment and rollback, evidence recording, provenance |
| `config/decision.yaml` | Every threshold used by the decision engine and health window |
| `tests/` | 205 automated tests (16 need Docker) |
| `results/` | Generated tables and dashboard; `evidence.jsonl` holds one raw row per candidate evaluation |
| `runs/<run_id>/` | Raw artifacts of every pipeline run (incident, diagnosis, patches, gate logs, decisions, approvals, deployments, rollbacks) |
| `cache/` | Recorded LLM requests and responses (for replay) |
| `docs/` | Report, audit, phase notes, runbook |
| `tools/` | Dashboard generator, audit manifest tool, demo helpers |

## Key evidence (runs of 2026-11-08)
- Full self-healing runs: `runs/f06-rule-scripted-20261108t173444z`, `runs/f01-rule-scripted-20261108t174806z`,
  `runs/f04-rule-scripted-20261108t175754z`.
- Human approval, then deployment: `runs/f04-rule-scripted-20261108t175754z/F04-scripted-835a25e8/`.
- Automatic rollback (staged demo): `runs/f06-rule-scripted-20261108t180955z/F06-scripted-7509cb64/rollback.json`.

## Run it (Windows, needs Python 3.12 and Docker Desktop)
```
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -r requirements.lock
.\.venv\Scripts\python -m pytest -rs
.\.venv\Scripts\python -m pipeline run --fault F06 --diag-mode rule --patch-mode scripted
.\.venv\Scripts\python analyse.py --check
```
The `.venv` folder is deliberately not included: a virtual environment only works on the machine that created it.
