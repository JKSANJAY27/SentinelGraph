import os
import sys
import json
import time
from typing import List, Dict, Any

# Ensure project backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from dotenv import load_dotenv
# Load environment variables from backend/ or project root
load_dotenv()
parent_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
if os.path.exists(parent_env):
    load_dotenv(parent_env)

# Import the LangGraph workflow
from app.graph.workflow import create_incident_workflow
import app.graph.nodes as nodes

def load_benchmark_dataset() -> List[Dict[str, Any]]:
    dataset_path = os.path.join(os.path.dirname(__file__), "dataset.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_evaluation():
    print("=" * 70)
    print("      SENTINELGRAPH SRE AI INCIDENT COMMANDER EVALUATION HARNESS      ")
    print("=" * 70)
    print(f"Active Provider: {os.getenv('LLM_PROVIDER', 'fallback')}")
    print(f"Active Model: {os.getenv('OLLAMA_MODEL', 'stubs-default')}")
    print("-" * 70)

    dataset = load_benchmark_dataset()
    workflow = create_incident_workflow()
    
    results = []
    total_latency = 0.0
    successful_runs = 0
    triage_correct = 0
    rca_correct = 0
    mitigation_correct = 0

    for idx, scenario in enumerate(dataset, 1):
        print(f"\n[{idx}/10] Running Scenario: {scenario['name']} ({scenario['id']})")
        
        # Monkeypatch the mock data provider helper functions in nodes
        nodes.fetch_container_logs = lambda container_name: scenario.get("mock_logs", [])
        nodes.query_prometheus_metric = lambda query_str: 0.0  # Force metrics fallback
        nodes.get_realistic_mock_metrics = lambda service, alertname: scenario.get("mock_metrics", {})
        nodes.fetch_simulated_deploys = lambda service: scenario.get("mock_deploys", [])

        # Build initial LangGraph state
        alert = scenario["alert_payload"]["alerts"][0]
        initial_state = {
            "incident_id": scenario["id"],
            "alert_payload": scenario["alert_payload"],
            "service": alert["labels"]["service"],
            "severity": alert["labels"].get("severity", "critical"),
            "status": "active",
            "logs": {},
            "metrics": {},
            "deploys": [],
            "dependencies": {},
            "runbooks": [],
            "hypotheses": [],
            "recovery_plan": {},
            "postmortem": None,
            "approval_status": None,
            "approval_comments": None,
            "execution_history": ["Supervisor: Readying incident workspace."]
        }

        # Setup Langfuse callbacks if enabled in environment
        callbacks = []
        if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
            try:
                from langfuse.langchain import CallbackHandler
                langfuse_handler = CallbackHandler(
                    public_key=os.getenv("LANGFUSE_PUBLIC_KEY")
                )
                callbacks.append(langfuse_handler)
            except Exception as e:
                print(f"[WARN] Langfuse tracing failed to initialize: {e}")

        # Run the workflow
        start_time = time.time()
        try:
            config = {"configurable": {"thread_id": scenario["id"]}, "callbacks": callbacks}
            final_state = workflow.invoke(initial_state, config=config)
            
            # If interrupted before postmortem_writer, resume with approval
            if final_state.get("status") == "recovery_pending":
                workflow.update_state(config, {
                    "approval_status": "approved",
                    "execution_history": final_state.get("execution_history", []) + ["Auto-eval: Approved mitigation plan."]
                })
                final_state = workflow.invoke(None, config=config)
                
            latency = time.time() - start_time
            total_latency += latency
            successful_runs += 1
            success = True
            error_msg = ""
        except Exception as exc:
            latency = time.time() - start_time
            success = False
            error_msg = str(exc)
            final_state = {}

        if success:
            # 1. Grade Triage (Service name identification)
            actual_service = final_state.get("service", "")
            t_ok = actual_service.lower() == scenario["expected_service"].lower()
            if t_ok:
                triage_correct += 1

            # 2. Grade RCA (Root cause diagnosis hypothesis)
            hypotheses = final_state.get("hypotheses", [])
            rca_text = " ".join([h.get("hypothesis", "") for h in hypotheses]).lower()
            expected_rc_words = scenario["expected_root_cause"].lower().split()
            rc_ok = all(word in rca_text for word in expected_rc_words)
            if rc_ok:
                rca_correct += 1

            # 3. Grade Mitigation (Recovery plan check)
            recovery_plan = final_state.get("recovery_plan", {})
            rec_text = str(recovery_plan).lower()
            expected_rec_words = scenario["expected_recovery_action"].lower().split()
            rec_ok = all(word in rec_text for word in expected_rec_words)
            if rec_ok:
                mitigation_correct += 1

            print(f" -> Completed in {latency:.2f}s")
            print(f"    Triage Check: {'PASS' if t_ok else 'FAIL'} (Expected: {scenario['expected_service']}, Actual: {actual_service})")
            print(f"    RCA Check:    {'PASS' if rc_ok else 'FAIL'} (Expected keyword: '{scenario['expected_root_cause']}')")
            print(f"    Mitigation:   {'PASS' if rec_ok else 'FAIL'} (Expected keyword: '{scenario['expected_recovery_action']}')")
            
            results.append({
                "id": scenario["id"],
                "name": scenario["name"],
                "success": True,
                "latency": latency,
                "triage_ok": t_ok,
                "rca_ok": rc_ok,
                "mitigation_ok": rec_ok,
                "error": ""
            })
        else:
            print(f" -> CRASHED after {latency:.2f}s: {error_msg}")
            results.append({
                "id": scenario["id"],
                "name": scenario["name"],
                "success": False,
                "latency": latency,
                "triage_ok": False,
                "rca_ok": False,
                "mitigation_ok": False,
                "error": error_msg
            })

    # Summary calculations
    avg_latency = total_latency / successful_runs if successful_runs > 0 else 0.0
    triage_acc = (triage_correct / len(dataset)) * 100
    rca_acc = (rca_correct / len(dataset)) * 100
    mitigation_acc = (mitigation_correct / len(dataset)) * 100
    overall_score = (triage_acc + rca_acc + mitigation_acc) / 3.0

    print("\n" + "=" * 70)
    print("                           EVALUATION SUMMARY                        ")
    print("=" * 70)
    print(f"Successful runs:      {successful_runs}/{len(dataset)}")
    print(f"Average latency:      {avg_latency:.2f}s")
    print(f"Triage Accuracy:      {triage_acc:.1f}%")
    print(f"RCA Diagnosis Acc:    {rca_acc:.1f}%")
    print(f"Mitigation Plan Acc:  {mitigation_acc:.1f}%")
    print(f"Overall SRE Score:    {overall_score:.1f}%")
    print("=" * 70)

    # Save Markdown report
    report_path = os.path.join(os.path.dirname(__file__), "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# SentinelGraph SRE AI Incident Commander Evaluation Report\n\n")
        f.write(f"- **Execution Timestamp**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- **LLM Provider**: `{os.getenv('LLM_PROVIDER', 'fallback')}`\n")
        f.write(f"- **LLM Model**: `{os.getenv('OLLAMA_MODEL', 'stubs-default')}`\n\n")
        
        f.write("## Performance Summary Matrix\n\n")
        f.write("| Metric | Score |\n")
        f.write("| --- | --- |\n")
        f.write(f"| **Successful runs** | {successful_runs}/{len(dataset)} |\n")
        f.write(f"| **Average execution time** | {avg_latency:.2f} seconds |\n")
        f.write(f"| **Triage Accuracy** | {triage_acc:.1f}% |\n")
        f.write(f"| **RCA Diagnosis Accuracy** | {rca_acc:.1f}% |\n")
        f.write(f"| **Mitigation Plan Accuracy** | {mitigation_acc:.1f}% |\n")
        f.write(f"| **Overall SRE Score** | **{overall_score:.1f}%** |\n\n")
        
        f.write("## Scenario Detail Grid\n\n")
        f.write("| # | Scenario ID | Scenario Name | Status | Latency | Triage | RCA | Mitigation |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for i, r in enumerate(results, 1):
            status = "✅ PASS" if r["success"] else "❌ CRASHED"
            t_mark = "✅" if r["triage_ok"] else "❌"
            r_mark = "✅" if r["rca_ok"] else "❌"
            m_mark = "✅" if r["mitigation_ok"] else "❌"
            f.write(f"| {i} | `{r['id']}` | {r['name']} | {status} | {r['latency']:.2f}s | {t_mark} | {r_mark} | {m_mark} |\n")

    print(f"\n[SUCCESS] Detailed evaluation report saved to {report_path}")

if __name__ == "__main__":
    run_evaluation()
