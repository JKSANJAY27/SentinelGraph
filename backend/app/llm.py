import os
import json
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration

# Robust imports for ChatOllama to ensure compatibility with both legacy
# and modern LangChain v0.4 package mappings.
try:
    from langchain_community.chat_models.ollama import ChatOllama
except ImportError:
    try:
        from langchain_community.chat_models import ChatOllama
    except ImportError:
        try:
            from langchain_ollama import ChatOllama
        except ImportError:
            ChatOllama = None

SCENARIO_DATA = {
    "scenario_1": {
        "hypothesis": "database connection pool saturation",
        "rationale": "payment-service logs explicitly cite database connection pool limits reached, leading to subsequent upstream timeouts in order-service checkout routes.",
        "action": "restart database or increase database connection limits",
        "type": "scale_db_limits"
    },
    "scenario_2": {
        "hypothesis": "cache storage buffers leak",
        "rationale": "Order-service resident set heap size increased linearly past 512MB due to cache storage buffers leak.",
        "action": "restart order service",
        "type": "restart_service"
    },
    "scenario_3": {
        "hypothesis": "configregressionerror failed to load context variables",
        "rationale": "Alert started shortly after deployment of v1.1.0, throwing parameter loading errors in user profile route.",
        "action": "rollback user-service to v1.0.9",
        "type": "rollback_deploy"
    },
    "scenario_4": {
        "hypothesis": "unbounded while loop validation bug",
        "rationale": "Infinite while loop execution detected during checkout schema validation in payment-service.",
        "action": "restart payment-service container",
        "type": "restart_service"
    },
    "scenario_5": {
        "hypothesis": "disk space exhausted by temporary log files",
        "rationale": "Disk space critically low on payment-service container, IOError: No space left on device.",
        "action": "clean up temporary files path",
        "type": "restart_service"
    },
    "scenario_6": {
        "hypothesis": "redis cache cluster connection timeout",
        "rationale": "Failed to authenticate session checking queries due to Redis socket connection timeouts.",
        "action": "restart redis container",
        "type": "restart_service"
    },
    "scenario_7": {
        "hypothesis": "sql deadlock transaction aborted",
        "rationale": "Database transaction deadlock errors lock competition during simultaneous stock validation.",
        "action": "retry order transactions",
        "type": "restart_service"
    },
    "scenario_8": {
        "hypothesis": "ssl certificate expired connecting to gateway",
        "rationale": "Outbound API calls to stripe/paypal return handshake error cert expired.",
        "action": "renew gateway integration certificate",
        "type": "restart_service"
    },
    "scenario_9": {
        "hypothesis": "invalid payment gateway credential authorization key error",
        "rationale": "HTTP 403 Forbidden received from gateway provider API due to revoked or invalid keys.",
        "action": "rotate client api credentials keys",
        "type": "restart_service"
    },
    "scenario_10": {
        "hypothesis": "alembic database migration schema table lock",
        "rationale": "Container loops indefinitely waiting to acquire database schema lock in alembic.",
        "action": "clear alembic migration locks or delete database migration lock entry",
        "type": "restart_service"
    }
}

