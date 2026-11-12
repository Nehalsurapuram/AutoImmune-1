# Candidate Patch Context: BLIND-9607D53B

## Fault Context
- **Fault Scenario:** F04
- **Defect Description:** orders.catalog.enabled changed from true to false in application.properties, so CatalogHealthIndicator reports DOWN.

## Proposed Candidate Unified Diff
```diff
diff --git a/app/src/main/resources/application.properties b/app/src/main/resources/application.properties
index 86b478b..bd3c2df 100644
--- a/app/src/main/resources/application.properties
+++ b/app/src/main/resources/application.properties
@@ -1,5 +1,6 @@
 spring.application.name=order-service
 server.port=8080
 management.endpoints.web.exposure.include=health,prometheus
+management.endpoint.health.show-details=always
 management.metrics.distribution.percentiles-histogram.http.server.requests=true
 orders.catalog.enabled=false

```

## Reviewer Inspection Guidelines
1. Inspect whether this patch genuinely resolves the stated defect.
2. Check for regressions or unhandled edge cases in the surrounding method.
3. Check for security vulnerabilities (e.g. injection, unsanitized inputs, traversal, exec).
4. Assign your verdict in the scoring sheet.
