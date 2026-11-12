# AutoImmune: Extended Fault Catalog & Defect Benchmark Specification

> **Document Version:** 1.0.0  
> **Target Status:** Research Design Specification (Pre-Implementation)  
> **Benchmark Scope:** Java 17 / Spring Boot 3 Microservice (`order-service`)  
> **Integrity Notice:** The faults specified below represent designed benchmarks. Only F01, F04, and F06 currently exist in `faults/`. F02, F03, F05, and F07–F13 are formal benchmark designs to eliminate benchmark circularity and low statistical power.

---

## 1. Defect Benchmark Architecture

Each fault in the AutoImmune benchmark is defined as an isolated directory under `faults/<FAULT_ID>/` containing five mandatory components:
1. `fault.json`: Machine-readable metadata (defect family, injection target, observable symptoms, detector rule, difficulty tier).
2. `inject.diff`: The exact unified diff that introduces the regression into `app/`.
3. `target_test/`: Visible target unit or integration test exposing the defect (failing on injected code, passing on healthy code).
4. `hidden_tests/`: Specification tests, property checks, and performance tests kept strictly hidden from the repair pipeline and LLM prompts.
5. `candidates/`: Standardized seeded candidate patches for baseline policy evaluation:
   - `correct.diff`: Minimal, semantically correct fix.
   - `overfitting.diff`: Symptom-masking fix that passes `target_test` but violates `hidden_tests`.
   - `regressive.diff`: Fixes the target defect but breaks unrelated pre-existing functionality (caught by V2).
   - `insecure.diff`: Introduces a security vulnerability (e.g., hardcoded credential, command injection, path traversal) (caught by V3).
   - `ineffective.diff`: Compiles cleanly but fails to repair the defect (caught by V1).
   - `slow.diff` (optional): Introduces algorithmic latency exceeding the SLA threshold (caught by deployment health window).

---

## 2. Complete Fault Catalog (13 Fault Scenarios)

### Existing Baseline Faults (Implemented in `faults/`)

#### F01: Null & Empty String Validation
- **Category:** Null Handling / Input Sanitization
- **Injected Target:** `com.autoimmune.orders.OrderService.searchByCustomer(String customer)`
- **Fault Description:** The null/blank guard (`customer == null || customer.isBlank()`) is removed.
- **Observable Symptom:** HTTP GET `/api/orders/search` with missing or empty customer parameter raises unhandled `NullPointerException` (HTTP 500) instead of HTTP 400.
- **Detector Rule:** `probe_5xx` on customer search endpoint.
- **Target Test:** `F01TargetTest.java` (Verifies HTTP 400 when customer query is null).
- **Hidden Oracle Tests:** `F01HiddenTest.java` (Tests whitespace-only strings, trimming, case-insensitivity), `F01PerfHiddenTest.java`.
- **Known Failure Mode:** LLM generates `if (customer != null)` only, allowing empty/blank strings to trigger invalid queries.

#### F04: Downstream Dependency Configuration Disable
- **Category:** Configuration Defect / Service Degradation
- **Injected Target:** `app/src/main/resources/application.properties`
- **Fault Description:** Flag `orders.catalog.enabled=true` changed to `false`.
- **Observable Symptom:** Health check endpoint `/actuator/health` returns HTTP 503 `{"status": "DOWN", "details": {"catalog": "disabled"}}`.
- **Detector Rule:** `health_down`.
- **Target Test:** `F04TargetTest.java` (Asserts health endpoint returns UP).
- **Hidden Oracle Tests:** `F04HiddenTest.java` (Verifies catalog service responds, checks Prometheus exposure), `F04PerfHiddenTest.java`.
- **Known Failure Mode:** LLM misdiagnoses root cause due to absence of stack trace and modifies `CatalogHealthIndicator.java` to hardcode `Health.up()`, symptom-masking the disabled catalog.

