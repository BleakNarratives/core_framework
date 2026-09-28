# BUNNYSPACE — DNA Back-Tagger Red-Team Audit

**Audit date:** 2026-09-25  
**Repository root:** `/home/bleaknarratives`  
**Branch at session start:** `feature/ribbon-animation`  
**Scope:** legacy Back-Tagger, DNA_TAG variants, BULL, PheromoneStore/schema and
callers, pheromone ledgers/views, CAPS stego, HOP/BULL/provenance claims, and the
new `Bufftag/` replacement.  
**Method:** local source inspection plus deterministic, offline tests. No model,
network, live database, package install, persistent monitor, or external service
was used.

## Verdict

The existing stack is **not rigorous provenance and should not be used as
evidence that a file, author, dependency, or prior action is genuine**.

The strongest concrete problem is not cosmetic. A file can receive a valid-looking
DNA header by saying `[DNA_TAG]` in ordinary text, and the tag does not bind to
file content at all. BULL can report `Clean` after omitting most directories.
The pheromone ledger accepts schema-invalid records and has a release race. The
stego layer is intentionally hidden from scanners and has no integrity signal.
The original Back-Tagger output map includes literal unexpanded placeholders.

This establishes false-assurance and drift risk in the artifacts. It does **not**
establish Gemini's, Qwen's, or another agent's subjective intent. Code and logs
cannot prove motive; they can prove that the claims and controls do not support
the conclusions made from them.

A separate replacement candidate now exists at `Bufftag/`. It has strict header
parsing, atomic bounded writes, symlink refusal, content receipts, an append-only
hash chain, optional HMAC authentication, recursive drift checks, and an opt-in
watch mode. It deliberately does not import claims from legacy DNA headers.

## Active and legacy components found

| Component | Observed role | Trust verdict |
|---|---|---|
| `RootBase/dna_backtagger/dna_engine.py` | Moto-era hardcoded tagger/scanner | Prototype; unsafe mass-write CLI |
| `RootBase/dna_backtagger/tagger_parser.py` | Hardcoded Android-storage scanner | Prototype; no validation or safety |
| `RootBase/dna_backtagger/dna_parser.py` | Regex metadata extractor | Decoy-prone; no authenticity |
| `RootBase/dna_backtagger/moto_bn_only_engine.py` | Hardcoded global scanner | Prototype; stale target paths |
| `RootBase/dna_backtagger/dna_ecosystem_map.json` | Three-record generated map | Invalid as evidence; contains `{origin}` etc. |
| `tools/provenance/dna_tag_v1.py` | Interactive/current DNA writer lineage | Substring parser and unsafe placement |
| `BULL.py` | Pillar drift reporter/fixer | False-clean scope and unaudited “fix” claim |
| `tools/provenance/pheromone_store.py` | JSONL event and claim ledger | Concurrency/schema/authentication gaps |
| `pheromones.jsonl*` | Historic event/receipt-shaped files | Unauthenticated evidence, not proof |
| `tools/provenance/caps_stego.py` | Case-bit path concealment | Deliberately scanner-opaque; not provenance |
| `tools/provenance/decay_sweep.py` | Expired ghost detector | Does not consume its declared pheromone ledger |
| `HOP_PROTOCOL.md`, `WHO_DID_WHAT*.md`, `PROVENANCE.md` | Operational claims/ledgers | Useful intent/history, not verification |

## Findings

### Critical

#### 1. “DNA” headers are self-asserted comments with no content binding

The legacy `has_tag()` logic searches for the substring `[DNA_TAG]`, while BULL
searches the first `PILLAR:` line near the top of a file. Neither format includes
a file digest, receipt identifier, signature, or verifier reference. Changing
the code does not stale the DNA tag.

The old Moto back-tagger files carry their supposed headers **inside module
docstrings**, and their parser deliberately extracts `# [DNA_TAG]` from the first
4096 bytes. Its checked-in map consequently records its own template values:

```json
"ORIGIN": "{origin}",
"PILLAR": "{pillar}",
"ROLE": "{role}",
"LAST_SYNC": "{timestamp}"
```

