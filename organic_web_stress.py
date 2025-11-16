#!/usr/bin/env python3
"""
Organic Web Stress - Realistic Traffic Simulator
Designed for Docker Swarm Load Balancing Testing
"""
import asyncio
import json
import math
import random
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn

app = FastAPI(title="Organic Web Stress", version="1.0")

# Server identification (set by environment or hostname)
import socket
SERVER_ID = socket.gethostname()

# Request counter for tracking distribution
request_counter = {"total": 0, "by_endpoint": {}}

# ==============================
# REALISTIC WORKLOAD FUNCTIONS
# ==============================

def simulate_database_query(complexity: str = "simple") -> float:
    """Simulate database query delay"""
    delays = {
        "simple": (0.01, 0.05),    # 10-50ms
        "medium": (0.05, 0.15),    # 50-150ms
        "complex": (0.15, 0.40),   # 150-400ms
        "heavy": (0.40, 0.80),     # 400-800ms
    }
    min_delay, max_delay = delays.get(complexity, (0.01, 0.05))
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)
    return delay

def simulate_cpu_work(intensity: str = "light") -> dict:
    """Simulate CPU-intensive work like rendering, calculations"""
    intensities = {
        "light": 100_000,       # ~10ms
        "medium": 500_000,      # ~50ms
        "heavy": 2_000_000,     # ~200ms
        "extreme": 5_000_000,   # ~500ms
    }
    iterations = intensities.get(intensity, 100_000)
    
    start = time.time()
    result = 0
    for i in range(iterations):
        result += math.sqrt(random.random() * 999)
    elapsed = time.time() - start
    
    return {"iterations": iterations, "elapsed_ms": round(elapsed * 1000, 2)}

def simulate_memory_work(size_mb: int = 10, hold_seconds: float = 0.1) -> dict:
    """Simulate memory allocation (session data, caching)"""
    start = time.time()
    data = bytearray(size_mb * 1024 * 1024)
    data[0] = 1
    data[-1] = 1
    time.sleep(hold_seconds)
    allocated = len(data)
    del data
    elapsed = time.time() - start
    
    return {"allocated_mb": size_mb, "elapsed_ms": round(elapsed * 1000, 2)}

def generate_response_data(size_kb: int = 1) -> bytes:
    """Generate response data of specific size"""
    template = b'{"data": "x", "timestamp": "%s"}' % str(time.time()).encode()
    repeats = (size_kb * 1024) // len(template)
    return template * max(1, repeats)

# ==============================
# TRACKING & HEADERS
# ==============================

def add_tracking_headers(response: Response, endpoint: str, start_time: float):
    """Add tracking headers to response"""
    elapsed = time.time() - start_time
    request_id = str(uuid.uuid4())
    
    response.headers["X-Server-ID"] = SERVER_ID
    response.headers["X-Response-Time-Ms"] = str(round(elapsed * 1000, 2))
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Endpoint"] = endpoint
    
    # Update counter
    request_counter["total"] += 1
    request_counter["by_endpoint"][endpoint] = request_counter["by_endpoint"].get(endpoint, 0) + 1

# ==============================
# REALISTIC ENDPOINTS
# ==============================

@app.get("/")
async def homepage(response: Response):
    """Homepage - Light load (typical landing page)"""
    start = time.time()
    
    # Simulate: DB query + minimal CPU + small response
    db_time = simulate_database_query("simple")
    cpu_stats = simulate_cpu_work("light")
    
    data = {
        "page": "homepage",
        "message": "Welcome to Organic Web Stress",
        "server_id": SERVER_ID,
        "processing": {
            "db_query_ms": round(db_time * 1000, 2),
            "cpu_work_ms": cpu_stats["elapsed_ms"],
        }
    }
    
    add_tracking_headers(response, "homepage", start)
    return JSONResponse(data)