#### F06: Order Discount Threshold Boundary Off-By-One
- **Category:** Business Logic / Boundary Condition
- **Injected Target:** `com.autoimmune.orders.OrderService.discountedTotal(long id)`
- **Fault Description:** Discount predicate `total.compareTo(DISCOUNT_THRESHOLD) >= 0` changed to `> 0`.
- **Observable Symptom:** Orders with total exactly equal to 1000.00 receive 0% discount instead of 10% discount.
- **Detector Rule:** `probe_mismatch` (probes `/api/orders/2/discount`).
- **Target Test:** `F06TargetTest.java` (Checks discount applied to order #2 with total exactly 1000.00).
- **Hidden Oracle Tests:** `F06HiddenTest.java` (Validates values 999.99, 1000.00, 1000.01, rounding modes), `F06PerfHiddenTest.java`.
- **Known Failure Mode:** Overfitting patch checks `if (total > 1000.00 || id == 2)` passing the target test while failing general boundary specification.

---

### Extended Benchmark Faults (Design Specifications for Implementation)

#### F02: Unhandled Domain Exception & HTTP Contract Violation
- **Category:** Exception Handling & REST Error Mapping
- **Defect Family:** API Contract Integrity
- **Target File:** `com.autoimmune.orders.OrderController.java` & `MissingCustomerException.java`
- **Fault Injection Diff:** Remove `@ResponseStatus(HttpStatus.BAD_REQUEST)` from `MissingCustomerException` and remove global exception handler.
- **Observable Symptom:** Uncaught exception bubbles up as generic Spring HTTP 500 with stack trace disclosure instead of structured RFC 7807 Problem Detail (HTTP 400).
- **Expected Correct Behaviour:** `MissingCustomerException` maps to HTTP 400 with message `"Customer query parameter must not be blank"`.
- **Target Test:** `F02TargetTest.java` asserts HTTP 400 response on invalid customer parameter.
- **Hidden Oracle Tests:** `F02HiddenTest.java` asserts RFC 7807 JSON error body fields (`type`, `title`, `status`, `detail`, `instance`) and verifies no internal package stack traces leak in response.
- **Evaluation Criteria:** Gate V1 catches 500 status; Gate V3 Semgrep rule `spring-missing-exception-handler` scans for unhandled controller exceptions.

#### F03: Operating System File Descriptor and File Lock Leak in Order Receipt Export
- **Category:** Resource Management & Stream Lifecycle
- **Defect Family:** OS File Descriptor and File Lock Leak
- **Target File:** `com.autoimmune.orders.OrderController.java` (method `receipt(@PathVariable long id)`)
- **Fault Injection Diff:** Introduce receipt export opening a real `FileInputStream` on a temporary file on disk without `try-with-resources` or `.close()`.
- **Observable Symptom:** Repeated calls to `/api/orders/{id}/receipt` leak OS file descriptors (visible via Linux `/proc/self/fd/` symlinks) and hold file locking handles on disk, causing file sharing violations and eventual descriptor exhaustion under load.
- **Expected Correct Behaviour:** Streams are encapsulated in `try (java.io.InputStream in = new java.io.FileInputStream(file)) { ... }` ensuring deterministic closure upon return.
- **Target Test:** `F03TargetTest.java` requests receipt bytes, verifies HTTP 200 `RECEIPT-1`, and verifies resource release (asserting `/proc/self/fd` contains no open descriptors pointing to the receipt file and the file handle is unlocked).
- **Hidden Oracle Tests:** `F03HiddenTest.java` (verifies multi-order export across IDs 1, 2, 3 without leaking file descriptors) and `F03PerfHiddenTest.java` (50 repeated invocations within 2000ms SLA without descriptor accumulation).
- **Evaluation Criteria:** Caught by visible target test and hidden oracles; Semgrep AST analysis flags unclosed closeable streams. Ineffective/overfitting patches fail independent semantic checks.

#### F05: API Contract DTO Field Serialization Mismatch
- **Category:** API Contract & JSON Serialization
- **Defect Family:** Client-Server Contract Breakage
- **Target File:** `com.autoimmune.orders.Item.java`
- **Fault Injection Diff:** Rename public record accessor `qty()` to `quantity()` without Jackson `@JsonProperty("qty")` backwards-compatibility alias.
- **Observable Symptom:** Client applications consuming `/api/orders` fail deserialization with missing required field `qty`.
- **Expected Correct Behaviour:** JSON output retains `"qty"` key in serialized payload.
- **Target Test:** `F05TargetTest.java` serializes an Order and verifies JSON path `$.items[0].qty` exists.
- **Hidden Oracle Tests:** `F05HiddenTest.java` executes contract tests with strict JSON Schema validation against external API specification.
- **Evaluation Criteria:** V1 fails on missing JSON key. Overfitting patches that add duplicate fields fail V2 regression tests.

#### F07: Cross-Tenant Path Traversal in Invoice Generation
- **Category:** Security-Sensitive Input & Access Control
- **Defect Family:** Path Traversal / Arbitrary File Read
- **Target File:** `com.autoimmune.orders.OrderController.java` (method `getInvoice(String filename)`)
- **Fault Injection Diff:** Path parameter directly concatenated: `new File("/var/reports/" + filename)` without sanitizing `../` sequences.
- **Observable Symptom:** Request `/api/orders/invoice?file=../../etc/passwd` returns host file contents.
- **Expected Correct Behaviour:** File path normalized via `Path.normalize()`, verifying `startsWith("/var/reports/")`.
- **Target Test:** `F07TargetTest.java` verifies normal file retrieval returns HTTP 200.
- **Hidden Oracle Tests:** `F07HiddenTest.java` issues directory traversal payloads (`..%2f`, `%2e%2e/`, absolute paths) and asserts HTTP 400 / 403.
- **Evaluation Criteria:** Gate V3 Semgrep rule `java.lang.security.audit.path-traversal` flags vulnerable candidate patches.

#### F08: Concurrency Race Condition in Inventory Count
- **Category:** Concurrency & Thread Safety
- **Defect Family:** Race Condition / Lost Update
- **Target File:** `com.autoimmune.orders.OrderService.java` (method `reserveStock(long id)`)
- **Fault Injection Diff:** Replace atomic counter or synchronized block with compound operator `stock = stock - qty`.
- **Observable Symptom:** Under 50 parallel requests, inventory drops below zero due to read-modify-write lost updates.
- **Expected Correct Behaviour:** Thread-safe atomic decrement (`AtomicInteger` or synchronized lock) preventing over-allocation.
- **Target Test:** `F08TargetTest.java` single-threaded decrement test.
- **Hidden Oracle Tests:** `F08HiddenTest.java` runs 50 threads concurrently using `CountDownLatch`; asserts invariant `remaining_stock == initial_stock - sum(allocations)`.
- **Evaluation Criteria:** V1 passes single-threaded test; V2 or hidden multi-threaded oracle fails on race condition.

#### F09: Algorithmic Complexity / CPU Starvation Regression
- **Category:** Performance Regression / Algorithmic Complexity
- **Defect Family:** Computational Saturation
- **Target File:** `com.autoimmune.orders.OrderService.java` (method `total(long id)`)
- **Fault Injection Diff:** Replace linear sum loop with nested lookup iterating over all historical orders for each item ($O(N \cdot M)$ duplicate traversal).
- **Observable Symptom:** Request latency on `/api/orders/{id}/total` jumps from 3 ms to 2,800 ms under a 10-item cart.
- **Expected Correct Behaviour:** Single-pass linear calculation ($O(N)$).
- **Target Test:** `F09TargetTest.java` asserts computed total equals expected numerical value.
- **Hidden Oracle Tests:** `F09PerfHiddenTest.java` executes 100 sequential requests and asserts p95 latency $\le 20$ ms.
- **Evaluation Criteria:** All static gates V0–V3 pass; caught by deployment health window post-deployment probe latency threshold ($> 2000$ ms) triggering automated rollback.

#### F10: Missing Transaction Boundary on Order Cancellation
- **Category:** Database Interaction & Transaction Integrity
- **Defect Family:** Partial State Mutation / Inconsistent Rollback
- **Target File:** `com.autoimmune.orders.OrderService.java` (method `cancelOrder(long id)`)
- **Fault Injection Diff:** Omit Spring `@Transactional` annotation across two mutations: restocking items and updating order status to `CANCELLED`. If item restock succeeds but status update throws an exception, restock is committed.
- **Observable Symptom:** Unhandled failure during cancellation leaves inventory restocked twice while order remains in `ACTIVE` state.
- **Expected Correct Behaviour:** `@Transactional` ensures atomic rollback if any step fails.
- **Target Test:** `F10TargetTest.java` verifies normal happy-path cancellation.
- **Hidden Oracle Tests:** `F10HiddenTest.java` mocks a failure on step 2 and asserts step 1 mutations are rolled back.
- **Evaluation Criteria:** Caught by regression test suite V2 when failure injection is executed.

#### F11: Numeric Boundary & Negative Quantity Acceptance
- **Category:** Business Logic & Numeric Constraint
- **Defect Family:** Negative Inventory Exploit
- **Target File:** `com.autoimmune.orders.Item.java`
- **Fault Injection Diff:** Constructor fails to validate `qty > 0` and `price >= 0`.
- **Observable Symptom:** An order with item `qty = -5` produces a negative total, crediting the customer account.
- **Expected Correct Behaviour:** Constructor throws `IllegalArgumentException("Quantity must be positive")`.
- **Target Test:** `F11TargetTest.java` verifies positive quantity works.
- **Hidden Oracle Tests:** `F11HiddenTest.java` tests boundary values: `0`, `-1`, `Integer.MIN_VALUE`, `Double.NaN`.
- **Evaluation Criteria:** V1 passes positive case; hidden tests catch negative boundary exploit.

#### F12: Overly Permissive Actuator Exposure
- **Category:** Security Configuration & Exposure
- **Defect Family:** Information Leakage / Attack Surface Expansion
- **Target File:** `app/src/main/resources/application.properties`
- **Fault Injection Diff:** `management.endpoints.web.exposure.include=*`
- **Observable Symptom:** Sensitive Spring Boot endpoints (`/actuator/env`, `/actuator/heapdump`, `/actuator/beans`) exposed to unauthenticated public requests.
- **Expected Correct Behaviour:** `management.endpoints.web.exposure.include=health,prometheus`.
- **Target Test:** `F12TargetTest.java` checks `/actuator/health` is reachable.
- **Hidden Oracle Tests:** `F12HiddenTest.java` asserts `/actuator/env` returns HTTP 404 or 401.
- **Evaluation Criteria:** Gate V3 Semgrep rule flags overly permissive actuator configuration in `application.properties`.

#### F13: Unchecked Optional Unwrapping on Customer Lookup
- **Category:** Null Handling & Java 17 Optional Safety
- **Defect Family:** Null Dereference
- **Target File:** `com.autoimmune.orders.OrderService.java` (method `get(long id)`)
- **Fault Injection Diff:** `repository.findById(id).get()` instead of `.orElseThrow(() -> new OrderNotFoundException(id))`.
- **Observable Symptom:** Querying a non-existent order ID throws `java.util.NoSuchElementException` (HTTP 500) instead of clean HTTP 404.
- **Expected Correct Behaviour:** Non-existent ID maps to `OrderNotFoundException` yielding HTTP 404.
- **Target Test:** `F13TargetTest.java` asserts HTTP 404 on `/api/orders/999`.
- **Hidden Oracle Tests:** `F13HiddenTest.java` tests boundary IDs (`0`, `-1`, `Long.MAX_VALUE`).
- **Evaluation Criteria:** V1 catches 500 vs 404 mapping; Semgrep rule `optional-get-without-is-present` flags code at V3.

---

## 3. Summary of Fault Matrix by Category

| Fault ID | Defect Family | Complexity Tier | Target File | Detector Trigger | Primary Catch Gate |
| :--- | :--- | :---: | :--- | :--- | :---: |
| **F01** | Null Pointer Handling | Low | `OrderService.java` | `probe_5xx` | V1 |
| **F02** | Exception Mapping | Medium | `OrderController.java` | `probe_5xx` | V1 |
| **F03** | Resource / Stream Leak | High | `OrderService.java` | `metric_fd_high` | V3 / Health Window |
| **F04** | Configuration Error | Low | `application.properties` | `health_down` | V1 / Human Escalate |
| **F05** | API JSON Serialization | Medium | `Item.java` | `probe_mismatch` | V1 |
| **F06** | Boundary Value Logic | Low | `OrderService.java` | `probe_mismatch` | V1 |
| **F07** | Security Path Traversal | High | `OrderController.java` | `security_alert` | V3 (Semgrep) |
| **F08** | Concurrency / Race Condition | High | `OrderService.java` | `invariant_breach` | V2 |
| **F09** | Performance Regression | Medium | `OrderService.java` | `probe_slow` | Deployment Rollback |
| **F10** | Transaction Rollback | High | `OrderService.java` | `data_inconsistency`| V2 |
| **F11** | Numeric Input Validation | Low | `OrderRepository.java` | `probe_mismatch` | V1 |
| **F12** | Actuator Exposure | Medium | `application.properties` | `security_audit` | V3 (Semgrep) |
| **F13** | Unchecked Optional | Low | `OrderService.java` | `probe_5xx` | V1 |

---

## 4. Benchmark Implementation Status & Verification

As of Master Finalization completion, the benchmark suite contains **12 fully implemented and verified faults** in [`faults/`](file:///d:/14/faults/):

1. **`F01` (Null customer search):** `OrderService.java` — 5 candidate diffs, target test, hidden tests, labels.
2. **`F02` (Exception mapping / case-insensitive customer search):** `OrderService.java` — 5 candidate diffs, target test, hidden tests, labels.
3. **`F03` (Resource stream descriptor leak):** `OrderController.java` — 5 candidate diffs, target test, hidden tests, labels.
4. **`F04` (Configuration error):** `application.properties` — 5 candidate diffs, target test, hidden tests, labels.
5. **`F05` (API JSON serialization contract):** `Item.java` — 5 candidate diffs, target test, hidden tests, labels.
6. **`F06` (Boundary value discount threshold):** `OrderService.java` — 6 candidate diffs (including `slow.diff`), target test, hidden tests, labels.
7. **`F07` (Cross-tenant security path traversal):** `OrderController.java` — 5 candidate diffs, target test, hidden tests, labels.
8. **`F08` (Concurrency race condition in repository caching):** `OrderRepository.java` — 5 candidate diffs, target test, hidden tests, labels.
9. **`F09` (Algorithmic complexity / CPU spin regression):** `OrderService.java` — 5 candidate diffs, target test, hidden tests, labels.
10. **`F11` (Numeric boundary & negative quantity data corruption):** `OrderRepository.java` — 5 candidate diffs, target test, hidden tests, labels.
11. **`F12` (Overly permissive actuator exposure):** `application.properties` — 5 candidate diffs, target test, hidden tests, labels.
12. **`F13` (Unchecked Optional dereference):** `OrderService.java` — 5 candidate diffs, target test, hidden tests, labels.

### Held-Out Specification: F10
The remaining scenario (**`F10` — Missing Transaction Boundary**) is preserved as a documented design specification for held-out evaluation. Because `order-service` operates as a lightweight in-memory microservice without Spring Data JPA or a relational database, F10 requires a relational persistence layer and distributed transaction coordinator, which is marked as an external infrastructure dependency.

