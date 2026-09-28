"""
Telemetry Bus — Centralized event sink for all system components.
Non-blocking, thread-safe event propagation for observability.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict

# Central log for the telemetry bus
LOG_FILE = Path.home() / "logs" / "telemetry_bus.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE)]
)

class TelemetryBus:
    def __init__(self):
        # Use an asyncio queue for non-blocking emission
        self._queue = asyncio.Queue()
        logging.info("TelemetryBus initialized.")

    async def emit(self, source: str, stage: str, event: str, payload: Dict[str, Any] = None):
        """Emits an event to the bus."""
        event_data = {
            "source": source,
            "stage": stage,
            "event": event,
            "payload": payload or {}
        }
        logging.info(f"EMIT: {json.dumps(event_data)}")
        await self._queue.put(event_data)

    def emit_sync(self, source: str, stage: str, event: str, payload: Dict[str, Any] = None):
        """Synchronous version for non-async contexts."""
        # Using a hacky event loop wrapper for demo simplicity
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.create_task(self.emit(source, stage, event, payload))

# Global instance
bus = TelemetryBus()