**Evidence:** `RootBase/dna_backtagger/dna_ecosystem_map.json:3-19`;  
`test_checked_in_ecosystem_map_contains_literal_placeholders` passes.

**Impact:** coverage, authorship, role, and sync claims can survive complete
content replacement. A scanner that reports coverage is measuring comments, not
identity or integrity.

#### 2. Parser decoys can forge metadata

Legacy `dna_parser.extract_dna_header()` accepts a marker in a docstring. The
Bufftag characterization fixture creates a normal Python docstring containing a
legacy tag and the parser returns `ORIGIN: forged`.

**Evidence:** `test_legacy_parser_accepts_a_docstring_decoy` passes.

**Impact:** quoted examples, audit reports, and attacker-controlled source text
can impersonate provenance. Regex proximity does not establish that a block is
an operative header.

#### 3. BULL can falsely report `Clean` while omitting files

`BULL.iter_scan_dirs()` only yields a hard-coded subset of top-level home
directories and scans only `*.py` directly inside each yielded directory. It
does not recursively scan project trees, does not report unmapped directories,
and its `unknown-dir` branch is unreachable for those omitted paths. Its `bin`
special case is not yielded by the iterator.

A temporary project with `unmapped/deep/orphan.py` receives exit code `0` and a
`Clean` message.

**Evidence:** `BULL.py:145-155,174-230`;  
`test_bull_reports_clean_while_omitting_an_unmapped_directory` passes.

**Impact:** “filesystem mirrors the DNA tags” and “no strays” are unsupported.
A clean result means only that selected top-level files in selected directories
matched selected pillar rules.

#### 4. Pheromone claims are unauthenticated and schema-invalid input is accepted

`pheromone_schema.md` says strength is `0.0–1.0`, but `PheromoneStore.emit()`
does not validate strength, decay rate, source, payload shape, timestamp, or
event identity. The probe successfully stores `strength=99.0` and
`decay_rate=-7.0`.

The JSONL log has no record hash chain or signature. Corrupt lines are skipped
after a stdout warning, so a machine consumer can silently operate on a partial
view. Historic `pheromones.jsonl.receipts.jsonl` rows only map spotting IDs to
bus message IDs; they do not sign content or event payloads.

**Evidence:** `pheromone_schema.md:25-36`,
`tools/provenance/pheromone_store.py:83-128`;  
`test_pheromone_emit_accepts_schema_violating_strength` passes.

**Impact:** “trace/receipt log” and “one real source of truth” are storage
descriptions, not integrity or authenticity claims. An agent can write plausible
events into the same authority boundary it is later judged by.

### High

#### 5. Task release has a check-then-append race

`claim_task()` uses `flock`, but `release_task()` performs its ownership check
and release append without the same lock. It also chooses the latest event by
timestamp instead of append position. A stale owner can pass the check, another
agent can claim after expiry, and the stale owner's release can then become the
latest event.

The offline probe recreates exactly that interleaving and ends with
`latest_task_event() == TASK_RELEASE` from `old-agent`.

**Evidence:** `tools/provenance/pheromone_store.py:145-200`;  
`test_pheromone_release_race_can_release_a_new_claim` passes.

**Impact:** “double-claim prevention” is not established for the full
claim/release lifecycle.

#### 6. The current DNA writer can break direct executability

The writer prepends the complete tag before existing content. A shebang must be
the first bytes for direct Unix execution, but the characterization probe proves
the resulting file no longer starts with `#!`. This contradicts the workspace
cheat-sheet's own shebang rule.

**Evidence:** `tools/provenance/dna_tag_v1.py:91-95`;
`test_legacy_stamp_breaks_shebang_placement` passes.

**Impact:** a provenance write can turn a working script into one that must be
invoked through `python` rather than directly.

#### 7. `bull fix --go` prints an audit claim without writing an audit artifact

After changing a PILLAR, BULL prints `HOP_LOG: fix logged <date>` but performs no
HOP log write. The temporary-directory probe confirms the output contains the
claim and no HOP_LOG artifact exists.

