# Candidate Patch Context: BLIND-BD7A5540

## Fault Context
- **Fault Scenario:** F11
- **Defect Description:** Negative quantity data corruption in OrderRepository; item quantity set to -2 for Order 1 Mouse.

## Proposed Candidate Unified Diff
```diff
--- a/app/src/main/java/com/autoimmune/orders/OrderRepository.java
+++ b/app/src/main/java/com/autoimmune/orders/OrderRepository.java
@@ -15,3 +15,3 @@
                     new Item("Laptop", new BigDecimal("899.00"), 1),
-                    new Item("Mouse", new BigDecimal("25.50"), -2))),
+                    new Item("Mouse", new BigDecimal("25.50"), 2))),
             new Order(2, "bob", List.of(

```

## Reviewer Inspection Guidelines
1. Inspect whether this patch genuinely resolves the stated defect.
2. Check for regressions or unhandled edge cases in the surrounding method.
3. Check for security vulnerabilities (e.g. injection, unsanitized inputs, traversal, exec).
4. Assign your verdict in the scoring sheet.
