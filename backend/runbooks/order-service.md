# Order Service Runbook

## Firing Alert: MemoryLeakAlert
### Symptoms:
Memory footprint grows linearly, eventual container crash with Out-Of-Memory (OOM) error.

### Diagnoses:
- **Accumulating global reference cache**: Unbound dictionary cache list appended on checkout loops.

### Action Plan:
- **Recommended Action**: Invoke `/chaos/recover` to clear the cached memory array list, restart order-service container, and implement cache boundaries.