**Evidence:** `BULL.py:237-270`;  
`test_bull_claims_an_hop_log_but_writes_none` passes.

**Impact:** the tool creates a false audit signal precisely when a consequential
write occurs. A log-shaped sentence is not an audit record.

#### 8. CAPS is intentional evidence suppression, not integrity

CAPS encodes a path in letter case and its own guide says ordinary grep and
graph scanners do not see the forward. There is no MAC, digest, signature, or
length frame. A one-letter case flip changes the decoded path. The library-level
`check(path)` with no expected value treats any non-empty decode—including
replacement-corrupted bytes—as `ok`.

**Evidence:** `tools/provenance/CAPS_HYGIENE.md:21-35`,
`tools/provenance/caps_stego.py:85-178`;  
`test_caps_codec_has_no_integrity_failure_signal` passes.

**Impact:** CAPS may be useful for a bounded private migration trick, but it must
never feed provenance, graph completeness, public hygiene, or audit claims. The
phrase “graph honest” is contradicted by the documented fact that the graph
cannot see the dependency.

### Medium

#### 9. The “semantic” back-tagger has four divergent implementations

`dna_engine.py`, `tagger_parser.py`, `dna_parser.py`, and
`moto_bn_only_engine.py` duplicate a regex and metadata parser with different
suffix sets, error handling, paths, and write behavior. None accepts a test root
argument. The only active-looking `dna_engine.py` main hardcodes
`/storage/emulated/0/BleakNarratives`, auto-tags every discovered Python file
with generic metadata, and overwrites the map.

**Impact:** there is no single executable contract, and running the “engine” is
a mass mutation rather than a parser.

#### 10. The documented scout integration is broken from the repository root

`projects/agents/scouts/scout_clout.py` imports top-level `pheromone_store`, but
the canonical file is now `tools/provenance/pheromone_store.py` and no root
`pheromone_store.py` exists. The direct command fails before argument handling.

**Evidence:** `python projects/agents/scouts/scout_clout.py` exits `1` with
`ModuleNotFoundError: No module named 'pheromone_store'`.

**Impact:** “emits real pheromones” and “working scout” are not currently
reproducible through the documented path.

#### 11. Decay and ledger claims are disconnected

`pheromone_schema.md` says STANK and WHO_DID_WHAT are generated views.
`pheromone_store.py` can regenerate them, but no `pheromone_views.py` exists as
promised, generated WDW overwrites a file described elsewhere as append-only,
and agent-controlled descriptions can inject new Markdown lines.
`decay_sweep.py` defines `LEDGER = HOME / "pheromones.jsonl"` but never reads it;
it only searches for textual ghost markers and a `decays` date.

**Impact:** the logs can be simultaneously described as append-only truth,
overwritable generated views, and unused by the decay sweeper.

#### 12. Registry and handoff claims are stale or overconnected

- `PROVENANCE.md` lists `Back-Tagger/`, which does not exist; the code is under
  `RootBase/dna_backtagger/`.
- `CLAUDE.md`, `index_readme.md`, and `canonical_state.json` claim a connection
  to `RootBase/dna_sweep.py`, but no such implementation was found in the
  checked-out tree; only prose references were found.
- `WHO_DID_WHAT` and HOP documents call hops “PROVEN” based on compile/decode/
  visibility checks, but those checks do not test content provenance, graph
  completeness, release safety, or resistance to tampering.
- `pheromone_schema.md` mentions companion `pheromone_views.py`; it is absent.

**Impact:** canonical-state and contribution documents should be treated as
historical claims requiring re-verification, not executable architecture.

#### 13. `visor-view` has a wider trust boundary than its CLI implies

CAPS `visor_view()` mutates `sys.path`, dynamically imports code from the user's
home directory, catches broad exceptions, and ignores its `visor_dir` argument.
It does not use the `ok` result from `Visor.may()` as the final decision.

**Impact:** this is local policy visualization, not a safe provenance verifier.
It should not be in the trust path of a scanner or gate.

## What actually stands up

