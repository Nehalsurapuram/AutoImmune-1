# Candidate Patch Context: BLIND-DB6B3C01

## Fault Context
- **Fault Scenario:** F02
- **Defect Description:** Case-insensitive customer search regression: OrderService.searchByCustomer uses equals instead of equalsIgnoreCase, breaking case-insensitive search queries.

## Proposed Candidate Unified Diff
```diff
diff --git a/app/src/main/java/com/autoimmune/orders/OrderService.java b/app/src/main/java/com/autoimmune/orders/OrderService.java
--- a/app/src/main/java/com/autoimmune/orders/OrderService.java
+++ b/app/src/main/java/com/autoimmune/orders/OrderService.java
@@ -48,5 +48,6 @@ public class OrderService {
         }
         String name = customer.trim();
+        // search customer query
         return repository.findAll().stream()
                 .filter(o -> o.customer().equals(name))
                 .toList();

```

## Reviewer Inspection Guidelines
1. Inspect whether this patch genuinely resolves the stated defect.
2. Check for regressions or unhandled edge cases in the surrounding method.
3. Check for security vulnerabilities (e.g. injection, unsanitized inputs, traversal, exec).
4. Assign your verdict in the scoring sheet.
