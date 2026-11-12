# Table 5: Validation Gate Execution Latency & Overhead

Computational cost and latency measured across all gate evaluations in Docker sandbox:

| Gate | Validation Target | Tools & Runtime | Candidates Intercepted (First Stop) | Min Latency (s) | Median Latency (s) | Mean Latency (s) | Max Latency (s) | Total Gate Execution (s) |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **V0** | Git Apply & Maven Compile | `git apply --check` + `mvn -o compile` | **31 candidates** (31 LLM) | 0.8s | **1.0s** | 1.1s | 2.1s | 110.2s |
| **V1** | Incident Target Test | `mvn -o test -Dtest=<TargetTest>` | **24 candidates** (9 Scripted, 15 LLM) | 1.5s | **2.1s** | 2.4s | 4.8s | 165.6s |
| **V2** | Full Regression Suite | `mvn -o test` (pre-existing suite) | **9 candidates** (9 Scripted) | 2.8s | **3.5s** | 3.8s | 6.2s | 171.0s |
| **V3** | Semgrep AST Security Scan | `semgrep:1.100.0` (offline) | **8 candidates** (8 Scripted) | 0.9s | **1.1s** | 1.2s | 1.9s | 43.2s |
| **Scope** | Scope & Path Rules | In-memory path allowlist & diff line check | **5 escalated** (3 Scripted, 2 LLM) | <0.01s | **<0.01s** | <0.01s | <0.01s | <0.01s |
| **Canary** | Post-Deploy SLA Probe | HTTP health probe over canary window | **1 rolled back** (F06 slow) | 3.0s | **3.0s** | 3.0s | 3.0s | 3.0s |
| **Full Pipeline Cascade** | Complete V0–V3 + Scope evaluation | Sequential V0–V3 + Risk Scope | **23 auto-applied**\* (18 Scripted, 5 LLM) | 6.2s | **8.2s** | 8.5s | 12.0s | 187.0s |

\* *Decisions vs. Deployments:* Across all 100 candidate units, 23 patches received an `AUTO_APPLY` policy decision (18 Scripted, 5 LLM). Live end-to-end container socket deployment was executed for 13 candidate runs, with 2 rollbacks recorded in telemetry (one induced by SLA latency breach and one recovery verification).

**Key Finding:** Fast-failing early gates (V0 syntax check in ~1.0s; V1 incident test in ~2.1s) intercept 55% of candidates before executing the heavier full regression suite (V2 in ~3.5s), minimizing overall CI/CD overhead during incident response.
