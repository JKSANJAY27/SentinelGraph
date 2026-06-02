import time
import random
import threading
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="Payment Service", version="1.0.0")

# Chaos States
chaos_active = {
    "db_saturation": False,
    "cpu_spike": False
}

# Prometheus Metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP Requests",
    ["method", "endpoint", "http_status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP Request Latency",
    ["method", "endpoint"]
)

class PaymentRequest(BaseModel):
    user_id: int
    amount: float
    order_id: str

class ChaosPayload(BaseModel):
    type: str

def busy_loop_worker(duration=1.0):
    """Spins the CPU for a duration in a background worker."""
    start = time.time()
    while time.time() - start < duration:
        _ = 9999 * 9999

@app.middleware("http")
async def monitor_requests(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    if request.url.path != "/metrics":
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            http_status=response.status_code
        ).inc()
        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)
        
    return response

@app.get("/health")
def health():
    status = "error" if (chaos_active["db_saturation"] or chaos_active["cpu_spike"]) else "ok"
    return {"status": status, "service": "payment-service", "version": "1.0.0"}

@app.post("/payments")
def process_payment(payment: PaymentRequest):
    if payment.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid payment amount")
    
    # 1. Simulate DB Saturation (High Latency)
    if chaos_active["db_saturation"]:
        time.sleep(2.5 + random.uniform(0.1, 0.5))
    else:
        time.sleep(0.05 + random.uniform(0.01, 0.03))
        
    # 2. Simulate CPU Spike (Busy loop)
    if chaos_active["cpu_spike"]:
        # Spin the CPU on request thread for 0.5s to generate high CPU metric
        busy_loop_worker(0.5)
        
    # Return mock payment transaction details
    tx_id = f"tx_{int(time.time())}_{random.randint(1000, 9999)}"
    return {
        "transaction_id": tx_id,
        "status": "success",
        "order_id": payment.order_id,
        "amount": payment.amount,
        "timestamp": time.time()
    }

@app.post("/chaos/inject")
def inject_chaos(payload: ChaosPayload):
    if payload.type in chaos_active:
        chaos_active[payload.type] = True
        return {"status": "injected", "chaos": payload.type}
    raise HTTPException(status_code=400, detail="Unsupported chaos type for payment-service")

@app.post("/chaos/recover")
def recover_chaos():
    for k in chaos_active:
        chaos_active[k] = False
    return {"status": "recovered"}

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8013)
