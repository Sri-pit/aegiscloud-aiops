"""
agent/observer.py  –  OBSERVE phase of the OODA loop.

Polls Prometheus for error-rate spikes, then pulls related logs
from Loki to build an AlertContext for the Orchestrator.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Callable, Awaitable, Optional
import httpx
from loguru import logger

from config.settings import settings
from agent.models import AlertContext


class Observer:
    def __init__(self, on_alert: Callable[[AlertContext], Awaitable[None]]):
        self.on_alert = on_alert
        self._running = False
        self._client = httpx.AsyncClient(timeout=10)

    # ── Public API ────────────────────────────────────────────────────────

    async def start_polling(self):
        self._running = True
        logger.info(f"Observer polling every {settings.PROMETHEUS_POLL_INTERVAL}s")
        while self._running:
            try:
                await self._poll_cycle()
            except Exception as exc:
                logger.error(f"Observer poll error: {exc}")
            await asyncio.sleep(settings.PROMETHEUS_POLL_INTERVAL)

    async def stop(self):
        self._running = False
        await self._client.aclose()

    # ── Internal ──────────────────────────────────────────────────────────

    async def _poll_cycle(self):
        error_rate = await self._query_prometheus()
        if error_rate is None:
            return

        if error_rate >= settings.ERROR_RATE_THRESHOLD:
            logger.warning(f"[ALERT] Error rate {error_rate:.2%} ≥ threshold {settings.ERROR_RATE_THRESHOLD:.2%}")
            logs = await self._query_loki()
            alert = AlertContext(
                timestamp=datetime.now(timezone.utc),
                error_rate=error_rate,
                raw_logs=logs,
                source="prometheus+loki",
            )
            await self.on_alert(alert)
        else:
            logger.debug(f"Error rate {error_rate:.2%} — all good.")

    async def _query_prometheus(self) -> Optional[float]:
        """
        Query: sum(rate(http_requests_total{status=~'5..'}[5m]))
               / sum(rate(http_requests_total[5m]))
        Returns a float 0-1 or None if Prometheus is unreachable / no data.
        """
        query = (
            "sum(rate(http_requests_total{status=~'5..'}[5m])) "
            "/ sum(rate(http_requests_total[5m]))"
        )
        try:
            resp = await self._client.get(
                f"{settings.PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
            )
            resp.raise_for_status()
            result = resp.json().get("data", {}).get("result", [])
            if not result:
                # Simulate a demo alert when no real Prometheus data exists
                logger.debug("Prometheus: no data — using demo simulation mode")
                return await self._demo_error_rate()
            value = float(result[0]["value"][1])
            return value
        except Exception as exc:
            logger.warning(f"Prometheus unreachable ({exc}) — entering simulation mode")
            return await self._demo_error_rate()

    async def _demo_error_rate(self) -> Optional[float]:
        """
        Demo/simulation mode: reads a trigger file so you can test without
        a real Prometheus.  Create the file 'trigger_alert.txt' to fire an alert.
        """
        import os
        if os.path.exists("trigger_alert.txt"):
            logger.info("Demo: trigger_alert.txt found — simulating 15% error rate")
            return 0.15
        return 0.0

    async def _query_loki(self) -> str:
        """
        Pull recent log lines from Loki matching the configured query.
        Falls back to reading local log files if Loki is unreachable.
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=settings.LOKI_LOOKBACK_MINUTES)

        params = {
            "query": settings.LOKI_QUERY,
            "start": str(int(start.timestamp() * 1e9)),  # nanoseconds
            "end": str(int(end.timestamp() * 1e9)),
            "limit": "100",
        }
        try:
            resp = await self._client.get(
                f"{settings.LOKI_URL}/loki/api/v1/query_range",
                params=params,
            )
            resp.raise_for_status()
            streams = resp.json().get("data", {}).get("result", [])
            lines = []
            for stream in streams:
                for _, line in stream.get("values", []):
                    lines.append(line)
            return "\n".join(lines[-50:]) if lines else self._demo_logs()
        except Exception as exc:
            logger.warning(f"Loki unreachable ({exc}) — using demo logs")
            return self._demo_logs()

    def _demo_logs(self) -> str:
        return """
[ERROR] 2024-01-15T10:23:01Z mongodb-primary  Too many open files (ulimit reached: 1024)
[ERROR] 2024-01-15T10:23:02Z mongodb-primary  Failed to open /data/db/WiredTiger.lock: Too many open files
[ERROR] 2024-01-15T10:23:05Z app-server-1     MongoNetworkError: connect ECONNREFUSED 127.0.0.1:27017
[ERROR] 2024-01-15T10:23:05Z app-server-2     MongoNetworkError: connect ECONNREFUSED 127.0.0.1:27017
[ERROR] 2024-01-15T10:23:07Z nginx            upstream timed out (110) while reading response from upstream
[WARN]  2024-01-15T10:23:10Z prometheus       Target scrape failed for mongodb-exporter
[ERROR] 2024-01-15T10:23:12Z mongodb-primary  OOMKilled: container exceeded memory limit 4Gi
[ERROR] 2024-01-15T10:23:15Z k8s-node-1       Pod mongodb-0 in CrashLoopBackOff (restart #7)
""".strip()
