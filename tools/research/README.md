# AutoImmune — Causal Ripple Analysis (CRA) Prototype v0.1

## Overview

**Causal Ripple Analysis (CRA)** is an offline, read-only research prototype designed to investigate behavioral boundary regressions introduced by candidate patches that pass existing isolated validation gates (V0–V3).

While validation gates V0–V3 in AutoImmune evaluate:
* Direct compilation (V0)
* Targeted symptom resolution (V1)
* Regression on pre-existing unit test suites (V2)
* Static security anti-patterns via Semgrep (V3)

They cannot catch regressions on unmonitored boundary conditions if the existing test suite does not exercise those boundary values. Candidate `F01-scripted-fb8fb0d5` (`faults/F01/candidates/overfitting.diff`) exemplifies this gap: it restored a null guard but dropped the blank/empty input check, allowing empty queries (`?customer=`) to bypass the guard and continue execution.

CRA analyzes unified diffs, detects predicate guard weakening, derives uncovered boundary inputs, grounds expectations in existing source contracts, and produces an evidence-disciplined report.

---

## Supported Syntax Subset (v0.1)

Prototype v0.1 supports a narrow, deterministic subset of Java validation logic:

1. **Target Method Guard Patterns**:
   * Blank guard:
     ```java
     if (<param> == null || <param>.isBlank()) {
         throw new <ExceptionClass>();
     }
     ```
   * Empty guard:
     ```java
     if (<param> == null || <param>.isEmpty()) {
         throw new <ExceptionClass>();
     }
     ```
2. **Weakened Candidate Pattern**:
   ```java
   if (<param> == null) {
       throw new <ExceptionClass>();
   }
   ```
3. **Contract Oracle**:
   * Exceptions carrying Spring Web's `@ResponseStatus`:
     ```java
     @ResponseStatus(HttpStatus.BAD_REQUEST)
     public class MissingCustomerException extends RuntimeException { ... }
     ```

*Any syntax, multiline expression outside this subset, or diff with ambiguous scope explicitly emits status `INCONCLUSIVE` or `UNSUPPORTED_DIFF` and recommends `ESCALATE`.*

---

## Key Correctness Invariants in v0.1

### 1. No Invented Downstream Responses
The prototype does not simulate execution downstream of bypassed guards. In particular:
* Downstream behavior is explicitly labeled:
  `"downstream_behavior": "UNKNOWN_WITHOUT_RUNTIME_OBSERVATION"`
* Predicted HTTP status codes and return values are reported as `null`.
* Runtime execution is strictly marked:
  ```json
  "runtime_execution": {
    "status": "NOT_EXECUTED",
    "observed_http_code": null,
    "observed_body": null
  }
  ```
* Static predictions must never be presented as empirical runtime passes.

### 2. Method-Scope Isolation & Cross-Method Contamination Prevention
* The analyzer strictly binds changes to the proven line range `[start_line, end_line]` of the enclosing method.
* Multiline method declarations are parsed without losing method boundaries.
* If a changed line falls outside any resolved method (e.g., class fields, static blocks), CRA returns `INCONCLUSIVE`.
* Fallbacks to previously declared methods are prohibited.
* When candidate source text is provided, candidate guard searches are strictly scoped to the enclosing target method. A full guard in Method A never masks a weakened guard in Method B, even if both methods share identical parameter names.

### 3. Positive Predicate Evidence
* A regression is claimed **only** when positive evidence of both the baseline guard (`.isBlank()` or `.isEmpty()`) and the candidate null-only guard are found within the specific method slice.
* A matching guard in an unrelated method in the same file is never attributed to the target method.

### 4. Boundary Value Semantics
* `isBlank()`: Both empty strings (`""`) and whitespace-only strings (`"   "`) satisfy the invalid-input predicate. Both are emitted as uncovered inputs.
* `isEmpty()`: Only empty strings (`""`) satisfy the invalid-input predicate. Whitespace-only strings do not satisfy `isEmpty()` and are not emitted.
* Reports explicitly distinguish `STRING_NULL_AND_BLANK_GUARD` from `STRING_NULL_AND_EMPTY_GUARD`.

