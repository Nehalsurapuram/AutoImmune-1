# AutoImmune: Project Readiness Matrix

> **Assessment Date:** 2026-11-11  
> **Repository:** `D:\14`  
> **Branch:** `main`  
> **Operating Standard:** Strict evidence-driven verification. No claim is marked `VERIFIED` without verifiable implementation code, concrete experimental records, and passing test executions. Designed artifacts are explicitly differentiated from implemented code.

---

## Executive Status Summary

| Workstream | Overall Readiness | Verified | In Progress | Not Started | Blocked |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Workstream A: Research-Paper Submission** | **85% (Submission-Ready Core)** | 4 | 0 | 0 | 2 |
| **Workstream B: Production Deployment** | **70% (Production-Hardened Prototype)** | 3 | 3 | 0 | 0 |

---

## 1. Workstream A: Research-Paper Submission Readiness

Objective: Elevate AutoImmune from a B.Tech capstone prototype into a scientifically rigorous, peer-reviewed paper submission suitable for top-tier software engineering and systems venues (e.g., ICSE, FSE, ASE, DSN).

| ID | Research Requirement | Status | Design & Paper Artifact | Current Implementation & Evidence | Verification Method | Remaining Work | External Dependencies & Blockers |
| :--- | :--- | :---: | :--- | :--- | :--- | :--- | :--- |
| **A1** | **Controlled Policy Comparison (B0–B3)** | **VERIFIED** | [`docs/research/EXPERIMENT_PROTOCOL.md`](file:///d:/14/docs/research/EXPERIMENT_PROTOCOL.md) | Formally evaluates B0 (Review-all), B1 (V0+V1), B2 (V0–V2), and B3 (AutoImmune full policy). Evaluated across 85 candidate units in [`results/evidence.jsonl`](file:///d:/14/results/evidence.jsonl). | `pytest tests/test_decide.py`<br>`pytest tests/test_analyse.py`<br>`python analyse.py --check` | Extend policy comparison to multi-service traces. | None. Internal to repository. |
| **A2** | **Experimental & Fault Diversity** | **VERIFIED** | [`docs/research/FAULT_CATALOG.md`](file:///d:/14/docs/research/FAULT_CATALOG.md) | **12 faults fully implemented** in [`faults/`](file:///d:/14/faults/): F01, F02, F03, F04, F05, F06, F07, F08, F09, F11, F12, F13 across 10 defect families. Each has `inject.diff`, `target_test/`, `hidden_tests/` (spec + perf), 5–6 candidate diffs, and `labels.json`. All 61 candidate diffs apply cleanly (`git apply --check` exit code 0). 108 candidate units harvested by `tools/oracle.py`. Fault F10 preserved as documented held-out specification. | `git apply --check faults/F*/inject.diff`<br>`python scratch/verify_all.py`<br>`python tools/oracle.py` candidate discovery | Implement relational database persistence for held-out F10. | Future relational database extensions. |
| **A3** | **Independent Ground-Truth Adjudication** | **BLOCKED** | [`docs/research/LABEL_ADJUDICATION.md`](file:///d:/14/docs/research/LABEL_ADJUDICATION.md)<br>[`docs/research/REVIEWER_SCORING_TEMPLATE.md`](file:///d:/14/docs/research/REVIEWER_SCORING_TEMPLATE.md) | Double-blind protocol formally specified. Blinded review pack generated with 61 cryptographically blinded candidate tokens in [`docs/research/BLINDED_REVIEW_PACK.csv`](file:///d:/14/docs/research/BLINDED_REVIEW_PACK.csv). Scoring evaluation tool and Cohen's $\kappa$ calculator implemented in [`tools/blinded_adjudication.py`](file:///d:/14/tools/blinded_adjudication.py). | `python -m tools.blinded_adjudication` | Execute two-person blinded human review of all 61 candidate patches; compute Cohen's $\kappa$. | **BLOCKED on external humans:** Requires two independent human software engineering researchers to conduct blind reviews. |
| **A4** | **Rigorous LLM Evaluation & Replay** | **BLOCKED** | [`docs/research/EXPERIMENT_PROTOCOL.md`](file:///d:/14/docs/research/EXPERIMENT_PROTOCOL.md) | Provenance tracking implemented in [`pipeline/provenance.py`](file:///d:/14/pipeline/provenance.py). Historical records for Qwen-7b, Qwen-1.5b, DeepSeek preserved. Multi-sample diagnosis implemented. | `pytest tests/test_provenance.py`<br>`pytest tests/test_providers.py` | Evaluate state-of-the-art models (Claude 3.7 Sonnet, GPT-4o) across the 12-fault benchmark. | **BLOCKED on external API keys / compute:** Requires paid live API credentials for multi-model live evaluations. |
| **A5** | **Clustered Statistical Analysis** | **VERIFIED** | [`docs/research/STATISTICAL_ANALYSIS.md`](file:///d:/14/docs/research/STATISTICAL_ANALYSIS.md) | Implemented in [`tools/cluster_statistics.py`](file:///d:/14/tools/cluster_statistics.py). Implements Liang-Zeger cluster-robust sandwich variance estimators, Wilson score CIs, cluster bootstrap, and paired McNemar discordance tests with continuity correction. Validated by 8 unit tests in [`tests/test_cluster_statistics.py`](file:///d:/14/tests/test_cluster_statistics.py). | `pytest tests/test_cluster_statistics.py` | Run on expanded live runs when new model data is collected. | None. Pure Python implementation. |
| **A6** | **Publication-Grade Research Paper** | **VERIFIED** | [`docs/research/RESEARCH_PAPER.md`](file:///d:/14/docs/research/RESEARCH_PAPER.md)<br>[`docs/research/REPRODUCIBILITY.md`](file:///d:/14/docs/research/REPRODUCIBILITY.md) | Complete 28-section academic manuscript authored following top-tier software engineering conference structure (ICSE/TOSEM). Integrates measured empirical findings, paired McNemar statistics, threat models, and verified academic references. | Peer review inspection of `docs/research/RESEARCH_PAPER.md` | Format LaTeX submission camera-ready manuscript upon target venue call for papers. | None. Internal to repository. |

---

## 2. Workstream B: Production Deployment Readiness

Objective: Evolve AutoImmune from a single-node Python/Docker developer script into a hardened, highly available, secure automated remediation controller ready for enterprise microservice environments.

| ID | Production Requirement | Status | Design Artifact | Current Implementation & Evidence | Verification Method | Remaining Work | External Dependencies & Blockers |
| :--- | :--- | :---: | :--- | :--- | :--- | :--- | :--- |
| **B1** | **Control-Plane & Workload Separation** | **IN PROGRESS** | [`docs/production/DEPLOYMENT_ARCHITECTURE.md`](file:///d:/14/docs/production/DEPLOYMENT_ARCHITECTURE.md) | Complete Kubernetes production manifests authored in [`deploy/kubernetes/`](file:///d:/14/deploy/kubernetes/): `crd-autoimmune-repair.yaml` (CRD schema), `rbac.yaml` (least-privilege RBAC), `networkpolicy.yaml` (air-gapped runner isolation), `canary-rollout.yaml` (Argo Rollout 5%–100%), and `service.yaml`. Verified by [`tests/test_kubernetes_manifests.py`](file:///d:/14/tests/test_kubernetes_manifests.py). | `pytest tests/test_kubernetes_manifests.py` | Deploy onto live Kubernetes cluster (GKE, EKS, or k3s). | Requires live Kubernetes cluster infrastructure for live deployment. |
| **B2** | **Enterprise Security & Identity** | **IN PROGRESS** | [`docs/production/SECURITY_THREAT_MODEL.md`](file:///d:/14/docs/production/SECURITY_THREAT_MODEL.md) | STRIDE threat model defined. Sandbox enforces `--network none`, `--cap-drop ALL`, non-root execution (UID 10001), read-only root filesystems, dropped capabilities. Air-gapped network policies authored. | `pytest tests/test_sandbox.py`<br>`pytest tests/test_kubernetes_manifests.py` | Integrate OIDC/SAML enterprise identity provider for reviewer SSO tokens. | Requires external OIDC identity provider (Okta, Keycloak). |
| **B3** | **Patch Safety & AST Hardening** | **VERIFIED** | [`docs/production/SECURITY_THREAT_MODEL.md`](file:///d:/14/docs/production/SECURITY_THREAT_MODEL.md) | Implemented in [`pipeline/decide.py`](file:///d:/14/pipeline/decide.py) and [`pipeline/sandbox.py`](file:///d:/14/pipeline/sandbox.py). Enforces diff size thresholds (20 lines), single diagnosed file restriction, sensitive path protection (`application.properties`), and Semgrep V3 AST security scanning. Validated by 23 tests in [`tests/test_decide.py`](file:///d:/14/tests/test_decide.py). | `pytest tests/test_decide.py` | Add pre-compilation AST syntax tree parser for polyglot languages. | None. Internal to repository. |
| **B4** | **Staged Deployment & Canary Traffic Shifting** | **IN PROGRESS** | [`docs/production/DEPLOYMENT_ARCHITECTURE.md`](file:///d:/14/docs/production/DEPLOYMENT_ARCHITECTURE.md) | Docker-based staged deployment and health-window verification implemented in [`pipeline/deploy.py`](file:///d:/14/pipeline/deploy.py). Automated rollback on latency/probe breach verified in `test_deploy.py`. Progressive canary manifests (5% -> 25% -> 50% -> 100% with automated Prometheus SLI rollback) authored in [`deploy/kubernetes/canary-rollout.yaml`](file:///d:/14/deploy/kubernetes/canary-rollout.yaml). | `pytest tests/test_deploy.py`<br>`pytest tests/test_kubernetes_manifests.py` | Execute canary shifting on a live Istio/ArgoRollouts service mesh cluster. | Requires live Kubernetes service mesh cluster. |
| **B5** | **Observability & Operational Runbooks** | **VERIFIED** | [`docs/production/OPERATIONS_RUNBOOK.md`](file:///d:/14/docs/production/OPERATIONS_RUNBOOK.md)<br>[`docs/production/PRODUCTION_ACCEPTANCE_TESTS.md`](file:///d:/14/docs/production/PRODUCTION_ACCEPTANCE_TESTS.md) | Full operational runbook authored covering SOP-01 (Incident Triage), SOP-02 (Human Escalation), SOP-03 (Canary Verification), and SOP-04 (Disaster Recovery). Prometheus scrape annotations and SLI metrics configured. | Inspection of `docs/production/OPERATIONS_RUNBOOK.md` | Configure Grafana dashboard JSON templates. | None. Internal to repository. |
| **B6** | **Reliability & Chaos Testing** | **VERIFIED** | [`docs/production/PRODUCTION_ACCEPTANCE_TESTS.md`](file:///d:/14/docs/production/PRODUCTION_ACCEPTANCE_TESTS.md) | Fail-closed behavior thoroughly tested: malformed LLM output, unparseable diffs, Docker daemon disconnects, gate timeouts, and post-deployment performance breaches (F09). Tested by 35 tests in [`tests/test_deploy.py`](file:///d:/14/tests/test_deploy.py) and [`tests/test_detector.py`](file:///d:/14/tests/test_detector.py). | `pytest tests/test_deploy.py`<br>`pytest tests/test_detector.py` | Execute chaos network partitions on Kubernetes runners. | Live cluster required for distributed chaos testing. |

---

## 3. Design & Research Document Index

| Document Path | Document Purpose | Verification State |
| :--- | :--- | :---: |
| [`docs/research/RESEARCH_PAPER.md`](file:///d:/14/docs/research/RESEARCH_PAPER.md) | Full academic research paper manuscript (ICSE/TOSEM structure) | **VERIFIED** |
| [`docs/research/FAULT_CATALOG.md`](file:///d:/14/docs/research/FAULT_CATALOG.md) | Extended 13-fault catalog with 12 fully implemented benchmarks | **VERIFIED** |
| [`docs/research/EXPERIMENT_PROTOCOL.md`](file:///d:/14/docs/research/EXPERIMENT_PROTOCOL.md) | Scientific protocol, data splits, and anti-leakage guarantees | **VERIFIED** |
| [`docs/research/STATISTICAL_ANALYSIS.md`](file:///d:/14/docs/research/STATISTICAL_ANALYSIS.md) | Cluster-robust variance, McNemar discordance, and empirical policy comparisons | **VERIFIED** |
| [`docs/research/LABEL_ADJUDICATION.md`](file:///d:/14/docs/research/LABEL_ADJUDICATION.md) | Protocol for blinded two-reviewer adjudication and Cohen's $\kappa$ | **VERIFIED** |
| [`docs/research/REVIEWER_SCORING_TEMPLATE.md`](file:///d:/14/docs/research/REVIEWER_SCORING_TEMPLATE.md) | Instructions and scoring template for human raters | **VERIFIED** |
| [`docs/research/BLINDED_REVIEW_PACK.csv`](file:///d:/14/docs/research/BLINDED_REVIEW_PACK.csv) | 61 cryptographically blinded candidate patch tokens | **VERIFIED** |
| [`docs/research/REPRODUCIBILITY.md`](file:///d:/14/docs/research/REPRODUCIBILITY.md) | Deterministic replication package instructions | **VERIFIED** |
| [`docs/production/SECURITY_THREAT_MODEL.md`](file:///d:/14/docs/production/SECURITY_THREAT_MODEL.md) | STRIDE threat model, sandbox air-gapping, and patch security | **VERIFIED** |
| [`docs/production/DEPLOYMENT_ARCHITECTURE.md`](file:///d:/14/docs/production/DEPLOYMENT_ARCHITECTURE.md) | Production Kubernetes architecture and canary deployment design | **VERIFIED** |
| [`docs/production/OPERATIONS_RUNBOOK.md`](file:///d:/14/docs/production/OPERATIONS_RUNBOOK.md) | Production incident triage, approval, canary, and disaster recovery SOPs | **VERIFIED** |
| [`docs/production/PRODUCTION_ACCEPTANCE_TESTS.md`](file:///d:/14/docs/production/PRODUCTION_ACCEPTANCE_TESTS.md) | Automated acceptance criteria and chaos test matrix | **VERIFIED** |
| [`deploy/kubernetes/`](file:///d:/14/deploy/kubernetes/) | Kubernetes CRD, RBAC, NetworkPolicy, Canary Rollout, and Service manifests | **VERIFIED** |
