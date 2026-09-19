# Herald — System Dependencies

Generated from inspection of the working tree on 2026-09-17.

## 1. What this document covers

This is the complete list of local tools, environment variables, system paths,
network endpoints, and Python package requirements the Herald project needs at
setup time and at runtime. It is derived from the source, not from memory: every
path and endpoint below was read out of `projects/herald/*.py` on the date above.

## 2. Project overview

Herald is a three-stage lead-generation pipeline:

```
monitor_leads.py   →   LEADS.md   →   outreach_agent.py   →   OUTREACH_DRAFTS.md
(Reddit/HN feeds)           (qualified leads)            (tailored email drafts)
```

- `monitor_leads.py` — fetches Reddit `/new.rss` feeds and HN Algolia API,
  filters for `[HIRING]` posts, extracts contact details, appends to `LEADS.md`.
- `hn_leads.py` — fetches the monthly HN "Who is hiring?" thread via Algolia,
  appends job posts to `LEADS.md`.
- `outreach_agent.py` — reads `LEADS.md`, qualifies leads, calls `bin/ai` to
  draft a tailored outreach email for each contactable lead, writes drafts to
  `OUTREACH_DRAFTS.md`.

All three scripts live in `projects/herald/` and are designed to be run from
that directory or imported as modules.

## 3. Python runtime

| Requirement | Value | Source |
|---|---|---|
| Python minor version | 3.13+ | `.pyc` files named `cpython-313`; `python3 --version` reports 3.13.5 |
| Executable | `python3` on PATH, or `~/bin/python3` | `bin/ai` shebang; `outreach_agent.py` uses `sys.executable` to invoke `bin/ai` |
| Venv (recommended) | `~/venv/bin/python` | test file header: `~/venv/bin/python -m pytest projects/herald/tests -q` |

## 4. Python package dependencies

All three Herald scripts use **stdlib only**. No `pip install` is required for
the pipeline itself.

| Package | Used by | Purpose |
|---|---|---|
| `argparse` | all three | CLI parsing |
| `json` | all three | state and envelope handling |
| `re` | all three | contact extraction, filtering |
| `urllib.request` / `urllib.error` | all three | HTTP transport |
| `xml.etree.ElementTree` | `monitor_leads.py`, `hn_leads.py` | Atom feed parsing |
| `html` (`unescape`) | `monitor_leads.py` | feed HTML → text |
| `datetime` | all three | timestamps |
| `pathlib` | all three | file paths |
| `subprocess` | `outreach_agent.py` | invokes `bin/ai` |
| `time` | `monitor_leads.py`, `outreach_agent.py` | feed delay, retry waits |
| `tempfile` | tests | isolated file fixtures |

**Test-only dependencies** (`tests/test_herald.py`):

| Package | Purpose |
|---|---|
| `pytest` 9.1.1 | test runner (`python -m pytest`) |
| `unittest.mock` | patches `fetch`, `_get`, `complete` |

No third-party packages (`requests`, `feedparser`, etc.) are used or required.

## 5. Local tools and system paths

### 5.1 `bin/ai` — required for `outreach_agent.py`

`outreach_agent.py` shells out to `bin/ai --json` for every model call. It
locates `bin/ai` by walking **upward** from `projects/herald/` until it finds
`bin/ai`, so the project does not depend on a fixed install depth.

**Required path:**

```
/home/bleaknarratives/bin/ai          (absolute on this host)
```

**Runtime contract** (`outreach_agent.complete`, lines 493–516):

- Must accept `--json <prompt>` on stdin/argv.
- Must print a JSON envelope with shape `{"ok": bool, "reply": str, "error": str}`.
- Must exit non-zero on transport failure; `outreach_agent` reads `proc.stdout`
  and `proc.stderr` and raises `RuntimeError` with the provider message.

`bin/ai` itself delegates to `bin/ai_lib.py`, which goes through the rotating
gateway at `http://127.0.0.1:7071`. Herald does not need to know the gateway
address; it only needs `bin/ai` on PATH or findable by path walk.

### 5.2 Project-local files (created or consumed at runtime)

| File | Role | Created by |
|---|---|---|
| `projects/herald/LEADS.md` | Lead data store, append-only | `monitor_leads.py`, `hn_leads.py` |
| `projects/herald/OUTREACH_DRAFTS.md` | Drafted emails, append-only | `outreach_agent.py` |
| `projects/herald/.herald_state.json` | Verdict memory (resumable batches) | `outreach_agent.py` |
| `projects/herald/ABOUT.md` | Offer paragraph for `--about-file` | operator |
| `projects/herald/ABOUT_EVIDENCE.md` | Evidence backing `ABOUT.md` claims | operator |
| `projects/herald/ABOUT_PRODUCT.md` | Product-role variant of the offer | operator |

`LEADS.md` and `OUTREACH_DRAFTS.md` are **deliberately gitignored** because
they contain third-party contact details. The code is tracked; the people are not.

### 5.3 `bin/ai` configuration (gateway keys)

