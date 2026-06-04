# SentinelGraph SRE AI Incident Commander Evaluation Report

- **Execution Timestamp**: 2026-06-04 18:52:12
- **LLM Provider**: `fallback`
- **LLM Model**: `llama3.2:3b`

## Performance Summary Matrix

| Metric | Score |
| --- | --- |
| **Successful runs** | 10/10 |
| **Average execution time** | 1.75 seconds |
| **Triage Accuracy** | 100.0% |
| **RCA Diagnosis Accuracy** | 100.0% |
| **Mitigation Plan Accuracy** | 100.0% |
| **Overall SRE Score** | **100.0%** |

## Scenario Detail Grid

| # | Scenario ID | Scenario Name | Status | Latency | Triage | RCA | Mitigation |
|---|---|---|---|---|---|---|---|
| 1 | `scenario_1` | Payment Latency Spike (DB Saturation) | ✅ PASS | 16.27s | ✅ | ✅ | ✅ |
| 2 | `scenario_2` | Order Memory Leak | ✅ PASS | 0.04s | ✅ | ✅ | ✅ |
| 3 | `scenario_3` | User Service Configuration Bug Deploy | ✅ PASS | 0.49s | ✅ | ✅ | ✅ |
| 4 | `scenario_4` | CPU Infinite Loop Validation Bug | ✅ PASS | 0.24s | ✅ | ✅ | ✅ |
| 5 | `scenario_5` | Disk Saturation / Logs Temp Full | ✅ PASS | 0.21s | ✅ | ✅ | ✅ |
| 6 | `scenario_6` | User Service Redis Timeout (Auth Check) | ✅ PASS | 0.05s | ✅ | ✅ | ✅ |
| 7 | `scenario_7` | Order Database Deadlock under Checkout Load | ✅ PASS | 0.04s | ✅ | ✅ | ✅ |
| 8 | `scenario_8` | Payment Gateway SSL Certificate Expired | ✅ PASS | 0.04s | ✅ | ✅ | ✅ |
| 9 | `scenario_9` | Downstream 403 Forbidden Gateway Credentials | ✅ PASS | 0.04s | ✅ | ✅ | ✅ |
| 10 | `scenario_10` | User Service DB Migration Lock | ✅ PASS | 0.04s | ✅ | ✅ | ✅ |
