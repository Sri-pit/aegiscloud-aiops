"""
features/chaos.py - Feature 5: Chaos Engineering
Simulates infrastructure failures and tests AegisNode's self-healing response.
"""

import asyncio
import random
from datetime import datetime
from typing import List, Dict, Callable, Awaitable
from loguru import logger


CHAOS_EXPERIMENTS = [
    {
        "id": "kill_pod",
        "name": "Kill Random Pod",
        "description": "Terminates a running pod to test restart recovery",
        "icon": "💥",
        "severity": "MEDIUM",
        "expected_recovery": "Pod restart via Deployment controller",
        "simulated_logs": [
            "[ERROR] Pod mongodb-0 terminated unexpectedly (exit code 137)",
            "[ERROR] Deployment controller detected pod failure",
            "[WARN]  Attempting pod restart (attempt 1/3)",
            "[ERROR] MongoNetworkError: connect ECONNREFUSED 127.0.0.1:27017",
            "[ERROR] Health check failed for mongodb-0",
        ]
    },
    {
        "id": "network_latency",
        "name": "Inject Network Latency",
        "description": "Adds 500ms latency to all pod communications",
        "icon": "🌐",
        "severity": "LOW",
        "expected_recovery": "Traffic rerouting via service mesh",
        "simulated_logs": [
            "[WARN]  Network latency spike detected: 500ms avg",
            "[ERROR] nginx: upstream timed out (110) while reading response",
            "[WARN]  API response time: 2400ms (threshold: 500ms)",
            "[ERROR] Circuit breaker OPEN for service: app-server",
            "[WARN]  Retrying request with exponential backoff",
        ]
    },
    {
        "id": "fill_disk",
        "name": "Fill Disk to 95%",
        "description": "Simulates disk pressure by filling storage to 95%",
        "icon": "💾",
        "severity": "HIGH",
        "expected_recovery": "Log rotation and temp file cleanup",
        "simulated_logs": [
            "[ERROR] Disk usage critical: 95.2% on /var/lib/docker",
            "[ERROR] Failed to write to /data/db/journal: No space left on device",
            "[WARN]  Container eviction triggered due to disk pressure",
            "[ERROR] MongoDB WiredTiger: unable to create journal file",
            "[ERROR] Node condition: DiskPressure=True",
        ]
    },
    {
        "id": "cpu_stress",
        "name": "CPU Stress Test",
        "description": "Pins CPU to 95% to test autoscaling response",
        "icon": "🔥",
        "severity": "MEDIUM",
        "expected_recovery": "Horizontal pod autoscaler triggers scale-out",
        "simulated_logs": [
            "[WARN]  CPU usage: 95.3% on compute-prod-cluster",
            "[ERROR] Request queue depth: 847 (threshold: 100)",
            "[WARN]  HPA: scaling deployment from 2 to 4 replicas",
            "[ERROR] Pod scheduling failed: insufficient CPU resources",
            "[WARN]  Throttling detected on container: app-server-1",
        ]
    },
    {
        "id": "node_failure",
        "name": "Simulate Node Failure",
        "description": "Takes an entire node offline to test workload redistribution",
        "icon": "🖥️",
        "severity": "CRITICAL",
        "expected_recovery": "Pod rescheduling to healthy nodes",
        "simulated_logs": [
            "[ERROR] Node k8s-node-2 unreachable (timeout after 40s)",
            "[ERROR] 7 pods affected by node failure",
            "[WARN]  Rescheduling pods to k8s-node-1 and k8s-node-3",
            "[ERROR] PersistentVolume detach failed on node k8s-node-2",
            "[WARN]  Node condition: Ready=False, NetworkUnavailable=True",
        ]
    },
]


