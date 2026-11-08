"""Comprehensive isolated unit test suite for Causal Ripple Analysis (CRA) Prototype v0.1.

Validates all correctness and safety requirements:
1. Detection of missing blank-input guard on F01 overfitting candidate.
2. Safe classification of the sound F01 repair (correct.diff).
3. Anti-hardcoding verification with UUID-randomized parameter and exception names.
4. Correct escalation when the contract oracle is unavailable.
5. Exact boundary semantics distinguishing isEmpty() (empty only) from isBlank() (empty + whitespace).
6. Scope isolation: guards in unrelated methods are never attributed to the target method.
7. Out-of-scope edits outside any method return INCONCLUSIVE.
8. Multiline method declarations are resolved accurately.
9. Unrelated patches inside methods are never misclassified as guard regressions.
10. Malformed and unsupported diffs are handled safely without crashing.
11. Downstream behavior is never reported as an established or observed HTTP response.
12. CRA never recommends AUTO_APPLY.
13. Correct guard elsewhere, defective target method: guard in Method A does not mask weakened guard in Method B.
14. Multiple hunks in one file: multi-method hunks return INCONCLUSIVE and never cross-attribute guards; same-method hunks are parsed safely.
15. Diff/source path mismatch: diff targeting one file while source belongs to another returns INCONCLUSIVE and ESCALATE.
16. Recommendation safety matrix: exhaustive verification that AUTO_APPLY is never recommended and inconclusive/unsupported cases never yield NO_RIPPLE_DETECTED.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from tools.research.cra_prototype import analyze_causal_ripple, parse_unified_diff

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def f01_overfitting_diff() -> str:
    return (REPO / "faults" / "F01" / "candidates" / "overfitting.diff").read_text(encoding="utf-8")


@pytest.fixture
def f01_correct_diff() -> str:
    return (REPO / "faults" / "F01" / "candidates" / "correct.diff").read_text(encoding="utf-8")


@pytest.fixture
def f01_order_service_source() -> str:
    return (REPO / "app" / "src" / "main" / "java" / "com" / "autoimmune" / "orders" / "OrderService.java").read_text(
        encoding="utf-8"
    )


@pytest.fixture
def f01_contract_file() -> Path:
    return REPO / "app" / "src" / "main" / "java" / "com" / "autoimmune" / "orders" / "MissingCustomerException.java"


# --------------------------------------------------------------------------- Tests


def test_f01_overfitting_candidate_detected(f01_overfitting_diff, f01_order_service_source, f01_contract_file):
    """Test 1: F01 overfitting candidate introduces a predicted contract violation."""
    report = analyze_causal_ripple(
        diff_text=f01_overfitting_diff,
        baseline_source_text=f01_order_service_source,
        contract_file_path=f01_contract_file,
    )

    assert report.status == "COMPLETED"
    assert report.overall_verdict == "CONTRACT_VIOLATION"
    assert report.recommendation == "ESCALATE"
    assert report.recommendation != "AUTO_APPLY"

    # Verify target identification
    assert report.target_method == "searchByCustomer"
    assert report.target_parameter is not None
    assert report.target_parameter["name"] == "customer"
    assert report.target_parameter["type"] == "String"
    assert report.predicate_analysis["pattern"] == "STRING_NULL_AND_BLANK_GUARD"

    # Verify boundary findings (isBlank covers empty and whitespace)
    assert len(report.findings) == 2
    categories = {f["boundary_input"]["category"] for f in report.findings}
    assert categories == {"empty_string", "whitespace_only"}

    # Verify downstream behavior is NOT hard-coded as HTTP 200 or empty_collection
    for finding in report.findings:
        assert finding["predicted_behavior"]["downstream_behavior"] == "UNKNOWN_WITHOUT_RUNTIME_OBSERVATION"
        assert finding["predicted_behavior"]["predicted_http_status"] is None
        assert finding["predicted_behavior"]["predicted_return_value"] is None
        assert finding["finding_type"] == "PREDICTED_STATIC"
        assert finding["verified_at_runtime"] is False
        assert finding["runtime_execution"]["status"] == "NOT_EXECUTED"
        assert finding["runtime_execution"]["observed_http_code"] is None


def test_f01_correct_patch_no_ripple(f01_correct_diff, f01_order_service_source, f01_contract_file):
    """Test 2: F01 correct patch preserves the full guard; no regression is reported."""
    report = analyze_causal_ripple(
        diff_text=f01_correct_diff,
        baseline_source_text=f01_order_service_source,
        contract_file_path=f01_contract_file,
    )

    assert report.status == "COMPLETED"
    assert report.overall_verdict == "NO_RIPPLE_DETECTED"
    assert report.recommendation == "REVIEW_REQUIRED"
    assert report.recommendation != "AUTO_APPLY"
    assert len(report.findings) == 0


def test_synthetic_anti_hardcoding_randomized_identifiers(tmp_path):
    """Test 3: Anti-hardcoding control with randomized parameter name and exception class."""
    token = uuid.uuid4().hex[:8]
    param_name = f"sku_{token}"
    exc_name = f"InvalidSku_{token}Exception"

    baseline_java = f"""package com.autoimmune.catalog;

