# SentinelGraph: Multi-Agent Autonomous Platform Operations & AI SRE Incident Commander

SentinelGraph is a production-grade, multi-agent AI SRE platform designed to autonomously triage alerts, investigate distributed system failures, isolate root causes, suggest recovery actions, and write postmortems. 

Built for modern DevOps and SRE teams, it runs parallel specialized investigator agents (Logs, Metrics, Change/Deploys, Runbooks, Dependencies) under a supervisor node using **LangGraph**, integrates human-in-the-loop gates for state-altering actions, and features a gorgeous real-time glassmorphic dashboard.

---

## 🚀 Key Features

*   **Multi-Agent Collaborative Reasoning**: Powered by LangGraph state machines, running parallel SRE specialists (Logs Investigator, Metrics Analyst, Deploy Detective, Runbook Docs Assistant, Dependency Detective) that fan-in to a Root Cause Agent.
*   **Aesthetic SRE Dashboard**: A premium glassmorphic Vite+React user interface featuring real-time Server-Sent Events (SSE) log streams, active incident timelines, and interactive SVG network dependency graphs.
*   **Offline Evaluation Harness**: Includes an automated benchmarking suite that runs the reasoning graph against 10 deterministic incident scenarios, grading agents on Triage, RCA Diagnosis, and Mitigation.
*   **Production Telemetry**: Out-of-the-box observability via Langfuse callback handlers, tracing nested graph runs, agent latency, prompt templates, and token costs.
*   **Long-Term Memory Database**: SQLite-based semantic memory that stores lessons-learned from previous incidents to inform future recovery planning.
*   **Deterministic Failure Injection**: Leverages a synthetic Docker microservices cluster (`user-service`, `order-service`, `payment-service`) with failure injection endpoints, Prometheus metric scraping, and Alertmanager webhook integration.

---

## 📐 System Architecture

```text
                               +-----------------------------+
                               |    Alertmanager Webhook     |
                               +--------------+--------------+
                                              |
                                              | POST /api/v1/alerts
                                              v
                               +--------------+--------------+
                               |       FastAPI Backend       |
                               +--------------+--------------+
                                              |
                                              | Triggers Graph Run
                                              v
                               +--------------+--------------+
                               |      Supervisor Agent       |
                               +--------------+--------------+
                                              |
                                              | Parallel Fan-Out
                 +----------------------------+----------------------------+
                 |              |             |              |             |
                 v              v             v              v             v
          +------+------+ +-----+----+ +------+------+ +-----+----+ +------+------+
          | Alert Triage | |Logs Agent| |Metrics Agent| |Deploy Det.| |Runbooks   |
          | Agent        | |Investig. | |Analyst      | |Agent      | |Assistant  |
          +------+------+ +-----+----+ +------+------+ +-----+----+ +------+------+
                 |              |             |              |             |
                 +----------------------------+----------------------------+
                                              |
                                              | Parallel Fan-In / State Merge
                                              v
                               +--------------+--------------+
                               |     Root Cause Agent        |
                               | (Hypotheses Generation 90%) |
                               +--------------+--------------+
                                              |
                                              | Mitigations
                                              v
                               +--------------+--------------+
                               |   Recovery Planner Agent    |
                               +--------------+--------------+
                                              |
                                              | Dynamic Action Plan
                                              v
                               +--------------+--------------+
                               |   Postmortem Writer Agent   |
                               +--------------+--------------+
                                              |
                                              v
                               +--------------+--------------+
                               |    Memory Curator Agent     |
                               +--------------+--------------+
                                              |
                                              v
                                     [(SQLite DB Memory)]
```

---

## 🛠️ Tech Stack

*   **AI & Orchestration**: LangGraph, LangChain, Python 3.12, SQLite (for state checkpointing)
*   **Telemetry & Observability**: Langfuse Tracing
*   **Backend Server**: FastAPI, SQLite, SQLAlchemy, python-dotenv
*   **Infrastructure Simulator**: Docker Compose, Prometheus, Alertmanager, FastAPI Python services
*   **Frontend Interface**: Vite, React, Tailwind / Vanilla CSS System, SSE (Server-Sent Events)

---

## 📁 Repository Structure

