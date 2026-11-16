#!/usr/bin/env python3
"""Smoke-level load check for the MGTS Infrastructure Intelligence API.

Runs a small concurrent scenario loop (login -> GET /assets -> GET /map/assets
-> GET /observations) against a running stack and reports p50/p95/max latency
plus error rate. This is a SMOKE test, not a capacity benchmark: it verifies
the stack stays responsive and error-free under light concurrent read traffic.

Usage (from backend/ with the project venv):
    uv run python ../scripts/load_smoke.py --base-url http://localhost:8000 \
        --concurrency 8 --duration 20 --username admin --password change-me-admin

Exit code 1 when error_rate > 1% or p95 latency > 2.0s.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

import httpx

_SCENARIO_PATHS = (
    "/api/v1/assets?page_size=20",
    "/api/v1/map/assets",
    "/api/v1/observations?page_size=20",
)


class Stats:
    def __init__(self) -> None:
        self.latencies: list[float] = []
        self.errors: int = 0
        self.total: int = 0

    def record(self, seconds: float, *, ok: bool) -> None:
        self.total += 1
        self.latencies.append(seconds)
        if not ok:
            self.errors += 1

    @property
    def error_rate(self) -> float:
        return self.errors / self.total if self.total else 1.0


async def _login(
    client: httpx.AsyncClient, username: str, password: str, stats: Stats
) -> str | None:
    start = time.perf_counter()
    try:
        response = await client.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
        ok = response.status_code == 200
        token = response.json().get("access_token") if ok else None
    except (httpx.HTTPError, ValueError):
        ok = False
        token = None
    stats.record(time.perf_counter() - start, ok=ok)
    return token


async def _worker(
    client: httpx.AsyncClient,
    username: str,
    password: str,
    deadline: float,
    stats: Stats,
) -> None:
    token = await _login(client, username, password, stats)
    if token is None:
        return
    headers = {"Authorization": f"Bearer {token}"}
    while time.monotonic() < deadline:
        for path in _SCENARIO_PATHS:
            if time.monotonic() >= deadline:
                break
            start = time.perf_counter()
            try:
                response = await client.get(path, headers=headers)
                ok = response.status_code == 200
            except httpx.HTTPError:
                ok = False
            stats.record(time.perf_counter() - start, ok=ok)


async def _run(args: argparse.Namespace) -> Stats:
    stats = Stats()
    deadline = time.monotonic() + args.duration
    limits = httpx.Limits(max_connections=args.concurrency + 4)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=10.0, limits=limits) as client:
        await asyncio.gather(
            *(
                _worker(client, args.username, args.password, deadline, stats)
                for _ in range(args.concurrency)
            )
        )
    return stats


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--duration", type=float, default=20.0, help="seconds")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="change-me-admin")
    args = parser.parse_args()
    if args.concurrency < 1 or args.duration <= 0:
        parser.error("--concurrency must be >= 1 and --duration must be > 0")

    stats = asyncio.run(_run(args))
    if not stats.latencies:
        print("FAIL: no requests completed (login failed?)")
        return 1

    p50 = _percentile(stats.latencies, 0.50)
    p95 = _percentile(stats.latencies, 0.95)
    worst = max(stats.latencies)
    print(f"requests={stats.total} errors={stats.errors} error_rate={stats.error_rate:.4f}")
    print(f"latency_seconds p50={p50:.3f} p95={p95:.3f} max={worst:.3f}")

    if stats.error_rate > 0.01:
        print(f"FAIL: error rate {stats.error_rate:.4f} > 0.01")
        return 1
    if p95 > 2.0:
        print(f"FAIL: p95 latency {p95:.3f}s > 2.0s")
        return 1
    print("LOAD SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
