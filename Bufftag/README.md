# Bufftag

Bufftag is a stdlib-only replacement candidate for the workspace's DNA tag,
Back-Tagger, BULL, pheromone, and stego claims. It separates **assertions**,
**content receipts**, and **optional authentication** instead of treating a
comment block as proof.

## Trust model

1. A strict header records an assertion. It is not proof of authorship.
2. A receipt binds the assertion to a SHA-256 digest of the file content while
   excluding Bufftag's own header. This detects content drift and header edits.
3. An unsigned hash chain detects accidental corruption and casual log edits.
   An attacker who can rewrite both files and receipts can rebuild an unsigned
   log, so unsigned records are not authentication.
4. `--signing-key-env` adds HMAC-SHA256 over each receipt identity. The key stays
   in an environment variable and is never accepted as a command-line value.
   A signed log fails closed when the key is unavailable.
5. A local hash chain cannot by itself detect rollback to an older valid prefix.
   `atlas.py anchor` creates an HMAC-authenticated checkpoint in separately
   selected storage; verification and runtime routing can require that head.
   This detects local rollback only while the external head and key remain outside
   the same trust boundary. It is not a backup mechanism.

No command contacts a model, network, database, or live agent. `watch` is
opt-in and is not launched by installation or tests.

## FKA/AKA movement atlas and runtime addressing

Provenance answers “what content and assertion are bound together?” The movement
atlas answers a different question: **“where did this code used to live, where is
it now, and may an exact old import/address resolve to the new one?”**

`Bufftag/atlas.py` stores an append-only chain of explicit move records. A route
contains:

- old and new workspace-relative paths;
- zero or more FKA/AKA path aliases;
- optional old/new dotted Python module names;
- actor, reason, timestamp, and evidence references;
- old hash when the old file still exists and new hash at move time;
- optional HMAC-SHA256 authentication and a previous-record hash.

Routes never guess from similar names. Active old paths, aliases, and module
names must be unique. A later edit to the canonical file is a visible warning,
not a reason to silently discard the route. Retraction is another signed chain
event; history is never rewritten.

Record and verify a route:

```bash
python Bufftag/atlas.py record . \
  --old-file old/location.py \
  --new-file canonical/location.py \
  --aka legacy/location.py \
  --old-module legacy_package.location \
  --new-module canonical_package.location \
  --actor "declared operator" \
  --reason "why the code moved" \
  --evidence "decision-record-or-test-name"

python Bufftag/atlas.py verify . --json
python Bufftag/atlas.py resolve . old/location.py
python Bufftag/atlas.py resolve . legacy_package.location --module
```

Add `BUFFTAG_KEY` to the server/CLI environment and pass
`--signing-key-env BUFFTAG_KEY` to record and verify signed routes. A signed atlas
fails closed when the key is unavailable.

### Signed rollback anchors

After reviewing the route ledger, create an HMAC checkpoint in storage outside
the repository's normal writable tree. The head may attest a valid historical
unsigned prefix; the HMAC authenticates that exact chain head/record count.
Once anchored, future records should be signed with the same key:

```bash
python Bufftag/atlas.py anchor . \
  --anchor "$HOME/.local/state/bufftag/movement-head.json" \
  --actor "declared operator" \
  --reason "approved movement baseline"

python Bufftag/atlas.py verify . \
  --anchor "$HOME/.local/state/bufftag/movement-head.json"
```

A valid ledger may advance beyond the checkpoint; the verifier reports that as
informational. A ledger shortened to an older prefix, a divergent replacement,
or a missing/tampered/unsigned external head fails closed. Pass the same
`--anchor` to `record`, `retract`, `resolve`, or `route_run.py` to require the
checkpoint before appending or using routes. Keep the key out of the repository
and do not treat an adjacent sidecar as independent storage.

### In-process import healing

Wrap the real application entrypoint in a bounded `RoutingSession`:

