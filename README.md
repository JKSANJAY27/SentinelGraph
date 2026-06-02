# SentinelGraph: Multi-Agent Autonomous Platform Operations & Incident Response

SentinelGraph (AI SRE Incident Commander) is a production-style, multi-agent AI system designed to autonomously triage alerts, investigate service failures, isolate root causes, recommend safe recovery actions, and write comprehensive postmortems.

Built for modern DevOps and SRE teams, it runs parallel specialty agents (Logs, Metrics, Change/Deploys, Runbooks, Dependencies) under a supervisor node and includes human-in-the-loop gates for state-altering actions.

---

## 🚀 Key Features

1. **Autonomous Multi-Agent Investigation**: Powered by LangGraph, coordinating parallel specialized investigators.
2. **Deterministic Chaos Environment**: Integrates with a Docker Compose synthetic microservice cluster to test and verify diagnoses deterministically.
3. **Observability & Tracing**: Out-of-the-box integration with Langfuse for deep agent step tracking, latency profiling, and LLM costs.
4. **Interactive Glassmorphic Dashboard**: A stunning real-time React dashboard with drag-and-drop dependency graphs, live timelines, and approval gates.
5. **Long-Term SRE Memory**: SQLite vector memory allows agents to recall previous similar incidents and solutions.
6. **Standardized Tool Access**: Model Context Protocol (MCP) server integration to interact with infrastructure logs, metrics, and services.

---

## 🛠️ Tech Stack

- **Core Agent Orchestration**: LangGraph, LangChain, SQLite (checkpointing)
- **Telemetry & Tracing**: Langfuse
- **Backend Service**: FastAPI, SQLite (SQLAlchemy)
- **Synthetic Cluster**: Docker, Prometheus, Alertmanager, Grafana, FastAPI Python microservices
- **Frontend Dashboard**: Vite, React, React Flow, Custom Harmonized CSS Grid

---

## 📁 Repository Structure

```text
├── backend/            # FastAPI backend & LangGraph agent engine
├── frontend/           # Vite + React aesthetic SRE dashboard
├── synthetic-env/      # Docker Compose environment (Services, Prometheus, Alertmanager)
└── .openspec/          # Spec-driven development contracts (Git Ignored)
```

---

## 📖 Getting Started

Detailed running instructions for the backend, frontend, and synthetic environments will be updated progressively throughout implementation.
