import time
import random
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="Payment Service", version="1.0.0")

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
    return {"status": "ok", "service": "payment-service", "version": "1.0.0"}

@app.post("/payments")
def process_payment(payment: PaymentRequest):
    if payment.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid payment amount")
    
    # Simulate DB latency/processing delay
    time.sleep(0.05 + random.uniform(0.01, 0.03))
    
    # Return mock payment transaction details
    tx_id = f"tx_{int(time.time())}_{random.randint(1000, 9999)}"
    return {
        "transaction_id": tx_id,
        "status": "success",
        "order_id": payment.order_id,
        "amount": payment.amount,
        "timestamp": time.time()
    }

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8013)