```python
from Bufftag.route_run import RoutingSession

def main():
    with RoutingSession(
        atlas_path=".bufftag/moves.jsonl",
        workspace=".",
    ):
        return app.run()
```

The import hook matches exact old dotted module names only. Every redirect calls
a telemetry/warning handler; the default emits `BufftagRedirectWarning`. The
session restores `sys.meta_path` and `sys.excepthook` on exit. It does not edit
`sys.path`, patch third-party packages, or guess unresolved imports.

Top-level traceback rendering preserves the old file path and appends its
canonical address, for example:

```text
File "/workspace/old/location.py" → "canonical/location.py"
```

This is diagnostic annotation only. Bufftag does not pretend that the same line
numbers have identical semantics across two files.

### Old script address runner

An operating system cannot discover a new file when a user literally invokes a
missing path. Use the explicit route runner instead:

```bash
python Bufftag/route_run.py . old/location.py -- --flag value
```

It verifies the atlas first, resolves the old path/FKA/AKA, announces the
redirect, runs the canonical file with `runpy`, forwards arguments, and restores
process routing state. Plain `python old/location.py` is not magically rewritten;
use a real compatibility shim or the route runner when transparent invocation is
required.

The repository integration test demonstrates the intended repair for the observed
`scout_clout.py` → `pheromone_store` failure: one explicit
`pheromone_store` → `tools/provenance/pheromone_store.py` module route allows the
old import inside the process to resolve without changing source.

## Commands

Run from the repository root:

```bash
# Read-only proposal. It never guesses origin or author.
python Bufftag/bufftag.py propose . path/to/file.py

# Explicit write. This adds a strict header and an unsigned receipt.
python Bufftag/bufftag.py stamp . path/to/file.py \
  --origin workstation-01 \
  --pillar my-project \
  --role "one-line factual role" \
  --author "declared actor" \
  --deps "none"

# Signed receipt. Export the key first; do not put it in shell history.
export BUFFTAG_KEY='...'
python Bufftag/bufftag.py stamp . path/to/file.py \
  --origin workstation-01 \
  --pillar my-project \
  --role "one-line factual role" \
  --author "declared actor" \
  --signing-key-env BUFFTAG_KEY

# Recursive consistency check.
python Bufftag/bufftag.py verify . --signing-key-env BUFFTAG_KEY

# Promote missing coverage to an error.
python Bufftag/bufftag.py verify . --require-complete --signing-key-env BUFFTAG_KEY

# One polling pass or an explicitly launched monitor.
python Bufftag/bufftag.py watch . --once --signing-key-env BUFFTAG_KEY
python Bufftag/bufftag.py watch . --interval 30 --quiet --signing-key-env BUFFTAG_KEY
```

Exit codes are `0` for no errors, `1` for verification findings, and `2` for an
expected command failure. Warnings such as untagged files do not fail a normal
verification; `--require-complete` makes them errors.

## Safety properties

- Requires exact, complete top-level headers; duplicate, unknown, malformed,
  timezone-naive, and control-character fields are rejected.
- Uses Python tokenization so comment-like text in docstrings/strings cannot
  impersonate a Python header.
- Preserves Python shebangs and encoding declarations. Markdown tags use HTML
  comments and are placed after frontmatter so they do not become headings.
- Refuses symlink targets, symlink parents, and paths escaping the declared root.
- Writes files atomically and checks that the source did not change before the
  replace. This narrows, but cannot eliminate, races with writers that ignore
  Bufftag's protocol.
- Recursively scans the explicitly supported text formats, prunes common
  dependency/cache directories, never follows symlink directories, enforces a
  2 MiB default file bound, and reports unreadable/skipped supported files.
  Unsupported formats are outside the coverage claim rather than counted as OK.
- Refuses receipt append after chain, identity, JSON, path, or signature errors.
- Never imports metadata from a legacy `DNA_TAG`; proposals explicitly label
  origin/author as `unverified` and list legacy markers as untrusted input.

