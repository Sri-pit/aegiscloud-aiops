# AegisNode Runbook: EHR Infrastructure

## MongoDB Issues

### CrashLoopBackOff
- Pod is restarting. Check: `kubectl describe pod <name>`
- Exit code 137 = OOMKilled → increase memory limits
- Exit code 1 = config/auth error → check ConfigMap
- Always check `kubectl logs --previous <pod>` for last crash

### Too Many Open Files (ulimit)
- Symptom: `EMFILE` or "Too many open files" in logs
- Cause: OS file descriptor limit (default 1024) too low for MongoDB
- Fix on Kubernetes node:
  ```
  sysctl -w fs.file-max=500000
  echo "* soft nofile 65536" >> /etc/security/limits.conf
  echo "* hard nofile 65536" >> /etc/security/limits.conf
  ```
- For pods: add `ulimits` in pod spec or use init container

### OOMKilled
- Increase memory limit: `kubectl patch deployment mongodb -p '{"spec":{"template":{"spec":{"containers":[{"name":"mongodb","resources":{"limits":{"memory":"4Gi"}}}]}}}}'`
- Check for memory leaks with `mongostat`
- Review queries with `db.setProfilingLevel(1)` for slow queries

### Connection Refused (port 27017)
- Check pod running: `kubectl get pods -l app=mongodb`
- Test from app: `kubectl exec app-pod -- nc -zv mongodb 27017`
- Check NetworkPolicy: never expose 27017 externally (HIPAA requirement)
- Restart service: `kubectl rollout restart deployment/mongodb`

## Kubernetes General

### CrashLoopBackOff Recovery
1. `kubectl describe pod <pod> -n <ns>` — look at Events section
2. `kubectl logs <pod> --previous` — get crash reason  
3. Common fixes: scale down to 0, fix config, scale back up

### Resource Limits Best Practice
- Set requests = 70% of limits
- Memory: never set limit lower than your app's peak usage
- CPU: throttling is safer than OOM — err on the side of more CPU

## HIPAA Compliance Notes
- MongoDB must never be exposed via NodePort or LoadBalancer externally
- All logs containing patient data must be encrypted at rest
- SSH access to database nodes requires MFA and audit logging
- Never store credentials in environment variables — use Kubernetes Secrets
- Incident response: any data breach must be reported within 60 days

## Terraform
- Always `terraform plan` before `apply`
- Store state in S3 with locking via DynamoDB
- Tag all resources with: `environment`, `owner`, `hipaa-compliant=true`
- Never `terraform destroy` production without written approval