@app.get("/api/data")
async def api_data(response: Response):
    """API Endpoint - Medium load (data processing)"""
    start = time.time()
    
    # Simulate: Medium DB query + moderate CPU + JSON response
    db_time = simulate_database_query("medium")
    cpu_stats = simulate_cpu_work("medium")
    
    # Generate some data
    items = [
        {"id": i, "value": random.randint(100, 999), "status": random.choice(["active", "pending"])}
        for i in range(50)
    ]
    
    data = {
        "endpoint": "api_data",
        "items": items,
        "count": len(items),
        "processing": {
            "db_query_ms": round(db_time * 1000, 2),
            "cpu_work_ms": cpu_stats["elapsed_ms"],
        }
    }
    
    add_tracking_headers(response, "api_data", start)
    return JSONResponse(data)

@app.get("/dashboard")
async def dashboard(response: Response):
    """Dashboard - Heavy load (complex queries + rendering)"""
    start = time.time()
    
    # Simulate: Multiple DB queries + heavy CPU + memory
    db_time1 = simulate_database_query("complex")
    db_time2 = simulate_database_query("medium")
    db_time3 = simulate_database_query("simple")
    
    cpu_stats = simulate_cpu_work("heavy")
    mem_stats = simulate_memory_work(20, 0.1)
    
    # Generate dashboard data
    metrics = {
        "users_online": random.randint(100, 500),
        "requests_per_sec": random.randint(50, 200),
        "error_rate": round(random.uniform(0.1, 2.0), 2),
        "avg_response_ms": random.randint(100, 500),
    }
    
    charts = [
        {"type": "line", "data": [random.randint(10, 100) for _ in range(24)]},
        {"type": "bar", "data": [random.randint(50, 200) for _ in range(12)]},
        {"type": "pie", "data": {"success": 95, "error": 5}},
    ]
    
    data = {
        "page": "dashboard",
        "metrics": metrics,
        "charts": charts,
        "processing": {
            "db_queries_ms": round((db_time1 + db_time2 + db_time3) * 1000, 2),
            "cpu_work_ms": cpu_stats["elapsed_ms"],
            "memory_work_ms": mem_stats["elapsed_ms"],
        }
    }
    
    add_tracking_headers(response, "dashboard", start)
    return JSONResponse(data)

@app.get("/search")
async def search(q: str = "default", response: Response = None):
    """Search - Variable load based on query complexity"""
    start = time.time()
    
    # Query complexity based on search term length
    complexity = "simple" if len(q) < 5 else "medium" if len(q) < 15 else "complex"
    
    db_time = simulate_database_query(complexity)
    cpu_stats = simulate_cpu_work("medium")
    
    # Generate search results
    results = [
        {
            "id": i,
            "title": f"Result {i} for '{q}'",
            "relevance": round(random.uniform(0.5, 1.0), 2),
            "snippet": f"This is a search result snippet for query: {q}..."
        }
        for i in range(random.randint(5, 20))
    ]
    
    data = {
        "query": q,
        "results": results,
        "count": len(results),
        "processing": {
            "db_query_ms": round(db_time * 1000, 2),
            "cpu_work_ms": cpu_stats["elapsed_ms"],
            "complexity": complexity,
        }
    }
    
    add_tracking_headers(response, "search", start)
    return JSONResponse(data)

@app.get("/media/{media_id}")
async def media(media_id: str, size_mb: int = 2, response: Response = None):
    """Media serving - Network intensive (large responses)"""
    start = time.time()
    
    # Simulate: Simple DB lookup + large data transfer
    db_time = simulate_database_query("simple")
    
    # Generate media data (streaming)
    chunk_size = 256 * 1024  # 256KB chunks
    total_bytes = size_mb * 1024 * 1024
    
    async def stream_media():
        sent = 0
        while sent < total_bytes:
            chunk = b"X" * min(chunk_size, total_bytes - sent)
            yield chunk
            sent += len(chunk)
            await asyncio.sleep(0)  # Allow other tasks to run
    
    add_tracking_headers(response, "media", start)
    return StreamingResponse(
        stream_media(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=media_{media_id}.bin",
            "X-Media-Size-MB": str(size_mb),
        }
    )

