# Snarkie

**A multi-project workspace, not a single product.**

This repository's root is the machine's home directory (`/home/bleaknarratives`),
so it holds many independent projects rather than one codebase. Tracked source
is small — roughly 12 MB — and a `.gitignore` allowlist deliberately keeps the
surrounding home tree out of version control.

**If you are here to evaluate the work, start with
[`cascade-arbitration/`](cascade-arbitration/README.md).** It is a standalone,
dependency-free package that can be read and run without any of the rest of this
tree.

## Start here

| I want to… | Go to |
|---|---|
| Evaluate the shippable work | [`cascade-arbitration/`](cascade-arbitration/README.md) |
| Understand what's in this workspace | [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md) |
| Find the agent runtime | [`src/skill/`](src/skill/) — Scout, Oracle, Governor, bus |
| Find the field-intelligence workbench | [`Whorl/`](Whorl/README.md) — **separate Git repository** |
| Reproduce the local-inference measurements | [`docs/LOCAL_INFERENCE_LIMITS_20260926.md`](docs/LOCAL_INFERENCE_LIMITS_20260926.md) |

## Repository boundaries

These are load-bearing, not stylistic:

- **The root is a home directory.** 188 top-level directories live here. Most are
  unrelated to this repository and are deliberately untracked.
- **`Whorl/` and `projects/lean/` are nested Git repositories.** They have their
  own `.git` and their own history. Commit inside them separately; adding them
  here would record a gitlink no clone could resolve.
- **`.gitignore` is an allowlist, not a denylist.** It blocks everything at root
  (`/*`) and then re-admits specific paths. This exists because a stray `*` from
  `python -m venv` once made the repository unable to add any file at all. Use
  negation only when adding a path — an explicit ignore line is self-defeating,
  because Git never descends into an ignored directory to evaluate the negation.

## Tests

```bash
python -m pytest tests/ -q                        # repository-level
cd Whorl && python -m pytest tests/ -q           # Whorl, separate repo
python3 -m unittest discover -s tests -v          # per AGENTS.md
```

Tests must stay deterministic: no live services, no API credits, no credentials,
no writes to live databases. Use temp dirs, temp SQLite, mocks, local fixtures.

Some suites skip rather than fail when their subject is absent, because parts of
this workspace are untracked by design and simply do not exist in a clean clone.

## Tooling: Qwentag / DNA_TAG

Provenance system for maintaining codebase integrity across the Whorl environment.
Deployed to `~/Qwentag/`, added to `PATH` on shell restart.

- **Auto-Provenance** — tags every file with origin, pillar, role, metadata.
- **Drift Detection** — pre-commit hooks and `lint` block or report schema drift.
- **Orphan Recovery** — `backtag.py` restores metadata to moved or renamed files.

Commands: `dna_tag.py` (tagging, linting, reconciliation), `backtag.py` (orphan
restoration).
