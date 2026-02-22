# AegisNode 🛡️
### Self-Healing Infrastructure Agent using GenAI

> **AIOps agent that monitors logs, uses a local LLM (Llama 3 on your RTX 5080) to diagnose failures, validates fixes through OPA policies, and autonomously remediates Kubernetes/infrastructure issues.**

---

## Architecture (OODA Loop)

```
Prometheus/Loki → Observer → Orchestrator → LLM (Ollama/Llama3)
                                  ↓                ↓
                             ChromaDB RAG      Pydantic Guard
                                  ↓                ↓
                            OPA Validator → Executor (kubectl/terraform)
                                                    ↓
                                             Verifier (wait 300s)
                                                    ↓
                                           Rollback if failed
                                                    ↓
                                           LangSmith (traces)
                                                    ↓
                                         Slack Notification
```

---

## Step 1 — Install Python Dependencies

Open your VS Code terminal and run:

```bash
pip install -r requirements.txt
```

---

## Step 2 — Install Ollama (runs your LLM locally on RTX 5080)

1. Go to **https://ollama.com/download**
2. Download the Windows installer
3. Run the installer (it installs as a background service)
4. Open a NEW terminal in VS Code and run:

```bash
ollama pull llama3
```

This downloads the 4.7GB Llama 3 8B model. Your RTX 5080 will handle it easily.

> **Want more reasoning power?** Run `ollama pull llama3:70b` instead (requires ~40GB VRAM — your 5080 handles 8B comfortably at full speed).

---

## Step 3 — Install Docker Desktop (for Prometheus, Loki, OPA)

1. Go to **https://www.docker.com/products/docker-desktop/**
2. Download Docker Desktop for Windows
3. Install and restart if prompted
4. Open VS Code terminal and run:

```bash
docker compose up -d
```

This starts:
- **Prometheus** at http://localhost:9090
- **Loki** at http://localhost:3100
- **OPA** at http://localhost:8181
- **Grafana** at http://localhost:3000 (login: admin / aegisnode)

---

## Step 4 — Configure your environment

```bash
# Copy the template
copy .env.example .env
```

Open `.env` in VS Code. The defaults work out of the box.

**Optional but recommended:** Sign up at https://smith.langchain.com (free) and paste your API key as `LANGSMITH_API_KEY=` — this gives you a beautiful dashboard showing every LLM reasoning trace.

---

## Step 5 — Run AegisNode

```bash
python main.py
```

You should see:
```
╔═══════════════════════════════════════════════════════════╗
║           AegisNode  •  Self-Healing AI Agent             ║
╚═══════════════════════════════════════════════════════════╝
✅ AegisNode is LIVE — monitoring started.
```

---

## Step 6 — Fire a Demo Alert

Open a **second terminal** in VS Code:

```bash
# Trigger a fake alert (simulates 15% error rate)
python demo_trigger.py
```

Watch the main terminal — within 30 seconds you'll see:
1. Observer detects the spike
2. Loki logs pulled
3. ChromaDB retrieves relevant runbooks
4. Llama 3 analyzes the logs and writes a fix plan
5. OPA validates each action
6. Actions execute (or dry-run if `KUBECTL_DRY_RUN=true`)
7. Verifier waits for health to improve

To simulate the fix working:
```bash
python demo_trigger.py --clear
```

---

## Dry Run Mode (Safe Testing)

In your `.env` file, set:
```
KUBECTL_DRY_RUN=true
TERRAFORM_AUTO_APPLY=false
```

In dry-run mode AegisNode does full analysis and prints every command it **would** run, but never actually applies anything. Perfect for demos and interviews.

---

## Tools Used — Where Each One Lives in the Code

| Tool | File | Role |
|------|------|------|
| **Prometheus** | `agent/observer.py` | Scrapes error rate metrics |
| **Loki** | `agent/observer.py` | Pulls log lines during alerts |
| **LangChain** | `agent/analyzer.py` | Orchestrates LLM prompt chain |
| **Ollama (Llama 3)** | `agent/analyzer.py` | Local LLM on your RTX 5080 |
| **ChromaDB** | `agent/rag.py` | Vector store for runbooks |
| **Pydantic** | `agent/models.py` | Validates LLM JSON output (Guardrail #1) |
| **OPA** | `agent/validator.py` | Policy-as-Code safety gate (Guardrail #2) |
| **Kubernetes/Kopf** | `agent/executor.py` | Applies kubectl fixes |
| **Terraform** | `agent/executor.py` | Generates/applies infra changes |
| **Paramiko (SSH)** | `agent/executor.py` | Node-level fixes (ulimit etc.) |
| **LangSmith** | `agent/orchestrator.py` | Traces full agent reasoning |
| **Slack** | `agent/notifier.py` | Sends fix reports to your channel |

---

## Project Structure

```
aegisnode/
├── main.py                  # Entry point
├── demo_trigger.py          # Demo tool
├── requirements.txt
├── docker-compose.yml       # Prometheus + Loki + OPA
├── .env.example
├── agent/
│   ├── observer.py          # Prometheus + Loki scraping
│   ├── orchestrator.py      # OODA loop coordinator
│   ├── rag.py               # ChromaDB vector store
│   ├── analyzer.py          # LangChain + Ollama LLM
│   ├── validator.py         # OPA policy check
│   ├── executor.py          # kubectl / terraform / ssh
│   ├── verifier.py          # Wait-and-verify loop
│   ├── notifier.py          # Slack webhook
│   └── models.py            # All Pydantic schemas
├── config/
│   ├── settings.py          # All config via .env
│   ├── prometheus.yml
│   └── promtail.yml
├── policies/
│   └── remediation.rego     # OPA Rego safety rules
└── runbooks/
    └── ehr_runbook.md       # Knowledge base for RAG
```

---

