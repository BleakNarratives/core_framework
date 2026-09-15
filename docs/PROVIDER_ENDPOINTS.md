# Provider endpoints — the list to go get keys with

Everything here is an **OpenAI-compatible** chat-completions URL, which is the
only shape `bin/ai_gateway.py` speaks. Paste the URL into `PROVIDERS`, the env
name into `bin/vault-env`, and the model id into `FALLBACK_MODEL`.

**Reachability below was probed 2026-09-15** by sending a dummy key and reading
the status: `401/403` means the endpoint exists and reached auth, `404` means
wrong path, `unreachable` means the host did not resolve. It does **not** prove
the key works — only `bin/ai --providers` does that.

---

## Already wired (all four fields filled in)

| provider | endpoint | env var | model id | state 2026-09-15 |
|---|---|---|---|---|
| groq | `https://api.groq.com/openai/v1/chat/completions` | `GROQ_API_KEY` | `openai/gpt-oss-120b` | **11/11 keys live** |
| openrouter | `https://openrouter.ai/api/v1/chat/completions` | `OPENROUTER_API_KEY` | `nvidia/nemotron-3-super-120b-a12b:free` | 5 keys, live but flaky |
| mistral | `https://api.mistral.ai/v1/chat/completions` | `MISTRAL_API_KEY` | `mistral-small-latest` | 429 — no subscription |
| openai | `https://api.openai.com/v1/chat/completions` | `OPENAI_API_KEY` | `gpt-4o-mini` | 429 — no credits |
| gemini | `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions` | `GEMINI_API_KEY` | `gemini-flash-latest` | 429 — free quota spent |
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