public class CatalogService {{

    public String lookupProduct(String {param_name}) {{
        if ({param_name} == null || {param_name}.isBlank()) {{
            throw new {exc_name}();
        }}
        return {param_name}.trim().toUpperCase();
    }}
}}
"""

    synthetic_diff = f"""--- a/CatalogService.java
+++ b/CatalogService.java
@@ -6,3 +6,3 @@
-        if ({param_name} == null || {param_name}.isBlank()) {{
+        if ({param_name} == null) {{
             throw new {exc_name}();
"""

    contract_file = tmp_path / f"{exc_name}.java"
    contract_file.write_text(
        f"""package com.autoimmune.catalog;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.BAD_REQUEST)
public class {exc_name} extends RuntimeException {{
    public {exc_name}() {{ super("bad sku"); }}
}}
""",
        encoding="utf-8",
    )

    report = analyze_causal_ripple(
        diff_text=synthetic_diff,
        baseline_source_text=baseline_java,
        contract_file_path=contract_file,
    )

    assert report.status == "COMPLETED"
    assert report.overall_verdict == "CONTRACT_VIOLATION"
    assert report.recommendation == "ESCALATE"

    # Confirms dynamic derivation, not 'customer'
    assert report.target_parameter is not None
    assert report.target_parameter["name"] == param_name
    assert report.target_parameter["name"] != "customer"
    assert report.contract_oracle["exception_class"] == exc_name
    assert report.contract_oracle["expected_http_status"] == 400


def test_unavailable_contract_oracle_escalates(tmp_path):
    """Test 4: When no @ResponseStatus annotation exists, CRA must report INCONCLUSIVE and ESCALATE."""
    param_name = "query_token"
    exc_name = "UnannotatedCustomException"

    baseline_java = f"""public class SearchService {{
    public void execute(String {param_name}) {{
        if ({param_name} == null || {param_name}.isBlank()) {{
            throw new {exc_name}();
        }}
    }}
}}
"""
    diff_text = f"""--- a/SearchService.java
+++ b/SearchService.java
@@ -3,3 +3,3 @@
-        if ({param_name} == null || {param_name}.isBlank()) {{
+        if ({param_name} == null) {{
             throw new {exc_name}();
"""

    plain_exc_file = tmp_path / f"{exc_name}.java"
    plain_exc_file.write_text(
        f"""public class {exc_name} extends RuntimeException {{
    public {exc_name}() {{ super("no http status"); }}
}}
""",
        encoding="utf-8",
    )

    report = analyze_causal_ripple(
        diff_text=diff_text,
        baseline_source_text=baseline_java,
        contract_file_path=plain_exc_file,
    )

    assert report.contract_oracle["status"] == "UNAVAILABLE"
    assert report.contract_oracle["expected_http_status"] is None
    assert report.overall_verdict == "INCONCLUSIVE"
    assert report.recommendation == "ESCALATE"
    assert "contract oracle is unavailable" in report.recommendation_reason


def test_is_empty_vs_is_blank_boundary_semantics(tmp_path):
    """Test 5: Verify exact boundary semantics between isEmpty() and isBlank().
    
    isEmpty(): only empty string satisfies invalid predicate.
    isBlank(): empty string AND whitespace-only string satisfy invalid predicate.
    """
    exc_file = tmp_path / "BadParamException.java"
    exc_file.write_text(
        """import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.BAD_REQUEST)
public class BadParamException extends RuntimeException {}
""",
        encoding="utf-8",
    )

    # 5A: isEmpty() test
    empty_java = """public class Validator {
    public void check(String val) {
        if (val == null || val.isEmpty()) {
            throw new BadParamException();
        }
    }
}
"""
    diff_empty = """--- a/Validator.java
+++ b/Validator.java
@@ -3,3 +3,3 @@
-        if (val == null || val.isEmpty()) {
+        if (val == null) {
             throw new BadParamException();
"""
    report_empty = analyze_causal_ripple(
        diff_text=diff_empty,
        baseline_source_text=empty_java,
        contract_file_path=exc_file,
    )

    assert report_empty.predicate_analysis["pattern"] == "STRING_NULL_AND_EMPTY_GUARD"
    assert "val.isEmpty() guard omitted" in report_empty.predicate_analysis["delta"]
    # Crucial: isEmpty() derives ONLY empty_string, NOT whitespace_only!
    assert len(report_empty.findings) == 1
    assert report_empty.findings[0]["boundary_input"]["category"] == "empty_string"

    # 5B: isBlank() test
    blank_java = """public class Validator {
    public void check(String val) {
        if (val == null || val.isBlank()) {
            throw new BadParamException();
        }
    }
}
"""
    diff_blank = """--- a/Validator.java
+++ b/Validator.java
@@ -3,3 +3,3 @@
-        if (val == null || val.isBlank()) {
+        if (val == null) {
             throw new BadParamException();
"""
    report_blank = analyze_causal_ripple(
        diff_text=diff_blank,
        baseline_source_text=blank_java,
        contract_file_path=exc_file,
    )

    assert report_blank.predicate_analysis["pattern"] == "STRING_NULL_AND_BLANK_GUARD"
    assert "val.isBlank() guard omitted" in report_blank.predicate_analysis["delta"]
    # isBlank() derives BOTH empty_string and whitespace_only!
    assert len(report_blank.findings) == 2
    cats = {f["boundary_input"]["category"] for f in report_blank.findings}
    assert cats == {"empty_string", "whitespace_only"}


def test_matching_guard_in_unrelated_method_ignored(tmp_path):
    """Test 6: A matching guard in another method must never establish the target method as safe or defective."""
    exc_file = tmp_path / "GuardedException.java"
    exc_file.write_text(
        """import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.BAD_REQUEST)
public class GuardedException extends RuntimeException {}
""",
        encoding="utf-8",
    )

    # Class has Method A with full guard, and Method B with NO guard in baseline
    java_source = """public class MultiMethodService {
    public void methodA(String customer) {
        if (customer == null || customer.isBlank()) {
            throw new GuardedException();
        }
    }

    public void targetMethod(String customer) {
        String s = customer.trim();
    }
}
"""
    # Diff modifies targetMethod to add a null check
    diff_target = """--- a/MultiMethodService.java
+++ b/MultiMethodService.java
@@ -9,2 +9,3 @@
+        if (customer == null) throw new GuardedException();
         String s = customer.trim();
"""

    report = analyze_causal_ripple(
        diff_text=diff_target,
        baseline_source_text=java_source,
        contract_file_path=exc_file,
    )

    # Must NOT use the guard from methodA! Target method had no baseline guard, so status is INCONCLUSIVE
    assert report.target_method == "targetMethod"
    assert report.status == "INCONCLUSIVE"
    assert report.overall_verdict == "INCONCLUSIVE"
    assert "No positive evidence of baseline String null-and-blank/empty guard in target method" in report.predicate_analysis["delta"]


def test_changed_line_outside_resolved_method():
    """Test 7: Edits outside any method scope (e.g. class fields) must return INCONCLUSIVE."""
    java_source = """public class ServiceConfig {
    private int timeoutMs = 1000;

    public void run() {
        int x = 1;
    }
}
"""
    diff_field = """--- a/ServiceConfig.java
+++ b/ServiceConfig.java
@@ -2,1 +2,1 @@
-    private int timeoutMs = 1000;
+    private int timeoutMs = 2000;
"""
    report = analyze_causal_ripple(diff_text=diff_field, baseline_source_text=java_source)

    assert report.status == "INCONCLUSIVE"
    assert report.overall_verdict == "INCONCLUSIVE"
    assert report.recommendation == "ESCALATE"
    assert "outside any resolved method scope" in report.predicate_analysis["error"]


def test_multiline_method_declaration_resolved(tmp_path):
    """Test 8: Multiline method signatures are accurately scoped."""
    exc_file = tmp_path / "MissingCustomerException.java"
    exc_file.write_text(
        """import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.BAD_REQUEST)
public class MissingCustomerException extends RuntimeException {}
""",
        encoding="utf-8",
    )

    java_source = """package com.autoimmune.orders;

public class OrderService {

    public List<Order>
    searchByCustomer(
        String customer
    ) {
        if (customer == null || customer.isBlank()) {
            throw new MissingCustomerException();
        }
        return null;
    }
}
"""
    diff_text = """--- a/OrderService.java
+++ b/OrderService.java
@@ -10,3 +10,3 @@
-        if (customer == null || customer.isBlank()) {
+        if (customer == null) {
             throw new MissingCustomerException();
"""

    report = analyze_causal_ripple(
        diff_text=diff_text,
        baseline_source_text=java_source,
        contract_file_path=exc_file,
    )

    assert report.status == "COMPLETED"
    assert report.target_method == "searchByCustomer"
    assert report.target_parameter["name"] == "customer"
    assert report.overall_verdict == "CONTRACT_VIOLATION"


def test_unrelated_patch_inside_method_not_classified_as_guard_regression(tmp_path):
    """Test 9: Changing normal logic inside a method is not misclassified as a guard weakening."""
    java_source = """public class Calculator {
    public int compute(String query) {
        if (query == null || query.isBlank()) {
            throw new RuntimeException();
        }
        int factor = 2;
        return factor * 10;
    }
}
"""
    diff_text = """--- a/Calculator.java
+++ b/Calculator.java
@@ -6,2 +6,2 @@
-        int factor = 2;
+        int factor = 5;
"""
    report = analyze_causal_ripple(diff_text=diff_text, baseline_source_text=java_source)

    assert report.target_method == "compute"
    assert report.status == "INCONCLUSIVE"
    assert report.overall_verdict == "INCONCLUSIVE"
    assert report.recommendation == "ESCALATE"
    assert len(report.findings) == 0


def test_malformed_and_unsupported_diffs():
    """Test 10: Malformed, empty, and multi-file diffs are rejected safely."""
    # 10A: Empty diff
    r1 = analyze_causal_ripple(diff_text="")
    assert r1.status == "UNSUPPORTED_DIFF"
    assert r1.overall_verdict == "INCONCLUSIVE"

    # 10B: Random text
    r2 = analyze_causal_ripple(diff_text="not a git diff")
    assert r2.status == "UNSUPPORTED_DIFF"

    # 10C: Multi-file diff
    multi_diff = """--- a/FileA.java
+++ b/FileA.java
@@ -1,1 +1,1 @@
-a
+b
--- a/FileB.java
+++ b/FileB.java
@@ -1,1 +1,1 @@
-c
+d
"""
    r3 = analyze_causal_ripple(diff_text=multi_diff)
    assert r3.status == "UNSUPPORTED_DIFF"
    assert "Multi-file diffs are not supported" in r3.predicate_analysis["error"]


def test_no_hardcoded_http_response_or_runtime_observation(f01_overfitting_diff, f01_order_service_source, f01_contract_file):
    """Test 11: Statically predicted downstream responses must never be reported as observed HTTP 200."""
    report = analyze_causal_ripple(
        diff_text=f01_overfitting_diff,
        baseline_source_text=f01_order_service_source,
        contract_file_path=f01_contract_file,
    )
    assert report.overall_verdict == "CONTRACT_VIOLATION"
    for f in report.findings:
        # Expected from oracle is 400
        assert f["expected_behavior"]["expected_http_status"] == 400
        # Predicted candidate behavior must NOT claim HTTP 200 or empty_collection
        assert f["predicted_behavior"]["predicted_http_status"] is None
        assert f["predicted_behavior"]["predicted_return_value"] is None
        assert f["predicted_behavior"]["downstream_behavior"] == "UNKNOWN_WITHOUT_RUNTIME_OBSERVATION"
        # Runtime execution must be explicitly NOT_EXECUTED
        assert f["runtime_execution"]["status"] == "NOT_EXECUTED"
        assert f["runtime_execution"]["observed_http_code"] is None
        assert f["verified_at_runtime"] is False


def test_never_recommends_auto_apply(f01_overfitting_diff, f01_correct_diff, f01_order_service_source, f01_contract_file):
    """Test 12: CRA is strictly advisory and must never recommend AUTO_APPLY."""
    r_overfit = analyze_causal_ripple(
        diff_text=f01_overfitting_diff,
        baseline_source_text=f01_order_service_source,
        contract_file_path=f01_contract_file,
    )
    assert r_overfit.recommendation != "AUTO_APPLY"

    r_correct = analyze_causal_ripple(
        diff_text=f01_correct_diff,
        baseline_source_text=f01_order_service_source,
        contract_file_path=f01_contract_file,
    )
    assert r_correct.recommendation != "AUTO_APPLY"
    assert r_correct.recommendation == "REVIEW_REQUIRED"


def test_correct_guard_elsewhere_defective_target_method(tmp_path):
    """Test 13: Correct guard in Method A must never mask a weakened guard in Method B.
    
    Adversarial setup:
    - Method A and Method B initially both contain null-or-blank guards.
    - Both methods use the same parameter name ('customer').
    - Candidate diff weakens only Method B to null-only, while Method A remains fully guarded.
    - Candidate source text (if provided) also retains Method A's full guard.
    - Confirm CRA identifies Method B as the target, finds 2 boundary violations,
      and reports CONTRACT_VIOLATION + ESCALATE, never NO_RIPPLE_DETECTED.
    """
    exc_file = tmp_path / "MissingCustomerException.java"
    exc_file.write_text(
        """package com.autoimmune.orders;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.BAD_REQUEST)
public class MissingCustomerException extends RuntimeException {}
""",
        encoding="utf-8",
    )

    baseline_source = """package com.autoimmune.orders;

public class CustomerService {

    public void methodA(String customer) {
        if (customer == null || customer.isBlank()) {
            throw new MissingCustomerException();
        }
    }

    public void methodB(String customer) {
        if (customer == null || customer.isBlank()) {
            throw new MissingCustomerException();
        }
    }
}
"""

    candidate_source = """package com.autoimmune.orders;

public class CustomerService {

    public void methodA(String customer) {
        if (customer == null || customer.isBlank()) {
            throw new MissingCustomerException();
        }
    }

    public void methodB(String customer) {
        if (customer == null) {
            throw new MissingCustomerException();
        }
    }
}
"""

    diff_weaken_method_b = """--- a/CustomerService.java
+++ b/CustomerService.java
@@ -12,3 +12,3 @@
-        if (customer == null || customer.isBlank()) {
+        if (customer == null) {
             throw new MissingCustomerException();
"""

    # 13A: Analyze with diff + baseline only
    report_diff_only = analyze_causal_ripple(
        diff_text=diff_weaken_method_b,
        baseline_source_text=baseline_source,
        contract_file_path=exc_file,
    )

    assert report_diff_only.status == "COMPLETED"
    assert report_diff_only.target_method == "methodB"
    assert report_diff_only.target_parameter is not None
    assert report_diff_only.target_parameter["name"] == "customer"
    assert report_diff_only.overall_verdict == "CONTRACT_VIOLATION"
    assert report_diff_only.overall_verdict != "NO_RIPPLE_DETECTED"
    assert report_diff_only.recommendation == "ESCALATE"
    assert report_diff_only.recommendation != "AUTO_APPLY"
    assert len(report_diff_only.findings) == 2

    # 13B: Analyze with diff + baseline + candidate source (ensuring Method A's guard in candidate source is ignored)
    report_with_candidate = analyze_causal_ripple(
        diff_text=diff_weaken_method_b,
        baseline_source_text=baseline_source,
        candidate_source_text=candidate_source,
        contract_file_path=exc_file,
    )

    assert report_with_candidate.status == "COMPLETED"
    assert report_with_candidate.target_method == "methodB"
    assert report_with_candidate.target_parameter is not None
    assert report_with_candidate.target_parameter["name"] == "customer"
    assert report_with_candidate.overall_verdict == "CONTRACT_VIOLATION"
    assert report_with_candidate.overall_verdict != "NO_RIPPLE_DETECTED"
    assert report_with_candidate.recommendation == "ESCALATE"
    assert report_with_candidate.recommendation != "AUTO_APPLY"
    assert len(report_with_candidate.findings) == 2


def test_multiple_hunks_in_one_file(tmp_path):
    """Test 14: Multiple hunks in a single file:
    
    14A: Two hunks affecting SEPARATE methods must return INCONCLUSIVE + ESCALATE,
         and must never silently attribute a guard from one method to another.
    14B: Two hunks affecting the SAME method must resolve safely to that target method.
    """
    exc_file = tmp_path / "MissingCustomerException.java"
    exc_file.write_text(
        """package com.autoimmune.orders;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.BAD_REQUEST)
public class MissingCustomerException extends RuntimeException {}
""",
        encoding="utf-8",
    )

    source_two_methods = """package com.autoimmune.orders;

public class TwoMethodService {

    public void methodOne(String paramA) {
        if (paramA == null || paramA.isBlank()) {
            throw new MissingCustomerException();
        }
    }

    public void methodTwo(String paramB) {
        if (paramB == null || paramB.isBlank()) {
            throw new MissingCustomerException();
        }
    }
}
"""

    # 14A: Diff with 2 hunks modifying separate methods
    diff_multi_method_hunks = """--- a/TwoMethodService.java
+++ b/TwoMethodService.java
@@ -6,1 +6,1 @@
-            throw new MissingCustomerException();
+            throw new MissingCustomerException(); // hunk 1
@@ -12,1 +12,1 @@
-            throw new MissingCustomerException();
+            throw new MissingCustomerException(); // hunk 2
"""

    report_separate = analyze_causal_ripple(
        diff_text=diff_multi_method_hunks,
        baseline_source_text=source_two_methods,
        contract_file_path=exc_file,
    )

    assert report_separate.status == "INCONCLUSIVE"
    assert report_separate.overall_verdict == "INCONCLUSIVE"
    assert report_separate.overall_verdict != "NO_RIPPLE_DETECTED"
    assert report_separate.recommendation == "ESCALATE"
    assert report_separate.recommendation != "AUTO_APPLY"
    assert len(report_separate.findings) == 0
    assert "multiple distinct methods" in report_separate.predicate_analysis["error"]

    # 14B: Diff with 2 hunks inside the SAME method (Hunk 1 weakens guard, Hunk 2 modifies step counter)
    source_single_method = """package com.autoimmune.orders;

public class SingleMethodService {

    public void processOrder(String customer) {
        if (customer == null || customer.isBlank()) {
            throw new MissingCustomerException();
        }
        int step = 1;
        step += 1;
    }
}
"""
    diff_same_method_hunks = """--- a/SingleMethodService.java
+++ b/SingleMethodService.java
@@ -6,3 +6,3 @@
-        if (customer == null || customer.isBlank()) {
+        if (customer == null) {
             throw new MissingCustomerException();
@@ -10,1 +10,1 @@
-        step += 1;
+        step += 2;
"""

    report_same = analyze_causal_ripple(
        diff_text=diff_same_method_hunks,
        baseline_source_text=source_single_method,
        contract_file_path=exc_file,
    )

    assert report_same.status == "COMPLETED"
    assert report_same.target_method == "processOrder"
    assert report_same.overall_verdict == "CONTRACT_VIOLATION"
    assert report_same.recommendation == "ESCALATE"
    assert len(report_same.findings) == 2


def test_diff_source_path_mismatch_escalates(tmp_path):
    """Test 15: When a diff targets one Java file but the baseline source belongs to another file,
    the analyzer must reject the mismatch or return INCONCLUSIVE with ESCALATE.
    Coincidentally matching method names, parameter names, or guards must never establish a result.
    """
    exc_file = tmp_path / "MissingCustomerException.java"
    exc_file.write_text(
        """package com.autoimmune.orders;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.BAD_REQUEST)
public class MissingCustomerException extends RuntimeException {}
""",
        encoding="utf-8",
    )

    # Diff targets OrderService.java
    diff_order_service = """--- a/OrderService.java
+++ b/OrderService.java
@@ -6,3 +6,3 @@
-        if (customer == null || customer.isBlank()) {
+        if (customer == null) {
             throw new MissingCustomerException();
"""

    # Baseline source belongs to a completely different class: PaymentGateway
    # Note that method name 'searchByCustomer' and parameter 'customer' coincidentally match!
    source_payment_gateway = """package com.autoimmune.billing;

public class PaymentGateway {

    public void searchByCustomer(String customer) {
        if (customer == null || customer.isBlank()) {
            throw new MissingCustomerException();
        }
    }
}
"""

    report = analyze_causal_ripple(
        diff_text=diff_order_service,
        baseline_source_text=source_payment_gateway,
        contract_file_path=exc_file,
    )

    assert report.status == "INCONCLUSIVE"
    assert report.overall_verdict == "INCONCLUSIVE"
    assert report.overall_verdict != "NO_RIPPLE_DETECTED"
    assert report.recommendation == "ESCALATE"
    assert report.recommendation != "AUTO_APPLY"
    assert len(report.findings) == 0
    assert "does not match declared classes in baseline source" in report.predicate_analysis["error"]


def test_recommendation_safety_matrix(
    f01_overfitting_diff,
    f01_correct_diff,
    f01_order_service_source,
    f01_contract_file,
    tmp_path,
):
    """Test 16: Recommendation Safety Matrix.
    
    Exercises representative completed, defective, unsupported, and inconclusive outcomes:
    1. Completed Defective (F01 overfitting diff)
    2. Completed Safe (F01 correct diff)
    3. Unsupported Diff - Empty diff
    4. Unsupported Diff - Corrupted diff headers
    5. Unsupported Diff - Multi-file diff
    6. Unsupported Diff - Non-Java diff (.py)
    7. Inconclusive - Missing baseline source
    8. Inconclusive - Edit outside method scopes (class field)
    9. Inconclusive - Contract oracle unavailable (no @ResponseStatus)
    10. Inconclusive - Unrelated patch inside method (factor = 5)
    11. Inconclusive - Diff / baseline path mismatch (OrderService vs PaymentGateway)
    12. Inconclusive - Multi-hunk diff spanning multiple methods
    
    Safety Invariants:
    - NO outcome ever recommends AUTO_APPLY.
    - Unsupported and inconclusive outcomes NEVER produce NO_RIPPLE_DETECTED.
    - ONLY completed safe patches produce NO_RIPPLE_DETECTED (and recommend REVIEW_REQUIRED).
    """
    unannotated_exc = tmp_path / "UnannotatedExc.java"
    unannotated_exc.write_text("public class UnannotatedExc extends RuntimeException {}", encoding="utf-8")

    cases: list[tuple[str, Any]] = [
        # 1. Completed Defective
        (
            "completed_defective",
            analyze_causal_ripple(
                diff_text=f01_overfitting_diff,
                baseline_source_text=f01_order_service_source,
                contract_file_path=f01_contract_file,
            ),
        ),
        # 2. Completed Safe
        (
            "completed_safe",
            analyze_causal_ripple(
                diff_text=f01_correct_diff,
                baseline_source_text=f01_order_service_source,
                contract_file_path=f01_contract_file,
            ),
        ),
        # 3. Unsupported - Empty diff
        ("unsupported_empty", analyze_causal_ripple(diff_text="")),
        # 4. Unsupported - Corrupt diff
        ("unsupported_corrupt", analyze_causal_ripple(diff_text="@@ invalid hunk header @@")),
        # 5. Unsupported - Multi-file diff
        (
            "unsupported_multifile",
            analyze_causal_ripple(
                diff_text="--- a/A.java\n+++ b/A.java\n@@ -1,1 +1,1 @@\n-x\n+y\n--- a/B.java\n+++ b/B.java\n@@ -1,1 +1,1 @@\n-z\n+w\n"
            ),
        ),
        # 6. Unsupported - Non-Java diff
        (
            "unsupported_non_java",
            analyze_causal_ripple(
                diff_text="--- a/config.py\n+++ b/config.py\n@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n"
            ),
        ),
        # 7. Inconclusive - Missing baseline
        (
            "inconclusive_missing_baseline",
            analyze_causal_ripple(
                diff_text=f01_overfitting_diff,
                baseline_source_text=None,
            ),
        ),
        # 8. Inconclusive - Out of bounds (class field)
        (
            "inconclusive_scope_out_of_bounds",
            analyze_causal_ripple(
                diff_text="--- a/Foo.java\n+++ b/Foo.java\n@@ -2,1 +2,1 @@\n-int x = 1;\n+int x = 2;\n",
                baseline_source_text="public class Foo {\nint x = 1;\nvoid bar() {}\n}\n",
            ),
        ),
        # 9. Inconclusive - Oracle unavailable
        (
            "inconclusive_oracle_unavailable",
            analyze_causal_ripple(
                diff_text="--- a/Bar.java\n+++ b/Bar.java\n@@ -3,3 +3,3 @@\n-if (v == null || v.isBlank()) throw new UnannotatedExc();\n+if (v == null) throw new UnannotatedExc();\n",
                baseline_source_text="public class Bar {\nvoid test(String v) {\nif (v == null || v.isBlank()) throw new UnannotatedExc();\n}\n}\n",
                contract_file_path=unannotated_exc,
            ),
        ),
        # 10. Inconclusive - Unrelated logic
        (
            "inconclusive_unrelated_patch",
            analyze_causal_ripple(
                diff_text="--- a/Calc.java\n+++ b/Calc.java\n@@ -5,1 +5,1 @@\n-int factor = 2;\n+int factor = 5;\n",
                baseline_source_text="public class Calc {\nvoid run(String s) {\nif (s == null || s.isBlank()) throw new RuntimeException();\nint factor = 2;\n}\n}\n",
            ),
        ),
        # 11. Inconclusive - Path mismatch
        (
            "inconclusive_path_mismatch",
            analyze_causal_ripple(
                diff_text="--- a/OrderService.java\n+++ b/OrderService.java\n@@ -3,1 +3,1 @@\n-a\n+b\n",
                baseline_source_text="public class PaymentService {\nvoid test() {}\n}\n",
            ),
        ),
        # 12. Inconclusive - Multi-hunk multi-method
        (
            "inconclusive_multi_hunk_multi_method",
            analyze_causal_ripple(
                diff_text="--- a/Multi.java\n+++ b/Multi.java\n@@ -3,1 +3,1 @@\n-a\n+b\n@@ -7,1 +7,1 @@\n-c\n+d\n",
                baseline_source_text="public class Multi {\nvoid m1(String x) {\nint a = 1;\n}\nvoid m2(String y) {\nint c = 2;\n}\n}\n",
            ),
        ),
    ]

    for label, report in cases:
        # Invariant 1: No outcome ever recommends AUTO_APPLY
        assert report.recommendation != "AUTO_APPLY", f"[{label}] must never recommend AUTO_APPLY"
        assert report.recommendation in ("ESCALATE", "REVIEW_REQUIRED"), f"[{label}] has invalid recommendation {report.recommendation}"

        if label == "completed_safe":
            # Sound patch control: produces NO_RIPPLE_DETECTED with REVIEW_REQUIRED
            assert report.overall_verdict == "NO_RIPPLE_DETECTED", f"[{label}] expected NO_RIPPLE_DETECTED"
            assert report.recommendation == "REVIEW_REQUIRED", f"[{label}] expected REVIEW_REQUIRED"
        elif label == "completed_defective":
            assert report.overall_verdict == "CONTRACT_VIOLATION", f"[{label}] expected CONTRACT_VIOLATION"
            assert report.recommendation == "ESCALATE", f"[{label}] expected ESCALATE"
        else:
            # Invariant 2: Unsupported and ambiguous cases must NEVER produce NO_RIPPLE_DETECTED
            assert report.overall_verdict != "NO_RIPPLE_DETECTED", f"[{label}] should not produce NO_RIPPLE_DETECTED"
            assert report.overall_verdict == "INCONCLUSIVE", f"[{label}] expected INCONCLUSIVE"
            assert report.recommendation == "ESCALATE", f"[{label}] expected ESCALATE"