- The legacy parsers can extract simple key/value comments from clean fixtures.
- `claim_task()` serializes its read-check-append section on one POSIX host when
  all contenders use that function and the store file.
- `DirectoryWatcher` can notice file hash changes and emits created/modified/deleted
  observations, though its 64-bit truncated hashes are suitable only as quick
  change hints.
- The workspace contains enough documentation to identify intended invariants;
  the problem is that enforcement and claims are stronger than implementation.
- The new Bufftag candidate passes its offline unit, integration, tamper, scope,
  and legacy-characterization tests. That establishes tested behavior for the
  covered cases, not universal authorship proof or deployment security.

## Bufftag replacement design

`Bufftag/bufftag.py` is intentionally separate from the Gemini/Qwen-era
lineage. It uses only the Python standard library.

### Strict assertions

The exact top-level header has six required single-line fields: `author`, `deps`,
`origin`, `pillar`, `recorded_at`, and `role`. Duplicate, unknown, malformed,
timezone-naive, overlong, and control-character fields fail closed. Python tags
must be real tokenizer comments, not strings. Markdown uses HTML comments after
frontmatter. Shebang and encoding declarations retain their required positions.

### Content receipts

A receipt binds the relative path, exact metadata, and SHA-256 of file content
excluding Bufftag's own header. This catches body drift, metadata edits, header
removal for receipted files, missing files, and legacy coverage claims.

Receipts form an append-only hash chain. The writer refuses to append after any
JSON, identity, path, chain, or signature error. The implementation uses
`flock`, `fsync`, same-directory atomic replacement, bounded reads, strict UTF-8,
symlink refusal, root containment, and a pre-replace source-change check.

### Authentication and its limit

`--signing-key-env` applies HMAC-SHA256 to the canonical receipt identity. A
signed log without its key fails verification. Unsigned logs say so and are not
presented as authenticated.

A hash chain still cannot detect a complete rollback to an older valid prefix.
For high-value claims, periodically export the chain head/signed checkpoint to
separate durable storage. A signature also does not prove the declared human or
agent identity; that requires an external key registry and governance process.

### Propose versus stamp

`propose` can extract a Python docstring summary and top-level imports, but it
sets origin and author to `unverified` and emits warnings. `stamp` requires the
operator to provide origin, role, and author explicitly. Legacy tags are never
copied into new assertions.

### Monitoring

`watch --once` is a deterministic single pass. Continuous `watch` is available
but was not launched. `--quiet` suppresses unchanged passes after the initial
report. Scope pruning and unsupported files are explicit; there is no
“everything is clean” fallback for omitted data.

## Test evidence

Commands actually run from `/home/bleaknarratives`:

```bash
python -m unittest discover -s Bufftag/tests -v
# PASS: 77 tests in 1.885s; result OK

python -m unittest discover -s Bufftag/tests -p 'test_atlas.py' -v
# PASS: 21 atlas/anchor/runtime tests in 0.066s; result OK

python -m unittest discover -s Bufftag/tests -p 'test_puter*.py' -v
# PASS: 13 Puter adapter/integration tests in 0.051s; result OK

python -m py_compile Bufftag/bufftag.py Bufftag/atlas.py \
  Bufftag/route_run.py Bufftag/puter_adapter.py Bufftag/server.py \
  RootBase/puter/ai_router.py RootBase/puter/persona.py \
  RootBase/puter/concierge.py RootBase/puter/valet.py \
  RootBase/puter/puter_cli.py projects/agents/scouts/scout_clout.py
# PASS: exit 0, no output

python RootBase/puter/puter_cli.py --help
# PASS: exit 0; advertises --bufftag-lane, --bufftag-atlas, and
# --bufftag-anchor without initializing provider or state services

python Bufftag/atlas.py verify . --json --signing-key-env ''
# PASS: exit 0; files_scanned=3, receipt_count=5, findings=[], ok=true

# In a bounded RoutingSession, exact legacy imports resolved to:
# dna_tag -> tools/provenance/dna_tag_v1.py
# pheromone_store -> tools/provenance/pheromone_store.py
# Both emitted BufftagRedirectWarning on stderr.

node --check Bufftag/web/src/main.js
# PASS: exit 0, no output

# Earlier in this session, before the rollback/Pputer batch:
# Real loopback server smoke on 127.0.0.1:18765 passed with
# health=bufftag-local, writes=False, html_bytes=9157.
# Its temporary log was deleted with user approval.

python -m unittest discover -s tests -v
# PASS: 406 tests in 21.859s; result OK
```