@app.post("/checkout")
async def checkout(response: Response):
    """Checkout - High CPU + Memory (transaction processing)"""
    start = time.time()
    
    # Simulate: Multiple operations (validation, calculation, DB writes)
    db_time1 = simulate_database_query("medium")  # Read user data
    cpu_stats1 = simulate_cpu_work("heavy")       # Price calculation
    mem_stats = simulate_memory_work(30, 0.15)    # Session/cart data
    db_time2 = simulate_database_query("complex") # Write transaction
    cpu_stats2 = simulate_cpu_work("medium")      # Generate receipt
    
    transaction = {
        "transaction_id": str(uuid.uuid4()),
        "amount": round(random.uniform(10.0, 500.0), 2),
        "status": "completed",
        "timestamp": datetime.now().isoformat(),
    }
    
    data = {
        "checkout": "success",
        "transaction": transaction,
        "processing": {
            "total_db_ms": round((db_time1 + db_time2) * 1000, 2),
            "total_cpu_ms": cpu_stats1["elapsed_ms"] + cpu_stats2["elapsed_ms"],
            "memory_work_ms": mem_stats["elapsed_ms"],
        }
    }
    
    add_tracking_headers(response, "checkout", start)
    return JSONResponse(data)

@app.get("/product/{product_id}")
async def product(product_id: str, response: Response):
    """Product page - Medium load (common e-commerce pattern)"""
    start = time.time()
    
    db_time = simulate_database_query("medium")
    cpu_stats = simulate_cpu_work("medium")
    
    product_data = {
        "id": product_id,
        "name": f"Product {product_id}",
        "price": round(random.uniform(10.0, 1000.0), 2),
        "description": "Lorem ipsum dolor sit amet " * 20,
        "stock": random.randint(0, 100),
        "rating": round(random.uniform(3.0, 5.0), 1),
        "reviews": random.randint(0, 500),
    }
    
    data = {
        "product": product_data,
        "recommendations": [f"prod_{i}" for i in range(6)],
        "processing": {
            "db_query_ms": round(db_time * 1000, 2),
            "cpu_work_ms": cpu_stats["elapsed_ms"],
        }
    }
    
    add_tracking_headers(response, "product", start)
    return JSONResponse(data)

# ==============================
# EXTREME LOAD ENDPOINTS
# ==============================

@app.get("/extreme/cpu")
async def extreme_cpu(duration: int = 5, workers: int = 4, response: Response = None):
    """Extreme CPU load - 99% CPU utilization"""
    start = time.time()
    
    # Intense CPU work
    total_iterations = 0
    deadline = start + duration
    
    while time.time() < deadline:
        for _ in range(1_000_000):
            math.sqrt(random.random() * 99999)
            total_iterations += 1
    
    elapsed = time.time() - start
    
    data = {
        "type": "extreme_cpu",
        "duration_seconds": duration,
        "iterations": total_iterations,
        "elapsed_seconds": round(elapsed, 3),
    }
    
    add_tracking_headers(response, "extreme_cpu", start)
    return JSONResponse(data)

