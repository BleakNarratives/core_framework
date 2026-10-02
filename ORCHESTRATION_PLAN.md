# Orchestration Plan: 5-Day Agent Swarm & Convergence Ingest

## Objective
Operationalize the orchestration layer, execute the 5-day swarm itinerary, and perform a codebase convergence/ingest against the BUP Slim (6-month) baseline.

## Convergence Ingest (Pre-Swarm Task)
- **Goal:** Merge three codebase branches/snapshots, diff against BUP Slim baseline to evaluate progress.
- **Task:** 
    1.  Pull assets from remote rclone storage (cloud/storage sources).
    2.  Merge the three distinct codebases.
    3.  Compare (diff) the converged result against the saved BUP Slim snapshot.
    4.  Document the results in `core_framework/CONVERGENCE_REPORT.md`.

## 5-Day Swarm Itinerary

### Day 1: Diff Theater & Dry Runs
- **Goal:** Validate canonical integration and automated testing.
- **Task:** Verify `core_framework/launchers/` and `Diff-Theater/` interaction. Execute automated dry-runs and log to `DIFF_THEATER_LOG.md`.

### Day 2: Tribunal UI Sidebar Integration
- **Goal:** Audit IDE/VSCode binding.
- **Task:** Test sidebar event-bus messaging against `server.py` in `Tribunal/`. Log UI component readiness.

### Day 3: Code City Bundle Spin-Up
- **Goal:** Establish 3D viewport.
- **Task:** Configure and run `core_framework/launchers/code_city.py`. Verify socket handler on port 8765.

### Days 4-5: MarketTwin & Continuous Scouting Patrols
- **Goal:** Automate market data scouting.
- **Task:** Integrate `AxeScout/` findings with `axescout-market-twin` pipeline. Ensure continuous cron/loop execution.

## Verification
- For each step, create a corresponding verification script/log in `core_framework/tests/` or `logs/`.
- Ensure all components communicate via the `core_framework` shared bus.