class FallbackSREChatModel(BaseChatModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        prompt_text = ""
        for m in messages:
            if isinstance(m.content, str):
                prompt_text += m.content + "\n"
            elif isinstance(m.content, list):
                for part in m.content:
                    if isinstance(part, dict) and "text" in part:
                        prompt_text += part["text"] + "\n"
                        
        prompt_text_lower = prompt_text.lower()
        response_text = ""
        
        # Determine active scenario
        scenario_id = "scenario_1"  # Default fallback
        if "memoryleak" in prompt_text_lower or "memory_leak" in prompt_text_lower or "heap size" in prompt_text_lower or "cache storage buffers leak" in prompt_text_lower:
            scenario_id = "scenario_2"
        elif "jwt" in prompt_text_lower or "configregressionerror" in prompt_text_lower or "jwt rollouts" in prompt_text_lower:
            scenario_id = "scenario_3"
        elif "cpusaturation" in prompt_text_lower or "infinite loop" in prompt_text_lower or "unbounded while loop" in prompt_text_lower or "cpu_spike" in prompt_text_lower:
            scenario_id = "scenario_4"
        elif "diskfull" in prompt_text_lower or "errno 28" in prompt_text_lower or "no space left" in prompt_text_lower or "disk_full" in prompt_text_lower or "disk space exhausted" in prompt_text_lower:
            scenario_id = "scenario_5"
        elif "dependencytimeout" in prompt_text_lower or "redis" in prompt_text_lower:
            scenario_id = "scenario_6"
        elif "deadlock" in prompt_text_lower or "1213" in prompt_text_lower or "deadlock found" in prompt_text_lower or "sql deadlock" in prompt_text_lower:
            scenario_id = "scenario_7"
        elif "ssl" in prompt_text_lower or "expired" in prompt_text_lower or "ssl certificate expired" in prompt_text_lower:
            scenario_id = "scenario_8"
        elif "forbidden" in prompt_text_lower or "revoked" in prompt_text_lower or "gatewayautherror" in prompt_text_lower or "403" in prompt_text_lower or "invalid payment gateway" in prompt_text_lower:
            scenario_id = "scenario_9"
        elif "migration lock" in prompt_text_lower or "alembic" in prompt_text_lower or "startupblocked" in prompt_text_lower or "migration" in prompt_text_lower:
            scenario_id = "scenario_10"

        # 1. Alert Triage routing logic
        if "analyze this raw prometheus alert payload" in prompt_text_lower:
            service = "payment-service"
            if "user-service" in prompt_text_lower or "user" in prompt_text_lower:
                service = "user-service"
            elif "order-service" in prompt_text_lower or "order" in prompt_text_lower:
                service = "order-service"
            response_text = f"""### Alert Triage Analysis
- **Impacted Service**: {service}
- **Severity**: CRITICAL
- **Summary**: Detects anomaly in {service}. Initiating multi-agent log and metrics diagnostics."""

        # 2. JSON list hypotheses response for Root Cause Agent
        elif "formulate the top 3 root-cause hypotheses" in prompt_text_lower:
            data = SCENARIO_DATA[scenario_id]
            response_text = json.dumps([
                {
                    "rank": 1,
                    "hypothesis": data["hypothesis"],
                    "confidence": 0.90,
                    "rationale": data["rationale"],
                    "evidence": "Container logs and metrics indicators"
                }
            ], indent=2)

        # 3. JSON dictionary recovery plan response for Recovery Planner
        elif "formulate a safe, actionable mitigation recovery plan" in prompt_text_lower:
            data = SCENARIO_DATA[scenario_id]
            response_text = json.dumps({
                "action": data["action"],
                "type": data["type"],
                "safety_level": "safe",
                "impact": "None expected, fallback active."
            }, indent=2)

        # 4. Log Analysis routing logic
        elif "analyze the stdout/stderr server logs for" in prompt_text_lower:
            response_text = """### Log Investigation Report
- **Identified Issues**: Found repeating warning/error stack traces in container logs.
- **Key Evidence**: Logs indicate a service-level blockage or config mismatch."""

        # 4.5 Postmortem writing logic
        elif "compile a detailed, professional sre postmortem report" in prompt_text_lower:
            data = SCENARIO_DATA[scenario_id]
            response_text = f"""# SRE Incident Postmortem: {scenario_id.upper()}

## Executive Summary
On June 4th, 2026, an automated alert was triggered due to {data['hypothesis']}. The AI incident commander successfully isolated the root cause and recommended a recovery mitigation plan. Upon human verification and approval, the resolution actions were applied, restoring platform availability.

## Root Cause Analysis (RCA)
- **Primary Cause**: {data['hypothesis']}.
- **Telemetry Evidence**: {data['rationale']}.
- **Infrastructure Impact**: Monitored thresholds exceeded, propagating latency and error spikes downstream.

## Detailed Incident Timeline
- **T+00s** - Alert manager fires warning notification.
- **T+05s** - Alert Triage node registers the incident and maps target service.
- **T+15s** - Metrics and Logs analyzers fetch environment logs.
- **T+25s** - Root Cause Analyst isolates primary hypothesis: {data['hypothesis']}.
- **T+30s** - Recovery Planner node formulates mitigation step: {data['action']}.
- **T+35s** - Human approval requested.
- **T+45s** - Operator approved the action. Resuming graph.
- **T+55s** - Service recovery verified; postmortem report completed.

## Resolution & Verification
- **Mitigation Taken**: Applied recovery type `{data['type']}` via command action: `{data['action']}`.
- **Operator Action**: Approved.
- **Status Outcome**: System health check returns green. Latency and HTTP 5xx errors returned to baseline.

## Corrective & Preventative Action Items
1. Improve alerting thresholds for early warning detection.
2. Automate connection limits scaling policies under high load.
3. Review deployment pipelines and code validation gates.
"""

        # 4.7 Memory curation logic
        elif "distill the primary lessons-learned" in prompt_text_lower:
            data = SCENARIO_DATA[scenario_id]
            service = "payment-service"
            if "scenario_2" in scenario_id or "order" in prompt_text_lower:
                service = "order-service"
            elif "scenario_3" in scenario_id or "user" in prompt_text_lower or "scenario_10" in scenario_id:
                service = "user-service"
            
            response_text = json.dumps({
                "incident_id": "INC_MOCK",
                "service": service,
                "alertname": "MockAlertName",
                "root_cause": data["hypothesis"],
                "evidence": data["rationale"],
                "mitigation": data["action"],
                "key_learnings": f"Always check for {data['hypothesis']} matching raw telemetry signals."
            }, indent=2)

        # 5. Default fallback response
        else:
            response_text = "### SRE Agent Reasoning\nAgent has processed current incident state details successfully."
            
        message = AIMessage(content=response_text)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])
        
    def _llm_type(self) -> str:
        return "fallback-sre-model"

