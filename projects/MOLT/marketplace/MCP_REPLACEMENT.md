# MCP Replacement Runtimes — pitch: "Stop paying the MCP tool-calling tax"

## The pitch (paste into listing / README)

> Convert heavy MCP server integrations (Jira, GitHub, Postman, HubSpot) into a single **MOLT** package. The **Scout daemon runs on a local cron job**, pre-fetching API schemas, active tickets, and recent commits directly into `sidecar.json`. When the developer opens their IDE, the prompt is **already 100% hydrated — 0 tool calls required**.

## What you're replacing

| Before (MCP) | After (MOLT) |
|---|---|
| MCP server per integration (Jira, GitHub, HubSpot...) | One `daemon/scout.py` cron job |
| `LLM → call tool → wait → LLM` loop every turn | Scout pre-fetches **before** the API call |
| 70–90% of tokens burned on tool schemas + round-trips | Hydrated prompt is ready at IDE open |
| Server process to keep alive + auth per tool | `sidecar.json` typed contract, `sidecar.schema.json` validated |

## The bundle that proves it

`bundles/mcp-replacement/` — **$199–$399** — *Dev teams & Product Ops*

- **Feeds:** `api_schemas` · `active_tickets` · `recent_commits` · `deal_pipeline`
- **Sidecar keys:** `schemas_cached` · `ticket_snapshot` · `commit_digest` · `pipeline_state`
- **Interval:** `15m` · **Depth:** `3`

```bash
# Install instead of an MCP server
cp projects/MOLT/marketplace/bundles/mcp-replacement/SKILL.md .agents/skills/mcp-replacement/SKILL.md
cp projects/MOLT/marketplace/bundles/mcp-replacement/sidecar.json rag_storage/sidecars/mcp-replacement.json

# Enable the daemon (no server to run)
# Option A: cron
#   */15 * * * * python projects/MOLT/marketplace/bundles/mcp-replacement/daemon/scout.py
# Option B: systemd timer (see daemon/config.yaml)

# One-shot hydrate — any model, no tool loop
python -m src.skill.inference_bridge --skill mcp-replacement --dry-run "what's blocked in sprint 17?"

# Or let Scout pre-hydrate before you open the IDE — then hydration is literally 0 tool calls:
python projects/MOLT/marketplace/bundles/mcp-replacement/daemon/scout.py
python -m src.skill.inference_bridge --skill mcp-replacement --dry-run "summarize standup"
```

## How to demo the "N → 0" metric

Add this to your marketplace listing video:

1. **Before (MCP):** screen-record the IDE making 4–8 tool calls to answer "what's blocked?" — show the token count.
2. **After (MOLT):** same question, `sidecar.json` already has `ticket_snapshot` + `commit_digest` — single hydrated response, 0 tool calls. Overlay the **70–90% API cost** number.

## Related

- `KID_TOOLCHAINS.md` — sub-agent Kids that compose with this bundle (negotiation-ghost reads `ticket_snapshot` directly)
- `BUNDLE_SPEC.md` — bundle layout + authoring flow
- `PITCH_AND_PRICING.md` — banner one-liner + pricing table (70–90% metric)