@app.get("/extreme/memory")
async def extreme_memory(mb: int = 512, hold: int = 5, response: Response = None):
    """Extreme Memory load - High memory allocation"""
    start = time.time()
    
    chunks = []
    try:
        for _ in range(mb // 64):
            chunk = bytearray(64 * 1024 * 1024)
            chunk[0] = 1
            chunk[-1] = 1
            chunks.append(chunk)
        
        time.sleep(hold)
        allocated = sum(len(c) for c in chunks)
    except MemoryError:
        allocated = sum(len(c) for c in chunks)
    finally:
        chunks.clear()
    
    elapsed = time.time() - start
    
    data = {
        "type": "extreme_memory",
        "requested_mb": mb,
        "allocated_bytes": allocated,
        "allocated_mb": round(allocated / (1024 * 1024), 2),
        "hold_seconds": hold,
        "elapsed_seconds": round(elapsed, 3),
    }
    
    add_tracking_headers(response, "extreme_memory", start)
    return JSONResponse(data)

@app.get("/extreme/all")
async def extreme_all(
    cpu_duration: int = 5,
    memory_mb: int = 256,
    network_mb: int = 50,
    response: Response = None
):
    """Extreme ALL - 99% CPU + Memory + Network"""
    start = time.time()
    
    # CPU work in background
    async def cpu_work_async():
        deadline = time.time() + cpu_duration
        iterations = 0
        while time.time() < deadline:
            for _ in range(100_000):
                math.sqrt(random.random() * 99999)
                iterations += 1
        return iterations
    
    # Memory allocation
    chunks = []
    try:
        for _ in range(memory_mb // 64):
            chunk = bytearray(64 * 1024 * 1024)
            chunk[0] = 1
            chunks.append(chunk)
    except MemoryError:
        pass
    
    # Start CPU work
    cpu_task = asyncio.create_task(cpu_work_async())
    
    # Stream network data
    async def stream_all():
        chunk_size = 1024 * 1024  # 1MB chunks
        total_bytes = network_mb * 1024 * 1024
        sent = 0
        
        while sent < total_bytes:
            chunk = b"X" * min(chunk_size, total_bytes - sent)
            yield chunk
            sent += len(chunk)
            await asyncio.sleep(0)
        
        # Wait for CPU work to finish
        iterations = await cpu_task
        chunks.clear()
        
        # Send summary
        summary = json.dumps({
            "type": "extreme_all",
            "cpu_iterations": iterations,
            "memory_allocated_mb": len(chunks) * 64,
            "network_sent_mb": network_mb,
            "elapsed_seconds": round(time.time() - start, 3),
        })
        yield b"\n" + summary.encode()
    
    add_tracking_headers(response, "extreme_all", start)
    return StreamingResponse(stream_all(), media_type="application/octet-stream")

@app.get("/extreme/cpu-mem")
async def extreme_cpu_mem(
    cpu_duration: int = 5,
    memory_mb: int = 256,
    response: Response = None
):
    """Extreme CPU + Memory (99% both, network stays low)"""
    start = time.time()
    
    # Allocate memory
    chunks = []
    try:
        for _ in range(memory_mb // 64):
            chunk = bytearray(64 * 1024 * 1024)
            chunk[0] = 1
            chunk[-1] = 1
            chunks.append(chunk)
    except MemoryError:
        pass
    
    # CPU work
    iterations = 0
    deadline = time.time() + cpu_duration
    while time.time() < deadline:
        for _ in range(1_000_000):
            math.sqrt(random.random() * 99999)
            iterations += 1
    
    allocated = sum(len(c) for c in chunks)
    chunks.clear()
    
    elapsed = time.time() - start
    
    data = {
        "type": "extreme_cpu_mem",
        "cpu_iterations": iterations,
        "memory_allocated_mb": round(allocated / (1024 * 1024), 2),
        "elapsed_seconds": round(elapsed, 3),
    }
    
    add_tracking_headers(response, "extreme_cpu_mem", start)
    return JSONResponse(data)

# ==============================
# MONITORING ENDPOINTS
# ==============================

@app.get("/health")
async def health():
    """Health check for load balancer"""
    return {"status": "healthy", "server_id": SERVER_ID}

@app.get("/ready")
async def ready():
    """Readiness check for load balancer"""
    return {"status": "ready", "server_id": SERVER_ID}

@app.get("/metrics")
async def metrics():
    """Basic metrics for monitoring"""
    return {
        "server_id": SERVER_ID,
        "total_requests": request_counter["total"],
        "requests_by_endpoint": request_counter["by_endpoint"],
        "timestamp": datetime.now().isoformat(),
    }

@app.get("/request-stats")
async def request_stats():
    """Request distribution statistics"""
    return {
        "server_id": SERVER_ID,
        "hostname": socket.gethostname(),
        "total_requests": request_counter["total"],
        "by_endpoint": request_counter["by_endpoint"],
        "timestamp": datetime.now().isoformat(),
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7777)