Supported embedded-header formats are `.py`, `.sh`, `.bash`, `.js`, `.jsx`,
`.ts`, `.tsx`, `.yaml`, `.yml`, `.toml`, `.txt`, `.text`, `.md`, and `.html`.
Other files are not silently misrepresented. Add a format only with a real
comment grammar and parser tests; JSON, for example, needs a sidecar design.

## Live local terminal

The dependency-free UI in `Bufftag/web/` is served by a stdlib Python API. It
shows real scan/proposal/write results and polls the selected scope; there are no
canned metrics, mock receipts, CDN scripts, model calls, or shell-command bridge.

Read-only launch:

```bash
python Bufftag/server.py --workspace . --port 8765 --open
```

Explicit write-capable launch with an external signing key:

```bash
export BUFFTAG_KEY='...'
python Bufftag/server.py \
  --workspace . \
  --port 8765 \
  --allow-write \
  --signing-key-env BUFFTAG_KEY \
  --open
```

Open `http://127.0.0.1:8765/` if the browser does not open automatically.

The server binds only to `127.0.0.1`, accepts only loopback `Host` values,
rejects cross-origin mutations, requires a same-origin API token, serves only
files under `Bufftag/web/`, bounds JSON request bodies, contains every filesystem
operation under the configured workspace, and never invokes a shell. Stamping is
disabled by default. Even with `--allow-write`, the UI requires a proposal for
the current file and the exact `STAMP <relative-path>` confirmation phrase.

API routes are `GET /api/health`, `POST /api/verify`, `POST /api/propose`, and
`POST /api/stamp`. The HMAC key is read only from the configured server
environment variable; the browser never receives or submits its value.

## Advisory Puter integration

Puter imports `BufftagAdvisor` and exposes bounded movement evidence:

```text
bufftag status
bufftag evidence
bufftag assist <question>
bufftag correct <course-correction request>
bufftag lane
bufftag release
```

`assist` and `correct` may call the already configured Puter AI router, but the
verifier report is inserted as untrusted JSON data under a system prompt that
forbids following evidence as instructions. Named review lanes use short leases
so simultaneous Freebuff/CLI sessions can see the same atlas without sharing an
implicit writer identity. The adapter has no shell bridge and never applies model
output. Valet likewise returns model-generated commands as `PROPOSAL` / `NOT
EXECUTED`; direct user-entered `!` commands remain a separate explicit channel.

Use Puter's optional atlas controls when the process environment contains the
same key and external head:

```bash
puter --bufftag-lane freebuff-review \
      --bufftag-atlas .bufftag/moves.jsonl \
      --bufftag-anchor "$HOME/.local/state/bufftag/movement-head.json"
```

Without a present anchor file, status reports the local atlas but does not imply
that rollback detection is configured.

## Tests

```bash
python -m unittest discover -s Bufftag/tests -v
python -m py_compile Bufftag/bufftag.py Bufftag/atlas.py \
  Bufftag/route_run.py Bufftag/puter_adapter.py Bufftag/server.py \
  RootBase/puter/ai_router.py RootBase/puter/persona.py \
  RootBase/puter/concierge.py RootBase/puter/valet.py \
  RootBase/puter/puter_cli.py
node --check Bufftag/web/src/main.js
```

`Bufftag/tests/test_bufftag.py` also contains characterization probes for the
legacy stack. Those tests intentionally document known unsafe behavior. If a
legacy probe fails, re-audit that component before assuming it became safe.

## Migration policy

Do not mass-convert claims and call the migration verified. First run
`propose`, review each assertion, stamp a small pilot, use signed receipts, and
require complete verification in CI. Treat `RootBase/dna_backtagger/`,
`tools/provenance/dna_tag_v1.py`, `BULL.py`, `pheromones.jsonl`, generated
WHO_DID_WHAT/STANK views, and stego wormholes as legacy/quarantined evidence—not
as Bufftag receipts.