The Bufftag command includes eight legacy characterization probes. They pass by
observing the current unsafe behavior; they are not endorsements. If one fails,
re-audit the old component rather than automatically declaring it fixed.

The full repository suite passed. No persistent monitor was started.

## Migration recommendation

1. **Quarantine claims, not files.** Keep legacy code and ledgers for history,
   but mark their output `UNVERIFIED LEGACY` in dashboards and agent prompts.
2. **Pilot Bufftag.** Run `propose` on one small project, review every field,
   stamp signed receipts, then require complete verification in CI.
3. **Separate authorship from authorship claims.** Bufftag records what a
   declared actor asserted; key custody and external identity remain separate.
4. **Remove BULL's clean language.** Until replaced, report “selected checks
   passed” plus files/directories skipped. Never suppress phantom audit claims.
5. **Fix or retire PheromoneStore before reuse.** Validate all fields, lock the
   full claim/release transaction, use append order, add a hash chain, and define
   rollback/key policy. Keep generated views outside the authority boundary.
6. **Quarantine CAPS from provenance and graphs.** If retained for a private
   migration, use an expiring explicit redirect manifest and test both low- and
   high-trust views. Do not describe hidden edges as graph-honest.
7. **Repair imports and registries last.** Make one canonical import path and one
   registry entry, but do not call the system integrated until the safe verifier
   passes from a clean process with no special `PYTHONPATH`.
8. **Red-team with mutation, not rhetoric.** Require fixtures for decoy tags,
   duplicate fields, Unicode/control characters, CRLF, frontmatter, shebangs,
   symlinks, path escape, concurrent write, rollback, corrupt/truncated logs,
   missing key, wrong key, hidden directories, and generated-view injection.

## Viable replacement: live terminal plus code movement atlas

The replacement now has two deliberately separate planes.

### Provenance plane

`Bufftag/bufftag.py` and `Bufftag/server.py` expose live local verification,
read-only proposals, and explicitly gated atomic stamping. `Bufftag/web/` is a
real terminal, not a static mock: every metric and finding comes from the local
API, the monitor polls actual files, and write controls remain closed unless the
server starts with `--allow-write` and the operator supplies the exact
`STAMP <path>` phrase. The server binds only to loopback and blocks cross-origin
mutation, host rebinding, path escape, traversal, and oversized bodies.

### Code-postal plane

`Bufftag/atlas.py` is the FKA/AKA movement index. It records old/new paths,
aliases, optional old/new Python module names, reason, actor, evidence, move-time
hashes, and optional HMAC signatures in an append-only chain. `route_run.py`
uses only explicit routes to:

1. resolve an exact old dotted import during a bounded process session;
2. emit a visible `BufftagRedirectWarning`/telemetry callback;
3. launch a canonical script from an old path/FKA/AKA with forwarded arguments;
4. annotate old file paths in top-level tracebacks with their new addresses; and
5. restore import/traceback hooks after the scope.

It does not guess from filename similarity, mutate `sys.path`, rewrite caller
source, or pretend that plain `python old/file.py` can discover a file that no
longer exists. Use `route_run.py` or an explicit compatibility shim for that case.

The repository integration test proves the concept against a real observed
failure: an explicit `pheromone_store` →
`tools/provenance/pheromone_store.py` module route lets
`projects.agents.scouts.scout_clout` import its store in-process. This repairs
that edge only while the routing session is installed; it does not certify the
rest of the legacy stack.

## Rollback anchors and Puter course correction

