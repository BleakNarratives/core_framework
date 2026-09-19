# Vertical AI Workspace

This is the navigation hub for the scattered Vertical AI workspaces. It is a map,
not a claim that these projects have already been merged.

## Active and related workspaces

| Workspace | Purpose | Manifest / docs | Verification |
|---|---|---|---|
| [`vertical_ai`](../vertical_ai/README.md) | Review discovery and outreach prototype | [`manifest.json`](../vertical_ai/manifest.json) | Syntax/import checks; live network and SMTP intentionally skipped |
| [`vertical_local`](../vertical_local/README.md) | FastAPI wrapper and deterministic debate engine | [`manifest.json`](../vertical_local/manifest.json) | `python scripts/verify_vertical_ai.py --project vertical_local` |
| [`vertical_radar`](../vertical_radar/README.md) | Search/scrape risk-assessment prototype | [`manifest.json`](../vertical_radar/manifest.json) · [`requirements.txt`](../vertical_radar/requirements.txt) | Syntax/import checks; live services skipped |
| [`vertical_radar_dupe`](../vertical_radar_dupe/README.md) | Suspected incomplete historical duplicate | [`manifest.json`](../vertical_radar_dupe/manifest.json) · [disposition](../docs/VERTICAL_RADAR_DUPLICATE_DISPOSITION.md) | Provenance only; do not execute or delete |
| [`vertical_ai_engine`](../vertical_ai_engine/README.md) | Coach Bleak / Veritas legacy document-analysis prototype | [`manifest.json`](../vertical_ai_engine/manifest.json) | Syntax/import checks; optional services skipped |
| [`Official-Vertical-AI-Boardroom`](../The-Werkz/Official-Vertical-AI-Boardroom/README.md) | Multi-agent boardroom and simulation engine | [migration map](../docs/VERTICAL_AI_MIGRATION.md) | Nested-repository checks and Boardroom-specific offline harness |

## Safe verification

From the repository root:

```bash
python scripts/verify_vertical_ai.py
```

This performs manifest validation, AST syntax checks, local import resolution, and
the deterministic `vertical_local` debate check. If FastAPI is not installed, its
route check is reported as skipped rather than replaced or installed automatically.
It never reads credential files, contacts providers, starts a server, or invokes an
LLM.

## Migration gates

- [`docs/PROJECT_MAP.md`](../docs/PROJECT_MAP.md) — canonical workspace map.
- [`docs/VERTICAL_AI_MIGRATION.md`](../docs/VERTICAL_AI_MIGRATION.md) — dependency graph and phased move checklist.
- [`docs/VERTICAL_AI_ARTIFACT_POLICY.md`](../docs/VERTICAL_AI_ARTIFACT_POLICY.md) — generated-artifact and secret boundaries.
- [`docs/VERTICAL_RADAR_DUPLICATE_DISPOSITION.md`](../docs/VERTICAL_RADAR_DUPLICATE_DISPOSITION.md) — reversible duplicate recommendation.
- [`scripts/verify_vertical_ai.py`](../scripts/verify_vertical_ai.py) — offline verifier.

## Current rule

Do not physically consolidate these workspaces until imports, external integrations,
outputs, secrets, nested Git boundaries, and rollback paths have been verified.
