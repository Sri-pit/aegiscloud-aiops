"""
agent/rag.py  –  ORIENT phase: Retrieval-Augmented Generation.

Loads runbooks from ./runbooks/ into ChromaDB (local vector store).
When an alert fires, retrieves the most relevant runbook chunks to
give the LLM grounded context instead of hallucinating fixes.
"""

import os
import glob
import asyncio
from loguru import logger
import chromadb
from chromadb.utils import embedding_functions

from config.settings import settings


RUNBOOK_DIR = "./runbooks"


class RAGEngine:
    def __init__(self):
        self._client = None
        self._collection = None

    async def initialize(self):
        """Load ChromaDB and ingest runbook documents."""
        await asyncio.to_thread(self._init_chroma)

    def _init_chroma(self):
        self._client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)

        # Use the default sentence-transformer embeddings (runs locally, no API key)
        ef = embedding_functions.DefaultEmbeddingFunction()

        self._collection = self._client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION,
            embedding_function=ef,
        )

        # Only ingest if collection is empty
        if self._collection.count() == 0:
            self._ingest_runbooks()
        else:
            logger.info(f"ChromaDB: {self._collection.count()} runbook chunks already loaded.")

    def _ingest_runbooks(self):
        """Read all .md and .txt files from ./runbooks/ and add to ChromaDB."""
        files = glob.glob(f"{RUNBOOK_DIR}/**/*.md", recursive=True) + \
                glob.glob(f"{RUNBOOK_DIR}/**/*.txt", recursive=True)

        if not files:
            logger.warning(f"No runbook files found in {RUNBOOK_DIR}/ — loading built-in defaults")
            self._ingest_defaults()
            return

        docs, ids, metas = [], [], []
        for i, path in enumerate(files):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            # Chunk by 500-char windows with 100-char overlap
            chunks = self._chunk(content, size=500, overlap=100)
            for j, chunk in enumerate(chunks):
                docs.append(chunk)
                ids.append(f"{os.path.basename(path)}_chunk_{j}")
                metas.append({"source": path})

        self._collection.add(documents=docs, ids=ids, metadatas=metas)
        logger.success(f"ChromaDB: ingested {len(docs)} chunks from {len(files)} runbook files.")

    def _ingest_defaults(self):
        """Built-in runbook knowledge so the system works out of the box."""
        defaults = [
            {
                "id": "rb_crashloop",
                "text": (
                    "CrashLoopBackOff Runbook: Pod is restarting repeatedly. "
                    "Steps: 1) kubectl describe pod <name> to get exit code. "
                    "2) If OOMKilled, increase memory limits with kubectl patch. "
                    "3) If config error, check ConfigMap. "
                    "4) kubectl logs --previous <pod> for last crash output. "
                    "Root causes: OOMKilled (increase limits), bad env vars (fix ConfigMap), "
                    "missing secrets (check kubectl get secrets)."
                ),
            },
            {
                "id": "rb_oomkilled",
                "text": (
                    "OOMKilled Runbook: Container exceeded memory limit and was killed. "
                    "Fix: kubectl patch deployment <name> -p '{\"spec\":{\"template\":{\"spec\":"
                    "{\"containers\":[{\"name\":\"<container>\",\"resources\":{\"limits\":"
                    "{\"memory\":\"2Gi\"}}}]}}}}'. "
                    "For MongoDB specifically: increase to 4Gi, also check mongostat for query patterns. "
                    "Prevention: set resource requests = 70% of limits."
                ),
            },
            {
                "id": "rb_ulimit",
                "text": (
                    "Too Many Open Files / ulimit Runbook: Process hit OS file descriptor limit. "
                    "Symptoms: 'Too many open files', EMFILE errors in logs. "
                    "Fix on Linux node: sudo sysctl -w fs.file-max=500000, "
                    "also edit /etc/security/limits.conf: '* soft nofile 65536' and '* hard nofile 65536'. "
                    "For Kubernetes: add securityContext or init container to set ulimits. "
                    "For MongoDB: set systemLog.path and storage.dbPath on separate volumes."
                ),
            },
            {
                "id": "rb_mongodb_connections",
                "text": (
                    "MongoDB Connection Refused Runbook: App cannot connect to MongoDB. "
                    "Diagnose: kubectl exec -it mongodb-0 -- mongosh --eval 'db.serverStatus()'. "
                    "Common causes: 1) MongoDB crashed (check pod status), "
                    "2) Network policy blocking port 27017, "
                    "3) Too many connections (check maxIncomingConnections in mongod.conf). "
                    "Fix: kubectl rollout restart deployment/mongodb. "
                    "HIPAA note: Never expose MongoDB port externally."
                ),
            },
            {
                "id": "rb_terraform_drift",
                "text": (
                    "Configuration Drift Runbook: Terraform state differs from actual infra. "
                    "Diagnose: terraform plan -out=drift.tfplan. "
                    "Fix: terraform apply drift.tfplan (after human review). "
                    "Never terraform destroy in production without a backup. "
                    "Always run terraform plan before apply and review the diff carefully."
                ),
            },
        ]

        self._collection.add(
            documents=[d["text"] for d in defaults],
            ids=[d["id"] for d in defaults],
        )
        logger.success(f"ChromaDB: loaded {len(defaults)} built-in runbook entries.")

    @staticmethod
    def _chunk(text: str, size: int, overlap: int) -> list[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            chunks.append(text[start:end])
            start += size - overlap
        return chunks

    async def query(self, log_text: str, n_results: int = 3) -> str:
        """Return the most relevant runbook chunks as a single context string."""
        results = await asyncio.to_thread(
            self._collection.query,
            query_texts=[log_text[:2000]],   # truncate query to avoid token overflow
            n_results=n_results,
        )
        chunks = results.get("documents", [[]])[0]
        context = "\n\n---\n\n".join(chunks)
        logger.debug(f"RAG retrieved {len(chunks)} chunks from ChromaDB")
        return context
