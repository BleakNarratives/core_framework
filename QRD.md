# QRD — Strategic Session Record

## 1. Unfinished Tasks (Blockers)

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 1 | Daemon / non-blocking launcher hardening | `core_framework/launchers/` | Blocked |
| 2 | Unified `.venv` site-packages mapping | `core_framework/shared/config.py`, launchers | Blocked |
| 3 | Dual-stream commercial exporters (3D + CSV/JSON alpha) | `core_framework/bin/scout_vehicle.py` | Blocked |

Notes:
- Daemon hardening is required before `server.py` can run safely inside subshell CLI sandboxes without fd hangs.
- Venv unification depends on confirming which interpreter the WebSocket frontend/browser can reach from this Chromebook environment.
- Commercial exporters are gated on live network access for real scout sources.

## 2. CLI Agent Delegation Model

| Agent | Role | Scope | Latency | Accuracy |
|-------|------|-------|---------|----------|
| Gemini CLI | Deep Analyst / Macro Engine | SEC filings, 10-K/10-Q/8-K, debt covenants, legal transcripts | Slow, heavy context | Near 100% ground truth |
| Vibe CLI | High-Frequency Scout / Noise Filter | News feeds, social sentiment, supply-chain chatter, price/volume anomalies | Rapid, low effort per item | Variable S/N |

Key rule: Gemini CLI owns structured dense documents. Vibe CLI owns early-warning signals. Neither owns the full pipeline alone.

## 3. Medium-Agnostic Scoring Formula

```
Points = Base Value × Difficulty Multiplier × Confidence × Novelty
```

### Base Values by Medium

| Medium | Agent | Base Points | Multiplier |
|--------|-------|-------------|------------|
| Regulatory / SEC Filings | Gemini CLI | 50 | 3.5× |
| Real-time News / Social | Vibe CLI | 10 | 1.0× |

### Bonuses & Penalties

| Rule | Delta |
|------|-------|
| Cross-Validation Bounty (Gemini confirms Vibe early signal) | +100 pts (Gemini) |
| Early Predictor Bonus (Vibe called it first) | +25 pts (Vibe) |
| Signal Decay / False Positive Penalty | -20 pts |

### Cross-Validation Flow

1. Vibe CLI flags early distress rumor → logged as Pending Signal.
2. Gemini CLI parses subsequent filing that confirms the distress → Gemini gets base + 100-pt bounty.
3. Vibe CLI receives 25-pt Early Predictor Bonus.

## 4. Commercial Trajectory

```
Ephemeral CLI Swarms
    ↓
ScoutVehicle deduplication + asymmetric scoring
    ↓
Dual-stream output:
  A) 3D Spatial Payloads → MarketTwin viewport (port 8765)
  B) CSV/JSON Alpha Streams → distress intelligence buyers
```

Target buyers:
- Quant hedge funds
- PE / distressed M&A brokers
- Corporate Chief Risk Officers

## 5. Verified System Baseline (This Session)

- Backend broadcast: `PASS` (`messages_sent=1`, `first_type=market_twin`)
- ScoutVehicle patrol pass: produces valid `to_ws_payload()` output
- MarketTwinTranslator: real pipeline importable, canonical `capability_slots.py` syntax fixed
- Frontend: `renderMarketTwin` wired into `rampage-refactor/index.html`
- Component layout: `core_framework/` is a pure pointer layer; no canonical files moved or duplicated

## 6. Session Boundary

This QRD is the canonical record of the session. All other files (`ROADMAP.md`, `README.md`) reference this document.
