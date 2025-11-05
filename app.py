#!/usr/bin/env python3
import asyncio
import json
import math
import random
import time
import os
from concurrent.futures import ProcessPoolExecutor
from enum import Enum
from typing import Any, Awaitable, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="PyMonNet Stress WebApp v4", version="4.0")

# ==============================
# ENUM + PROFILE MAPPINGS
# ==============================
class StressProfile(str, Enum):
    CPU = "cpu"
    MEMORY = "memory"
    NETWORK = "network"
    CPU_MEMORY = "cpu-memory"
    CPU_NETWORK = "cpu-network"
    MEMORY_NETWORK = "memory-network"
    ALL = "all"

PROFILE_FLAGS: dict[StressProfile, set[str]] = {
    StressProfile.CPU: {"cpu"},
    StressProfile.MEMORY: {"memory"},
    StressProfile.NETWORK: {"network"},
    StressProfile.CPU_MEMORY: {"cpu", "memory"},
    StressProfile.CPU_NETWORK: {"cpu", "network"},
    StressProfile.MEMORY_NETWORK: {"memory", "network"},
    StressProfile.ALL: {"cpu", "memory", "network"},
}

# ==============================
# CORE STRESS FUNCTIONS
# ==============================
def _cpu_spin(duration: float) -> dict[str, float | int]:
    start = time.time()
    iterations = 0
    if duration == 0.0:
        for _ in range(1_000_000):
            math.sqrt(random.random() * 9999)
            iterations += 1
    else:
        deadline = start + duration
        while time.time() < deadline:
            math.sqrt(random.random() * 9999)
            iterations += 1
    elapsed = time.time() - start
    return {"elapsed_seconds": elapsed, "iterations": iterations}


def cpu_work(duration: float, workers: int) -> dict[str, Any]:
    """Perform CPU-bound work across up to `workers` processes."""
    duration = max(duration, 0.0)
    workers = max(1, workers)
    if workers == 1:
        stats = _cpu_spin(duration)
        return {
            "target_duration_seconds": round(duration, 3),
            "elapsed_seconds": round(stats["elapsed_seconds"], 3),
            "iterations": stats["iterations"],
            "workers": workers,
        }

    max_workers = os.cpu_count() or 1
    workers = min(workers, max_workers * 4)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(_cpu_spin, [duration] * workers))
    total_iterations = sum(result["iterations"] for result in results)
    max_elapsed = max(result["elapsed_seconds"] for result in results)
    return {
        "target_duration_seconds": round(duration, 3),
        "elapsed_seconds": round(max_elapsed, 3),
        "iterations": total_iterations,
        "workers": workers,
    }


def memory_work(megabytes: int, hold_seconds: float, chunk_mb: int) -> dict[str, Any]:
    """Allocate memory in chunks, touch each page, hold for a duration, then release."""
    megabytes = max(megabytes, 0)
    hold_seconds = max(hold_seconds, 0.0)
    chunk_mb = max(chunk_mb, 1)
    target_bytes = megabytes * 1024 * 1024
    chunk_bytes = chunk_mb * 1024 * 1024

    allocated_bytes = 0
    chunks: list[bytearray] = []
    memory_errors = 0

    remaining = target_bytes
    while remaining > 0:
        size = min(chunk_bytes, remaining)
        try:
            chunk = bytearray(size)
        except MemoryError:
            memory_errors += 1
            break
        if size:
            chunk[0] = 1
            chunk[-1] = 1
        chunks.append(chunk)
        allocated_bytes += len(chunk)
        remaining -= len(chunk)

    chunk_count = len(chunks)
    if hold_seconds and allocated_bytes:
        time.sleep(hold_seconds)
    chunks.clear()

    return {
        "target_megabytes": megabytes,
        "allocated_bytes": allocated_bytes,
        "allocated_megabytes": round(allocated_bytes / (1024 * 1024), 3),
        "hold_seconds": round(hold_seconds, 3),
        "chunk_mb": chunk_mb,
        "chunk_count": chunk_count,
        "memory_errors": memory_errors,
    }


def network_work(megabytes: int, chunk_kilobytes: int) -> dict[str, int]:
    """Return stats describing the intended network workload."""
    megabytes = max(megabytes, 0)
    chunk_kilobytes = max(chunk_kilobytes, 1)
    total_bytes = megabytes * 1024 * 1024
    chunk_bytes = chunk_kilobytes * 1024
    return {"target_megabytes": megabytes, "total_bytes": total_bytes, "chunk_bytes": chunk_bytes}


