# ABOUT_EVIDENCE — the proofs behind the `--about` paragraph

Split out of `ABOUT.md` on 2026-09-17, when that file was cut down to the single
paragraph that `--about-file` actually feeds to the model. Nothing here is prompt
text; it exists so that every sentence in the paragraph can be checked, and so that
a future edit cannot quietly turn a verified claim into an invented one.

## The rule this file exists to enforce

A claim that cannot be checked does not belong in `ABOUT.md`. Nothing there asserts
experience, seniority, clients, revenue or outcomes, because none of that is in the
repository and all of it would be invented. What is asserted is that specific things
exist, work, and can be read or run — which is a weaker claim than most pitches make,
and a far more useful one to send to someone who is hiring.

## The evidence, so you can check the paragraph is true

| Claim | Where it is proven |
|---|---|
| Gateway fronts twelve provider pools, rotates per key | `bin/ai_gateway.py` — `PROVIDERS`, and `_cool()` branching on `COOLDOWN_429` vs `QUARANTINE_401`. **Twelve is the *live* count**, confirmed against the running `/providers` endpoint; the source declares 14 and the other two have no keys. Say "twelve pools", never "twelve providers" |
| 429 cools a key; 401 quarantines it | Same file, and the rotator was exercised live: four sequential calls returned on four different key fingerprints; one call walked all six Mistral keys |
| Detects "200 with an error body" | Same file, the `"200-with-error"` cooldown branch |
| Runs for ~1.3 CPU-seconds/day | `docs/AUTOMATION_BUDGET.md`, from systemd's own accounting |
| Client is stdlib-only, ~25 MB, 79 tests | `projects/lean/` — `lean.py`, `tests/test_lean.py`, and the RSS measurement in `WHO_DID_WHAT.md` |
| Vendor client used 436–566 MB on the same box | Same measurement, plus `docs/AUTOMATION_BUDGET.md` |
| Path tools confined by resolution, not by request | `projects/lean/lean.py` — `_within_workspace()`, which resolves and rejects, including through a symlink |
| Writes and shell are separate approvals | Same file — `MUTATING` vs `SHELL`, with the deliberate absence of a command blacklist explained in the README |
| Append-only change log, one entry per change | Every project's `WHO_DID_WHAT.md`, including the entries recording **my own mistakes** |
| Measurement discipline | `docs/AUTOMATION_BUDGET.md` contains a section headed "CORRECTION" that overturns its own earlier headline finding |

If a sentence in the paragraph cannot be traced to that table, **delete the
sentence.** That table is the reason this offer can be sent at all.

## Variants

Not prompt text either — swap one in when a lead is clearly about one of these.
Never paste more than one of them into `--about-file`.

A variant that has been promoted to a file of its own can be fed directly:

| File | Offer | When |
|---|---|---|
| `ABOUT.md` | coding-agent cost and containment | the default |
| `ABOUT_PRODUCT.md` | Python backend work and LLM features in a product | most "Who is hiring?" posts are product roles, and the default file measures as too narrow for them |

The two quoted variants below have **not** been promoted, so they are documentation
rather than something you can pass to `--about-file`. Promote one the same way if you
find yourself wanting it more than once.

For a lead that is really about a messy codebase:

> I do small, bounded cleanups of legacy Python — one module, one endpoint, or one
> tangled dependency at a time, fixed price. I also leave a repo in a state where a
> coding agent can work in it without wrecking it: the agent is confined to the
> working directory by path resolution, "may edit files" and "may run shell" are
> separate approvals, and every change lands in an append-only log with who did it
> and why. I work alone, based in [TIMEZONE]. [RATES].

For a lead that is really about spend or rate limits:

> I make LLM traffic predictable. I run a local, OpenAI-compatible gateway that
> fronts twelve provider pools and rotates keys per provider, tracking a cooldown
> per key so a rate limit degrades one key rather than killing the run, and
> quarantining keys that come back revoked instead of retrying them. It also tells
> the difference between "this provider returned 200 with an error inside it" and a
> real success, which is the failure mode that silently corrupts a pipeline. It
> costs about 1.3 CPU-seconds per day to run. Fixed-price work, [TIMEZONE].
> [RATES].

## What the model may NOT claim

Put plainly, because these are the things a model writing sales copy will invent
unless it is told not to:

- **No years of experience, no client names, no employers, no revenue, no
  outcomes.** None of that exists in this repository.
- **No "we" and no "team".** This is one person.
- **No scale words.** Not "production-grade", not "enterprise", not "battle-tested".
  The gateway serves one machine. Say what it is.
- **No novelty.** Key rotation and cooldown are old, standard ideas, competently
  implemented. Claiming invention invites a correction you cannot afford.
- **Nothing about the prospect's codebase** beyond what their own post says.
- **No timeline or price** that is not in this file.
- **Nothing about the commercial client's internals as a service offered** — the
  BYOK finding is reconnaissance, not a product.
- **No promise to contact, post or send anything on someone's behalf.**

## What only you can fill in

The blanks in the paragraph are blanks because inventing them would be the same lie
as inventing a client list:

- `[TIMEZONE]` — and, if it matters for the job, your working hours.
- `[YOUR RATES]` — or a deliberate refusal to quote before scoping. Both are
  answers; saying nothing is not.
- **Whether you will take paid contract work at all**, and under what terms —
  invoice, entity, contract.
- **A link the prospect can actually open.** The strongest version of this pitch is
  a repo or a two-minute screen recording, not a paragraph. Right now the paragraph
  says "code you can read" and gives nowhere to read it, which is the weakest line
  in it.
- **Whether your name is used.** It is not in the paragraph on purpose.

## The honest footnote

The best thing this repository has is not a service, it is that these are working
artifacts with tests and a measurement log. That is genuinely rare, and it is
sellable as evidence.

But note which paragraph is strongest. It is the **cost and containment** one, not
"I will build you a client" — because the vendor gives its client away free, so there
is no willingness to pay for a replacement, and a replacement is the one thing a
prospect can most easily believe they do not need. What people do pay for is the
thing they cannot see: spend that behaves, keys that fail one at a time, and an agent
that cannot quietly edit 150 files while nobody is looking.

## Why `ABOUT.md` must stay one paragraph

Measured 2026-09-17. The 7.4 KB version of `ABOUT.md` made the prompt ~2,100 tokens
against the one-liner's ~300, and Groq's free tier caps at 8,000 tokens per minute:
**8 of 10 calls came back HTTP 429 and the run produced nothing.** A bigger `--about`
file does not buy a better email, it buys a shorter run. The 7 KB also contained the
words "Write one short outreach email…"-shaped instructions about the task itself,
and at least one reply came back as the *prompt echoed verbatim* rather than an
answer — a failure the tool used to write to disk as a draft.

Both of those are why the model may only ever see the paragraph.