`bin/ai` reads provider API keys from environment variables via `bin/vault-env`
or a `.env` file in `bin/`. Herald does not read these directly, but
`outreach_agent.py` will fail at model-call time if the gateway has no live
keys. Keys Herald has been exercised against (from `docs/PROVIDER_ENDPOINTS.md`):

| Provider | Env var | Status 2026-09-15 |
|---|---|---|
| groq | `GROQ_API_KEY` | 11/11 keys live |
| openrouter | `OPENROUTER_API_KEY` | 5 keys, live but flaky |
| gemini | `GEMINI_API_KEY` | 6 keys, throttled |
| deepinfra | `DEEPINFRA_API_KEY` | endpoint OK, no key in vault |
| cerebras | `CEREBRAS_API_KEY` | 402 — needs billing |
| mistral | `MISTRAL_API_KEY` | 429 — no subscription |
| openai | `OPENAI_API_KEY` | 429 — no credits |
| swarms | `SWARMS_API_KEY` | 1 key, live |
| sambanova | `SAMBANOVA_API_KEY` | host unreachable |

## 6. Network endpoints and external APIs

All network calls are made with stdlib `urllib`. No DNS rebinding or proxy
configuration is used or tested.

### 6.1 Reddit Atom feeds (monitor_leads.py)

Two feeds, fetched sequentially with a 2-second polite delay between them.

| Feed | URL | Notes |
|---|---|---|
| r/forhire — new | `https://www.reddit.com/r/forhire/new.rss` | Returns Atom; Reddit replies 403 to default User-Agent |
| r/freelance_forhire — new | `https://www.reddit.com/r/freelance_forhire/new.rss` | Same constraints |

**Headers required:** `User-Agent: monitor_leads/2.0 (personal feed reader; stdlib urllib)`

**Known failure mode:** Reddit rate-limits this host aggressively. Both feeds
returned HTTP 429 on 2026-09-16 and again after a 30-second wait. A failed feed
is reported and skipped; it does not silently drop entries. The `Retry-After`
header is surfaced in the error message but not waited on, because the observed
limit is per-host, not per-run.

### 6.2 HN Algolia API (hn_leads.py)

| Endpoint | Purpose |
|---|---|
| `https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=20` | Find the latest "Who is hiring?" thread |
| `https://hn.algolia.com/api/v1/search?tags=comment,story_{id}&hitsPerPage=200&page={n}` | Paginated comment fetch (up to 6 pages) |

**Headers required:** `User-Agent: hn_leads/2.0 (personal feed reader; stdlib urllib)`

**Known constraints:**
- Algolia caps responses; the September 2026 thread had 403 comments across
  multiple pages. `MAX_PAGES = 6` with `PAGE_SIZE = 200` covers this.
- A one-page fetch returns a silent subset — the failure mode where a list
  looks complete and is not.
- HN item identity is the `objectID` query parameter on `news.ycombinator.com/item?id=N`;
  `normalize_url()` deliberately strips queries, so HN keys on `hn:{id}` rather
  than on the normalized URL.

### 6.3 Model gateway (outreach_agent.py → bin/ai → gateway)

`outreach_agent.py` does not call any model API directly. It invokes:

```
python3 bin/ai --json [--model <model>] "<prompt>"
```

`bin/ai` then routes through the local gateway at `http://127.0.0.1:7071`,
which rotates across provider pools. Herald is tested against:

| Provider | Typical model used |
|---|---|
| groq | `openai/gpt-oss-120b` |
| openrouter | `nvidia/nemotron-3-super-120b-a12b:free` |

**Rate-limit behavior** (measured 2026-09-17):
- Groq free tier: 8,000 TPM ceiling. 8 of 10 calls in one run answered 429.
- A 429 with a provider-stated wait interval is retried up to 3 times.
- A 429 caused by an empty account (`insufficient_quota`, `credit_balance_exhausted`,
  `no credits remaining`) is **not** retried — waiting cannot fix billing.

## 7. Runtime assumptions and constraints

1. **`bin/ai` must be findable.** `outreach_agent.py` walks up from
   `projects/herald/` looking for `bin/ai`. If the project is moved without
   `bin/ai` above it, model calls fail with `RuntimeError`.

2. **Reddit will 429.** Both `r/forhire` and `r/freelance_forhire` feeds are
   rate-limited per-host. A run that finds nothing new is the normal case, not
   an error. Do not retry aggressively; the limit does not reset on retry.

3. **HN Algolia is the productive source.** On 2026-09-17 the HN "Who is hiring?"
   thread returned 403 comments, 263 top-level job posts, 69 publishing an email.
   Reddit returned 429 for every feed on the same day.

4. **A link is not a contact.** Application forms (Ashby, Greenhouse, Lever,
  Deel, Workday, etc.) are recorded as `apply:` hints and do **not** count as
   reaching a person. Company homepages and job documents are recorded as
   `venue:` hints and also do **not** count. Only `email:`, `dm`, and `profile:`
   hints on messaging platforms count.

