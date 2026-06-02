import os
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

# A mock chat model that mimics LLM responses based on prompt keywords.
# This ensures SentinelGraph runs flawlessly out-of-the-box without paid API keys
# or local Ollama configurations, but immediately lights up when a real LLM is provided.
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
        
        # 1. Alert Triage routing logic
        if "triage" in prompt_text_lower or "alert" in prompt_text_lower:
            response_text = """### Alert Triage Analysis
- **Impacted Service**: payment-service
- **Severity**: CRITICAL
- **Summary**: Detects anomalous error spike or high latency in database transactions. Initiating multi-agent log and metrics diagnostics."""
            if "latency" in prompt_text_lower or "highlatency" in prompt_text_lower:
                response_text = response_text.replace("payment-service", "payment-service").replace("error spike", "latency spike")
            elif "memory" in prompt_text_lower or "leak" in prompt_text_lower:
                response_text = response_text.replace("payment-service", "order-service").replace("error spike", "memory leak")
            elif "deploy" in prompt_text_lower or "config" in prompt_text_lower:
                response_text = response_text.replace("payment-service", "user-service").replace("error spike", "bad deployment")

        # 2. Log Analysis routing logic
        elif "log" in prompt_text_lower or "trace" in prompt_text_lower:
            response_text = """### Log Investigation Report
- **Identified Issues**: Found repeating warning/error stack traces in container logs.
- **Key Evidence**:
  * `[ERROR] DatabaseSaturation: Max connection limit reached on db host.` (in payment-service stdout logs)
  * `[ERROR] ConfigRegressionError: failed to load context variables` (in user-service stdout logs)
  * Memory footprint growing rapidly by 10MB blocks in order-service.
- **Conclusion**: Logs indicate a service-level blockage or config mismatch."""
            if "payment" in prompt_text_lower:
                response_text = """### Log Investigation: payment-service
- **Evidence**: live container stdout reveals active database connection timeout anomalies and pool exhaustion warnings.
- **Key Log Line**: `[ERROR] DatabaseSaturation: Max connection limit reached on db host.`"""
            elif "user" in prompt_text_lower:
                response_text = """### Log Investigation: user-service
- **Evidence**: user-service returns HTTP 500 on validation routes due to configuration parameters loading error.
- **Key Log Line**: `[ERROR] ConfigRegressionError: failed to load context variables`"""
            elif "order" in prompt_text_lower:
                response_text = """### Log Investigation: order-service
- **Evidence**: order-service background loop reveals cache storage buffers expanding without bounds.
- **Key Log Line**: `[INFO] Allocated cached elements heap footprint expanded.`"""

        # 3. Root Cause Agent routing logic
        elif "root cause" in prompt_text_lower or "hypotheses" in prompt_text_lower:
            response_text = """### Root Cause Analysis Report
1. **Hypothesis 1**: Database Connection Saturation under Load (Confidence: 90%)
   - *Rationale*: payment-service logs explicitly cite database connection pool limits reached, leading to subsequent upstream timeouts in order-service checkout routes.
   - *Evidence*: `[ERROR] DatabaseSaturation: Max connection limit reached on db host.`
2. **Hypothesis 2**: Recent Bad Code Release / Configuration Rollout (Confidence: 45%)
   - *Rationale*: A config parameter rollout occurred shortly before latency spikes began.
   - *Evidence*: Deploy history log entry for `v1.1.0-bad`."""
            if "user-service" in prompt_text_lower:
                response_text = response_text.replace("Database Connection Saturation", "Injected Config Regression in v1.1.0").replace("payment-service logs", "user-service logs").replace("Max connection limit reached", "ConfigRegressionError")
            elif "order-service" in prompt_text_lower:
                response_text = response_text.replace("Database Connection Saturation", "Memory Leak in cache compilation loop").replace("payment-service logs", "order-service heap analysis").replace("Max connection limit reached", "Allocated cached elements heap")

        # 4. Default fallback response
        else:
            response_text = "### SRE Agent Reasoning\nAgent has processed current incident state details successfully."
            
        # Core SRE Fix: BaseChatModel._generate must return a ChatResult containing ChatGenerations,
        # otherwise modern LangChain raises: 'AIMessage' object has no attribute 'generations'
        message = AIMessage(content=response_text)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])
        
    def _llm_type(self) -> str:
        return "fallback-sre-model"

def get_llm() -> BaseChatModel:
    """LLM Model Factory supporting Gemini Generative AI, local Ollama, and fallbacks."""
    provider = os.getenv("LLM_PROVIDER", "fallback").lower()
    
    if provider == "gemini":
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            print("[WARNING] GEMINI_API_KEY is not defined in env. Falling back to SRE stubs.")
            return FallbackSREChatModel()
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=gemini_key)
        except Exception as exc:
            print(f"[ERROR] Failed to instantiate ChatGoogleGenerativeAI: {str(exc)}. Falling back.")
            return FallbackSREChatModel()
            
    elif provider == "ollama":
        if ChatOllama is None:
            print("[ERROR] ChatOllama class could not be loaded from any import path. Falling back.")
            return FallbackSREChatModel()
        model_name = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        try:
            return ChatOllama(model=model_name, base_url=base_url)
        except Exception as exc:
            print(f"[ERROR] Failed to connect to Ollama server: {str(exc)}. Falling back.")
            return FallbackSREChatModel()
    
    # Defaults to our custom fallback SRE model
    return FallbackSREChatModel()
