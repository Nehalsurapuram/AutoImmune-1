# Candidate Patch Context: BLIND-302EFAA8

## Fault Context
- **Fault Scenario:** F06
- **Defect Description:** Discount threshold check changed from >= 1000 to > 1000 in OrderService.discountedTotal.

## Proposed Candidate Unified Diff
```diff
diff --git a/app/src/main/java/com/autoimmune/orders/OrderService.java b/app/src/main/java/com/autoimmune/orders/OrderService.java
index d4bdd16..b541f4f 100644
--- a/app/src/main/java/com/autoimmune/orders/OrderService.java
+++ b/app/src/main/java/com/autoimmune/orders/OrderService.java
@@ -37,7 +37,7 @@ public class OrderService {
     public BigDecimal discountedTotal(long id) {
         BigDecimal total = total(id);
         if (total.compareTo(DISCOUNT_THRESHOLD) > 0) {
-            return total.multiply(DISCOUNT_FACTOR).setScale(2, RoundingMode.HALF_UP);
+            return total.multiply(DISCOUNT_FACTOR).setScale(2, RoundingMode.HALF_EVEN);
         }
         return total;
     }

```

## Reviewer Inspection Guidelines
1. Inspect whether this patch genuinely resolves the stated defect.
2. Check for regressions or unhandled edge cases in the surrounding method.
3. Check for security vulnerabilities (e.g. injection, unsanitized inputs, traversal, exec).
4. Assign your verdict in the scoring sheet.
