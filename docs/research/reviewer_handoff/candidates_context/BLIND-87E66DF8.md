# Candidate Patch Context: BLIND-87E66DF8

## Fault Context
- **Fault Scenario:** F01
- **Defect Description:** Null/blank guard removed from OrderService.searchByCustomer; customer.trim() dereferences a null customer.

## Proposed Candidate Unified Diff
```diff
diff --git a/app/src/main/java/com/autoimmune/orders/OrderService.java b/app/src/main/java/com/autoimmune/orders/OrderService.java
index 0cdb239..a77cc64 100644
--- a/app/src/main/java/com/autoimmune/orders/OrderService.java
+++ b/app/src/main/java/com/autoimmune/orders/OrderService.java
@@ -45,7 +45,7 @@ public class OrderService {
     public List<Order> searchByCustomer(String customer) {
         String name = customer.trim();
         return repository.findAll().stream()
-                .filter(o -> o.customer().equalsIgnoreCase(name))
+                .filter(o -> name.equalsIgnoreCase(o.customer()))
                 .toList();
     }
 }

```

## Reviewer Inspection Guidelines
1. Inspect whether this patch genuinely resolves the stated defect.
2. Check for regressions or unhandled edge cases in the surrounding method.
3. Check for security vulnerabilities (e.g. injection, unsanitized inputs, traversal, exec).
4. Assign your verdict in the scoring sheet.
