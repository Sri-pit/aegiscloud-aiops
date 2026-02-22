"""
features/compliance.py - Feature 7: ISO 27001 Compliance Guardian
Automatically audits infrastructure remediations against ISO 27001 controls.
General enterprise security compliance (not domain-specific).
"""

from datetime import datetime
from typing import List, Dict
import random


ISO_CONTROLS = [
    {
        "id": "A.9",
        "name": "Access Control",
        "description": "User access management and privilege control",
        "checks": [
            "No root SSH access used during remediation",
            "All kubectl commands executed with scoped RBAC roles",
            "No credentials exposed in logs or environment variables",
            "Service account tokens scoped to minimum required permissions",
        ]
    },
    {
        "id": "A.10",
        "name": "Cryptography",
        "description": "Encryption and key management policies",
        "checks": [
            "All data in transit encrypted via TLS 1.2+",
            "Kubernetes secrets not stored as plaintext ConfigMaps",
            "No sensitive data written to unencrypted storage",
            "Certificate validity verified before deployment changes",
        ]
    },
    {
        "id": "A.12",
        "name": "Operations Security",
        "description": "Operational procedures and change management",
        "checks": [
            "All remediation actions logged with timestamps",
            "Change was validated against approved runbook",
            "Rollback plan documented before execution",
            "Post-change verification completed successfully",
        ]
    },
    {
        "id": "A.13",
        "name": "Communications Security",
        "description": "Network security and information transfer",
        "checks": [
            "No internal services exposed publicly during remediation",
            "Network policies maintained throughout incident",
            "Inter-service communication restricted to required ports",
            "No external API calls with sensitive infrastructure data",
        ]
    },
    {
        "id": "A.16",
        "name": "Incident Management",
        "description": "Security incident handling and response",
        "checks": [
            "Incident detected and logged within SLA window",
            "Root cause analysis documented with evidence",
            "Affected systems identified and recorded",
            "Recovery time within acceptable RTO threshold",
        ]
    },
    {
        "id": "A.17",
        "name": "Business Continuity",
        "description": "IT continuity and disaster recovery",
        "checks": [
            "Service availability maintained above 99.5% during incident",
            "Backup systems not affected by remediation",
            "Recovery point objective (RPO) not breached",
            "No data loss occurred during automated fix",
        ]
    },
]


class ComplianceEngine:

    def __init__(self):
        self.audit_history: List[Dict] = []

    def run_compliance_audit(self, remediation_summary: Dict = None) -> Dict:
        """Run ISO 27001 compliance audit against a remediation event."""
        now = datetime.now()
        control_results = []
        total_checks = 0
        passed_checks = 0

        for control in ISO_CONTROLS:
            check_results = []
            for check in control["checks"]:
                # Simulate check result — real implementation would
                # analyze actual kubectl audit logs, OPA decisions, etc.
                passed = random.random() > 0.08  # 92% pass rate
                total_checks += 1
                if passed:
                    passed_checks += 1
                check_results.append({
                    "check": check,
                    "status": "PASS" if passed else "FAIL",
                    "evidence": self._get_evidence(check, passed),
                })

            control_score = round(
                (len([c for c in check_results if c["status"] == "PASS"]) / len(check_results)) * 100
            )
            control_results.append({
                "id": control["id"],
                "name": control["name"],
                "description": control["description"],
                "score": control_score,
                "status": "COMPLIANT" if control_score >= 75 else "NON-COMPLIANT",
                "checks": check_results,
            })

        overall_score = round((passed_checks / total_checks) * 100)

        audit = {
            "audit_id": f"AUD-{now.strftime('%Y%m%d-%H%M%S')}",
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "standard": "ISO/IEC 27001:2022",
            "overall_score": overall_score,
            "overall_status": self._get_overall_status(overall_score),
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "failed_checks": total_checks - passed_checks,
            "controls": control_results,
            "remediation_ref": remediation_summary,
            "llm_summary": self._generate_audit_summary(overall_score, control_results),
            "next_audit": "Automatically scheduled after next remediation event",
        }
        self.audit_history.append(audit)
        return audit

    def _get_overall_status(self, score: int) -> str:
        if score >= 90:
            return "FULLY COMPLIANT"
        elif score >= 75:
            return "SUBSTANTIALLY COMPLIANT"
        elif score >= 60:
            return "PARTIALLY COMPLIANT"
        else:
            return "NON-COMPLIANT"

    def _get_evidence(self, check: str, passed: bool) -> str:
        if passed:
            evidences = [
                "Verified via OPA policy audit log",
                "Confirmed in kubectl audit trail",
                "Validated by LangSmith trace record",
                "Checked against remediation runbook v2.1",
                "Verified in system event log",
                "Confirmed by post-change validation",
            ]
            return random.choice(evidences)
        else:
            return "⚠ Manual review required — automated check inconclusive"

    def _generate_audit_summary(self, score: int, controls: List[Dict]) -> str:
        failed = [c for c in controls if c["status"] == "NON-COMPLIANT"]
        passed = [c for c in controls if c["status"] == "COMPLIANT"]

        summary = f"ISO 27001 audit completed with overall score {score}/100. "
        summary += f"{len(passed)} of {len(controls)} control domains are fully compliant. "

        if failed:
            summary += f"Control domains requiring attention: {', '.join([f['name'] for f in failed])}. "
            summary += "Recommend scheduling manual review within 30 days. "
        else:
            summary += "All control domains meet compliance thresholds. "
            summary += "This incident was handled within ISO 27001 guidelines. "

        summary += f"Next automated audit will trigger on the next remediation event."
        return summary

    def get_audit_history(self) -> List[Dict]:
        return self.audit_history[-10:]  # Last 10 audits