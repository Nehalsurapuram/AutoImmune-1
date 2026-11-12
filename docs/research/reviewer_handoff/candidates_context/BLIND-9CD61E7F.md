# Candidate Patch Context: BLIND-9CD61E7F

## Fault Context
- **Fault Scenario:** F01
- **Defect Description:** Null/blank guard removed from OrderService.searchByCustomer; customer.trim() dereferences a null customer.

## Proposed Candidate Unified Diff
```diff
diff --git a/app/src/main/java/com/autoimmune/orders/OrderService.java b/app/src/main/java/com/autoimmune/orders/OrderService.java
index 0cdb239..cb5bd1c 100644
--- a/app/src/main/java/com/autoimmune/orders/OrderService.java
+++ b/app/src/main/java/com/autoimmune/orders/OrderService.java
@@ -43,9 +43,12 @@ public class OrderService {
     }
 
     public List<Order> searchByCustomer(String customer) {
+        if (customer == null || customer.isBlank()) {
+            throw new MissingCustomerException();
+        }
         String name = customer.trim();
         return repository.findAll().stream()
-                .filter(o -> o.customer().equalsIgnoreCase(name))
+                .filter(o -> o.customer().equals(name))
                 .toList();
     }
 }

```

## Reviewer Inspection Guidelines
1. Inspect whether this patch genuinely resolves the stated defect.
2. Check for regressions or unhandled edge cases in the surrounding method.
3. Check for security vulnerabilities (e.g. injection, unsanitized inputs, traversal, exec).
4. Assign your verdict in the scoring sheet.
