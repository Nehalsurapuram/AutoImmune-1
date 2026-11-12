# Table 1: The AutoImmune Fault Benchmark Suite

| Fault ID | Defect Family | Complexity | Target Component | Symptom | Detection Rule | Evaluation Status | Evaluated Candidates |
| :--- | :--- | :---: | :--- | :--- | :--- | :---: | :---: |
| **`F01`** | Null Pointer Dereference | Low | `OrderService.java` | HTTP 500 NPE on missing customer parameter | `probe_5xx` | **Fully Evaluated** | 5 Scripted, 9 LLM |
| **`F02`** | Search Case Sensitivity | Medium | `OrderService.java` | Incomplete search results for uppercase queries | `probe_mismatch` | **Evaluated** | 5 Scripted |
| **`F03`** | Resource Descriptor Leak | High | `OrderController.java` | File descriptor exhaustion on receipt export | Latency creep *(Exploratory)* | **Exploratory** | 5 Scripted |
| **`F04`** | Configuration Drift | Low | `application.properties` | Health indicator returns HTTP 503 DOWN | `health_down` | **Fully Evaluated** | 5 Scripted, 6 LLM |
| **`F05`** | API DTO Serialization | Medium | `Item.java` | Deserialization mismatch on order item properties | `probe_mismatch` | **Evaluated** | 5 Scripted |
| **`F06`** | Boundary Value Logic Bug | Low | `OrderService.java` | Off-by-one threshold discount miscalculation | `probe_mismatch` | **Fully Evaluated** | 6 Scripted, 38 LLM |
| **`F07`** | Security Path Traversal | High | `OrderController.java` | Unsanitized directory traversal in report export | `report-path-traversal` | **Evaluated** | 5 Scripted |
| **`F08`** | Concurrency Race Condition | High | `OrderRepository.java` | Lost update during concurrent order counter increment | Concurrent race *(Excluded)* | **EXCLUDED** | 5 Scripted |
| **`F09`** | Algorithmic CPU Starvation | Medium | `OrderService.java` | Cyclic loop spin on circular graph traversal | Latency SLA *(Exploratory)* | **Exploratory** | 5 Scripted |
| **`F11`** | Negative Accounting Defect | Low | `OrderRepository.java` | Unchecked negative order line total | Inconsistency *(Exploratory)* | **Exploratory** | 5 Scripted |
| **`F12`** | Permissive Endpoint Exposure | Medium | `application.properties` | Sensitive Actuator endpoints exposed to HTTP | Config scan *(Exploratory)* | **Exploratory** | 5 Scripted |
| **`F13`** | Timezone Drift Inconsistency | Medium | `OrderService.java` | Receipt date serialized in non-UTC timezone | Format check *(Exploratory)* | **Exploratory** | 5 Scripted |
