#!/usr/bin/env python3
# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: thoth
# ROLE: Undocumented module
# TIER: Scout (6)
# AUTHOR: BleakNarratives
# SESSION: 2026-08-22 ShipWreckD OS Builder — auto-tagged by DNA Sweeper
# [/DNA_TAG]
"""
Local JSONL event bus for the RootBase agent ecosystem.

This stays entirely on-device and is safe for simple hooks, triggers, and
cross-repo coordination without requiring a network service.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

# Default to $HOME, not a pinned path. Tests and tools redirect HOME to keep runtime
# state contained, and a hardcoded default wrote into one specific user's home no
# matter what HOME said -- which is how a redirected-HOME test appended a real event
# to the live bus. An explicit ROOTBASE_DIR (or ROOTBASE_BUS_DIR /
# ROOTBASE_EVENT_FILE) still wins, so pinning the location remains possible.
ROOTBASE_DIR = Path(os.environ.get(
    "ROOTBASE_DIR",
    str(Path.home() / "RootBase"),
))
BUS_DIR = Path(os.environ.get(
    "ROOTBASE_BUS_DIR",
    str(ROOTBASE_DIR / "logs" / "shared"),
))
BUS_FILE = Path(os.environ.get(
    "ROOTBASE_EVENT_FILE",
    str(BUS_DIR / "agent_events.jsonl"),
))
DLQ_FILE = Path(os.environ.get(
    "ROOTBASE_DLQ_FILE",
    str(BUS_DIR / "dead_letters.jsonl"),
))
COURIER_STATE = Path(os.environ.get(
    "ROOTBASE_COURIER_STATE",
    str(BUS_DIR / "courier_state.json"),
))


def ensure_bus() -> Path:
    BUS_DIR.mkdir(parents=True, exist_ok=True)
    BUS_FILE.touch(exist_ok=True)
    return BUS_FILE


def bus_state_path() -> Path:
    return BUS_DIR / "agent_bus_state.json"


def current_line_count() -> int:
    ensure_bus()
    with BUS_FILE.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def emit_event(
    event_type: str,
    payload: Dict[str, Any] | None = None,
    *,
    source: str = "thoth",
    origin: str | None = None,
    channel: str = "local",
    tags: Iterable[str] | None = None,
) -> Dict[str, Any]:
    ensure_bus()
    event = {
        "event_id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event_type": event_type,
        "payload": payload or {},
        "source": source,
        "origin": origin or source,
        "channel": channel,
        "tags": list(tags or []),
    }
    with BUS_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, separators=(",", ":")) + "\n")
    return event


def read_events(offset: int = 0, limit: int | None = None) -> Tuple[List[Dict[str, Any]], int]:
    ensure_bus()
    events: List[Dict[str, Any]] = []
    next_offset = offset
    with BUS_FILE.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if index < offset:
                continue
            if limit is not None and len(events) >= limit:
                break
            line = line.strip()
            if not line:
                next_offset = index + 1
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({
                    "event_type": "bus.decode_error",
                    "payload": {"line_index": index, "raw": line[:200]},
                    "source": "agent_bus",
                    "origin": "agent_bus",
                    "channel": "local",
                    "tags": ["decode_error"],
                })
            next_offset = index + 1
    return events, next_offset


def write_state(state: Dict[str, Any]) -> None:
    BUS_DIR.mkdir(parents=True, exist_ok=True)
    with bus_state_path().open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def read_state() -> Dict[str, Any]:
    path = bus_state_path()
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class Courier:
    """Hermes courier role: delivers bus events to subscribed handlers.

    Mirrors the retry-with-backoff pattern already used in
    vertical_radar/src/tools/tools.py. A fresh courier starts its cursor at
    the current bus head (like MotherBrain) so only NEW events are delivered
    on first run; the cursor is persisted in courier_state.json so restarts
    don't redeliver. Handlers that exhaust all retries are written to the
    dead-letter queue (dead_letters.jsonl) so nothing is silently dropped.
    """

    def __init__(self, max_attempts: int = 3, backoff_seconds: float = 2.0):
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self._handlers: List[Tuple[str, Any]] = []
        self._cursor = self._load_cursor()

    def subscribe(self, event_type: str, handler: Any) -> None:
        """Register a handler for an event_type. '*' matches all events."""
        self._handlers.append((event_type, handler))

    def process(self, limit: int = 500) -> Dict[str, Any]:
        """Read events since the cursor and dispatch to matching handlers.

        Returns a summary: delivered, failed, dead_lettered, processed.
        The cursor only advances when there are handlers registered and
        events are actually read.
        """
        if not self._handlers:
            return {
                "delivered": 0,
                "failed": 0,
                "dead_lettered": 0,
                "processed": 0,
                "note": "no handlers registered",
            }
        events, next_offset = read_events(offset=self._cursor, limit=limit)
        delivered = 0
        failed = 0
        dead_lettered = 0
        for event in events:
            for event_type, handler in self._handlers:
                if event_type == "*" or event.get("event_type") == event_type:
                    result = self._dispatch(event, handler)
                    if result == "ok":
                        delivered += 1
                    elif result == "dlq":
                        dead_lettered += 1
                        failed += 1
                    else:  # "error" — handler raised but not dead-lettered
                        failed += 1
        self._cursor = next_offset
        self._save_cursor()
        return {
            "delivered": delivered,
            "failed": failed,
            "dead_lettered": dead_lettered,
            "processed": len(events),
        }

    def _dispatch(self, event: Dict[str, Any], handler: Any) -> str:
        """Retry a handler up to max_attempts. Returns 'ok', 'dlq', or 'error'."""
        last_err: Any = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                handler(event)
                return "ok"
            except Exception as err:  # noqa: BLE001 - courier must survive handler bugs
                last_err = err
                if attempt < self.max_attempts:
                    time.sleep(self.backoff_seconds * attempt)
        self._dead_letter(event, handler, last_err)
        return "dlq"

    def _dead_letter(self, event: Dict[str, Any], handler: Any, err: Any) -> None:
        ensure_bus()
        entry = {
            "dead_letter_id": uuid.uuid4().hex,
            "dead_lettered_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": event,
            "handler": getattr(handler, "__name__", repr(handler)),
            "error": repr(err),
            "attempts": self.max_attempts,
        }
        with DLQ_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")

    def _load_cursor(self) -> int:
        if COURIER_STATE.exists():
            try:
                with COURIER_STATE.open("r", encoding="utf-8") as handle:
                    return json.load(handle).get("cursor", 0)
            except (json.JSONDecodeError, OSError):
                return 0
        # Fresh courier: start at the current bus head so we only deliver NEW events.
        return current_line_count()

    def _save_cursor(self) -> None:
        BUS_DIR.mkdir(parents=True, exist_ok=True)
        with COURIER_STATE.open("w", encoding="utf-8") as handle:
            json.dump({"cursor": self._cursor}, handle, indent=2)


def read_dead_letters(offset: int = 0, limit: int | None = None) -> Tuple[List[Dict[str, Any]], int]:
    """Read dead-lettered events for inspection or replay."""
    ensure_bus()
    if not DLQ_FILE.exists():
        return [], 0
    entries: List[Dict[str, Any]] = []
    next_offset = offset
    with DLQ_FILE.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if index < offset:
                continue
            if limit is not None and len(entries) >= limit:
                break
            line = line.strip()
            if not line:
                next_offset = index + 1
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                entries.append({
                    "dead_letter_id": None,
                    "error": "decode_error",
                    "line_index": index,
                    "raw": line[:200],
                })
            next_offset = index + 1
    return entries, next_offset


courier = Courier()
