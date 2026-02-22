"""
config/settings.py  –  All configuration in one place.
Edit this file to match your environment.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # ── Prometheus ────────────────────────────────────────────────────────
    PROMETHEUS_URL: str = "http://localhost:9090"
    PROMETHEUS_POLL_INTERVAL: int = 30          # seconds between scrapes
    ERROR_RATE_THRESHOLD: float = 0.05          # 5 % → triggers agent

    # ── Loki ──────────────────────────────────────────────────────────────
    LOKI_URL: str = "http://localhost:3100"
    LOKI_QUERY: str = '{job="aegisnode"}'        # LogQL selector
    LOKI_LOOKBACK_MINUTES: int = 5

    # ── Ollama / LLM ──────────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"                 # change to llama3:70b if VRAM allows
    OLLAMA_TEMPERATURE: float = 0.1
    OLLAMA_MAX_TOKENS: int = 2048

    # ── ChromaDB ──────────────────────────────────────────────────────────
    CHROMA_PERSIST_DIR: str = "./chroma_db"
    CHROMA_COLLECTION: str = "runbooks"

    # ── OPA ───────────────────────────────────────────────────────────────
    OPA_URL: str = "http://localhost:8181"
    OPA_POLICY_PATH: str = "aegisnode/remediation"

    # ── Kubernetes ────────────────────────────────────────────────────────
    KUBECTL_DRY_RUN: bool = False                # True = safe mode, never applies
    KUBECONFIG: Optional[str] = None             # None = use default ~/.kube/config
    KUBERNETES_NAMESPACE: str = "default"

    # ── Terraform ─────────────────────────────────────────────────────────
    TERRAFORM_DIR: str = "./terraform"
    TERRAFORM_AUTO_PLAN: bool = True             # always runs plan
    TERRAFORM_AUTO_APPLY: bool = False           # requires human approval by default

    # ── LangSmith ─────────────────────────────────────────────────────────
    LANGSMITH_TRACING: bool = True
    LANGSMITH_API_KEY: Optional[str] = None      # set in .env
    LANGSMITH_PROJECT: str = "aegisnode"

    # ── Slack ─────────────────────────────────────────────────────────────
    SLACK_WEBHOOK_URL: Optional[str] = None      # set in .env, None = disable

    # ── Remediation ───────────────────────────────────────────────────────
    VERIFY_TIMEOUT_SECONDS: int = 300            # wait-and-verify window
    VERIFY_POLL_INTERVAL: int = 30
    ROLLBACK_ON_FAILURE: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
