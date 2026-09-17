# ABOUT — the offer herald drafts from

This is the `--about` source. Every sentence herald writes is bounded by this file:
the model may tailor it per lead and may reply `NO FIT`, but it may not add a claim
that is not here. So this file is not a pitch, it is a **ceiling**.

```bash
python3 outreach_agent.py --about-file ABOUT.md
```

## The rule this file exists to enforce

A claim that cannot be checked does not belong here. Nothing below asserts
experience, seniority, clients, revenue or outcomes, because none of that is in the
repository and all of it would be invented. What is asserted is that specific
things exist, work, and can be read or run — which is a weaker claim than most
pitches make, and a far more useful one to send to someone who is hiring.

---

## The paragraph to draft from

Not the text that gets sent. `outreach_agent` compresses this into a sub-120-word
email tailored per lead, so this is source material and the caps below do not apply
to it — but it is kept tight on purpose, because everything in it is something the
model may repeat.

> I make LLM coding agents cheap enough and contained enough to run on hardware you
> already own. I run a self-hosted, OpenAI-compatible gateway fronting twelve
> provider pools that rotates keys per provider, so a 429 cools one key instead of
> ending the run and a revoked key gets quarantined instead of retried forever. The
> client on top of it is stdlib-only Python: ~25 MB resident against 436–566 MB
> measured for the commercial client on the same machine, 79 tests, no animation
> loop. I also wrote the containment that makes an agent safe to leave running —
> file edits and shell commands approved as separate tiers, and every path-taking
> tool confined to the working directory by resolving the path, not by asking the
> model nicely. It is all code you can read and run. I take small fixed-price jobs
> with a defined end; no retainers. Based in [TIMEZONE].
> [YOUR RATES OR "rate on request"].

### Narrow variants

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

---

## The evidence, so you can check the paragraph is true

| Claim | Where it is proven |
|---|---|
| Gateway fronts twelve provider pools, rotates per key | `bin/ai_gateway.py` — `PROVIDERS`, and `_cool()` branching on `COOLDOWN_429` vs `QUARANTINE_401`. Note **twelve is the *live* count**, confirmed against the running `/providers` endpoint; the source declares 14 and the other two have no keys. Say "twelve pools", never "twelve providers" |
| 429 cools a key; 401 quarantines it | Same file, and the rotator was exercised live: four sequential calls returned on four different key fingerprints; one call walked all six Mistral keys |
| Detects "200 with an error body" | Same file, the `"200-with-error"` cooldown branch |
| Runs for ~1.3 CPU-seconds/day | `docs/AUTOMATION_BUDGET.md`, from systemd's own accounting |
| Client is stdlib-only, ~25 MB, 79 tests | `projects/lean/` — `lean.py`, `tests/test_lean.py`, and the RSS measurement in `WHO_DID_WHAT.md` |
| Vendor client used 436–566 MB on the same box | Same measurement, plus `docs/AUTOMATION_BUDGET.md` |
| Path tools confined by resolution, not by request | `projects/lean/lean.py` — `_within_workspace()`, which resolves and rejects, including through a symlink |
| Writes and shell are separate approvals | Same file — `MUTATING` vs `SHELL`, with the deliberate absence of a command blacklist explained in the README |
| Append-only change log, one entry per change | Every project's `WHO_DID_WHAT.md`, including the entries recording **my own mistakes** |
| Measurement discipline | `docs/AUTOMATION_BUDGET.md` contains a section headed "CORRECTION" that overturns its own earlier headline finding |

If a sentence in the paragraph above cannot be traced to that table, **delete the
sentence.** That table is the reason this offer can be sent at all.

---

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

---

## What only you can fill in

The blanks above are blanks because inventing them would be the same lie as
inventing a client list:

- `[TIMEZONE]` — and, if it matters for the job, your working hours.
- `[YOUR RATES]` — or a deliberate refusal to quote before scoping. Both are
  answers; saying nothing is not.
- **Whether you will take paid contract work at all**, and under what terms —
  invoice, entity, contract.
- **A link the prospect can actually open.** The strongest version of this pitch is
  a repo or a two-minute screen recording, not a paragraph. Right now the paragraph
  says "code you can read" and gives nowhere to read it, which is the weakest line
  in it.
- **Whether your name is used.** It is not in this file on purpose.

---

## The honest footnote

The best thing this repository has is not a service, it is that these are working
artifacts with tests and a measurement log. That is genuinely rare, and it is
sellable as evidence.

But note which paragraph is strongest. It is the **cost and containment** one, not
"I will build you a client" — because the vendor gives its client away free, so
there is no willingness to pay for a replacement, and a replacement is the one thing
a prospect can most easily believe they do not need. What people do pay for is the
thing they cannot see: spend that behaves, keys that fail one at a time, and an
agent that cannot quietly edit 150 files while nobody is looking.