The movement atlas now has an explicit rollback control that does not pretend a
local hash chain can detect replacement by an older valid prefix. `anchor` writes
an HMAC-SHA256 checkpoint containing the ledger record count and chain head to a
separately selected file. Verification accepts a ledger that has advanced past
the checkpoint, but rejects a missing, unsigned, tampered, divergent, or
rolled-back ledger. `route_run.py` and `RoutingSession` can require that anchor
before installing any redirect.

The anchor is not a backup and does not repair a rolled-back ledger. An attacker
who controls both the ledger and its separately stored head can replace both.
The head therefore needs storage outside the repository's normal writable trust
boundary and an independently controlled signing key. `BUFFTAG_KEY` was not set
in the audit environment, so no production anchor or secret was fabricated.

Puter now consumes Bufftag's bounded report through
`Bufftag/puter_adapter.py`. `bufftag status` and `bufftag evidence` are local;
`bufftag assist` and `bufftag correct` ask the configured AI router for an
advisory response over evidence explicitly marked untrusted. A short, HMAC-aware
review lease coordinates named lanes across simultaneous sessions. The adapter
has no shell/subprocess bridge, parses no model command for execution, and
returns `executed_actions: []`.

The integration also corrects two unsafe Puter claims:

- Valet now labels model-generated commands as `PROPOSAL` / `NOT EXECUTED` and
  includes risks and rollback steps. Directly user-entered `!` commands retain
  their existing explicit-command behavior.
- Provider status reports only `SET` / `NOT SET`; it no longer renders the first
  eight characters of any API key.

## Moving-tree audit after implementation

A fresh source search and filesystem inventory found:

- `RootBase/dna_backtagger/` still contains four divergent Moto-era engines and
  a placeholder-filled ecosystem map. Three engines still hardcode
  `/storage/emulated/0/BleakNarratives`; the parser also hardcodes a
  `Back-Tagger` output path that does not exist.
- `tools/provenance/dna_tag.py` is currently absent while
  `tools/provenance/dna_tag_v1.py` is untracked. Multiple cheat sheets, examples,
  and taggers still name the missing `dna_tag.py`. These are stale caller/docs
  candidates, not evidence that the files were equivalent.
- The canonical `tools/provenance/pheromone_store.py` exists and
  `projects/agents/scouts/scout_clout.py` now imports it by its canonical module
  path. The earlier direct-run `ModuleNotFoundError` is therefore repaired; the
  legacy top-level module route remains useful only for external historical
  callers and must be recorded explicitly.
- The earlier parent-repository search missed nested-repository files.
  `RootBase/dna_sweep.py` does exist inside the separate RootBase Git repository,
  but it is currently untracked there. It hardcodes `$HOME/RootBase`, shells out to
  `find`, regex-substring parses DNA tags, and offers an auto-tag mode. It is a live
  legacy mutation tool, not missing functionality and not Bufftag evidence.
- The Puter launcher now derives its repository location from
  `${PUTER_HOME:-$HOME/RootBase}` rather than a hardcoded `/home/bleaknarratives`
  path. Puter itself still has no checked-in tests outside the new Bufftag
  policy fixtures, and its model-facing chat/context path remains a prompt-injection
  risk that advisory mode does not magically solve.

Three explicit production routes are now recorded in `.bufftag/moves.jsonl`:
`dna_tag` plus the historical `tools/provenance/dna_tag.py` alias to
`dna_tag_v1.py`; top-level `pheromone_store` to
`tools/provenance/pheromone_store.py`; and old `scout_clout.py` to
`projects/agents/scouts/scout_clout.py`. The first draft of the DNA route was
retracted after runtime verification showed that a differing `new_module` would
require `tools/provenance` to be an import package root; the replacement keeps
the exact legacy module name and loads the current file directly. The resulting
ledger has five records (three active routes, one retraction, one replacement
route), and offline verification reports `ok: true` for three targets.

These records are currently unsigned because `BUFFTAG_KEY` was not set. A later
HMAC external head may attest the complete valid historical prefix; subsequent
records should then be signed. No secret was generated or stored in the project.
The safe next action is to set the operator-controlled key, review the three
routes, and write the signed head outside the repository.

