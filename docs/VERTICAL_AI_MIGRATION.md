# Vertical AI Dependency Map and Migration Checklist

**Audit date:** 2026-09-17  
**Scope:** `The-Werkz/Official-Vertical-AI-Boardroom`, `vertical_ai`,
`vertical_local`, `vertical_radar`, `vertical_radar_dupe`, and
`vertical_ai_engine`  
**Mode:** read-only audit; no workspace moves or deletions performed.

This document is an evidence-based migration plan. It deliberately distinguishes
live code from stale manifests, generated artifacts, credentials, and historical
notes.

## Executive decision

Do **not** consolidate the Vertical AI workspaces into one directory yet. First make
the Boardroom's current layout internally truthful, then migrate one independently
verifiable workspace at a time.

The safest first consolidation candidate is the **Boardroom source boundary** itself:
its code is already arranged under `core/`, `tools/`, `bridges/`, `scouts/`, `tests/`,
`data/`, and `outputs/`. The sibling workspaces should initially be represented as
external integrations or related projects—not copied into the Boardroom.

## Workspace map

| Workspace | Primary role | Entry point(s) | Dependency posture | Migration disposition |
|---|---|---|---|---|
| `The-Werkz/Official-Vertical-AI-Boardroom` | Main multi-agent boardroom, simulation, genetics, outreach | `vertical_ai.py`, `vertical_ai_v2.py`, `vertical_ai_v3.py`, `king_kong.py` | Highest coupling; nested Git repo; existing `_paths.py` compatibility layer | Stabilize in place first |
| `vertical_ai` | Google review/business discovery and outreach automation | `automate_outreach.py`, `scrape_google_reviews.py` | Small standalone workflow; README says vault-managed keys | Keep separate initially; later connect through an explicit adapter |
| `vertical_local` | Local/API FastAPI wrapper, debate engine, web face | `app.py`, `run_boardroom.sh`, `debate_engine.py` | Separate app and web package; own requirements | Keep separate; possible provider/UI integration later |
| `vertical_radar` | Risk-assessment prototype using LangChain, DuckDuckGo, Trafilatura, Ollama, Gemini | `src/radar/main.py` | Requirements/package markers now declared; live network and credentials remain | Preserve as prototype; compare before any merge |
| `vertical_radar_dupe` | Older copy of the same stated radar concept | No `main.py`; only `src/tools/tools.py` | Incomplete relative to `vertical_radar`; same README/runbook | Quarantine as candidate duplicate; do not delete yet |
| `vertical_ai_engine` | Coach Bleak/Veritas application and conversation/archive material | `foia_cli.py`, modules under `modules/` | Mixed app/archive; own requirements/tests; proprietary disclaimer | Keep as separate legacy/product archive |
| `projects/vai_2d259c8e22fa` | Manifest-only artifact | `manifest.json` | No source discovered in this audit | Treat as evidence/artifact, not a source project |

## Boardroom dependency graph

```text
Entry points
├── vertical_ai.py
│   ├── vault_loader.init_vault           [MISSING inside Boardroom tree]
│   ├── boardroom.run_boardroom          -> core/boardroom.py via _paths/shim intent
│   ├── genetics.run_arena                -> core/genetics.py
│   ├── router.{ModelTier,call_model,...} -> core/router.py
│   ├── simulator.run_fractal_simulation -> core/simulator.py
│   ├── state.{save,load,list}            -> core/state.py
│   ├── verdict_bus.publish_verdict       -> core/verdict_bus.py
│   └── projects.manager.save_project_data -> projects/manager.py
│
├── vertical_ai_v2.py
│   ├── local Ollama HTTP endpoint
│   ├── local evidence files via Path
│   ├── optional scouts.{cfpb,web_search}
│   ├── optional firefly_lite
│   └── optional MotherBrain adapter / JSONL output
│
├── vertical_ai_v3.py
│   └── vertical_ai_v2 public API + local llama.cpp HTTP endpoint
│
├── boardroom_bridge.py / buffface_server.py
│   ├── subprocess / HTTP server behavior
│   ├── outputs/sessions/** and outputs/debriefs/**
│   └── vertical_ai.py subprocess path
│
└── king_kong.py
    └── core/king_kong.py -> boardroom, simulator, genetics, scouts, projects, reports

Shared internal layers
├── _paths.py       canonical roots and sys.path injection (but not imported by all live entrypoints)
├── core/           canonical engines
├── tools/          scouts, reports, ingestion, guard, patches
├── bridges/        local servers and adapters
├── scouts/         CFPB, business, web, and scout-brain modules
├── shared/         schemas
├── data/           verticals, targets, projects, ingest, neo4j cargo
└── outputs/        session and debrief artifacts
```

### Boardroom path/import findings

#### Confirmed high-risk issues

