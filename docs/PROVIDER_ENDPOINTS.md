# Provider endpoints — the list to go get keys with

Everything here is an **OpenAI-compatible** chat-completions URL, which is the
only shape `bin/ai_gateway.py` speaks. Paste the URL into `PROVIDERS`, the env
name into `bin/vault-env`, and the model id into `FALLBACK_MODEL`.

**Reachability below was probed 2026-09-15** by sending a dummy key and reading
the status: `401/403` means the endpoint exists and reached auth, `404` means
wrong path, `unreachable` means the host did not resolve. It does **not** prove
the key works — only `bin/ai --providers` does that.

**The dated sections at the end are different, and stronger.** They were written
from the real keys in the vault, not dummy ones, so each row is evidence about
*that account* rather than about the endpoint. Check the heading before trusting
a row.

---

## Already wired (all four fields filled in)

| provider | endpoint | env var | model id | state 2026-09-15 |
|---|---|---|---|---|
| groq | `https://api.groq.com/openai/v1/chat/completions` | `GROQ_API_KEY` | `openai/gpt-oss-120b` | **11/11 keys live** |
| openrouter | `https://openrouter.ai/api/v1/chat/completions` | `OPENROUTER_API_KEY` | `nvidia/nemotron-3-super-120b-a12b:free` | 5 keys, live but flaky |
| mistral | `https://api.mistral.ai/v1/chat/completions` | `MISTRAL_API_KEY` | `mistral-small-latest` | 429 — no subscription |
| openai | `https://api.openai.com/v1/chat/completions` | `OPENAI_API_KEY` | `gpt-4o-mini` | 429 — no credits |
| gemini | `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions` | `GEMINI_API_KEY` | `gemini-flash-latest` | throttled, not dead — 6 keys as of 2026-09-15 |
| cerebras | `https://api.cerebras.ai/v1/chat/completions` | `CEREBRAS_API_KEY` | `gpt-oss-120b` | 402 — needs billing |
| deepinfra | `https://api.deepinfra.com/v1/openai/chat/completions` | `DEEPINFRA_API_KEY` | `meta-llama/Meta-Llama-3.3-70B-Instruct` | endpoint OK, no key |
| sambanova | `https://api.sambanova.ai/v1/chat/completions` | `SAMBANOVA_API_KEY` | `Meta-Llama-3.3-70B-Instruct` | **host unreachable** — do not buy here until fixed |

### Two gotchas worth remembering

- **Cerebras serves only three models**: `gpt-oss-120b`, `qwen-3.8-27b`,
  `gemma-4-31b`. A wrong id returns 404 and makes a perfectly good key look
  revoked.
- **Groq and Cerebras sit behind Cloudflare**, which bans urllib's default
  User-Agent with `403 error code: 1010` *before* auth. The gateway now sends a
  real UA; if you ever add a provider and everything 403s, check this first.

---

## Reachable, not yet wired (endpoint verified)

Add these if you get a key. Model ids here are **unverified** — a wrong one
404s and the chain falls through, and `bin/ai --providers` will say `bad-model`.

| provider | endpoint | env var | likely model | probe |
|---|---|---|---|---|
| deepseek | `https://api.deepseek.com/v1/chat/completions` | `DEEPSEEK_API_KEY` | `deepseek-chat` | 401 = exists |
| together | `https://api.together.xyz/v1/chat/completions` | `TOGETHER_API_KEY` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | 403 = exists |
| nebius | `https://api.studio.nebius.com/v1/chat/completions` | `NEBIUS_API_KEY` | `meta-llama/Meta-Llama-3.3-70B-Instruct` | 401 = exists |
| novita | `https://api.novita.ai/v3/openai/chat/completions` | `NOVITA_API_KEY` | `deepseek/deepseek-v3` | 401 = exists |
| hyperbolic | `https://api.hyperbolic.xyz/v1/chat/completions` | `HYPERBOLIC_API_KEY` | `meta-llama/Meta-Llama-3.1-70B-Instruct` | 403 = exists |
| moonshot | `https://api.moonshot.ai/v1/chat/completions` | `MOONSHOT_API_KEY` | `kimi-k2-0711-preview` | 401 = exists |
| zhipu / z.ai | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | `ZHIPU_API_KEY` | `glm-4.6` | 401 = exists |
| minimax | `https://api.minimax.chat/v1/chat/completions` | `MINIMAX_API_KEY` | `MiniMax-Text-01` | 401 = exists |
| perplexity | `https://api.perplexity.ai/chat/completions` | `PERPLEXITY_API_KEY` | `sonar` | 401 = exists |
| xai | `https://api.x.ai/v1/chat/completions` | `XAI_API_KEY` | `grok-4` | 400 = exists |
| anthropic | `https://api.anthropic.com/v1/chat/completions` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-5` | 401 = exists |

**Unverified path:** `fireworks` — `https://api.fireworks.ai/inference/v1/chat/completions`
returned 404 on the probe, so the path is probably wrong. Check their docs
before wiring it.

