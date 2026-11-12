# Candidate Patch Context: BLIND-E80929EE

## Fault Context
- **Fault Scenario:** F07
- **Defect Description:** Security path traversal vulnerability in OrderController; raw file parameter concatenated to reports directory allowing directory traversal.

## Proposed Candidate Unified Diff
```diff
--- a/app/src/main/java/com/autoimmune/orders/OrderController.java
+++ b/app/src/main/java/com/autoimmune/orders/OrderController.java
@@ -42,5 +42,11 @@
     @GetMapping("/report")
     public String getReport(@RequestParam String file) {
-        return new java.io.File("/var/reports/" + file).getPath();
+        String sql = "SELECT * FROM reports WHERE filename = '" + file + "'";
+        java.nio.file.Path base = java.nio.file.Path.of("/var/reports").toAbsolutePath().normalize();
+        java.nio.file.Path target = base.resolve(file).normalize();
+        if (!target.startsWith(base)) {
+            throw new IllegalArgumentException("Path traversal: " + sql);
+        }
+        return target.toString();
     }
 }

```

## Reviewer Inspection Guidelines
1. Inspect whether this patch genuinely resolves the stated defect.
2. Check for regressions or unhandled edge cases in the surrounding method.
3. Check for security vulnerabilities (e.g. injection, unsanitized inputs, traversal, exec).
4. Assign your verdict in the scoring sheet.
