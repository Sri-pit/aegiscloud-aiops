"""
AegisNode - Self-Healing Infrastructure Agent
Entry point: python main.py
"""

import asyncio
import sys
from loguru import logger
from agent.observer import Observer
from agent.orchestrator import Orchestrator
from config.settings import settings

# ── Banner ──────────────────────────────────────────────────────────────────
BANNER = """
╔═══════════════════════════════════════════════════════════╗
║           AegisNode  •  Self-Healing AI Agent             ║
║   Observe → Orient → Decide → Act   (OODA Loop)           ║
╚═══════════════════════════════════════════════════════════╝
"""

async def main():
    print(BANNER)
    logger.info("AegisNode starting up...")
    logger.info(f"Watching Prometheus @ {settings.PROMETHEUS_URL}")
    logger.info(f"Watching Loki       @ {settings.LOKI_URL}")
    logger.info(f"LLM Model           : {settings.OLLAMA_MODEL}")
    logger.info(f"OPA URL             : {settings.OPA_URL}")

    orchestrator = Orchestrator()
    await orchestrator.initialize()

    observer = Observer(on_alert=orchestrator.handle_alert)

    logger.success("AegisNode is LIVE — monitoring started. Press Ctrl+C to stop.")

    try:
        await observer.start_polling()
    except KeyboardInterrupt:
        logger.warning("Shutdown signal received. Stopping gracefully...")
        await observer.stop()
        sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("AegisNode stopped.")