"""
agent/models.py  –  All Pydantic schemas used throughout AegisNode.
"""

from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


class AlertContext(BaseModel):
    timestamp: datetime
    error_rate: float
    raw_logs: str
    source: str


class RemediationAction(BaseModel):
    action_type: Literal[
        "kubectl_restart_pod",
        "kubectl_scale",
        "kubectl_patch_resource_limits",
        "kubectl_exec_command",
        "terraform_apply",
        "ssh_exec_command",
        "notify_slack",
        "no_action",
        # Extra types the LLM sometimes invents — all mapped to ssh_exec_command internally
        "sysctl_set_value",
        "ulimit_increase",
        "service_restart",
        "config_update",
    ]
    target: str = Field(description="Pod name, deployment name, node hostname, etc.")
    namespace: str = Field(default="default")
    parameters: dict = Field(default_factory=dict)
    justification: str = Field(description="One sentence explaining WHY this action fixes the issue")
    risk_level: Literal["low", "medium", "high"] = Field(default="low")


class RootCauseAnalysis(BaseModel):
    summary: str
    root_cause: str
    affected_components: List[str]
    confidence: float = Field(ge=0.0, le=1.0)
    actions: List[RemediationAction] = Field(max_length=5)
    rollback_plan: str


class OPAInput(BaseModel):
    actions: List[RemediationAction]
    namespace: str
    error_rate: float
    timestamp: str


class OPAResult(BaseModel):
    allow: bool
    denied_actions: List[str] = Field(default_factory=list)
    reason: str = ""


class ActionResult(BaseModel):
    action: RemediationAction
    success: bool
    output: str
    error: Optional[str] = None


class RemediationReport(BaseModel):
    alert: AlertContext
    rca: RootCauseAnalysis
    opa_result: OPAResult
    action_results: List[ActionResult]
    verified: bool
    rollback_triggered: bool = False
    total_duration_seconds: float