---

## How to wire one (3 edits + 1 env line)

1. `bin/ai_gateway.py` → `PROVIDERS`: add `"provider": "<endpoint>"`.
2. same file → `FALLBACK_MODEL`: add `"provider": "<model id>"`.
3. same file → `AUTO_CHAIN`: add it where it should sit in the fallback order.
4. `bin/vault-env` → the `mapping` dict: add `"provider": "<ENV_VAR>"`.

Then:

```bash
python3 ~/valet_concierge_system/concierge.py add <provider> <KEY>
systemctl --user restart ai-gateway
bin/ai --providers          # must say live, not just present
```

A provider with no key is skipped automatically, so wiring one early is safe.

## Why Groq is first in the chain

`AUTO_CHAIN` is ordered by evidence, not preference: Groq is the only pool that
is fully live (11/11) and free, so it is first. Paid providers come next and are
inert without a key. The flaky free tiers are last, because they can answer
`HTTP 200` with an error body or hang, and that must not swallow a request a
working provider could have served.

`swarms` now sits second: it is free, it returned a real completion in 2.30 s
(fastest of five ids tested), and it fronts 1908 model ids — including
`gemini/gemini-3.1-pro-preview`, so there is a working route to Gemini models
that does not depend on the Google key at all.

---

## Reconciled 2026-09-15 — every vault pool, probed with its real key

Six pools existed in `keys_by_provider` with **no route in `PROVIDERS`**, so their
keys arrived and were never read. All six were probed with the actual key from
the vault. `GET /v1/models` returned **200 for every one of them**, which proves
the host *and* the key are real. Chat is what separates the usable from the
merely authenticated:

| pool | endpoint | chat result | what it actually means |
|---|---|---|---|
| **swarms** | `https://api.swarms.world/v1/chat/completions` | **200 in 2.30–4.7 s** | **live, free, 1908 model ids** |
| sageox | `https://api.sageox.ai/v1/chat/completions` | `502` provider temporarily unavailable | key and URL correct; upstream is down, retryable |
| bazaar | `https://api.bazaarlink.ai/v1/chat/completions` | `402` insufficient credits | valid key, empty balance — top up |
| zenmux | `https://zenmux.ai/api/v1/chat/completions` | `403` `api_key_source: payg` | key has no entitlement on this account |
| orcarouter | `https://api.orcarouter.ai/v1/chat/completions` | `429` `free_rate_limited` | free models unlock by linking a GitHub account |
| puter | `https://api.puter.com/puterai/openai/v1/chat/completions` | `402` subscription required | token valid; API access needs a subscription |

### The lesson this file keeps relearning

**`/v1/models` returning 200 does not mean a key is usable.** Bazaar, zenmux and
orcarouter all listed hundreds of models and then refused every chat request.
This is the Cerebras failure generalised: there, four valid keys looked revoked
because of a wrong model id; here, four valid keys look live because the listing
endpoint only checks *authentication*. A 1-token chat is the only honest probe.

Two more traps found the same day:

- **Puter has no `/v1/models` at all** (404). For it, a chat call is not the
  better probe — it is the only one.
- **`bazaar` is not at `bazaar.ai`.** `sk-bl-` keys belong to **BazaarLink**; the
  provider key in `PROVIDERS` is `bazaar` only because it must match the vault
  pool name, and it points at `bazaarlink.ai`.

### Two pools that needed no route, because they were duplicates

- **`vibe` = `mistral`.** All six keys are byte-identical. Wiring `vibe`
  separately would have made the gateway round-robin the same six keys twice,
  doubling apparent pool size and corrupting any per-key cooldown.
