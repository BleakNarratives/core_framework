# Source inventory and provenance

Inventory date: 2026-10-13. This file distinguishes inspected local assets from assumed compatibility.

| Source | Location | Observed role | Used here | Not carried over |
|---|---|---|---|---|
| Block Berd | `~/Applications/Berd-0.6.4.AppImage`; upstream `https://github.com/block/berd` | Tauri desktop agent workspace; installed app includes `berdctl`, which supports projects, agents, skills, sessions, and info | Optional project host; this repo supplies plain Markdown persona/skill briefs | No Berd source fork, private APIs, or app modification |
| Vertical AI outreach | `~/vertical_ai/` | `scrape_google_reviews.py`, `automate_outreach.py`, `outreach_adapter.py`; manifest labels the first two live network/SMTP entrypoints | Lead concepts and field names; new project requires explicit user-provided source/provenance | No Google scraping, placeholder-recipient emailing, SMTP, or unmocked transports |
| AskHole v3 | `~/UNPACKED/intake_2026-08-22-rclone-ready-for-cloud_AskHole-V-3/AskHole-V-3/` | CLI draft generator, `economics.json`, Google Places/LLM providers, shell dispatchers | Economics table, output-section pattern, directness; numbers labeled as imported/unverified context | No API calls, secrets, shell dispatchers, cache reads, or automatic send |
| Coach Bleak / Veritas | `~/vertical_ai_engine/` | Legacy Coach Bleak/FOIA/document-analysis archive; manifest calls it a legacy prototype | Context and review warnings only; its features are not lead research | No psychological profiling, random personality metrics, automated accusations, legal advice, or claims treated as evidence |
| Berd bundled help / personas | `~/.local/share/xyz.block.berd/`; `.agents/agents/` contains repository agent examples | Installed Berd app data and Markdown personas | Project's plain-text briefs follow the inspectable project/persona model | No modifications to global Berd config or existing user personas without approval |
| Local model | Ollama `llama3.2:1b` present; API at `127.0.0.1:11434` was listening during inventory | Local inference runtime | Optional future draft/review adapter, default off in MVP | No prompts/data sent unless a future explicit local model mode is enabled |
| Existing utilities | `projects/agents/sim/bi_scouts.py`, MOLT Scout/Oracle/Governor modules | Bounded scout coordinator and trust gates | Reference for evidence limits, provenance, and keeping findings unverified | No imports from those modules in the standalone MVP |

## Reproducibility notes

- AskHole file inventory and economics keys were read from the exact local intake path above; no source code was executed.
- Vertical AI manifests and source scripts were inspected read-only.
- `berdctl --help` confirms project/agent/skill subcommands, but creating Berd-side records changes the app database. That has not been done automatically.
- This new directory is a standalone project root under `$HOME`, which is itself the surrounding workspace Git root. Its files are currently excluded by that root repository's allowlist; the directory is not a separate Git repository. No existing source directories were moved or rewritten.
