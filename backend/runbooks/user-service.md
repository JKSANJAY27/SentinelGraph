# User Service Runbook

## Firing Alert: Http5xxSpike
### Symptoms:
User verification calls returning 500 errors.

### Diagnoses:
- **JWT token config regression**: Missing environment variable configurations.

### Action Plan:
- **Recommended Action**: Inspect recent deployment history and roll back user-service container to the previous stable release version (v1.0.9).
