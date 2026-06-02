import time
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="User Service", version="1.0.0")

# Chaos States
chaos_active = {
    "bad_deploy": False
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

class ChaosPayload(BaseModel):
    type: str

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
    status = "error" if chaos_active["bad_deploy"] else "ok"
    return {"status": status, "service": "user-service", "version": "1.1.0" if chaos_active["bad_deploy"] else "1.0.0"}

@app.get("/users/{user_id}")
def get_user(user_id: int):
    # Simulate a bad deployment throwing internal errors
    if chaos_active["bad_deploy"]:
        raise HTTPException(status_code=500, detail="ConfigRegressionError: failed to load context variables")

    if user_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid user ID")
    if user_id > 100:
        raise HTTPException(status_code=404, detail="User not found")
        
    return {
        "id": user_id,
        "name": f"SRE User {user_id}",
        "email": f"user{user_id}@sentinelgraph.io",
        "tier": "enterprise" if user_id % 10 == 0 else "standard"
    }

@app.post("/chaos/inject")
def inject_chaos(payload: ChaosPayload):
    if payload.type == "bad_deploy":
        chaos_active["bad_deploy"] = True
        return {"status": "injected", "chaos": "bad_deploy"}
    raise HTTPException(status_code=400, detail="Unsupported chaos type for user-service")

@app.post("/chaos/recover")
def recover_chaos():
    chaos_active["bad_deploy"] = False
    return {"status": "recovered"}

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8011)