## Whorl solidarity pass — 2026-09-25

The selected Whorl security, bridge, runtime, host-conformance, and bounded
capability workstreams were implemented in the nested `Whorl/` repository. This
section records the boundary; it does not claim that the separate Claude/Qwenbuff/
Bufftag convergence is complete.

### Delivered and locally testable

- `Whorl/whorl/runtime.py` treats model output as untrusted proposal data and
  exposes strict proposal compilation, observation-only handling, host profiles,
  approval leases, structured execution receipts, and one-time lease replay
  protection. Receipt persistence is opt-in through an injected JSONL path.
- `Whorl/whorl/bridge/__init__.py` and the CLI now share the explicit remote-bind
  opt-in, validate loopback `Host`/port-matched `Origin`, cap JSON bodies at
  1 MiB, and return client errors for malformed/oversized bodies. The bridge
  exposes `/runtime/observe`; it has no proposal-execution route.
- `Whorl/whorl/host_profiles.py` provides offline Termux, Crostini, and Windows
  PowerShell profiles. PowerShell has no network capability by declaration.
- `BoundedContextMultiplier` is bounded context fan-out only, and
  `whorl_easter_egg()` is a side-effect-free discovery string. Neither can grant
  capabilities, approve effects, or execute commands.

### Evidence

```text
cd Whorl && python -m unittest tests.test_agent_runtime tests.test_runtime_bridge -v
# PASS: 20 tests, OK

cd Whorl && python -m unittest tests.test_security_redteam tests.test_agent_runtime tests.test_host_profiles tests.test_runtime_bridge -v
# PASS: 24 tests, OK

cd Whorl && python -m py_compile whorl/runtime.py whorl/bridge/__init__.py whorl/cli/__init__.py whorl/cli/core.py tests/test_agent_runtime.py tests/test_runtime_bridge.py
# PASS: exit 0
```

The final full Whorl suite, `git diff --check`, and both repository status
reviews remain pending. Existing parent and nested-Whorl modifications were
preserved; no reset, clean, move, delete, commit, push, or external convergence
ingest was performed.

### Deliberately unresolved

- The bridge remains local/loopback-first and has no authentication token. A
  remote bind is an explicit operator opt-in, not a safe default deployment.
- DNS-rebinding validation is now enforced at the HTTP Host boundary, but the
  Scout network probe still does not pin a validated DNS IP through connection
  establishment.
- No signing key or secret was invented. Bufftag's unsigned local movement
  ledger and the proposed Claude/Qwenbuff/Bufftag convergence therefore remain
  a separate, evidence-required follow-up rather than an implicit merge.
- Live Termux, Crostini, and Windows hosts were unavailable; only offline
  profile/conformance tests were run.


- `.bufftag/moves.jsonl` is currently a valid **unsigned** five-record ledger.
  `BUFFTAG_KEY` was not set, so no production HMAC anchor exists and rollback
  detection is not yet active. This is expected, not a clean-authentication claim.
- Puter lives in the separate nested `RootBase` repository, currently
  `master...origin/master [ahead 1]`. The six Puter files changed here are local
  modifications in that nested repository and will not be included in a commit of
  the parent repository. RootBase also had many unrelated pre-existing changes;
  none were reset or staged.
- `tools/provenance/dna_tag.py` existed during the initial inventory and source
  inspection, then disappeared before the first Bufftag test import completed.
  Bufftag did not delete or rename it. The current tree must be re-checked before
  any migration or attribution decision. The surviving characterization test
  uses `dna_tag_v1.py`, whose relevant write behavior is the same.
- The pre-existing working tree had unrelated modified files at session start.
  Bufftag did not reset, clean, move, or overwrite them.
- The binary `Semantic DNA Back-Tagging Engine - Google Gemini.pdf` was not used
  as executable evidence. `PROVENANCE.md` itself classifies the paper UNKNOWN and
  says authorship must be verified before publication.
- A test passing means its fixture is handled as specified. It does not turn an
  unsigned local assertion into externally verified truth.