class ChaosEngine:
    def __init__(self, on_alert: Callable = None):
        self.on_alert = on_alert
        self.results: List[Dict] = []
        self.active_experiment = None
        self._running_experiment = False

    def get_experiments(self) -> List[Dict]:
        return CHAOS_EXPERIMENTS

    def get_resilience_score(self) -> Dict:
        if not self.results:
            return {"score": 0, "total": 0, "passed": 0, "failed": 0}
        passed = len([r for r in self.results if r["recovered"]])
        total = len(self.results)
        return {
            "score": round((passed / total) * 100),
            "total": total,
            "passed": passed,
            "failed": total - passed,
        }

    async def run_experiment(
        self,
        experiment_id: str,
        log_callback: Callable[[str, str], None],
    ) -> Dict:
        """Run a chaos experiment and simulate AegisNode's response."""
        if self._running_experiment:
            return {"error": "Another experiment is already running"}

        exp = next((e for e in CHAOS_EXPERIMENTS if e["id"] == experiment_id), None)
        if not exp:
            return {"error": "Unknown experiment"}

        self._running_experiment = True
        self.active_experiment = experiment_id
        start = datetime.now()

        log_callback("CHAOS", f"\n{'='*50}")
        log_callback("CHAOS", f"{exp['icon']}  CHAOS EXPERIMENT: {exp['name']}")
        log_callback("CHAOS", f"Severity: {exp['severity']}")
        log_callback("CHAOS", f"{'='*50}")

        # Phase 1: Inject chaos
        log_callback("CHAOS", "\n[PHASE 1] Injecting chaos...")
        await asyncio.sleep(1)
        for log_line in exp["simulated_logs"]:
            log_callback("CHAOS_ERROR" if "[ERROR]" in log_line else "CHAOS_WARN", log_line)
            await asyncio.sleep(0.4)

        # Phase 2: AegisNode detects
        log_callback("CHAOS", "\n[PHASE 2] AegisNode detecting anomaly...")
        await asyncio.sleep(1.5)
        log_callback("CHAOS_DETECT", "🔍 Observer: Error rate spike detected!")
        log_callback("CHAOS_DETECT", "📚 ChromaDB: Retrieving relevant runbooks...")
        await asyncio.sleep(1)
        log_callback("CHAOS_DETECT", "🧠 Llama 3: Analyzing root cause...")
        await asyncio.sleep(2)
        log_callback("CHAOS_DETECT", f"✅ LLM: Root cause identified — {exp['expected_recovery']}")
        log_callback("CHAOS_DETECT", "🛡️  OPA: Validating remediation actions...")
        await asyncio.sleep(0.8)
        log_callback("CHAOS_DETECT", "✅ OPA: All actions approved")

        # Phase 3: Remediation
        log_callback("CHAOS", "\n[PHASE 3] Executing remediation...")
        await asyncio.sleep(1)
        recovery_actions = self._get_recovery_actions(experiment_id)
        for action in recovery_actions:
            log_callback("CHAOS_FIX", f"  → {action}")
            await asyncio.sleep(0.6)

        # Phase 4: Verify
        log_callback("CHAOS", "\n[PHASE 4] Verifying recovery...")
        await asyncio.sleep(2)
        recovered = random.random() > 0.1  # 90% success rate

        duration = (datetime.now() - start).seconds

        if recovered:
            log_callback("CHAOS_SUCCESS", f"\n✅ EXPERIMENT PASSED — Recovered in {duration}s")
            log_callback("CHAOS_SUCCESS", f"Expected: {exp['expected_recovery']}")
        else:
            log_callback("CHAOS_FAIL", f"\n❌ EXPERIMENT FAILED — Could not recover after {duration}s")
            log_callback("CHAOS_FAIL", "Rollback triggered automatically")

        result = {
            "experiment": exp["name"],
            "severity": exp["severity"],
            "recovered": recovered,
            "duration_seconds": duration,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
        self.results.append(result)
        self._running_experiment = False
        self.active_experiment = None
        return result

    def _get_recovery_actions(self, experiment_id: str) -> List[str]:
        actions = {
            "kill_pod":       ["kubectl rollout restart deployment/mongodb", "Waiting for pod to reach Running state", "Health check passed ✓"],
            "network_latency":["Identifying affected pods via Istio telemetry", "Applying network policy override", "Latency reduced to 12ms ✓"],
            "fill_disk":      ["Triggering log rotation on affected node", "Removing temp files: freed 8.2GB", "Disk pressure cleared ✓"],
            "cpu_stress":     ["kubectl scale deployment/app-server --replicas=4", "New pods scheduled on available nodes", "CPU load distributed ✓"],
            "node_failure":   ["Marking node k8s-node-2 as unschedulable", "Rescheduling 7 pods to healthy nodes", "All pods Running ✓"],
        }
        return actions.get(experiment_id, ["Executing generic recovery procedure"])