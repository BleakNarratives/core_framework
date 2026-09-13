# Kid Toolchains — Scout + Oracle Bundles (sub-agents that compose)

MOLT bundles are designed to **compose as toolchains without tool calls** — each `sidecar.json` is typed, so Kids read each other's sidecars directly.

## Included Kids

- **`negotiation-ghost`** — live deal whisperer. Scout feeds `sec_filings + salary_bands + deal_history → sidecar.counterparty_dossier`. Use *during* calls/chats; prompt is already hydrated before you enter the room.
- **`dopamine-architect-in-reverse`** — Attention OS. Analyzes `app_usage + screen_time + social_hooks` → rewrites `blocklist_patch + deep_work_schedule` for router/home OS.
- **`scout-foreman`** — Meta-agent. Herds every Scout you installed: health sweeps, memory footprint budgeting, secret rotation via `vault-launch`.
- **`provenance-oracle`** — Deepfake/C2PA verifier. Checks `c2pa_manifests + generator_signatures` → `provenance_seal` for Sora/Flux/Veo pipelines.

## How Kids compose

```bash
# Example: negotiation-ghost reads mcp-replacement's ticket_snapshot without calling a tool
python -m src.skill.inference_bridge --skill negotiation-ghost --compose mcp-replacement --dry-run "what leverage do I have on ACME deal?"
```

## Packaging note

Kid bundles live flat in `bundles/<kid-name>/` alongside flagships — the "kid-toolchains" label is a **category**, not a parent folder. This keeps `validate_bundle --all` simple and lets OpenRouter/VS Code marketplace list each Kid independently.

See also: `projects/MOLT/marketplace/MCP_REPLACEMENT.md`
