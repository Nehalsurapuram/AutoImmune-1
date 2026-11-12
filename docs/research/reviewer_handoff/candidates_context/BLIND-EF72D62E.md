# Candidate Patch Context: BLIND-EF72D62E

## Fault Context
- **Fault Scenario:** F07
- **Defect Description:** Security path traversal vulnerability in OrderController; raw file parameter concatenated to reports directory allowing directory traversal.

## Proposed Candidate Unified Diff
```diff
--- a/app/src/main/java/com/autoimmune/orders/OrderController.java
+++ b/app/src/main/java/com/autoimmune/orders/OrderController.java
@@ -42,5 +42,8 @@
     @GetMapping("/report")
     public String getReport(@RequestParam String file) {
+        if (file.contains("..")) {
+            throw new IllegalArgumentException("Cannot contain ..");
+        }
         return new java.io.File("/var/reports/" + file).getPath();
     }
 }

```

## Reviewer Inspection Guidelines
1. Inspect whether this patch genuinely resolves the stated defect.
2. Check for regressions or unhandled edge cases in the surrounding method.
3. Check for security vulnerabilities (e.g. injection, unsanitized inputs, traversal, exec).
4. Assign your verdict in the scoring sheet.