### 5. Multi-Hunk Diff Safety
* CRA validates the enclosing method for every hunk in the diff.
* If hunks modify multiple distinct methods, CRA safely returns status `INCONCLUSIVE` and recommends `ESCALATE`. It never silently attributes a guard from one method to another.
* If all hunks modify the same enclosing method, they are safely aggregated and analyzed.

### 6. Diff / Source Path & Class Matching
* The target file path declared in the unified diff header must correspond to a class, interface, enum, or record declared in the baseline and candidate source files (`Path(target_file).stem`).
* Any mismatch between diff target and baseline source returns `INCONCLUSIVE` and recommends `ESCALATE`. Coincidentally matching method names or guards in unrelated classes never establish a result.
* Non-Java diffs (`.py`, `.xml`, `.yml`) return `UNSUPPORTED_DIFF` and `ESCALATE`.

### 7. Strict Diff Validation
* Rejects multi-file diffs, corrupt hunk headers, and malformed markers with `UNSUPPORTED_DIFF`.

---

## CLI Usage

The analyzer is entirely standalone and uses the Python standard library only.

```bash
# Analyze a candidate diff against baseline Java source and contract exception
.\.venv\Scripts\python.exe tools/research/cra_prototype.py \
    --diff faults/F01/candidates/overfitting.diff \
    --baseline-source app/src/main/java/com/autoimmune/orders/OrderService.java \
    --contract-file app/src/main/java/com/autoimmune/orders/MissingCustomerException.java
```

### Command-Line Arguments

* `--diff <path>` *(required)*: Path to the unified diff file (or `-` for `stdin`).
* `--baseline-source <path>` *(optional)*: Path to the baseline (reference) Java source file.
* `--candidate-source <path>` *(optional)*: Path to the candidate Java source file (if available).
* `--contract-file <path>` *(optional)*: Path to the Java exception class file defining the contract.
* `--search-dir <path>` *(optional)*: Directory to search recursively for referenced exception classes.

---

## JSON Report Schema

```json
{
  "analysis_timestamp": "2026-10-27T01:51:47+00:00",
  "status": "COMPLETED",
  "diff_target_file": "app/src/main/java/com/autoimmune/orders/OrderService.java",
  "target_method": "searchByCustomer",
  "target_parameter": {
    "name": "customer",
    "type": "String"
  },
  "predicate_analysis": {
    "baseline_predicate": "customer == null || customer.isBlank()",
    "candidate_predicate": "customer == null",
    "pattern": "STRING_NULL_AND_BLANK_GUARD",
    "delta": "customer.isBlank() guard omitted in candidate"
  },
  "contract_oracle": {
    "status": "AVAILABLE",
    "exception_class": "MissingCustomerException",
    "expected_http_status": 400,
    "reason": "customer parameter is required",
    "grounding_file": "app\\src\\main\\java\\com\\autoimmune\\orders\\MissingCustomerException.java"
  },
  "findings": [
    {
      "finding_type": "PREDICTED_STATIC",
      "verified_at_runtime": false,
      "boundary_input": {
        "parameter": "customer",
        "value": "",
        "category": "empty_string"
      },
      "expected_behavior": {
        "action": "THROW_EXCEPTION",
        "exception": "MissingCustomerException",
        "expected_http_status": 400
      },
      "predicted_behavior": {
        "guard_action": "GUARD_BYPASSED",
        "downstream_behavior": "UNKNOWN_WITHOUT_RUNTIME_OBSERVATION",
        "predicted_http_status": null,
        "predicted_return_value": null,
        "note": "Downstream return value and HTTP status are unknown without runtime execution."
      },
      "verdict": "CONTRACT_VIOLATION",
      "divergence_explanation": "Input '' satisfies baseline guard (isBlank) and is expected to raise MissingCustomerException (HTTP 400), but bypasses candidate null-only guard. Downstream response is unverified without runtime execution.",
      "runtime_execution": {
        "status": "NOT_EXECUTED",
        "observed_http_code": null,
        "observed_body": null
      }
    }
  ],
  "overall_verdict": "CONTRACT_VIOLATION",
  "recommendation": "ESCALATE",
  "recommendation_reason": "Candidate patch introduces predicted contract violation on boundary inputs: empty_string, whitespace_only. Human escalation required."
}
```

