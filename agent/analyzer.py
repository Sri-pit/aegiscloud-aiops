"""
agent/analyzer.py  –  ORIENT phase: LLM Root Cause Analysis.
"""

import os
import json
from loguru import logger
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable

from config.settings import settings
from agent.models import AlertContext, RootCauseAnalysis

if settings.LANGSMITH_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT


SYSTEM_PROMPT = """You are AegisNode, an expert Site Reliability Engineer AI.
You analyze infrastructure logs and provide root cause analysis with remediation plans.

CRITICAL RULES:
- You MUST respond with ONLY valid JSON. No markdown, no explanation, no code blocks.
- Never suggest deleting databases, dropping tables, or destroying production resources.
- Never suggest actions with risk_level="high" unless confidence > 0.85.
- Maximum 5 actions. Prefer the least invasive fix first.
- For HIPAA-covered systems: never suggest exposing ports externally.

Your JSON must exactly match this structure:
{{
  "summary": "1-2 sentence plain English summary",
  "root_cause": "technical root cause",
  "affected_components": ["list", "of", "components"],
  "confidence": 0.85,
  "actions": [
    {{
      "action_type": "kubectl_restart_pod",
      "target": "mongodb-0",
      "namespace": "default",
      "parameters": {{}},
      "justification": "why this fixes it",
      "risk_level": "low"
    }}
  ],
  "rollback_plan": "how to undo these changes"
}}

Valid action_type values: kubectl_restart_pod, kubectl_scale, kubectl_patch_resource_limits, kubectl_exec_command, terraform_apply, ssh_exec_command, notify_slack, no_action
Valid risk_level values: low, medium, high
"""

USER_PROMPT = """## Alert Summary
- Timestamp: {timestamp}
- Error Rate: {error_rate}

## Raw Logs (last 5 minutes)
{raw_logs}

## Relevant Runbook Context
{runbook_context}

## Task
Analyze the logs, identify the root cause, and produce a remediation plan.
Respond with ONLY the JSON object, no other text.
"""


class Analyzer:
    def __init__(self):
        self._llm = ChatOllama(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
            temperature=settings.OLLAMA_TEMPERATURE,
            num_predict=settings.OLLAMA_MAX_TOKENS,
            format="json",
        )
        self._prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", USER_PROMPT),
        ])

    @traceable(name="llm_analyze")
    async def analyze(self, alert: AlertContext, runbook_context: str) -> RootCauseAnalysis:
        logger.debug("Sending logs to Ollama for RCA...")
        try:
            chain = self._prompt | self._llm
            response = await chain.ainvoke({
                "timestamp": alert.timestamp.isoformat(),
                "error_rate": f"{alert.error_rate:.2%}",
                "raw_logs": alert.raw_logs[:3000],
                "runbook_context": runbook_context,
            })

            # Parse the JSON response
            raw_text = response.content.strip()
            # Strip markdown code blocks if model adds them anyway
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
            
            raw_dict = json.loads(raw_text)
            rca = RootCauseAnalysis.model_validate(raw_dict)
            logger.success(f"LLM RCA complete. Root cause: {rca.root_cause} | Confidence: {rca.confidence:.0%}")
            return rca

        except Exception as exc:
            logger.error(f"LLM analysis failed: {exc}")
            return self._safe_fallback(alert, str(exc))

    def _safe_fallback(self, alert: AlertContext, error: str) -> RootCauseAnalysis:
        from agent.models import RemediationAction
        return RootCauseAnalysis(
            summary=f"LLM analysis failed. Manual investigation required.",
            root_cause="unknown — LLM unavailable",
            affected_components=["unknown"],
            confidence=0.0,
            actions=[
                RemediationAction(
                    action_type="no_action",
                    target="none",
                    parameters={},
                    justification="LLM unavailable, human operator must investigate manually",
                    risk_level="low",
                )
            ],
            rollback_plan="No automated actions were taken.",
        )