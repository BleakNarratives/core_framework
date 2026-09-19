# Vertical Radar Duplicate Disposition

**Date:** 2026-09-17  
**Decision:** retain in place; do not delete or move yet.

## Evidence observed

- `vertical_radar` contains `src/radar/main.py`; `vertical_radar_dupe` does not.
- README and runbook hashes are identical between the two directories.
- `manifest.json` differs: the active candidate reports two Python files, while the
  duplicate reports one.
- `src/tools/tools.py` differs. The active candidate has bounded scraper output and
  catches scraper failures; the duplicate is older and lets scraper exceptions
  escape.
- `vertical_radar` contains `.env`; it was not opened or copied.
- Neither workspace has a Git directory in the audited location, so local Git
  provenance is unavailable.

## Recommendation

Treat `vertical_radar_dupe` as **HISTORICAL / QUARANTINED** until an owner or an
external repository history establishes provenance. The active candidate is
`vertical_radar`.

The reversible archive action, when explicitly approved later, should be:

1. record a file-list and SHA-256 inventory without reading secret values;
2. create a dated archive directory outside active source paths;
3. copy the duplicate tree preserving relative paths and metadata;
4. write a provenance note identifying the source path, destination, date, and
   hashes;
5. verify the active candidate's syntax/package checks;
6. only then consider removing the duplicate, with separate explicit approval.

No step above has been executed by this change.

## Do not infer

- Identical README/runbook text does not prove identical implementation.
- A missing entrypoint does not prove the duplicate is disposable.
- The `.env` presence does not prove it is valid or safe to use.
- Manifest timestamps are historical metadata, not proof of ownership.
