"""
agent/validator.py  –  DECIDE phase: Policy-as-Code via OPA.

Sends every planned action to Open Policy Agent before execution.
OPA evaluates the Rego policies in ./policies/ and returns allow/deny.
Guardrail #2: even if the LLM plans something dangerous, OPA blocks it.
"""

from typing import List
from datetime import datetime, timezone
import httpx
from loguru import logger

from config.settings import settings
from agent.models import RemediationAction, AlertContext, OPAInput, OPAResult


class OPAValidator:
    def __init__(self):
        self._client = httpx.AsyncClient(timeout=10)

    async def health_check(self):
        try:
            resp = await self._client.get(f"{settings.OPA_URL}/health")
            resp.raise_for_status()
            logger.success("OPA: connected and healthy.")
        except Exception as exc:
            logger.warning(
                f"OPA unreachable ({exc}). "
                "Running in SAFE LOCAL MODE — high-risk actions will be auto-denied."
            )

    async def validate(
        self,
        actions: List[RemediationAction],
        alert: AlertContext,
    ) -> OPAResult:
        """
        POST the planned actions to OPA and get an allow/deny decision.
        Falls back to local safety rules if OPA is down.
        """
        payload = {
            "input": OPAInput(
                actions=actions,
                namespace=settings.KUBERNETES_NAMESPACE,
                error_rate=alert.error_rate,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ).model_dump()
        }

        try:
            resp = await self._client.post(
                f"{settings.OPA_URL}/v1/data/{settings.OPA_POLICY_PATH}",
                json=payload,
                timeout=5,
            )
            resp.raise_for_status()
            result = resp.json().get("result", {})

            return OPAResult(
                allow=result.get("allow", False),
                denied_actions=result.get("denied_actions", []),
                reason=result.get("reason", ""),
            )

        except Exception as exc:
            logger.warning(f"OPA call failed ({exc}) — using built-in safety rules.")
            return self._local_safety_check(actions)

    def _local_safety_check(self, actions: List[RemediationAction]) -> OPAResult:
        """
        Fallback when OPA is unreachable.
        Blocks anything obviously dangerous. Mirrors the Rego policy logic.
        """
        FORBIDDEN_TYPES = {"terraform_apply"}   # never auto-apply infra changes without OPA
        HIGH_RISK_BLOCKED = True                # block all high-risk actions without OPA

        denied = []
        for a in actions:
            if a.action_type in FORBIDDEN_TYPES:
                denied.append(f"{a.action_type}:{a.target} (forbidden without OPA)")
            if HIGH_RISK_BLOCKED and a.risk_level == "high":
                denied.append(f"{a.action_type}:{a.target} (high-risk blocked without OPA)")
            if "database" in a.target.lower() and a.action_type not in (
                "notify_slack", "no_action"
            ):
                denied.append(f"{a.action_type}:{a.target} (database operations require OPA)")

        if denied:
            return OPAResult(
                allow=False,
                denied_actions=denied,
                reason="Local safety rules denied one or more actions (OPA offline).",
            )

        return OPAResult(allow=True, reason="Local safety rules: all actions approved.")
