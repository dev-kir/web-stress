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

app = FastAPI()


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
    workers = min(workers, max_workers * 4)  # safety limit for runaway processes

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


def memory_work(megabytes: int, hold_seconds: float) -> dict[str, Any]:
    """Allocate memory, optionally hold it for a duration, then release."""
    megabytes = max(megabytes, 0)
    hold_seconds = max(hold_seconds, 0.0)
    allocated_bytes = megabytes * 1024 * 1024
    block = bytearray(allocated_bytes) if allocated_bytes else None

    if hold_seconds:
        time.sleep(hold_seconds)

    actual_bytes = len(block) if block is not None else 0

    if block is not None:
        del block

    return {
        "target_megabytes": megabytes,
        "allocated_bytes": actual_bytes,
        "hold_seconds": round(hold_seconds, 3),
    }


def network_work(megabytes: int, chunk_kilobytes: int) -> dict[str, int]:
    """Return stats describing the intended network workload."""
    megabytes = max(megabytes, 0)
    chunk_kilobytes = max(chunk_kilobytes, 1)
    total_bytes = megabytes * 1024 * 1024
    chunk_bytes = chunk_kilobytes * 1024
    return {"target_megabytes": megabytes, "total_bytes": total_bytes, "chunk_bytes": chunk_bytes}


async def _run_stress(
    *,
    cpu: bool,
    memory: bool,
    network: bool,
    cpu_duration: float,
    cpu_workers: int,
    memory_mb: int,
    memory_hold: float,
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
        memory_future = loop.run_in_executor(None, memory_work, memory_mb, memory_hold)

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
            if summary:
                prefix = b"\n" if total_bytes else b""
                yield prefix + summary.encode()

        return StreamingResponse(stream(), media_type="application/octet-stream")

    if cpu_future:
        stats["cpu"] = await cpu_future
    if memory_future:
        stats["memory"] = await memory_future

    return JSONResponse({"message": "stress execution complete", "stats": stats})


@app.get("/")
def index() -> dict[str, Any]:
    """Default endpoint that performs CPU work similar to earlier behaviour."""
    cpu_stats = cpu_work(1.0, 1)
    return {
        "message": "Request completed",
        "processing_time": cpu_stats["elapsed_seconds"],
        "cpu_iterations": cpu_stats["iterations"],
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stress")
async def stress(
    cpu: bool = Query(False, description="Simulate CPU load"),
    memory: bool = Query(False, description="Simulate memory pressure"),
    network: bool = Query(False, description="Simulate outbound network traffic"),
    cpu_duration: float = Query(
        1.0, ge=0.0, description="Target CPU work duration in seconds"
    ),
    cpu_workers: int = Query(
        1,
        ge=1,
        description="Number of parallel worker processes for CPU work",
    ),
    memory_mb: int = Query(
        128, ge=0, description="Megabytes of memory to allocate during the test"
    ),
    memory_hold: float = Query(
        1.0, ge=0.0, description="Seconds to hold the allocated memory before release"
    ),
    network_mb: int = Query(
        5, ge=0, description="Megabytes of response payload to stream to the client"
    ),
    network_chunk_kb: int = Query(
        256, ge=1, description="Chunk size (KB) for streaming network payload"
    ),
):
    if not any((cpu, memory, network)):
        raise HTTPException(
            status_code=400,
            detail="Select at least one stress type (cpu, memory, network).",
        )

    return await _run_stress(
        cpu=cpu,
        memory=memory,
        network=network,
        cpu_duration=cpu_duration,
        cpu_workers=cpu_workers,
        memory_mb=memory_mb,
        memory_hold=memory_hold,
        network_mb=network_mb,
        network_chunk_kb=network_chunk_kb,
    )


@app.get("/stress/profile/{profile}")
async def stress_profile(
    profile: StressProfile,
    cpu_duration: float = Query(1.0, ge=0.0, description="CPU duration in seconds"),
    cpu_workers: int = Query(
        1,
        ge=1,
        description="Number of parallel worker processes for CPU work",
    ),
    memory_mb: int = Query(128, ge=0, description="Memory allocation in MB"),
    memory_hold: float = Query(1.0, ge=0.0, description="Hold allocated memory for N seconds"),
    network_mb: int = Query(5, ge=0, description="Payload size in MB for network stress"),
    network_chunk_kb: int = Query(
        256, ge=1, description="Chunk size (KB) for streamed network payload"
    ),
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
        network_mb=network_mb,
        network_chunk_kb=network_chunk_kb,
    )
