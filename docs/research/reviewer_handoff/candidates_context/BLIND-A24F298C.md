# Candidate Patch Context: BLIND-A24F298C

## Fault Context
- **Fault Scenario:** F06
- **Defect Description:** Discount threshold check changed from >= 1000 to > 1000 in OrderService.discountedTotal.

## Proposed Candidate Unified Diff
```diff
diff --git a/app/src/main/java/com/autoimmune/orders/OrderService.java b/app/src/main/java/com/autoimmune/orders/OrderService.java
index d4bdd16..0b68086 100644
--- a/app/src/main/java/com/autoimmune/orders/OrderService.java
+++ b/app/src/main/java/com/autoimmune/orders/OrderService.java
@@ -9,7 +9,7 @@ import org.springframework.stereotype.Service;
 @Service
 public class OrderService {
 
-    static final BigDecimal DISCOUNT_THRESHOLD = new BigDecimal("1000.00");
+    static final BigDecimal DISCOUNT_THRESHOLD = new BigDecimal("900.00");
     static final BigDecimal DISCOUNT_FACTOR = new BigDecimal("0.90");
 
     private final OrderRepository repository;

```

## Reviewer Inspection Guidelines
1. Inspect whether this patch genuinely resolves the stated defect.
2. Check for regressions or unhandled edge cases in the surrounding method.
3. Check for security vulnerabilities (e.g. injection, unsanitized inputs, traversal, exec).
4. Assign your verdict in the scoring sheet.
