# AutoImmune: Production Acceptance & Security Verification Tests

## 1. Acceptance Verification Matrix

To establish production deployment readiness, the system is subjected to automated acceptance verification across five operational dimensions:

| ID | Domain | Test Description | Verification Target | Status |
| :--- | :--- | :--- | :--- | :---: |
| **PAT-01** | **Gate Integrity** | `git apply --check` & `mvn compile` fail-closed | Malformed patches or compile errors produce immediate `V0 fail` | **VERIFIED** |
| **PAT-02** | **Target Verification** | Visible test `V1` strictly catches fault symptom | Fault-specific target test passes only when defect is mitigated | **VERIFIED** |
| **PAT-03** | **Regression Guard** | Suite `V2` catches unintended behavioral changes | Existing service test suite passes 100% | **VERIFIED** |
| **PAT-04** | **Static Security** | Gate `V3` Semgrep scan catches net-new vulnerabilities | High severity finding produces immediate `REJECT` | **VERIFIED** |
| **PAT-05** | **Path Containment** | Patches modifying unallowlisted or sensitive files escalate | Modifying `application.properties` yields `ESCALATE` | **VERIFIED** |
| **PAT-06** | **Diff Envelope** | Patches larger than `max_diff_lines` escalate | Modifying $>20$ lines forces human review | **VERIFIED** |
| **PAT-07** | **Air-Gap Sandbox** | Repair sandbox runs with `--network none` and dropped caps | No egress traffic permitted; zero hidden tests mounted | **VERIFIED** |
| **PAT-08** | **Canary Rollback** | Deployment health window breach triggers rollback | Latency or error spike immediately reverts traffic | **VERIFIED** |
| **PAT-09** | **Audit Trail** | Cryptographic hash & provenance recorded per candidate | `evidence.jsonl` row carries patch hash and approval identity | **VERIFIED** |

---

## 2. Security & Chaos Verification Test Suite

### Chaos Scenario 1: Malformed LLM Output / Non-Diff Response
- **Test:** Provider outputs explanatory markdown prose without unified diff markers.
- **Expected Behavior:** `ScriptedProvider` / `LiveProvider` catches formatting violation, logs problem in `format_problems`, and exits cleanly without applying corrupt patch.

### Chaos Scenario 2: Docker Daemon Disconnection
- **Test:** Docker daemon socket becomes unreachable during sandbox execution.
- **Expected Behavior:** `SandboxError` is raised. The pipeline aborts fail-closed with step status `error`. Gate is never marked `pass`.

### Chaos Scenario 3: Compromised / Malicious Candidate Patch
- **Test:** Candidate diff introduces `Runtime.getRuntime().exec(...)` or SQL string concatenation.
- **Expected Behavior:** Gate V3 Semgrep scan detects new high-severity finding. Decision engine outputs `Decision("high", "REJECT", ...)`. Deployment is completely blocked.

### Chaos Scenario 4: Post-Deployment Performance Regression
- **Test:** Patch passes V0–V3, but inflates endpoint latency to 2,500ms (F09).
- **Expected Behavior:** Health window probe detects latency $>2,000$ms budget. Automated rollback immediately swaps traffic back to previous stable image tag. Rollback event written to `runs/<run_id>/rollback.json`.
