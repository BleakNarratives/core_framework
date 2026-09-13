# LICENSE — git-state-snapshotter

- **Base license** — Includes: `SKILL.md`, `sidecar.json` (first hydrate), `sidecar.schema.json`, `daemon/scout.py`, `daemon/config.yaml`.
- **Retainer (monthly)** — Unlocks `feed_entitlements` listed below. Gated via Oracle + license check (offline-capable nonce — see `daemon/config.yaml` → `license.key`).

## Feed entitlements

Base (no retainer):
- `feeds.base` — version_logs

Retainer (private, high-frequency):
- `feeds.premium` — mutation_diffs, branch_maps, rollback_events

## Enforcement

- Sidecar field `entitlements.active` declares which feed tiers are licensed.
- Oracle gate audits writes that claim a premium feed without an active entitlement → `warn`/`block`.

Contact the author to activate retainer feeds for this bundle.
