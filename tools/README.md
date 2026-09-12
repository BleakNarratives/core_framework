# tools/ — the introspection and boundary layer

Two tools that fix the root cause of this tree being unnavigable and unsafe to
send anywhere. Read this before adding a third.

## The problem both tools solve

Every earlier tool here (codemap, fartographer, triage, the boardroom) re-scanned
the whole 53 GB tree on every run. That is why they choked and why every map
became unusable. Separately, the tree contains live credentials inside files that
look like transcripts, which is why GitHub push protection blocked pushes and why
Google revoked four API keys as "leaked."

One tool fixes speed. The other fixes exposure.

---

## `tools/introspection/ariadne.py` — the index

Indexes the tree **once** into SQLite, then answers instantly.

```bash
ariadne index --deep    # build/refresh (also hashes dupes + indexes symbols)
ariadne zones           # signal vs noise: file counts by zone
ariadne find <pattern>  # instant path search
ariadne where <symbol>  # find a definition
ariadne what <path>     # explain a file; flags byte-identical copies
ariadne dupes           # redundant copies
ariadne broken          # files that do not parse, canon zone only
ariadne tour            # guided orientation
```

Index: `~/.local/share/ariadne/index.db` · Root override: `ARIADNE_ROOT`

### Zones — the core idea

The tree mixes recovered dumps with your real work. Every file gets a zone so you
can exclude noise instead of drowning in it.

| zone | what | files |
|---|---|---|
| `vendor` | node_modules, venv, site-packages | 474,478 |
| `recovery` | recovery_staged, _archive, GRAVEYARD | 70,154 |
| **`canon`** | **your actual projects** | **65,019** |
| `cache` | `__pycache__`, `*.pyc` | 23,306 |
| `intake` | NAT-Recovery-Kernel/intake dumps | 7,604 |
| `app` | top-level dot-dirs (`.local`, `.config`, `.codex`) | — |

**Measured:** the first query took 0.07 s. The same search as a plain `grep`
timed out at 180 s. Indexing 640,566 files takes ~4 minutes, once.

**Reality check:** canon holds **4,821 Python files with 72 broken (1.5%)** — not
the 2,101 (37.7%) the old triage reported. That number was inflated ~29x by
counting intake dumps and 28 duplicate copies of the same `server.py`.

---

## `tools/boundary/airlock.py` — nothing leaves unsanitized

One gate. Every outbound payload passes through it.

```bash
airlock rules            # 27 detection rules by tier
airlock probe            # which providers have keys; is local inference up
airlock check <file|->   # exit 1 if sensitive
airlock redact <file|->  # swap secrets for [REDACTED:rule:fingerprint]
airlock route <file|->   # print the routing decision and why
airlock scan --index     # which of YOUR files must never leave
```

Exit codes: `0` clean, `1` findings, `2` error.

### The decision (one place, one rule)

```
                    ┌─ secret found, --mode strict ──▶ LOCAL ONLY
    text ──▶ scan ───┼─ secret found, --mode redact ──▶ redact ──▶ CLOUD
                    └─ clean ───────────────────────▶ CLOUD
                              no cloud keys ─────────▶ LOCAL (degraded)
```

### Rules by tier

`critical` (15): private keys, GCP service accounts, AWS/OpenAI/Groq/Google/
Anthropic/Cerebras/HF/GitHub/Slack/Stripe keys, DB URIs with credentials.
`high` (4): JWTs, OAuth tokens, assigned secrets, basic-auth URLs.
`medium` (2): bearer tokens, long hex blobs.
`personal` (6): lightning, Monero, BTC, ETH addresses, email, phone.

### The fingerprint

A secret is replaced with `[REDACTED:groq-key:c24e45f8a2]`. The hash lets you
tell that the *same* secret appears in two files **without either file revealing
it**. That is how you trace exposure.

**airlock never prints a full secret.** Previews are masked to 3 chars + length.

### Vault schema it expects

`~/.concierge/vault.json` uses `{"keys": {"<provider>": {"key":…, "env_var":…,
"status":…}}}` — nested, **not** flat `GROQ_API_KEY`. Reading it flat silently
reports zero credentials and breaks every routing decision. Entries with
`status` of `dead`/`revoked`/`invalid` are skipped.

---

## Local fallback

A 0.5B model cannot reason about a codebase. It is **not** a capability fallback —
it is for two narrow cases: cloud keys exhausted (402/429), and calls the gate
refuses to release. Degraded but safe beats clever but leaky.

Measured on this box (Intel N200, 2.6 GB RAM, no GPU): **14.2 tok/s generation**
at 0.5B. Realistic ceiling ~1.5B; 3B+ swaps.

```bash
llama-server -m ~/models/glue/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf --port 11434
```

Endpoint is `AIRLOCK_LOCAL_ENDPOINT`, default `http://localhost:11434`.
Until something listens there, both local routing paths are dead ends.

---

## Automation

`airlock-scan.timer` (systemd user timer) runs a weekly sweep and writes a report
to `~/.local/share/airlock/report-<date>.md`.

```bash
systemctl --user start airlock-scan.service     # sweep now
journalctl --user -u airlock-scan.service -n 50
systemctl --user disable --now airlock-scan.timer
```

---

## Adding capabilities

Do **not** create a sibling tool. Add a subcommand, reuse the index, and
reuse the gate. Two tools that work beat seven that each half-work.

## Known gaps

- `ariadne index` is incremental by mtime, so a **zone-rule change requires
  deleting `index.db`** and rebuilding — zone is stored at index time.
- Full `airlock scan` has not been run end-to-end; the 6,000-file sample covered
  roughly A–R. `--min-tier high` hides personal-tier findings.
- `ariadne.py --deep` hashing and symbol indexing are untested at full scale.

---

## 2026-09-11 session — new tools (P0)

### `tools/rescue/` — A9 lifeboat
You tell the next model: "A9 may die." It runs `./tools/rescue/a9_rescue.sh --check` and knows whether to pull over ADB (Termux home) or fall back to the on-device `tar` you must run inside Termux before access is lost.

See `tools/rescue/README.md`, `tools/rescue/drift_reconcile.py`, `~/MRD_A9_RESCUE.md` (meatsuit line + rclone backup).

### `tools/guard/` — worktree mirrors of RootBase canon_guard
`guard.sh snap "msg"` → `guard.sh verify` → `guard.sh rollback <id>` + `guard.sh budget` (PSI + RAM + disk). Snapshots only tar `src+tools+package` so the bus doesn't lag.

### `src/ui/ribbon/` — spec-bound ribbon animation
CSS draw-in (`@keyframes ribbon-draw`) works with no JS; `ribbon.js` measures `getTotalLength()` and sets `--len/--dur/--easing` so loops stay exact. `validate.py` is the recompilation gate — zero deps, checks the v1 contract.

See `src/ui/ribbon/demo.html` (file:// works).

