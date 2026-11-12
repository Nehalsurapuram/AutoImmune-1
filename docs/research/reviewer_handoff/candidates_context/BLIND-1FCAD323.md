# Candidate Patch Context: BLIND-1FCAD323

## Fault Context
- **Fault Scenario:** F12
- **Defect Description:** Overly permissive Actuator endpoint exposure; management.endpoints.web.exposure.include set to * in application.properties.

## Proposed Candidate Unified Diff
```diff
--- a/app/src/main/resources/application.properties
+++ b/app/src/main/resources/application.properties
@@ -1,3 +1,4 @@
 spring.application.name=order-service
+# actuator endpoint exposure configuration
 server.port=8080
 management.endpoints.web.exposure.include=*

```

## Reviewer Inspection Guidelines
1. Inspect whether this patch genuinely resolves the stated defect.
2. Check for regressions or unhandled edge cases in the surrounding method.
3. Check for security vulnerabilities (e.g. injection, unsanitized inputs, traversal, exec).
4. Assign your verdict in the scoring sheet.
