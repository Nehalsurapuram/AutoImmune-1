# Live demo script (about 10–12 minutes)

## A. One hour before: checklist
Run these in the project folder (PowerShell). Every step must succeed before the demo.

```
# 1. Docker Desktop open and "Engine running"
docker version

# 2. Stop other projects' containers (they slow the gates)
docker stop observability-grafana observability-promtail observability-loki observability-prometheus observability-backend observability-frontend observability-postgres

# 3. Python environment works and the fast tests pass (about 10 s)
.\.venv\Scripts\python -m pytest -m "not docker" -q

# 4. Reports are current
.\.venv\Scripts\python analyse.py --check
.\.venv\Scripts\python tools\make_dashboard.py

# 5. Open the dashboard in the browser and leave the tab open
start results\dashboard.html
```

Also: plug in the charger, turn off sleep and notifications, make the terminal font large (Ctrl + mouse wheel),
and open two terminal windows in the project folder.

## B. The demo

| Time | You do | You say |
|---|---|---|
| 0:00 | Terminal 1: start the live run (command below) | "AutoImmune heals a Java microservice. I'm injecting a real configuration fault now; the whole loop runs on its own." |
| 0:30 | Switch to the **dashboard**, Executive Overview | "While it runs, here is the evidence from all our runs. Every number is regenerated from raw run records, never typed in." |
| 1:30 | Dashboard: **Validation Gates** | "Four gates in an isolated Docker sandbox with no network: V0 compiles, V1 target test, V2 full test suite, V3 Semgrep security scan. Each catches a different bad patch: ineffective at V1, regressive at V2, insecure at V3." |
| 3:00 | Dashboard: **Policy Comparison** | "Same patches, different policies: target test only would auto-apply 20 of 26 unsafe patches, adding the full suite 13, our full policy 7, and no correct patch was rejected." |
| 4:00 | Back to terminal 1: point at the stage lines | "It detected the fault within seconds, diagnosed it, and is gating 5 candidate patches now." |
| ~5:30 | **HUMAN APPROVAL REQUIRED** appears | "This patch edits a sensitive config file, so the policy will not auto-apply it. It asks a human." Let the examiner read the diff. Type **approve**. |
| ~6:30 | Run continues: deploy and health window | "It builds a new image, swaps it in, and watches health and latency for 30 s. If anything breaches, it swaps back automatically." |
| ~9:30 | Final summary: **PROMOTED** | "Promoted. Note the wording: the health window passed. The pipeline does not claim the patch is correct." |
| 10:00 | Dashboard: **Approval & Rollback** | "We also demonstrated automatic rollback: a planted slow patch passed all four gates, then breached the 2-second latency limit and was rolled back in 4 seconds." |
| 11:00 | Dashboard: **Known Limitations** | "Our key finding: overfitting patches pass every gate. Tests alone cannot prove a fix is correct. That's why the next step is independent hidden-test oracles." |

**Live run command (F04, human approval in the middle, about 10 min):**
```
.\.venv\Scripts\python -m pipeline run --fault F04 --diag-mode rule --patch-mode scripted
```
At the prompt, type only `approve` and press Enter. **Do not paste anything else.**

**If you have less than 10 minutes, use F01 instead (about 6 min, no prompt):**
```
.\.venv\Scripts\python -m pipeline run --fault F01 --diag-mode rule --patch-mode scripted
```

**Optional second live run, rollback (about 6.5 min):**
```
.\.venv\Scripts\python -m pipeline run --fault F06 --diag-mode rule --patch-mode scripted --candidate F06-scripted-7509cb64
```

## C. If something fails live
Stay calm and say: *"A failed run is recorded too: the pipeline never hides an error."* Then show the recorded runs:

| Show | Where |
|---|---|
| Human approval, then deploy | `runs\f04-rule-scripted-20261108t175754z\F04-scripted-835a25e8\approval.json` and `deploy.json` |
| Rollback | `runs\f06-rule-scripted-20261108t180955z\F06-scripted-7509cb64\rollback.json` |
| Full run summary | `runs\f01-rule-scripted-20261108t174806z\summary.json` |
| All tables | `results\pilot_report.md` |

Open a file quickly: `notepad runs\f06-rule-scripted-20261108t180955z\F06-scripted-7509cb64\rollback.json`

Common fixes:
- `failed to connect to the docker API`: Docker Desktop isn't running. Start it and wait for "Engine running".
- `No Python at ...`: run `py -3.12 -m venv .venv` then `.\.venv\Scripts\pip install -r requirements.lock`.
- The run stops at step 2 or 3: run `docker ps`. If an old `autoimmune-app` is stuck, `docker rm -f autoimmune-app`, then rerun.

## D. Likely viva questions, with honest answers

**Is the AI fixing the bugs?**
The AI is used only for diagnosis and drafting patches. In our pilot, local models (qwen2.5-coder 7b and 1.5b) did not
produce a patch that passed the target test (0 of 17), and we report that openly. The demo uses hand-built candidate
patches so the gates and the decision logic can be tested in a controlled way.

**Why not let the AI decide too (an agent)?**
For safety and auditability: every decision is deterministic code with written reasons, so it can be checked and
reproduced.

**How do you know the sandbox is isolated?**
A test runs inside the sandbox and tries DNS, TCP and HTTPS: all are blocked. A control run on a normal network
succeeds, which proves the test can detect access (`docs/audit/isolation_test.txt`).

**What's novel?**
Not repair or rollback by themselves. We measure what each layer of evidence catches on the same patches, and we show
honestly where tests fail (overfitting).

**What are the limitations?**
Three seeded faults, one service, no independent labels yet, local laptop deployment (a container swap, not a canary),
and only one reviewer.

**What would you do next?**
Hidden-test oracles with blind labels, more faults, stronger models, and side-by-side canary deployment with p95
latency.
