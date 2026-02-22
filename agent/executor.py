"""
agent/executor.py  –  ACT phase: Execute remediation actions.
"""

import asyncio
import json
from typing import List
from loguru import logger
from langsmith import traceable

from config.settings import settings
from agent.models import RemediationAction, RootCauseAnalysis, ActionResult


class Executor:

    @traceable(name="execute_actions")
    async def execute_all(self, actions: List[RemediationAction]) -> List[ActionResult]:
        results = []
        for action in actions:
            logger.info(f"  → Executing: {action.action_type} on {action.target}")
            result = await self._dispatch(action)
            results.append(result)
            if not result.success:
                logger.warning(f"    Action result: {result.output or result.error}")
        return results

    async def _dispatch(self, action: RemediationAction) -> ActionResult:
        handlers = {
            "kubectl_restart_pod":           self._kubectl_restart_pod,
            "kubectl_scale":                 self._kubectl_scale,
            "kubectl_patch_resource_limits": self._kubectl_patch_limits,
            "kubectl_exec_command":          self._kubectl_exec,
            "terraform_apply":               self._terraform_apply,
            "ssh_exec_command":              self._ssh_exec,
            "notify_slack":                  self._notify_slack_action,
            "no_action":                     self._no_action,
            "sysctl_set_value":               self._ssh_exec,
            "ulimit_increase":                self._ssh_exec,
            "service_restart":                self._kubectl_restart_pod,
            "config_update":                  self._kubectl_exec,
        }
        handler = handlers.get(action.action_type, self._unknown_action)
        try:
            return await handler(action)
        except Exception as exc:
            return ActionResult(action=action, success=False, output="", error=str(exc))

    # ── Kubernetes handlers ───────────────────────────────────────────────

    async def _kubectl(self, *args) -> tuple[bool, str]:
        cmd = ["kubectl"]
        if settings.KUBECTL_DRY_RUN:
            cmd += ["--dry-run=client"]
        if settings.KUBECONFIG:
            cmd += [f"--kubeconfig={settings.KUBECONFIG}"]
        cmd += list(args)

        logger.debug(f"kubectl {' '.join(args)}")
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            success = proc.returncode == 0
            output = stdout.decode() or stderr.decode()
            return success, output
        except FileNotFoundError:
            return False, "kubectl not found — install kubectl or set KUBECTL_DRY_RUN=true"

    async def _kubectl_restart_pod(self, action: RemediationAction) -> ActionResult:
        ns = action.namespace or settings.KUBERNETES_NAMESPACE
        ok, out = await self._kubectl("rollout", "restart", f"deployment/{action.target}", "-n", ns)
        return ActionResult(action=action, success=ok, output=out)

    async def _kubectl_scale(self, action: RemediationAction) -> ActionResult:
        ns = action.namespace or settings.KUBERNETES_NAMESPACE
        replicas = action.parameters.get("replicas", 1)
        ok, out = await self._kubectl("scale", f"deployment/{action.target}", f"--replicas={replicas}", "-n", ns)
        return ActionResult(action=action, success=ok, output=out)

    async def _kubectl_patch_limits(self, action: RemediationAction) -> ActionResult:
        ns = action.namespace or settings.KUBERNETES_NAMESPACE
        container = action.parameters.get("container", action.target)
        memory = action.parameters.get("memory_limit", "2Gi")
        cpu = action.parameters.get("cpu_limit", "1000m")
        patch = json.dumps({
            "spec": {"template": {"spec": {"containers": [{
                "name": container,
                "resources": {"limits": {"memory": memory, "cpu": cpu}}
            }]}}}
        })
        ok, out = await self._kubectl("patch", "deployment", action.target, "-p", patch, "-n", ns)
        return ActionResult(action=action, success=ok, output=out)

    async def _kubectl_exec(self, action: RemediationAction) -> ActionResult:
        ns = action.namespace or settings.KUBERNETES_NAMESPACE
        command = action.parameters.get("command", "echo ok")
        ok, out = await self._kubectl("exec", action.target, "-n", ns, "--", "sh", "-c", command)
        return ActionResult(action=action, success=ok, output=out)

    # ── Terraform handler ─────────────────────────────────────────────────

    async def _terraform_apply(self, action: RemediationAction) -> ActionResult:
        tf_dir = action.parameters.get("directory", settings.TERRAFORM_DIR)
        try:
            plan_proc = await asyncio.create_subprocess_exec(
                "terraform", "plan", "-out=aegisnode.tfplan",
                cwd=tf_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await plan_proc.communicate()
            plan_output = stdout.decode()

            if plan_proc.returncode != 0:
                return ActionResult(action=action, success=False, output=plan_output, error=stderr.decode())

            if not settings.TERRAFORM_AUTO_APPLY:
                msg = "Terraform plan generated. TERRAFORM_AUTO_APPLY=False — human review required."
                logger.warning(f"  {msg}")
                return ActionResult(action=action, success=True, output=plan_output + "\n" + msg)

            apply_proc = await asyncio.create_subprocess_exec(
                "terraform", "apply", "-auto-approve", "aegisnode.tfplan",
                cwd=tf_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await apply_proc.communicate()
            ok = apply_proc.returncode == 0
            return ActionResult(action=action, success=ok, output=stdout.decode(), error=stderr.decode() if not ok else None)
        except FileNotFoundError:
            return ActionResult(action=action, success=False, output="", error="terraform not found")

    # ── SSH handler ───────────────────────────────────────────────────────

    async def _ssh_exec(self, action: RemediationAction) -> ActionResult:
        try:
            import paramiko
        except ImportError:
            return ActionResult(action=action, success=False, output="", error="paramiko not installed")

        host = action.target
        command = action.parameters.get("command", "echo ok")
        username = action.parameters.get("username", "ubuntu")
        key_path = action.parameters.get("key_path", "~/.ssh/id_rsa")

        def _run():
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(host, username=username, key_filename=key_path)
            _, stdout, stderr = client.exec_command(command)
            out = stdout.read().decode()
            err = stderr.read().decode()
            client.close()
            return out, err

        try:
            out, err = await asyncio.to_thread(_run)
            ok = not err or "error" not in err.lower()
            return ActionResult(action=action, success=ok, output=out, error=err or None)
        except Exception as exc:
            return ActionResult(action=action, success=False, output="", error=str(exc))

    # ── Misc handlers ─────────────────────────────────────────────────────

    async def _notify_slack_action(self, action: RemediationAction) -> ActionResult:
        from agent.notifier import Notifier
        msg = action.parameters.get("message", "AegisNode alert")
        notifier = Notifier()
        await notifier.send(msg)
        # Always success — Slack is optional
        return ActionResult(action=action, success=True, output="Slack notification sent (or skipped if not configured)")

    async def _no_action(self, action: RemediationAction) -> ActionResult:
        logger.info("  LLM decided no action is needed — monitoring continues.")
        return ActionResult(action=action, success=True, output="No action taken per LLM recommendation.")

    async def _unknown_action(self, action: RemediationAction) -> ActionResult:
        return ActionResult(action=action, success=False, output="", error=f"Unknown action_type: {action.action_type}")

    # ── Rollback ──────────────────────────────────────────────────────────

    async def rollback(self, rca: RootCauseAnalysis):
        logger.warning(f"Rollback plan: {rca.rollback_plan}")
        for action in rca.actions:
            if action.action_type in ("kubectl_restart_pod", "kubectl_patch_resource_limits", "kubectl_scale"):
                ns = action.namespace or settings.KUBERNETES_NAMESPACE
                logger.warning(f"Rolling back deployment/{action.target}...")
                ok, out = await self._kubectl("rollout", "undo", f"deployment/{action.target}", "-n", ns)
                logger.info(f"Rollback result: {out}")
