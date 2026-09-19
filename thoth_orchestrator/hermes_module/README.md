# Hermes
**Status**: Consolidated into `agent_bus.py` (2026-09-07)
**Author**: BleakNarratives
**Ecosystem**: ShipWrekD OS / RootBase

## What this is
Message courier between Thoth and the agent swarm. Async delivery, retry logic, dead letter queue. The nervous system of the orchestration layer.

## Where it lives
The courier role is implemented as the `Courier` class in `../agent_bus.py` — not a
separate module. Hermes and Thoth are one engine; the bus *is* the courier.

- `Courier.subscribe(event_type, handler)` — register a handler; `'*'` matches all events.
- `Courier.process(limit=500)` — reads events since the persisted cursor, dispatches to
  matching handlers with retry+backoff, advances the cursor, returns a summary.
- Dead letters (handlers that exhaust retries) land in `dead_letters.jsonl` in the bus dir.
- Read them back with `read_dead_letters(offset, limit)`.
- A default `courier` instance is ready at module import.

## Status
- [x] Design
- [x] MVP
- [x] Tested (smoke test passed 2026-09-07: success, DLQ, wildcard, no-handlers paths)
- [ ] Shipped (pending wiring into `thoth_core.py`)

---
*Part of the BleakNarratives / Vertical AI ecosystem.*
