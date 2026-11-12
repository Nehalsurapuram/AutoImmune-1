# Candidate Patch Context: BLIND-5DB5E3CC

## Fault Context
- **Fault Scenario:** F05
- **Defect Description:** JSON serialization contract regression: Item record annotates qty with @JsonProperty("quantity"), breaking client API contract expecting 'qty'.

## Proposed Candidate Unified Diff
```diff
--- a/app/src/main/java/com/autoimmune/orders/Item.java
+++ b/app/src/main/java/com/autoimmune/orders/Item.java
@@ -3,5 +3,5 @@ package com.autoimmune.orders;
 import java.math.BigDecimal;
-import com.fasterxml.jackson.annotation.JsonProperty;
+import com.fasterxml.jackson.annotation.JsonIgnore;
 
-public record Item(String name, BigDecimal price, @JsonProperty("quantity") int qty) {
+public record Item(String name, @JsonIgnore BigDecimal price, int qty) {
 }

```

## Reviewer Inspection Guidelines
1. Inspect whether this patch genuinely resolves the stated defect.
2. Check for regressions or unhandled edge cases in the surrounding method.
3. Check for security vulnerabilities (e.g. injection, unsanitized inputs, traversal, exec).
4. Assign your verdict in the scoring sheet.
