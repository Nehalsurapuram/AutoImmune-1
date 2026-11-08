# Live demo script (about 10–13 minutes, depending on gate speed and how long the approval takes)

## A. One hour before: checklist
Run these in the project folder (PowerShell). Every step must succeed before the demo.

```
# 1. Docker Desktop open and "Engine running"
docker version

# 2. Stop other projects' containers (they share the laptop's CPU and memory with the gate containers;
#    the audit treats gate timings taken with them running as not clean)
docker stop observability-grafana observability-promtail observability-loki observability-prometheus observability-backend observability-frontend observability-postgres

# 3. Python environment works and the fast tests pass (about 10 s)
.\.venv\Scripts\python -m pytest -m "not docker" -q

# 4. Check the reports are current (must print "OK: results/ matches the current inputs";
#    if it prints STALE, run `.\.venv\Scripts\python analyse.py` and check again), then rebuild the dashboard
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
| 0:00 | Terminal 1: start the live run (command below) | "AutoImmune is a self-healing pipeline prototype for a Java microservice. I'm injecting a seeded configuration fault now: one flag flipped in application.properties makes the health check report DOWN. Detection, the four gates, the decision, deployment and the health window run automatically. This fix edits a sensitive config file, so the policy will stop once and ask me to approve. In this demo the diagnosis is rule-based and the candidate patches are hand-built, so no AI is used." |
| 0:30 | Switch to the **dashboard**, **System Overview** tab (the first tab, open by default) | "While it runs, here is the candidate-level evidence from every run that produced patch candidates. Runs that failed before that are listed in the run ledger, results\runs.csv. The counts, gate statistics and policy tables are regenerated from the raw run records by analyse.py. The test status and limitations panels come from our audit file, docs\audit\acceptance.json." |
| 1:30 | Dashboard: **Validation Gates** tab | "Four gates in an isolated Docker sandbox with no network: V0 the patch applies and compiles, V1 target test, V2 full test suite, V3 Semgrep security scan. Each catches a different bad patch: ineffective at V1, regressive at V2, insecure at V3." |
| 3:00 | Dashboard: **Evidence & Analytics** tab, "Policy Comparison (B0 – B3)" section, scripted cohort | "Same hand-built patches, different policies. We have 26 unsafe candidate units: 13 unsafe patches, each run under two diagnosis modes. With compile plus the target test only, 20 of 26 would be auto-applied. Adding the full suite, 13. One of those extra stops was a sandbox tool error, which we count as not passing. Our full policy, 7. No correct patch was rejected: 0 of 6." |
| 4:00 | Back to terminal 1: point at the stage lines | "It detected the fault within seconds. F04 has no stack trace, so in this rule-mode demo the faulty file is taken from the fault definition. That is oracle localisation, not a real diagnosis: the terminal shows oracle_localisation=True, and these runs are left out of our diagnosis accuracy numbers. Now it is gating 5 candidate patches." |
| ~5:30–8:30 (when the gates finish) | **HUMAN APPROVAL REQUIRED** appears | "This patch edits a sensitive config file, so the policy will not auto-apply it. It asks a human." Let the examiner read the diff. Type **approve**. |
| approve + about 30 s | Run continues: deploy and health window | "It builds a new image, smoke-tests it side by side, swaps it in, and watches health and latency for 30 s. If anything breaches, it swaps back automatically." |
| approve + about 1 min | Final summary: **PROMOTED** | "Promoted. Note the wording: the health window passed. The pipeline does not claim the patch is correct." |
| next | Dashboard: **Deployment & Rollback** tab (the approvals are on the separate **Human Approval** tab) | "We also demonstrated automatic rollback: a planted slow patch passed all four gates, then breached the 2-second latency limit and was rolled back in about 5 seconds, and we verified the old image was really restored. It was a staged test, not a real catch." |
| +1 min | Dashboard: **Evidence & Analytics** tab, scroll to the "Known Limitations" section | "Our key finding: wrong patches can pass every gate. All three of our hand-built overfitting patches passed V0 to V3. Our independent oracle, with hidden tests the pipeline never sees, found two AI patches that passed every gate and were auto-deployed but are incorrect. Tests alone cannot prove a fix is correct." |

Timings from the recorded F04 runs: the prompt appeared 5 min 34 s into `f04-rule-scripted-20261108t175754z` and
8 min 20 s into `f04-rule-scripted-20261108t205508z`. After approve, PROMOTED came 46 s later in the first run and
61 s later in the second, which also ran the side-by-side smoke test (build, smoke test, swap, then the 30 s window).

The dashboard cells that used to be typed in by hand (approvals subtext, model list, unit total, survivor decisions) are now
computed from the evidence. `results\pilot_report.md` has the same numbers in table form.

**Live run command (F04, human approval in the middle; about 5.5–8.5 min to the prompt, then about 1 min after you
approve; the two recorded runs took 9.9 min and 17.9 min in total, the difference being time spent at the prompt
and slower gates):**
```
.\.venv\Scripts\python -m pipeline run --fault F04 --diag-mode rule --patch-mode scripted
```
At the prompt, type only `approve` and press Enter. **Do not paste anything else.**

**If you have less than 10 minutes, use F01 instead (about 6 min, no prompt):**
```
.\.venv\Scripts\python -m pipeline run --fault F01 --diag-mode rule --patch-mode scripted
```

**Optional second live run, rollback (the recorded run took about 22 min, because it still gates all 6 F06
candidates before deploying the slow one; do not start it live unless you have that time):**
```
.\.venv\Scripts\python -m pipeline run --fault F06 --diag-mode rule --patch-mode scripted --candidate F06-scripted-7509cb64
```

## C. If something fails live
Stay calm and say: *"A failed run is recorded too: if a step raises an error, the pipeline writes error.json and
marks the run as 'error'. An interrupted run is not closed by the pipeline, but the run ledger lists it."* Then show
the recorded runs:

| Show | Where |
|---|---|
| Human approval, then deploy | `runs\f04-rule-scripted-20261108t175754z\F04-scripted-835a25e8\approval.json` and `deploy.json` |
| Rollback | `runs\f06-rule-scripted-20261108t201808z\F06-scripted-7509cb64\rollback.json` |
| Full run summary | `runs\f01-rule-scripted-20261108t174806z\summary.json` |
| All tables | `results\pilot_report.md` |

Open a file quickly: `notepad runs\f06-rule-scripted-20261108t201808z\F06-scripted-7509cb64\rollback.json`

Common fixes:
- `failed to connect to the docker API`: Docker Desktop isn't running. Start it and wait for "Engine running".
- `No Python at ...`: run `py -3.12 -m venv .venv` then `.\.venv\Scripts\pip install -r requirements.lock`.
- The run stops at step 2 or 3: open `runs\<run_id>\error.json` for the real cause. The recorded step 2 stops were
  Docker build errors: restart Docker Desktop, wait for "Engine running", then rerun. The pipeline removes an old
  `autoimmune-app` container by itself, so use `docker ps` only to check that no other container holds port 18080 or 18081.

## D. Likely viva questions, with honest answers

**Is the AI fixing the bugs?**
The AI is used only for diagnosis and drafting patches. Small local models (qwen2.5-coder 7b and 1.5b) produced no
patch that passed the target test. With gpt-oss-120b, 7 patches passed all four gates and 5 were auto-applied under our
policy. The oracle labels 4 of those 7 correct, including all three auto-applied F06 patches; one of them was deployed
and promoted. Two were wrong yet still auto-deployed and promoted: a null-only guard on F01, and a health check forced
to "UP" on F04 after a misdiagnosis. So the AI can fix bugs, but passing the tests does not prove a fix is correct.
The live demo uses no AI: hand-built candidates, so every gate and decision branch shows up in a controlled way, and
rule-mode diagnosis. In rule mode F01 is located from its stack trace. F04 and F06 have no stack trace, so the faulty
file is copied from `faults/<id>/fault.json`. That is oracle localisation, not a diagnosis: it is flagged
oracle_localisation=true and left out of our diagnosis accuracy numbers.

**Why not let the AI decide too (an agent)?**
For safety and auditability: every decision is deterministic code with written reasons, so it can be checked and
reproduced.

**How do you know the sandbox is isolated?**
A test runs inside the sandbox and tries DNS, TCP and HTTPS: all are blocked. A control run on a normal network
succeeds, which proves the test can detect access (`docs/audit/isolation_test.txt`).

**How do you know a patch is really correct?**
An independent oracle (`tools/oracle.py`) runs hidden tests the pipeline never sees, plus a performance test and a
security check, and labels every patch. Its labels are machine labels; a two-person human review is still pending.

**How do you know rollback works?**
In `f06-rule-scripted-20261108t201808z` a planted slow patch passed every gate and a side-by-side smoke test, was
deployed, breached the 2000 ms limit (3015 ms) and was rolled back in 5.1 s. The restored image ID matched the previous
one. It is a staged test, not a real incident.

**What's novel?**
Not repair or rollback by themselves. We measure what each layer of evidence catches on the same patches, and we show
honestly where tests fail (overfitting).

**What are the limitations?**
Three seeded faults on one service, no held-out faults, oracle labels not yet reviewed by two people, small samples
(differences are not statistically established), laptop deployment rather than a production canary, and only three
human approval decisions (one reject, two approve), made by two team members rather than independent reviewers.
Every model missed F04's configuration root cause, and in rule mode the F04 and F06 diagnosis comes from the fault
definition (oracle localisation), not from the pipeline.

**What would you do next?**
Blind two-person label review, about 10 more held-out faults, escalate when gate-passing patches disagree, treat
health-check code as sensitive, and repeat trials with more models.
