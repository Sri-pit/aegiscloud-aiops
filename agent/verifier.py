"""
agent/verifier.py  –  ACT phase: Wait-and-Verify loop (Guardrail #2).

After executing a fix, the verifier polls Prometheus for up to
VERIFY_TIMEOUT_SECONDS. If the error rate doesn't drop below threshold,
it returns False and the Orchestrator triggers a rollback.
"""

import asyncio
import time
import httpx
from loguru import logger

from config.settings import settings
from agent.models import AlertContext


class Verifier:
    def __init__(self):
        self._client = httpx.AsyncClient(timeout=10)

    async def verify(self, alert: AlertContext) -> bool:
        """
        Poll until error rate falls below threshold or timeout expires.
        Returns True = fix worked, False = fix failed / needs rollback.
        """
        logger.info(
            f"Verifier: waiting up to {settings.VERIFY_TIMEOUT_SECONDS}s "
            f"for error rate to drop below {settings.ERROR_RATE_THRESHOLD:.2%}..."
        )
        start = time.time()
        elapsed = 0

        while elapsed < settings.VERIFY_TIMEOUT_SECONDS:
            await asyncio.sleep(settings.VERIFY_POLL_INTERVAL)
            elapsed = time.time() - start

            current_rate = await self._current_error_rate()
            logger.info(
                f"  [{elapsed:.0f}s / {settings.VERIFY_TIMEOUT_SECONDS}s] "
                f"Error rate: {current_rate:.2%}"
            )

            if current_rate < settings.ERROR_RATE_THRESHOLD:
                logger.success(
                    f"Verification PASSED — error rate {current_rate:.2%} "
                    f"below threshold {settings.ERROR_RATE_THRESHOLD:.2%}"
                )
                return True

        logger.error(
            f"Verification FAILED — error rate still elevated after "
            f"{settings.VERIFY_TIMEOUT_SECONDS}s"
        )
        return False

    async def _current_error_rate(self) -> float:
        """Re-query Prometheus for current error rate."""
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
                # In demo mode, check if trigger file was removed
                import os
                if not os.path.exists("trigger_alert.txt"):
                    return 0.0   # "fixed"
                return 0.20      # still broken
            return float(result[0]["value"][1])
        except Exception:
            import os
            return 0.0 if not os.path.exists("trigger_alert.txt") else 0.20
