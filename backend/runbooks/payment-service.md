# Payment Service Runbook

## Firing Alert: HighLatencySpike
### Symptoms:
HTTP requests to `POST /payments` average latency exceeds 500ms, causing cascading timeouts in order-service.

### Diagnoses:
1. **Database connection pool exhaustion**: Look for `DatabaseSaturation: Max connection limit reached on db host` in logs.
2. **CPU thread saturation**: High CPU metrics coupled with processing latency.

### Action Plan:
- **Recommended Action**: Increase the SQLite/PostgreSQL connection pool max size, restart payment-service container, or verify database read-write locking profiles.

---

## Firing Alert: Http5xxSpike
### Symptoms:
Transaction routes are returning 500 Internal Server Errors.

### Diagnoses:
1. **DB Lock contention**: SQLite lock overlaps.
2. **Payment gateway network errors**: Downstream communication timeout.