5. **The model may refuse.** `outreach_agent` prompts the model to reply `NO FIT`
   when the offer does not match the post. Refusals are recorded in
   `.herald_state.json` and **not** written to `OUTREACH_DRAFTS.md`.

6. **Prompt echoes are possible.** At least one gateway route can return the
   prompt verbatim as the completion. `outreach_agent` validates replies before
   writing them and refuses echoed prompts, empty replies, and bodies over
   200 words. A run of all-malformed replies exits non-zero.

7. **Batches resume.** `.herald_state.json` records a verdict per lead source
   (`drafted`, `no_fit`, `malformed`, `failed`). The next batch skips answered
   leads. Use `--redo` to ignore memory. Deleting `.herald_state.json` resets
   all verdicts.

8. **`--about` is required for drafting.** The tool cannot write a pitch without
   an offer paragraph. `--about-file ABOUT.md` reads the paragraph from disk.

9. **Pin `--model` before comparing offers.** The default is `auto`, and the
   gateway rotates pools. Two runs of the same code can differ by pool selection
   rather than content.

10. **No send mode exists by design.** `OUTREACH_DRAFTS.md` carries `mailto:` links
    only. The operator presses send from their own identity after reading the copy.

## 8. Setup checklist

```bash
# 1. Verify Python
python3 --version          # must be 3.13+
which python3              # must resolve

# 2. Verify bin/ai is findable from projects/herald/
ls /home/bleaknarratives/bin/ai

# 3. (Optional) Activate venv for tests
source ~/venv/bin/activate

# 4. Verify gateway is running (outreach_agent dependency)
python3 bin/ai --health

# 5. Verify at least one provider key is live
python3 bin/ai --providers

# 6. Run offline tests (no network, no keys needed)
python3 -m pytest projects/herald/tests -q

# 7. Dry-run monitor_leads (requires live Reddit; will 429 during limits)
python3 projects/herald/monitor_leads.py --dry-run

# 8. Dry-run hn_leads (requires live Algolia)
python3 projects/herald/hn_leads.py --dry-run

# 9. List qualified leads (no model call)
python3 projects/herald/outreach_agent.py --list

# 10. Draft outreach (requires live gateway + keys)
python3 projects/herald/outreach_agent.py --about-file projects/herald/ABOUT.md --limit 5
```

## 9. Failure modes and their symptoms

| Symptom | Cause | Fix |
|---|---|---|
| `bin/ai not found` | `bin/ai` not walkable from `projects/herald/` | Symlink or move `bin/ai` above the project |
| `model call failed: gateway HTTP 429` with `Please try again in Xs` | Provider TPM ceiling | `outreach_agent` retries automatically; wait or switch model |
| `model call failed: gateway HTTP 429: no credits remaining` | Provider account empty | Top up account; retries will not help |
| `every feed failed; nothing written` | Reddit 429 on both feeds | Wait; this is the steady state, not a bug |
| `no 'Who is hiring?' story in the last 20 posts` | Algolia index changed or `whoishiring` account renamed | Pin a thread with `--thread <id>` |
| `bin/ai printed nothing` | Gateway not running, or `bin/ai_lib.py` missing | Start gateway; verify `bin/ai --health` |
| `ignoring unreadable .herald_state.json` | Corrupt or truncated state file | Delete it; all leads will be treated as new |
| `appended 0 draft(s)` after `--about` | All leads refused as `NO FIT` or malformed | Broaden offer paragraph or check lead set |

## 10. Environment variables

Herald scripts do **not** read API keys directly. Keys are consumed by
`bin/ai` → `bin/ai_lib.py` → `bin/ai_gateway.py`, which reads from
`bin/vault-env` or a `.env` file.

If you are running `outreach_agent.py` outside the normal gateway path, these
are the env vars the gateway looks for:

| Variable | Provider |
|---|---|
| `GROQ_API_KEY` | groq |
| `OPENROUTER_API_KEY` | openrouter |
| `GEMINI_API_KEY` | gemini |
| `DEEPINFRA_API_KEY` | deepinfra |
| `CEREBRAS_API_KEY` | cerebras |
| `MISTRAL_API_KEY` | mistral |
| `OPENAI_API_KEY` | openai |
| `SWARMS_API_KEY` | swarms |
| `SAMBANOVA_API_KEY` | sambanova |

No secrets are read from or written to the Herald project directory. The
state file `.herald_state.json` records verdicts only, never keys.

## 11. OS and hardware assumptions

| Item | Value |
|---|---|
| Primary development host | Crostini-Chromebook (Linux container) |
| Filesystem | case-sensitive, local SSD |
| Network | Residential IP; Reddit and Algolia are reachable without a proxy |
| Disk | LEADS.md grows by ~1 KB per 25 new entries; OUTREACH_DRAFTS.md by ~2 KB per draft |
| No GPU required | All computation is CPU-bound string matching and one subprocess call per draft |

## 12. License

All authored Herald code is MIT-licensed. `LEADS.md` and `OUTREACH_DRAFTS.md`
contain third-party contact details and are not tracked in version control.
