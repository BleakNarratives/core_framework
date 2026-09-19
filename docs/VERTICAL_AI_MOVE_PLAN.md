# Vertical AI Source-to-Destination Move Plan

**Status:** plan only; no moves, deletes, or archive copies executed.

## Proposed destinations

| Source | Proposed destination | Boundary | Required pre-move work |
|---|---|---|---|
| `vertical_ai/` | `projects/vertical-ai-outreach/` | standalone outreach prototype | mock HTTP/SMTP, preserve CSV as generated data, document vault source |
| `vertical_local/` | `projects/vertical-local/` | standalone FastAPI/local debate app | preserve `web/`, make route smoke test dependency-aware, exclude `.env`/`.venv` |
| `vertical_radar/` | `projects/vertical-radar/` | standalone prototype | keep requirements/package markers, fix import/package contract, mock live tools |
| `vertical_radar_dupe/` | dated archive/provenance location | historical evidence | record inventory/hashes and obtain explicit approval; do not merge blindly |
| `vertical_ai_engine/` | `projects/vertical-ai-engine/` | legacy Coach Bleak/Veritas app/archive | resolve missing `app.py` and `config.py`, separate thread dumps and outputs |
| `The-Werkz/Official-Vertical-AI-Boardroom/` | remains separate nested repository initially | canonical Boardroom repo | stabilize paths, adapters, manifests, and nested Git history before any relocation |

## Ordered migration gates

### Gate 0 — freeze

- Record root and nested Git status.
- Record all source/destination paths without opening credentials.
- Do not stage `.env*`, vaults, key-shaped files, databases, logs, caches, or model output.
- Preserve the pre-existing Boardroom edit in `verticals/saas.txt` as unrelated.

### Gate 1 — source verification

- Run `python scripts/verify_vertical_ai.py`.
- Run each workspace's syntax and available offline tests.
- Record missing dependencies as `BLOCKED`, not as passing substitutes.
- Verify manifests describe actual entrypoints and outputs.

### Gate 2 — dependency rewrite

- Replace absolute paths with file-relative/configured paths.
- Preserve public CLI names through wrappers only where needed.
- Update imports, scripts, package metadata, aliases, and docs in the same logical change.
- Keep external integrations optional and graceful when absent.

### Gate 3 — move one workspace

- Create destination ignore rules first.
- Copy source-only files; do not move generated data or secrets.
- Run syntax/import checks from both old and new working directories.
- Compare source inventory and destination inventory.
- Keep a rollback mapping from every destination file to its source.

### Gate 4 — stabilize and checkpoint

- Run tests and deterministic dry runs.
- Review `git diff --check` and explicit staged paths.
- Commit only that workspace's source/docs/tests.
- Do not include unrelated root modifications or nested-repository changes.

## `vertical_ai_engine` audit

### Actual runnable entrypoint

- `foia_cli.py` is the only discovered Python CLI with a `main()` and
  `if __name__ == "__main__"` block.
- It imports `modules.foia_generator.FOIAGeneratorMicroAgent` and supports
  `generate`, `analyze`, and `appeal` subcommands.
- The README claims `python app.py`, but no `vertical_ai_engine/app.py` exists in
  the audited filesystem.

### Missing or unresolved modules

- `vertical_ai_engine/tests/test_config.py` imports `config`, but no
  `vertical_ai_engine/config.py` was found.
- `vertical_ai_engine/tests/test_app_integration.py` imports `app` and service
  globals, but no `app.py` was found.
- `tests/test_gemini_service.py` imports
  `modules.services.gemini_service`, but the audited `modules/` tree contains no
  `services/` package.
- `tests/tests_init_.py` is not the conventional `tests/__init__.py` marker.

### Actual safe disposition

Treat `foia_cli.py` plus the four/five `modules/*.py` files as the current source
candidate. Treat README claims, missing Flask app/config/service modules, thread
dumps, HTML exports, logs, and generated output as unresolved legacy material.
Before moving, either restore the missing app/config/service sources from verified
history or mark those tests and README paths as historical/unavailable.