# ==============================
# MAIN ASYNC STRESS HANDLER
# ==============================
async def _run_stress(
    *,
    cpu: bool,
    memory: bool,
    network: bool,
    cpu_duration: float,
    cpu_workers: int,
    memory_mb: int,
    memory_hold: float,
    memory_chunk_mb: int,
    network_mb: int,
    network_chunk_kb: int,
):
    stats: dict[str, Any] = {"requested": {"cpu": cpu, "memory": memory, "network": network}}
    loop = asyncio.get_running_loop()
    cpu_future: Optional[Awaitable[dict[str, Any]]] = None
    memory_future: Optional[Awaitable[dict[str, Any]]] = None

    if cpu:
        cpu_future = loop.run_in_executor(None, cpu_work, cpu_duration, cpu_workers)
    if memory:
        memory_future = loop.run_in_executor(None, memory_work, memory_mb, memory_hold, memory_chunk_mb)

    if network:
        network_stats = network_work(network_mb, network_chunk_kb)
        stats["network"] = network_stats
        total_bytes = network_stats["total_bytes"]
        chunk_bytes = network_stats["chunk_bytes"]
        chunk = b"x" * chunk_bytes if chunk_bytes else b""

        async def stream():
            emitted = 0
            while emitted < total_bytes:
                to_send = min(chunk_bytes, total_bytes - emitted)
                if to_send:
                    yield chunk[:to_send]
                    emitted += to_send
                await asyncio.sleep(0)
            if cpu_future:
                stats["cpu"] = await cpu_future
            if memory_future:
                stats["memory"] = await memory_future
            summary = json.dumps({"message": "stress execution complete", "stats": stats})
            yield b"\n" + summary.encode()

        return StreamingResponse(stream(), media_type="application/octet-stream")

    if cpu_future:
        stats["cpu"] = await cpu_future
    if memory_future:
        stats["memory"] = await memory_future
    return JSONResponse({"message": "stress execution complete", "stats": stats})


# ==============================
# BASIC ROUTES
# ==============================
@app.get("/")
def index():
    cpu_stats = cpu_work(1.0, 1)
    return {
        "message": "Request completed",
        "processing_time": cpu_stats["elapsed_seconds"],
        "cpu_iterations": cpu_stats["iterations"],
    }

@app.get("/health")
def health():
    return {"status": "ok"}

# ==============================
# HEAVY / REALISTIC PAGE ROUTES
# ==============================
@app.get("/page-heavy")
def page_heavy(
    cpu_load: bool = Query(True, description="Simulate CPU-bound HTML rendering"),
    mem_mb: int = Query(64, ge=0, description="Temporary MB of memory used"),
    delay: float = Query(0.0, ge=0.0, description="Artificial delay (seconds)"),
    response_mb: int = Query(20, ge=1, description="Size of generated HTML page in MB")
):
    """Simulate realistic heavy webpage generation causing client-side slowdown."""
    import time
    start = time.time()

    if cpu_load:
        for _ in range(3_000_000):
            math.sqrt(random.random() * 99999)

    if mem_mb > 0:
        tmp = bytearray(mem_mb * 1024 * 1024)
        tmp[0] = 1
        tmp[-1] = 1

    if delay > 0:
        time.sleep(delay)

    html = "<html><body><h1>Heavy Stress Page</h1>" + ("<p>" * 1000) + "</body></html>"
    body = html.encode() * (response_mb * 1024 * 1024 // len(html.encode()))

    elapsed = round(time.time() - start, 3)
    return StreamingResponse(
        iter([body]),
        media_type="text/html",
        headers={
            "X-Elapsed": str(elapsed),
            "X-Size-MB": str(response_mb),
        },
    )


@app.get("/block")
def block(seconds: int = 60):
    """Completely block main thread (simulate deadlock / full freeze)."""
    import time
    time.sleep(seconds)
    return {"blocked_seconds": seconds, "ok": True}


@app.get("/download")
def download(size_mb: int = 200):
    """Serve large binary response to simulate big file transfer."""
    from fastapi.responses import StreamingResponse
    import io
    data = io.BytesIO(b"X" * size_mb * 1024 * 1024)
    return StreamingResponse(data, media_type="application/octet-stream")


# ==============================
# STRESS COMBINATION ROUTES
# ==============================
@app.get("/stress")
async def stress(
    cpu: bool = Query(False),
    memory: bool = Query(False),
    network: bool = Query(False),
    cpu_duration: float = Query(1.0),
    cpu_workers: int = Query(1),
    memory_mb: int = Query(128),
    memory_hold: float = Query(1.0),
    memory_chunk_mb: int = Query(32),
    network_mb: int = Query(5),
    network_chunk_kb: int = Query(256),
):
    if not any((cpu, memory, network)):
        raise HTTPException(status_code=400, detail="Select at least one stress type.")
    return await _run_stress(
        cpu=cpu,
        memory=memory,
        network=network,
        cpu_duration=cpu_duration,
        cpu_workers=cpu_workers,
        memory_mb=memory_mb,
        memory_hold=memory_hold,
        memory_chunk_mb=memory_chunk_mb,
        network_mb=network_mb,
        network_chunk_kb=network_chunk_kb,
    )

@app.get("/stress/profile/{profile}")
async def stress_profile(
    profile: StressProfile,
    cpu_duration: float = Query(1.0),
    cpu_workers: int = Query(1),
    memory_mb: int = Query(128),
    memory_hold: float = Query(1.0),
    memory_chunk_mb: int = Query(32),
    network_mb: int = Query(5),
    network_chunk_kb: int = Query(256),
):
    flags = PROFILE_FLAGS[profile]
    return await _run_stress(
        cpu="cpu" in flags,
        memory="memory" in flags,
        network="network" in flags,
        cpu_duration=cpu_duration,
        cpu_workers=cpu_workers,
        memory_mb=memory_mb,
        memory_hold=memory_hold,
        memory_chunk_mb=memory_chunk_mb,
        network_mb=network_mb,
        network_chunk_kb=network_chunk_kb,
    )
