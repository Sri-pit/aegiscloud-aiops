# policies/remediation.rego
# AegisNode safety policy evaluated by Open Policy Agent (OPA)
# Load this via: opa run --server --bundle ./policies/

package aegisnode.remediation

import future.keywords.in
import future.keywords.if

# ── Default deny ──────────────────────────────────────────────────────────────
default allow := false

# ── Allow if no actions are denied ───────────────────────────────────────────
allow if {
    count(denied_actions) == 0
}

# ── Collect all denied action identifiers ────────────────────────────────────
denied_actions := {msg |
    some action in input.actions
    is_denied(action)
    msg := sprintf("%v:%v", [action.action_type, action.target])
}

reason := concat(", ", denied_actions) if count(denied_actions) > 0
reason := "all actions approved" if count(denied_actions) == 0

# ── Deny rules ────────────────────────────────────────────────────────────────

# Never touch database pods directly (EHR / HIPAA data)
is_denied(action) if {
    action.action_type in {"kubectl_exec_command", "ssh_exec_command"}
    contains(action.target, "database")
}

is_denied(action) if {
    action.action_type in {"kubectl_exec_command", "ssh_exec_command"}
    contains(action.target, "mongo")
    not action.action_type in {"kubectl_restart_pod", "notify_slack", "no_action"}
}

# Never terraform apply without a human-approved flag
is_denied(action) if {
    action.action_type == "terraform_apply"
    not input.terraform_human_approved == true
}

# Block high-risk actions below 85% confidence threshold
# (confidence checked from the outer context via error_rate proxy)
is_denied(action) if {
    action.risk_level == "high"
    action.action_type not in {"notify_slack", "no_action"}
}

# Never scale to 0 replicas (kills the service entirely)
is_denied(action) if {
    action.action_type == "kubectl_scale"
    action.parameters.replicas == 0
}

# Never act on kube-system namespace
is_denied(action) if {
    action.namespace == "kube-system"
}

# Block SSH with root user
is_denied(action) if {
    action.action_type == "ssh_exec_command"
    action.parameters.username == "root"
}

# Limit remediation to known safe namespaces
allowed_namespaces := {"default", "production", "staging", "monitoring"}

is_denied(action) if {
    not action.namespace in allowed_namespaces
    action.action_type not in {"notify_slack", "no_action"}
}