1. **`vertical_ai.py` has a machine-specific path injection.**
   It appends `/home/bleaknarratives/The-Werkz` rather than resolving its own
   project root. Moving the Boardroom or running it from another machine breaks
   this immediately.
2. **`vault_loader` is imported but no `vault_loader.py` exists inside the
   Boardroom tree.** The import is therefore unresolved unless an external
   `PYTHONPATH` or installation supplies it. This is a pre-existing import risk,
   not a migration regression.
3. **`vertical_ai.py` does not import `_paths.py` at its entry point.** The file
   still writes `vai_output_*.json` in the current working directory, despite
   `_paths.py` and `CURATOR.md` describing canonical `outputs/sessions/vai/`
   routing. A move that relies on the documented layout would expose this drift.
4. **`projects.manager` is a compatibility-sensitive import.** The live file is
   `projects/manager.py`, while the canonical implementation is also documented
   under `core/projects_manager.py` / `data/projects/manager.py` in different
   historical records. This needs one source of truth before moving the project.
5. **`router.py` and `verdict_bus.py` retain external workspace assumptions.**
   Examples include `~/MikeySwarm/telemetry`, `~/bin/vault-env`, `~/RootBase`,
   `~/.modmind`, and `~/New-Heights/universal-mcp-core`. These are integration
   dependencies, not Boardroom-local paths, and need environment variables or
   optional adapters before relocation.
6. **Root compatibility claims are not fully aligned with the current tree.**
   `CURATOR.md` and `REORG_2026-09-13.md` describe thin root shims and symlinked
   data roots, but the live `vertical_ai.py` is a full conductor and the map must
   be revalidated rather than trusted as a migration proof.

#### Confirmed safe/healthy signals

- `_paths.py` resolves its root from `Path(__file__).resolve().parent`, which is
  the correct basis for a future relocation.
- `vertical_ai_v2.py` and `vertical_ai_v3.py` use file-relative/local endpoint
  configuration and are substantially easier to migrate than the legacy v1
  conductor.
- `vertical_ai_v3.py` explicitly disables the v2 MotherBrain adapter by default,
  preserving its local-only contract.
- The selected Boardroom files and both radar tool modules passed syntax
  compilation with `python -m py_compile`.
- The nested Boardroom repository currently has one pre-existing modification:
  `verticals/saas.txt`. It must not be folded into a migration commit without
  explicit review.

### Boardroom data and secret boundaries

Keep these out of a source move unless separately classified:

- `.env`, `.env.example`, `.env.template`, and any vault loader/configuration;
- `outputs/`, `logs/`, `data/ingest/`, `data/projects/`, `data/neo4j/`, and
  generated reports;
- `__pycache__/`, `.pytest_cache/`, `.bak`, `.judo_bak*`, and dated archives;
- `MarketScout.zip` and conversation/thread dumps;
- external integrations under `hub/` or symlink farms;
- any key-shaped or credential-bearing files, even if a README calls them local.

## Radar comparison

### Evidence

`diff -rq vertical_radar vertical_radar_dupe` found:

- only `vertical_radar` has `.env`;
- `manifest.json` differs (the duplicate claims one Python file versus two);
- only `vertical_radar` has `src/radar/main.py`;
- `src/tools/tools.py` differs;
- README and runbook are byte-identical.

The two `tools.py` files have the same public functions:

- `search_tool(query)` using `duckduckgo_search.DDGS`, retrying three times and
  then prompting for a manual override;
- `scrape_web_data(url)` using `trafilatura`.

The non-duplicate `vertical_radar/src/tools/tools.py` is the stronger candidate:

- it has explicit search/scraper sectioning and a local test block;
- it prints clearer status messages;
- scraper failures are caught and returned as bounded text rather than escaping;
- it caps extracted content at 15,000 characters.

The duplicate's scraper has no exception boundary and no content cap. Its only
potentially meaningful difference is that it is older/simpler—not a separate
feature set.

### Radar conclusion

`vertical_radar_dupe` is an **incomplete older copy**, not an independent product.
Do not consolidate or delete it yet because its provenance is unverified and the
workspace may be serving as historical evidence. The eventual safe action is:

1. compare manifests and timestamps with the owning history, if available;
2. preserve a dated archive or provenance note;
3. retain `vertical_radar/src/radar/main.py` and the stronger tools implementation;
4. add a real `requirements.txt` and non-interactive tests before calling the
   surviving radar runnable;
5. only then remove the duplicate after explicit confirmation.

### Radar blockers before migration

- Both manifests list no entrypoint and no requirements, while the README gives
  install commands that are not captured in metadata.
- `main.py` imports `src.tools.tools`, which is not a stable package boundary
  without a package root/`__init__.py` strategy.
- `main.py` hard-codes `GOOGLE_API_KEY` fallback to the literal string
  `PASTE_YOUR_KEY_HERE`; this should become a fail-closed configuration check.
- The radar invokes live network/search/LLM services and prompts interactively on
  failure, so it cannot be used as a deterministic migration smoke test.