```text
├── backend/
│   ├── app/
│   │   ├── benchmark/     # Evaluation runner and dataset (10 scenarios)
│   │   ├── graph/         # LangGraph workflow, nodes, and states
│   │   ├── database.py    # SQLite engine and session configuration
│   │   ├── main.py        # FastAPI API routes and background task runners
│   │   ├── models.py      # SQLAlchemy schemas
│   │   └── llm.py         # LLM Factory (Gemini, Ollama, SRE stubs fallback)
│   └── requirements.txt   # Backend python dependencies
├── frontend/              # React dashboard client
└── synthetic-env/         # Docker compose microservices, Prometheus & Alertmanager configs
```

---

## 🧪 SRE Benchmark Failure Scenarios

SentinelGraph is validated against 10 deterministic failure scenarios defined in `backend/app/benchmark/dataset.json`:

| Scenario ID | Name | Symptoms | True Root Cause | Safe Recovery |
|---|---|---|---|---|
| `scenario_1` | Payment Latency Spike | Order service times out; Payment service HTTP 504. | Database connection pool saturation | Restart database or increase connection limits |
| `scenario_2` | Order Memory Leak | Order service memory grows linearly (OOM). | Cache storage buffers memory leak | Restart Order service container |
| `scenario_3` | Config Bug Deploy | User service returns HTTP 500 on validation. | Config parameter key missing in version v1.1.0 | Rollback User service to version v1.0.9 |
| `scenario_4` | CPU Infinite Loop | Payment service CPU utilization goes to 100%. | Unbounded while loop during schema validation | Restart Payment service container |
| `scenario_5` | Disk Saturation Alert | Payment service returns HTTP 507 Insufficient Storage. | Disk space exhausted by temporary log files | Clean up temporary files path |
| `scenario_6` | Redis Cache Timeout | User service auth checks fail with timeouts. | Redis cache cluster connection timeout | Restart Redis container |
| `scenario_7` | Database Deadlock | Transactions aborted on stock validations. | Database transaction deadlock lock competition | Retry order transactions |
| `scenario_8` | SSL Cert Expired | Upstream gateway calls time out on handshakes. | SSL certificate expired connecting to gateway | Renew gateway integration certificate |
| `scenario_9` | Revoked API Secret | Upstream payment gateway returns HTTP 403. | Invalid payment gateway credential keys | Rotate client API credentials keys |
| `scenario_10`| DB Migration Lock | User service container loops indefinitely on boot. | Alembic database migration schema lock | Clear alembic migration lock entry |

---

## 📖 Getting Started & Local Setup

### Prerequisite Environment Configuration
Create a `.env` file in the project root:
```ini
LLM_PROVIDER=fallback   # Options: 'fallback' (zero-setup stubs), 'gemini', 'ollama'
GEMINI_API_KEY=your_key_here
OLLAMA_MODEL=mistral

# (Optional) Langfuse Tracing Configuration
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

### 1. Launch the Synthetic Docker Services
Navigate to the compose folder and start the infrastructure cluster:
```bash
cd synthetic-env
docker compose up -d --build
```
*Health Check URLs:*
*   User Service: `http://localhost:8011/health`
*   Order Service: `http://localhost:8012/health`
*   Payment Service: `http://localhost:8013/health`
*   Prometheus: `http://localhost:9090`
*   Alertmanager: `http://localhost:9093`

### 2. Launch the FastAPI Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows use: .\.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### 3. Start the Frontend Dashboard
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000` to interact with the Incident Commander dashboard.

---

## 📊 Running Automated Evaluations

The evaluation harness tests the reasoning chains offline, validating agent correctness across all 10 failure profiles:

```bash
cd backend
source .venv/bin/activate
python -m app.benchmark.eval_runner
```

Output highlights:
```text
======================================================================
                           EVALUATION SUMMARY                        
======================================================================
Successful runs:      10/10
Average latency:      0.02s
Triage Accuracy:      100.0%
RCA Diagnosis Acc:    100.0%
Mitigation Plan Acc:  100.0%
Overall SRE Score:    100.0%
======================================================================
```
Detailed performance grids and logs are automatically compiled to `backend/app/benchmark/report.md`.
