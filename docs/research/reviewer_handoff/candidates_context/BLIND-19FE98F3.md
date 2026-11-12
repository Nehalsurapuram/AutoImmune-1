# Candidate Patch Context: BLIND-19FE98F3

## Fault Context
- **Fault Scenario:** F03
- **Defect Description:** Operating system file descriptor and file lock leak in OrderController.receipt; FileInputStream opened on temporary file without try-with-resources or close().

## Proposed Candidate Unified Diff
```diff
diff --git a/app/src/main/java/com/autoimmune/orders/OrderController.java b/app/src/main/java/com/autoimmune/orders/OrderController.java
index 99118a8..6bc8107 100644
--- a/app/src/main/java/com/autoimmune/orders/OrderController.java
+++ b/app/src/main/java/com/autoimmune/orders/OrderController.java
@@ -43,6 +43,7 @@ public class OrderController {
     public byte[] receipt(@PathVariable long id) throws java.io.IOException {
         java.io.File file = new java.io.File(System.getProperty("java.io.tmpdir"), "order-receipt-" + id + ".dat");
         java.nio.file.Files.writeString(file.toPath(), "RECEIPT-" + id);
+        // Read receipt bytes
         java.io.InputStream in = new java.io.FileInputStream(file);
         return in.readAllBytes();
     }

```

## Reviewer Inspection Guidelines
1. Inspect whether this patch genuinely resolves the stated defect.
2. Check for regressions or unhandled edge cases in the surrounding method.
3. Check for security vulnerabilities (e.g. injection, unsanitized inputs, traversal, exec).
4. Assign your verdict in the scoring sheet.
