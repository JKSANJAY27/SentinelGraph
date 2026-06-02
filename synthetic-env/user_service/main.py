import time
from fastapi import FastAPI, HTTPException, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="User Service", version="1.0.0")

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

@app.middleware("http")
async def monitor_requests(request, call_next):
    start_time = time.time()
    # Execute request
    response = await call_next(request)
    
    # Calculate latency and increment counters
    duration = time.time() - start_time
    
    # Don't track metrics endpoint itself to prevent noise
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
    return {"status": "ok", "service": "user-service", "version": "1.0.0"}

@app.get("/users/{user_id}")
def get_user(user_id: int):
    # Standard static response
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

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8011)
