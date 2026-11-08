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
| [docs/DEMO.md](docs/DEMO.md) | Live demo script, pre-demo checklist, fallback plan |

## Folder map
| Folder | Contents |
|---|---|
| `app/` | The Java 17 / Spring Boot "order-service" being healed |
| `faults/F01, F04, F06/` | Seeded faults: description, injection diff, target test, scripted candidate patches, oracle labels (`candidates/labels.json`). Hidden oracle tests (`hidden_tests/`) are kept out of git and out of the sandbox |
| `pipeline/` | Python orchestrator: detector, LLM/rule providers, Docker sandbox gates, decision engine, deployment and rollback, evidence recording, provenance |
| `config/decision.yaml` | Every threshold used by the decision engine and health window |
| `tests/` | 249 automated tests (16 need Docker) |
| `results/` | Generated tables and dashboard; `evidence.jsonl` holds one raw row per candidate evaluation |
| `runs/<run_id>/` | Raw artifacts of every pipeline run (incident, diagnosis, patches, gate logs, decisions, approvals, deployments, rollbacks) |
| `cache/` | Recorded LLM requests and responses (for replay) |
| `docs/` | Report, audit, phase notes, runbook |
| `tools/` | Independent oracle (`oracle.py`), dashboard generator, healthy-load watch, audit manifest tool |

## Key evidence (runs of 2026-11-08)
- Full self-healing runs: `runs/f06-rule-scripted-20261108t173444z`, `runs/f01-rule-scripted-20261108t174806z`,
  `runs/f04-rule-scripted-20261108t175754z`.
- Human approval, then deployment: `runs/f04-rule-scripted-20261108t175754z/F04-scripted-835a25e8/`.
- Automatic rollback (staged demo, 5.1 s, restored image ID verified):
  `runs/f06-rule-scripted-20261108t201808z/F06-scripted-7509cb64/rollback.json`.
- Live AI (gpt-oss-120b) end-to-end runs: `runs/f06-live-live-20261108t193456z` (correct repair deployed),
  `runs/f01-live-live-20261108t195433z` and `runs/f04-live-live-20261108t200721z` (gate-passing patches the oracle
  labels incorrect).
- Independent oracle labels: `results/oracle_report.jsonl`. No false alarm under healthy load:
  `runs/healthy-watch-20261108t182609z`.

## Run it (Windows, needs Python 3.12 and Docker Desktop)
```
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -r requirements.lock
.\.venv\Scripts\python -m pytest -rs
.\.venv\Scripts\python -m pipeline run --fault F06 --diag-mode rule --patch-mode scripted
.\.venv\Scripts\python analyse.py --check
```
The `.venv` folder is deliberately not included: a virtual environment only works on the machine that created it.
