# Amend's "Nesting & Dupes Roadmap"

# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: tools
# DEPS: ariadne,humane_cannibal,dna_tag
# ROLE: Get nesting and duplicate copies under control without deleting anything
# AUTHOR: Amend (Codebuff) + BleakNarratives (operator)
# SESSION: 2026-09-23
# TIER: 2
# [/DNA_TAG]

> **Status: proposed. Nothing here has been executed.** No file was moved, archived, tagged,
> or deleted to produce this document. Every claim below is marked with how it was checked.

---

## The one ordering rule

**Tag before you merge, not after.** `tools/introspection/humane_cannibal.py:170-172` counts a
DNA_TAG as a *reason a file should win* its dupe group. So the order of operations changes which
copy survives:

```
wrong:  merge → tag the survivor     (winner chosen without provenance evidence)
right:  tag   → merge                (provenance informs the winner, per the tool's own rule)
```

That is the whole reason your two asks are one ask. "Wire up the tagger" and "get dupes under
control" are not independent tasks, and doing them in the other order silently discards the
signal `humane_cannibal` was built to read.

---

## What is actually there (verified)

| thing | evidence | reading |
|---|---|---|
| `tools/provenance/legacy/dna_tag_v0.py` + `dna_tag_v0.2.py` | both exist; **not byte-identical to any other file** — they appear in no hash group (see §Scan results) | one live tool, two *divergent* dead ancestors in a nesting layer |
| `.archive_cannibal_dryrun_20260911_0037.json` | group `~cross-dir~:dna_tag/dna_tag`; winner `provenance/dna_tag.py`; loser `provenance/legacy/dna_tag_v0.py`; `would_archive_to` → `tools/.archive_cannibal/20260911_003753/` | the merge was **already planned and dry-run** on 2026-09-11. `would_archive_to` means it never ran. |
| `tools/provenance/pheromone_store.py.bak_v1_20260911` | sibling of the live `pheromone_store.py`, same pattern | `.bak_v1_<date>` is a second dupe idiom, not covered by the cannibal group above |
| `tools/provenance/__pycache__/` | present in the listing | cache, not work — out of scope, ignore for measurements |

**Prior art exists.** This is not a greenfield cleanup; it is finishing a plan from 2026-09-11 that
stopped at the dry run. Read that manifest before designing anything new.

---

## Scan results — 2026-09-23 (read-only, no index built)

Content-hash pass over the allowlisted ship tree (`src tools tests docs scripts`): **287 files,
3,875,657 B**, 1 file skipped over 2 MB. No index, no writes, nothing archived.

**7 hash groups, 65,380 B wasted — but only 3 are worth acting on:**

| size | files | verdict |
|---|---|---|
| 24,031 B | `tools/lookingglass/chains/chain-42-tools-d2b2.json` · `tools/lookingglass/theater/theater.json` | generated output; confirm whether `theater.json` is a copy or a feed before touching |
| 19,982 B | `tools/atlas/atlas.json` · `tools/atlas/docs/atlas.seed42.json` | `docs/` mirror |
| 16,802 B | `tools/atlas/atlas.html` · `tools/atlas/docs/atlas.seed42.html` | `docs/` mirror |
| 1,925 B | `tools/coding/code_gamification.py` · `code_gamification2.py` | **the `2`-suffix idiom — real cleanup target** |
| 1,882 B | `tools/coding/code_visualizer.py` · `code_visualizer2.py` | **same idiom** |
| 758 B | `tools/taps/memorial/obituary.jsonl` · `graves/BleakNarratives__unspecified-streak.jsonl` | **do not merge** — see below |
| 0 B ×17 | every `__init__.py` | **do not merge** — package markers |

### The finding that changes the plan

`tools/provenance/legacy/dna_tag_v0.py` and `dna_tag_v0.2.py` **appeared in no hash group.** They are
not byte-identical copies of `dna_tag.py`; they are *divergent* copies. Therefore the two dedupe
tools see disjoint problems:

- `ariadne dupes` (content hash) will **never** surface the `legacy/` group. Not a bug — divergent
  files hash differently by definition.
- `humane_cannibal` (stem grouping + graft) is the only one that can, which is precisely why it
  grafts missing defs as `__from_loser_v1` rather than deleting a loser.

**So: the `legacy/` cleanup is a stem-grouping job, not a hash job.** An earlier draft of this
roadmap implied the opposite by calling v0.2 "near-identical". Corrected here.

### Two things that look like dupes and are not

- `obituary.jsonl` == `graves/<user>__<skill>.jsonl` (758 B) is `taps` working as designed: one
  burial writes both the all-skills obituary and the per-skill tombstone, so with a single burial
  they are the same bytes. Merging them would break the append-only contract documented in
  `tools/taps/README.md`.
- 17 empty `__init__.py` files are package markers. Waste is 0 B.

### Why an unbounded scan hangs (context for the next agent)

A walk from the repo root **times out**. The repo root is the operator's home directory — it holds a
literal `$HOME/` directory, plus `.9router/`, `._archive/`, `._incoming/`, `.agents/`, `.aider*`,
`.android/` and more. That is why `.gitignore` is `/*` plus an allowlist (`.gitignore:7`) and why
`ariadne` carries an `app` zone for top-level dot-dirs. **Scope every scan to the allowlisted roots**
— everything else is the 70 GB of noise the gitignore comment describes.

---

## Nesting audit — 2026-09-23 (read-only)

**The ship tree is shallow and healthy. The nesting the operator noticed is above it, not in it.**

