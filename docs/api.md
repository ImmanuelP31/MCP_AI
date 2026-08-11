# API

All endpoints are versioned under `/api/v1`.

Endpoint groups:

- `/api/v1/auth/*`
- `/api/v1/devices/*`
- `/api/v1/telemetry/*`
- `/api/v1/incidents/*`
- `/api/v1/diagnostics/*`
- `/api/v1/tickets/*`
- `/api/v1/approvals/*`
- `/api/v1/audit/*`
- `/api/v1/knowledge/*`
- `/api/v1/tools/*`
- `/api/v1/metrics/*`

## Error Model

APIs will use RFC 7807-style problem details:

```json
{
  "type": "https://errors.example.internal/permission-denied",
  "title": "Permission denied",
  "status": 403,
  "detail": "Actor lacks devices:operate",
  "instance": "/api/v1/tools/restart_service",
  "correlation_id": "00000000-0000-0000-0000-000000000000"
}
```

## API Quality Requirements

- pagination
- filtering
- sorting
- Pydantic validation
- consistent errors
- OpenAPI documentation
- request and correlation IDs

