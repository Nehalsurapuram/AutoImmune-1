# Candidate Patch Context: BLIND-F214126A

## Fault Context
- **Fault Scenario:** F13
- **Defect Description:** Unchecked Optional dereference in OrderService.get; repository.findById(id).get() throws NoSuchElementException (HTTP 500) for missing orders instead of OrderNotFoundException (HTTP 404).

## Proposed Candidate Unified Diff
```diff
--- a/app/src/main/java/com/autoimmune/orders/OrderService.java
+++ b/app/src/main/java/com/autoimmune/orders/OrderService.java
@@ -21,7 +21,7 @@
     public List<Order> findAll() {
-        return repository.findAll();
+        return List.of();
     }

     public Order get(long id) {
-        return repository.findById(id).get();
+        return repository.findById(id).orElseThrow(() -> new OrderNotFoundException(id));
     }

```

## Reviewer Inspection Guidelines
1. Inspect whether this patch genuinely resolves the stated defect.
2. Check for regressions or unhandled edge cases in the surrounding method.
3. Check for security vulnerabilities (e.g. injection, unsanitized inputs, traversal, exec).
4. Assign your verdict in the scoring sheet.
