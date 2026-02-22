"""
agent/notifier.py  –  Slack webhook notifications.

Sends alerts and remediation reports to your Slack channel.
Set SLACK_WEBHOOK_URL in .env to enable. Safe to leave blank.
"""

import httpx
from loguru import logger

from config.settings import settings
from agent.models import RemediationReport


class Notifier:
    async def send(self, message: str) -> bool:
        if not settings.SLACK_WEBHOOK_URL:
            logger.debug("Slack not configured — skipping notification.")
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    settings.SLACK_WEBHOOK_URL,
                    json={"text": message},
                )
                resp.raise_for_status()
                return True
        except Exception as exc:
            logger.warning(f"Slack notification failed: {exc}")
            return False

    async def send_report(self, report: RemediationReport):
        if not settings.SLACK_WEBHOOK_URL:
            return

        status_emoji = "✅" if report.verified else "❌"
        rollback = "🔄 Rollback triggered!" if report.rollback_triggered else ""

        actions_text = "\n".join(
            f"  {'✓' if r.success else '✗'} `{r.action.action_type}` → `{r.action.target}`"
            for r in report.action_results
        )

        message = (
            f"{status_emoji} *AegisNode Remediation Report* {rollback}\n"
            f"*Root Cause:* {report.rca.root_cause}\n"
            f"*Confidence:* {report.rca.confidence:.0%}\n"
            f"*Duration:* {report.total_duration_seconds:.1f}s\n"
            f"*Actions:*\n{actions_text}\n"
            f"*Summary:* {report.rca.summary}"
        )
        await self.send(message)
