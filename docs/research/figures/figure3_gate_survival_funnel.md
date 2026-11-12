# Figure 3: Candidate Survival Funnel Through Validation Gates

Survival funnel across all 100 primary candidate units evaluated in AutoImmune (47 Scripted mechanism checks and 53 Live LLM attempts):

```mermaid
flowchart TD
    Total["All Candidate Units Evaluated: 100 (100.0%)"] --> V0["Gate V0 Pass: 69 (69.0%)"]
    Total -.->|Failed Compilation: 31 LLM| StopV0["Stopped at V0 (31%)"]
    
    V0 --> V1["Gate V1 Pass: 45 (45.0%)"]
    V0 -.->|Failed Target Test: 24 (9 Scripted, 15 LLM)| StopV1["Stopped at V1 (24%)"]
    
    V1 --> V2["Gate V2 Pass: 36 (36.0%)"]
    V1 -.->|Failed Regression Suite: 9 Scripted| StopV2["Stopped at V2 (9%)"]
    
    V2 --> V3["Gate V3 Pass: 28 (28.0%)"]
    V2 -.->|Failed Semgrep AST Scan: 8 Scripted| StopV3["Stopped at V3 (8%)"]
    
    V3 --> Scope["Scope Evaluation: 28 Surviving Candidates"]
    Scope -.->|Sensitive Config / Large Diff: 5 Candidates| Escalate["ESCALATE to Human: 5 (5.0%)"]
    Scope --> AutoApply["AUTO_APPLY Decisions: 23 (23.0%)"]
    
    AutoApply --> Canary["Canary Health Evaluation<br/>(13 Live Deployments Executed)"]
    Canary -.->|Breached 2000ms SLA: F06 slow| Rollback["Canary Rollback Triggered<br/>(2 Telemetry Rollbacks)"]
    Canary --> Promoted["Healthy Canary Window Verified"]
```

### Key Statistical Funnel Observations
1. **Compilation Interception:** Gate V0 filters 31% of candidates (all from LLM synthesis) in $\approx 1.0\text{ s}$, protecting the test runner from invalid builds.
2. **Regression Interception:** Gate V2 intercepts 9 candidates (9.0%) that fixed the immediate incident but broke pre-existing endpoints.
3. **Security Interception:** Gate V3 intercepts 8 candidates (8.0%) that passed all functional tests but introduced static AST vulnerabilities.
4. **Scope Escalation:** Risk rules pause 5 candidates (5.0%) with high blast radius for human review.
5. **Decisions vs. Deployments:** 23 candidate units received `AUTO_APPLY` decisions (18 Scripted, 5 LLM). Live container deployment was evaluated across 13 runs, where post-deployment probing successfully detected runtime SLA violations and executed an automated rollback in 5.0 seconds.