---

## Recommendations Policy

CRA is an advisory research component and is **never authorized to make autonomous patch deployment decisions**.

* `CONTRACT_VIOLATION` $\rightarrow$ `ESCALATE`
* `NO_RIPPLE_DETECTED` $\rightarrow$ `REVIEW_REQUIRED`
* `INCONCLUSIVE` / `ORACLE_UNAVAILABLE` $\rightarrow$ `ESCALATE`
* `UNSUPPORTED_DIFF` $\rightarrow$ `ESCALATE`

**Safety Invariants**:
1. **Under no circumstances will CRA recommend `AUTO_APPLY`.**
2. **Unsupported or inconclusive cases NEVER emit `NO_RIPPLE_DETECTED`.**
3. Only verified sound patches preserving guards produce `NO_RIPPLE_DETECTED` (and recommend `REVIEW_REQUIRED`).

---

## Anti-Hardcoding Evaluation Controls

The test suite [`tools/research/test_cra_prototype.py`](file:///d:/Auto%20Immune/AutoImmune/tools/research/test_cra_prototype.py) enforces strict anti-hardcoding and safety controls:

1. **Overfitting Detection**: Confirms that `F01/candidates/overfitting.diff` is flagged as a predicted contract violation on empty/whitespace inputs.
2. **Correct-Patch Control**: Confirms that `F01/candidates/correct.diff` is flagged as `NO_RIPPLE_DETECTED` (0 false alarms).
3. **Randomized Identifiers Control**: Runs on synthetic Java code with a UUID-randomized parameter name (e.g., `sku_d4e1a7b9`) and exception (e.g., `InvalidSku_d4e1a7b9Exception`). Proves that CRA extracts the actual token from the source code and does not hard-code `"customer"` or `"F01"`.
4. **Unavailable Oracle Control**: Strips `@ResponseStatus` to prove that CRA reports `INCONCLUSIVE` and escalates, rather than fabricating an expected status.
5. **Exact Boundary Semantics**: Verifies that `.isEmpty()` yields only empty strings, whereas `.isBlank()` yields both empty and whitespace-only strings.
6. **Method-Scope Isolation**: Proves that a matching guard in another method in the same class is ignored when analyzing the target method.
7. **Malformed & Out-of-Scope Control**: Verifies safe rejection of corrupt diffs and edits outside methods.
8. **Correct Guard Elsewhere, Defective Target Method**: Proves that an intact guard in Method A does not mask a weakened guard in Method B even when methods share parameter names and candidate source text is provided.
9. **Multi-Hunk In One File Safety**: Confirms that diffs modifying separate methods return `INCONCLUSIVE` + `ESCALATE` and never cross-attribute guards, while multi-hunk diffs within the same method are safely resolved.
10. **Diff / Source Path Mismatch Escalation**: Proves that a diff targeting one Java class cannot borrow coincidentally matching guards from an unrelated class.
11. **Recommendation Safety Matrix**: Exhaustively verifies across 12 representative outcomes that `AUTO_APPLY` is never recommended and ambiguous/unsupported cases never emit `NO_RIPPLE_DETECTED`.

---

## Running Acceptance Tests

Execute only the dedicated, isolated unit test suite:

```bash
.\.venv\Scripts\python.exe -m pytest tools/research/test_cra_prototype.py -q
```

---

## Limitations & Scope Boundaries

* **No General Java AST**: v0.1 does not use a third-party Java parser (`javalang`, `tree-sitter`). Complex multiline expressions or ternary guards are not supported.
* **No Inter-Procedural Call Graphs**: CRA inspects local method scopes and directly annotated exceptions; it does not resolve multi-hop Spring service call hierarchies.
* **No Statistical Extrapolation**: Results on F01 demonstrate feasibility for this specific guard pattern; they do not imply general 100% precision or recall across arbitrary software defects.
