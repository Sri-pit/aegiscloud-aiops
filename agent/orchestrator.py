"""
agent/orchestrator.py  –  ORIENT + DECIDE phases of the OODA loop.

Ties together: RAG → LLM analysis → OPA validation → Execution → Verification.
"""

import time
import asyncio
from loguru import logger
from langsmith import traceable

from config.settings import settings
from agent.models import AlertContext, RemediationReport
from agent.rag import RAGEngine
from agent.analyzer import Analyzer
from agent.validator import OPAValidator
from agent.executor import Executor
from agent.verifier import Verifier
from agent.notifier import Notifier


class Orchestrator:
    def __init__(self):
        self.rag = RAGEngine()
        self.analyzer = Analyzer()
        self.validator = OPAValidator()
        self.executor = Executor()
        self.verifier = Verifier()
        self.notifier = Notifier()
        self._processing = False  # prevent concurrent alerts

    async def initialize(self):
        """Run all async init tasks (load runbooks into ChromaDB, etc.)"""
        logger.info("Initializing RAG engine (loading runbooks into ChromaDB)...")
        await self.rag.initialize()
        logger.info("Connecting to OPA...")
        await self.validator.health_check()
        logger.success("Orchestrator ready.")

    @traceable(name="handle_alert")   # LangSmith traces this entire function
    async def handle_alert(self, alert: AlertContext):
        if self._processing:
            logger.warning("Already processing an alert — skipping duplicate.")
            return

        self._processing = True
        start = time.time()

        try:
            logger.info("=" * 60)
            logger.info(f"ALERT RECEIVED  |  error_rate={alert.error_rate:.2%}")
            logger.info("=" * 60)

            # ── 1. ORIENT: RAG context retrieval ──────────────────────────
            logger.info("[1/5] Retrieving relevant runbooks from ChromaDB...")
            runbook_context = await self.rag.query(alert.raw_logs)

            # ── 2. ORIENT: LLM Root Cause Analysis ───────────────────────
            logger.info("[2/5] Running LLM root cause analysis (Llama 3 via Ollama)...")
            rca = await self.analyzer.analyze(alert, runbook_context)
            logger.info(f"      Root cause: {rca.root_cause}")
            logger.info(f"      Confidence: {rca.confidence:.0%}")
            logger.info(f"      Actions planned: {len(rca.actions)}")

            # ── 3. DECIDE: OPA policy validation ─────────────────────────
            logger.info("[3/5] Validating actions against OPA policies...")
            opa_result = await self.validator.validate(rca.actions, alert)

            if not opa_result.allow:
                logger.error(f"OPA DENIED remediation: {opa_result.reason}")
                await self.notifier.send(
                    f"⛔ AegisNode: OPA blocked remediation\n"
                    f"Reason: {opa_result.reason}\n"
                    f"Root cause: {rca.root_cause}"
                )
                return

            # ── 4. ACT: Execute remediation ───────────────────────────────
            logger.info("[4/5] Executing remediation actions...")
            action_results = await self.executor.execute_all(rca.actions)

            # ── 5. ACT: Verify + rollback if needed ───────────────────────
            logger.info("[5/5] Verifying fix (wait-and-verify loop)...")
            verified = await self.verifier.verify(alert)

            rollback_triggered = False
            if not verified and settings.ROLLBACK_ON_FAILURE:
                logger.error("Verification FAILED — triggering rollback!")
                await self.executor.rollback(rca)
                rollback_triggered = True

            # ── Report ────────────────────────────────────────────────────
            duration = time.time() - start
            report = RemediationReport(
                alert=alert,
                rca=rca,
                opa_result=opa_result,
                action_results=action_results,
                verified=verified,
                rollback_triggered=rollback_triggered,
                total_duration_seconds=duration,
            )

            self._log_report(report)
            await self.notifier.send_report(report)

        except Exception as exc:
            logger.exception(f"Orchestrator error: {exc}")
        finally:
            self._processing = False

    def _log_report(self, report: RemediationReport):
        status = "✅ SUCCESS" if report.verified else "❌ FAILED"
        rollback = " (ROLLBACK TRIGGERED)" if report.rollback_triggered else ""
        logger.info("=" * 60)
        logger.info(f"REMEDIATION {status}{rollback}")
        logger.info(f"Duration   : {report.total_duration_seconds:.1f}s")
        logger.info(f"Root cause : {report.rca.root_cause}")
        logger.info(f"Actions    : {len(report.action_results)}")
        for r in report.action_results:
            icon = "✓" if r.success else "✗"
            logger.info(f"  {icon} {r.action.action_type} → {r.action.target}")
        logger.info("=" * 60)
