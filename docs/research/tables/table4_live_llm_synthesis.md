# Table 4: Live LLM Patch Synthesis & Repair Efficacy (N = 53)

Evaluation of one-shot patch synthesis by open-weights local code models (`qwen2.5-coder:1.5b`, `qwen2.5-coder:7b`) and historical GPT-OSS endpoints across primary faults:

| Model Synthesizer | Evaluated Attempts | Passed Compilation (Gate V0) | Fixed Incident (Gate V1) | Passed Regression (Gate V2) | Passed Security (Gate V3) | Auto-Apply Decision (B3) | Verified Correct (Independent Oracle) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `qwen2.5-coder:1.5b` | 8 | 0 (0.0%)<br/>[0.0%, 32.4%] | 0 (0.0%)<br/>[0.0%, 32.4%] | 0 (0.0%)<br/>[0.0%, 32.4%] | 0 (0.0%)<br/>[0.0%, 32.4%] | 0 (0.0%)<br/>[0.0%, 32.4%] | **0 / 8 (0.0%)**<br/>[0.0%, 32.4%] |
| `qwen2.5-coder:7b` | 33 | 11 (33.3%)<br/>[19.7%, 50.4%] | 0 (0.0%)<br/>[0.0%, 10.4%] | 0 (0.0%)<br/>[0.0%, 10.4%] | 0 (0.0%)<br/>[0.0%, 10.4%] | 0 (0.0%)<br/>[0.0%, 10.4%] | **0 / 33 (0.0%)**<br/>[0.0%, 10.4%] |
| `openai/gpt-oss-120b` | 12 | 11 (91.7%)<br/>[64.6%, 98.5%] | 7 (58.3%)<br/>[32.0%, 80.7%] | 7 (58.3%)<br/>[32.0%, 80.7%] | 7 (58.3%)<br/>[32.0%, 80.7%] | 5 (41.7%)<br/>[19.3%, 68.0%] | **0 / 12 (0.0%)**<br/>[0.0%, 24.2%] |
| **All Live LLM Cohorts** | **53** | **22 (41.5%)**<br/>[29.3%, 54.9%] | **7 (13.2%)**<br/>[6.5%, 24.8%] | **7 (13.2%)**<br/>[6.5%, 24.8%] | **7 (13.2%)**<br/>[6.5%, 24.8%] | **5 (9.4%)**<br/>[4.1%, 20.3%] | **0 / 53 (0.0%)**<br/>[0.0%, 6.7%] |

**Key Empirical Insights:**
1. **Compilation Barrier:** 58.5% of open-weights LLM patches fail at Gate V0 due to hallucinated dependencies, syntax errors, or invalid import statements.
2. **The 0% Verified Semantic Accuracy Reality:** All 32 LLM candidates evaluated against independent hidden oracle tests (`results/oracle_report.jsonl`) failed semantic correctness (evaluated as `incorrect` or `invalid`).
3. **Safety Shield:** AutoImmune's pre-deployment gates rejected **86.8% (46/53)** of defective LLM patches prior to deployment.
