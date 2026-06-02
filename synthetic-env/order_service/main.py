import time
import os
import threading
import httpx
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="Order Service", version="1.0.0")

# Service URL configuration from Env
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://localhost:8011")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://localhost:8013")

# Chaos States
chaos_active = {
    "memory_leak": False
}

# Global list to accumulate leaked memory
leaked_memory_blocks = []
leak_thread = None
leak_lock = threading.Lock()

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

class OrderRequest(BaseModel):
    user_id: int
    amount: float
    items: list[str]

class ChaosPayload(BaseModel):
    type: str

def leak_worker():
    """Background thread that continually allocates memory while leak is active."""
    global leaked_memory_blocks
    while True:
        with leak_lock:
            if not chaos_active["memory_leak"]:
                break
            # Allocate approx 10MB of data every 2 seconds
            large_block = "X" * (10 * 1024 * 1024)
            leaked_memory_blocks.append(large_block)
        time.sleep(2)

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
    status = "error" if chaos_active["memory_leak"] else "ok"
    return {"status": status, "service": "order-service", "version": "1.0.0", "leak_active": chaos_active["memory_leak"]}

@app.post("/orders")
async def create_order(order: OrderRequest):
    if order.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid order amount")
        
    async with httpx.AsyncClient(timeout=5.0) as client:
        # 1. Verify user exists via user-service
        try:
            user_response = await client.get(f"{USER_SERVICE_URL}/users/{order.user_id}")
            if user_response.status_code == 404:
                raise HTTPException(status_code=404, detail="User not found")
            elif user_response.status_code != 200:
                raise HTTPException(status_code=502, detail="Error communicating with user service")
            user_data = user_response.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"User service unavailable: {str(exc)}")
            
        # 2. Process payment via payment-service
        try:
            order_id = f"ord_{int(time.time())}"
            pay_payload = {
                "user_id": order.user_id,
                "amount": order.amount,
                "order_id": order_id
            }
            pay_response = await client.post(f"{PAYMENT_SERVICE_URL}/payments", json=pay_payload)
            if pay_response.status_code != 200:
                raise HTTPException(status_code=502, detail="Payment processing failed")
            pay_data = pay_response.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Payment service unavailable: {str(exc)}")
            
    # Return complete order outcome
    return {
        "order_id": order_id,
        "user_id": order.user_id,
        "user_email": user_data.get("email"),
        "amount": order.amount,
        "items": order.items,
        "transaction_id": pay_data.get("transaction_id"),
        "status": "completed",
        "created_at": time.time()
    }

@app.post("/chaos/inject")
def inject_chaos(payload: ChaosPayload):
    global leak_thread
    if payload.type == "memory_leak":
        with leak_lock:
            if not chaos_active["memory_leak"]:
                chaos_active["memory_leak"] = True
                leak_thread = threading.Thread(target=leak_worker, daemon=True)
                leak_thread.start()
        return {"status": "injected", "chaos": "memory_leak"}
    raise HTTPException(status_code=400, detail="Unsupported chaos type for order-service")

@app.post("/chaos/recover")
def recover_chaos():
    global leaked_memory_blocks
    with leak_lock:
        chaos_active["memory_leak"] = False
        leaked_memory_blocks.clear()  # Free allocated memory blocks
    return {"status": "recovered"}

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8012)