- `vertical_radar/.env` was deliberately not opened. It is a credential boundary.

## Migration checklist

### Phase 0 — freeze and baseline

- [ ] Record root and nested-repository `git status` without staging anything.
- [ ] Record the current Boardroom modification `verticals/saas.txt` separately.
- [ ] Do not move `Whorl/` or any nested Git repository as part of this migration.
- [ ] Do not read, copy, or stage `.env`, vault, key, database, or credential files.
- [ ] Establish a temporary, non-secret baseline of entrypoint paths and test
      commands.

### Phase 1 — make the Boardroom internally truthful

- [ ] Replace the hard-coded `/home/bleaknarratives/The-Werkz` injection in
      `vertical_ai.py` with a file-relative root/import strategy.
- [ ] Decide the vault contract: package the missing `vault_loader` adapter,
      make it an optional dependency, or fail with a clear setup message.
- [ ] Make `vertical_ai.py` explicitly use `_paths.py` and route output through
      the canonical session/data directories, or document that v1 remains a
      legacy CWD-based entrypoint.
- [ ] Select one canonical implementation for project manifest persistence and
      make `projects.manager` a thin compatibility wrapper if needed.
- [ ] Convert external paths (`MikeySwarm`, `RootBase`, `bin`, `New-Heights`,
      `.modmind`) to optional environment-configured integrations.
- [ ] Reconcile `CURATOR.md`, `REORG_2026-09-13.md`, README, and actual files.
- [ ] Add offline import/syntax checks that do not invoke network, vault, Neo4j,
      Ollama, llama.cpp, or subprocess integrations.

### Phase 2 — establish contracts for sibling workspaces

- [ ] Give each sibling a small manifest containing entrypoint, dependencies,
      outputs, environment names (not values), and test command.
- [ ] Add deterministic dry-run/test seams to `vertical_ai`, `vertical_local`,
      and Boardroom adapters before connecting them.
- [ ] Define a JSON/JSONL handoff contract for Boardroom ↔ outreach and Boardroom
      ↔ local wrapper; do not import sibling source directly.
- [ ] Decide whether `vertical_ai_engine` is an active product, an archive, or
      both, before including any code in a current product tree.
- [ ] Keep `vertical_radar` as a separate prototype until its dependency and
      credential behavior is explicit.

### Phase 3 — radar disposition

- [ ] Preserve `vertical_radar_dupe` in an archive/provenance location first.
- [ ] Compare any available Git history or manifests without opening secrets.
- [ ] Keep the stronger `vertical_radar` implementation as the active candidate.
- [ ] Add package markers/import-safe paths and a requirements declaration.
- [ ] Replace the placeholder Google key fallback with a fail-closed error.
- [ ] Add mocked tests for search failure, scraper failure, empty search results,
      and bounded extraction.
- [ ] Remove the duplicate only after explicit approval and a recorded archive
      hash/location.

### Phase 4 — physical organization

- [ ] Move only one workspace at a time into the approved `projects/` layout.
- [ ] Preserve nested Git repositories as nested repositories unless their owner
      explicitly approves a history migration.
- [ ] Update imports, scripts, shell aliases, systemd/cron references, docs, and
      generated-state paths in the same logical change as each move.
- [ ] Add compatibility shims only where they preserve a documented public
      command; do not create broad duplicate source trees.
- [ ] Keep generated artifacts and secrets outside the source destination and
      write destination ignore rules before any move.

### Phase 5 — verification gates

For each moved workspace:

- [ ] `python -m py_compile` on changed Python files.
- [ ] Import tests from the new working directory and from the repository root.
- [ ] Existing local test suite, with network/credential-dependent tests skipped
      or mocked rather than “made green” through live services.
- [ ] Dry-run entrypoint produces an artifact in the expected destination.
- [ ] No old path remains in executable code/configuration unless documented as
      an intentional compatibility path.
- [ ] `git diff --check` and a review for secrets, generated files, unrelated
      modifications, and stale documentation.
- [ ] Re-run the dependency scan after the move and compare against the baseline.

## Commands run for this audit

- `git -C The-Werkz/Official-Vertical-AI-Boardroom status --short --branch`
  - result: branch `main`; pre-existing modification `verticals/saas.txt`.
- `diff -rq vertical_radar vertical_radar_dupe`
  - result: `.env`, both manifests, `src/radar/main.py`, and `src/tools/tools.py`
    differ.
- `sha256sum` on radar README/runbook/tools files
  - result: README and runbook identical; tools files different.
- `python -m py_compile ...`
  - result: exit 0 for the selected Boardroom and radar files.
- Repository searches for imports, hard-coded paths, vault references, and runtime
  output paths.

**Important limitation:** syntax compilation does not prove imports resolve or that
runtime integrations work. The missing `vault_loader` and external path assumptions
remain unresolved until Phase 1 is implemented and tested safely.