- **`jules` ⊇ `gemini`.** All three gemini keys sit inside jules' eight. Its five
  others are Google-format keys, and **three of them answered `200`** against
  the Gemini endpoint after a retry, so they were merged into `gemini` — taking
  that pool from 3 keys to 6. The `jules` pool is left intact: Jules is a
  separate Google product and those tokens may be intended for it.

A single verification attempt misread one of those keys: it returned `429` on
attempt one and `200` on attempt two. **Probe twice before declaring a key dead**
— a transient quota error and a revoked key are indistinguishable from one call.

---

## Re-probed 2026-09-16 — every routed pool, one real 1-token chat each

Same method as the reconciliation above, run a day later against the live
gateway: `GET http://127.0.0.1:7071/providers`, which is `probe_all()` in
`bin/ai_gateway.py` — the identical code path behind `bin/ai --providers`.
**Nothing moved.** Every pool landed in the state the 09-15 section predicted:

| pool | keys | chat result | state |
|---|---|---|---|
| **groq** | 11 | `200` | **live** |
| **openrouter** | 5 | `200` | **live** |
| **swarms** | 1 | `200` | **live** |
| mistral | 6 | `429` | rate-limited |
| orcarouter | 3 | `429` | rate-limited |
| cerebras | 4 | `402` | unpaid |
| bazaar | 6 | `402` | unpaid |
| puter | 3 | `402` | unpaid |
| openai | 3 | `429` with a quota body | unpaid |
| zenmux | 1 | `403` | auth-dead |
| gemini | 6 | `503` | upstream down |
| sageox | 2 | `502` | upstream down |

51 keys across 12 routed pools. Three serve. The other nine are blocked for a
reason that is neither the key nor the URL.

### What this run adds

- **The three live pools are the entire working surface.** Filtered to pools that
  hold a key, `AUTO_CHAIN` is groq → swarms → openrouter → mistral → gemini →
  openai → cerebras → bazaar → orcarouter → zenmux → sageox → puter. The first
  three answer, so `auto` should be served on its first hop; every hop after that
  is a known failure, useful only as fallback.
- **`openai` is the case study, not a mystery.** It answers `429`, which reads as
  transient, but the body carries a quota-exhaustion marker, so the gateway files
  it as `unpaid` and quarantines the key for an hour instead of walking the pool
  into it on every request. A bare status code would have got this backwards in
  exactly the direction this file keeps warning about.
- **`gemini` and `sageox` are not spent.** `502`/`503` are the providers failing,
  so these are the only two rows that can change without anyone touching a key.
  Re-probe them before treating either pool as dead. (The 09-15 row for sageox
  said the same thing, and a day later it still holds.)

### Two limits of this probe, recorded so they are not rediscovered

- **It tests one key per pool — `pool[0]`.** "groq: live" means *the first Groq
  key* answers. It does not support "11/11" and it does not show that the other
  ten are dead. Claiming a whole pool requires probing the whole pool, which the
  tool does not currently do.
- **The state map had no case for `502`/`503`** — they surfaced as raw
  `http-502` and `http-503`, which is honest but unhelpful: a transient upstream
  outage read the same as an unrecognised error. Fixed the same day: both codes
  now report `upstream` in `probe_provider()`. Verified offline across the whole
  map (401, 402, 403, 404, 429, 500, 502, 503) rather than by re-probing live,
  so the two rows in the table above still show the raw codes they returned
  before the fix. Restart `ai-gateway` for the running process to pick it up.

### Resolved 2026-09-30 — no unexplained pools remain

`concierge.py list` reports 16 pools; the gateway routes 12. `jules` and `vibe`
are the two the 09-15 section already resolves as duplicates of `gemini` and
`mistral`. The last two are now closed out, so every pool is routed, a known
duplicate, or retired — the "keys arrived and were never read" pattern has no
remaining instances:

- **`google`** — `status: retired` and no key present. Not routable and not
  expected to be; it is the superseded Google AI Studio key. Nothing to wire.
- **`unknown`** — a **placeholder value**, not a key. The vault recorded its
  source as `UNPACKED/equinex-forge-r&d/.env.local:GEMINI_API_KEY` with a stored
  prefix of `PLACEHOLDER_API_...`. It was retired (`status: retired`) rather than
  probed, because wiring a placeholder only adds a guaranteed-failing hop.