```
files: 288   dirs: 58   max depth: 5

deepest:  src/ui/ribbon/fixtures/{single,double,precise-width}.json      (depth 5)
          src/ui/ribbon/fixtures_invalid/{empty,bad-version,bad-kind}.json
busiest:  tests 31 · tools 28 · docs 22 · src/ui/ribbon/fixtures_invalid 17
          src/skill 15 · scripts 15 · tools/lookingglass/chains 14
```

Max depth 5 is fine. Nothing in the ship tree needs flattening. Two things that do matter:

1. **`tools/` has ~21 sibling subdirectories** — clipboard, extraction, scraping, coding, sharing,
   provenance, introspection, inference, curator, pooper, jerry-hearing, atlas, lookingglass,
   ruberg, boundary, rescue, guard, vertical.splat, marketplace, sovereign, taps. This is a
   **fan-out** problem, not a depth problem, and `tools/README.md` §"Adding capabilities" already
   names the fix: *"Do not create a sibling tool. Add a subcommand."* The next tool should be a
   subcommand of an existing one.
2. **The nesting that looks bad is above the ship tree**, at the repo root — which is the home
   directory. That layer is already managed by `.gitignore` (`/*` + allowlist) and no merge will
   improve it.

---

## Canon count — recency evidence, not proof

| doc | mtime | canon |
|---|---|---|
| `tools/README.md` | **2026-09-22 00:53** | 65,019 |
| `tools/ROADMAP.md` | 2026-09-11 21:55 | 30,357 |

The README is 11 days newer, so **30,357 is the stale figure**. `tools/README.md` is also one of the
files already modified in the working tree this session, consistent with a recent edit. That is
recency evidence, not proof — neither number is generated output. Settling it means running
`ariadne zones`, which requires the index at `~/.local/share/ariadne/index.db`, **outside this
repo**. Left unrun on purpose: this session already touched something outside the repo once, and
that is not happening again unattended.

---

## The tools that already do this (do not write a fourth)

- `ariadne dupes` — byte-identical groups by content hash. Requires `ariadne index --deep` first.
- `humane_cannibal.py <root>` — groups dupe stems, picks a winner, **archives losers and grafts
  their unique defs into the winner as `def name__from_loser_v1`**. Never deletes. `--dry-run` is
  the default; writes require `--execute`.
- `ariadne zones` — the nesting picture, once the index is fresh.

`tools/README.md` §"Adding capabilities" is explicit: *"Do not create a sibling tool. Add a
subcommand, reuse the index, and reuse the gate."* This roadmap adds no code.

---

## Plan — read-only until step 4

1. **Settle the count discrepancy first.**
   `tools/README.md` zone table says `canon` = **65,019** files. `tools/ROADMAP.md` (2026-09-11)
   says *"ariadne zones warm: canon=30,357 files."* One is stale. `AGENTS.md` §1 says not to trust
   stale README counts, so **do not plan nesting work off either number** until one is regenerated.
   ✅ proof: `ariadne zones` — compare against both figures and note which moved.

2. **Build the index.** `ariadne index --deep` (caches duplicate hashes + Python symbols).
   Note: this writes `~/.local/share/ariadne/index.db`, outside the repo, and is incremental by
   mtime — a zone-rule change needs the db deleted and rebuilt (`tools/README.md` §Known gaps).

3. **Read the dupes.** `ariadne dupes`. Compare the group list against
   `.archive_cannibal_dryrun_20260911_0037.json` — which groups from September still exist?

4. **Re-run the cannibal with the manifest kept off the tree.**
   ```
   python3 tools/introspection/humane_cannibal.py tools \
     --dry-run --out /tmp/amend_cannibal_$(date +%Y%m%d_%H%M).json
   ```
   `--out` matters: a plain dry run drops a manifest into the scanned root — that is how
   `tools/.archive_cannibal_dryrun_20260911_0037.json` got there. Send it to `/tmp` and the tree
   stays clean, or write it to `tools/` deliberately and accept the extra artifact.

5. **Review the winner for `legacy/` by hand before executing anything.** The prior manifest picked
   `provenance/dna_tag.py` over `legacy/dna_tag_v0.py`. Confirm that choice still holds — v0.2 was
   not in that group at all, so check whether it belongs in the same one.

6. **Only then** `--execute`, which archives rather than deletes. Verify the archive landed under
   `.archive_cannibal/<timestamp>/` and that `py_compile` still passes on every surviving file.

---

## What this plan refuses to do

- **No `rm`.** `humane_cannibal`'s contract is archive + graft; `tools/README.md` and
  `tools/lookingglass/README.md` both state "archive not delete". Deletion is not on the menu.
- **No `legacy/` removal.** A nesting layer holding dead ancestors is *correct* — it is the
  archive. The problem is not that it exists; it is that nothing records which copy is live.
  A README line in `legacy/` naming the live file may be worth more than a merge.
- **No reorganisation of `projects/`.** `AGENTS.md` §4: do not add a nesting layer merely to
  organise a category, and do not move assets into `projects/whorl_ecosystem/` without a mapped
  migration plan.

---

## Open questions for the operator

1. Which canon count is current — 65,019 or 30,357?
2. Is `tools/provenance/legacy/` intended as a permanent archive (then it needs a pointer to the
   live file, not a merge) or as a holding pen (then it needs the merge)?
3. Should `.bak_v1_<date>` siblings be brought into the same dupe pass as `legacy/`?

*Untouched and unverified: nothing in this document was executed. The cannibal has not been run,
the index has not been rebuilt, and no file has been tagged.*