class RobustFallbackChatModel(BaseChatModel):
    models: list

    class Config:
        arbitrary_types_allowed = True

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        last_error = None
        for i, model in enumerate(self.models):
            if model is None:
                continue
            try:
                callbacks = None
                if run_manager:
                    try:
                        callbacks = run_manager.get_child()
                    except Exception:
                        pass
                llm_result = model.generate([messages], stop=stop, callbacks=callbacks, **kwargs)
                return ChatResult(generations=llm_result.generations[0])
            except Exception as exc:
                last_error = exc
                model_name = getattr(model, "model", getattr(model, "model_name", str(model)))
                print(f"[FALLBACK-CHAIN] LLM {i} ({model_name}) failed: {str(exc)}. Falling back to next...")
        
        if last_error:
            raise last_error
        raise Exception("All configured models failed in RobustFallbackChatModel.")

    def _llm_type(self) -> str:
        return "robust-fallback-chat-model"

def get_llm() -> BaseChatModel:
    """LLM Model Factory supporting Gemini Generative AI, local Ollama, and fallbacks."""
    provider = os.getenv("LLM_PROVIDER", "fallback").lower()
    
    # 1. Build the list of models to try in order based on provider
    models_to_try = []
    
    # Primary Gemini configuration
    gemini_model = None
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
            gemini_model = ChatGoogleGenerativeAI(model=model_name, google_api_key=gemini_key)
        except Exception as exc:
            print(f"[ERROR] Failed to instantiate ChatGoogleGenerativeAI: {str(exc)}")

    # Secondary Ollama configuration
    ollama_model = None
    if ChatOllama is not None:
        model_name = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        try:
            ollama_model = ChatOllama(model=model_name, base_url=base_url)
        except Exception as exc:
            print(f"[ERROR] Failed to instantiate ChatOllama: {str(exc)}")

    # Tertiary Fallback Stub model
    stub_model = FallbackSREChatModel()

    # Determine order based on provider
    if provider == "gemini":
        if gemini_model:
            models_to_try.append(gemini_model)
        if ollama_model:
            models_to_try.append(ollama_model)
        models_to_try.append(stub_model)
        
    elif provider == "ollama":
        if ollama_model:
            models_to_try.append(ollama_model)
        models_to_try.append(stub_model)
        
    else:  # fallback
        models_to_try.append(stub_model)
        
    return RobustFallbackChatModel(models=models_to_try)
