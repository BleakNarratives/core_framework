# Résumé-ready writeups

Two bodies of work from this tree, written to be lifted into a résumé, a
portfolio site, or a consulting pitch. Every number here is traceable to a
command or an artifact in the repo; nothing is rounded up to sound bigger.

---

# 1. Local AI toolchain — unification and key rotation

**One line:** Rebuilt a fragmented set of AI coding CLIs (each with its own
config and its own single API key) into one rotating gateway with a single
config, a single interface, and a strict traceback auto-fixer.

### Bullets

- Consolidated **five independent AI CLI configs** into **one config**
  (`~/.config/ai/config.toml`) served by **one local OpenAI-compatible
  endpoint**, removing the failure mode where a dead key in one tool was
  invisible to every other tool.
- Implemented **provider-level key-pool rotation across 6 providers / 29
  vaulted keys**, with per-key rate-limit cooldown, auth-failure quarantine,
  and pool-level dead-provider skipping.
- Root-caused a stack-wide outage to **12 revoked keys (HTTP 403) and an
  exhausted OpenAI account**, then distinguished a permanent quota 429 from a
  transient rate limit so the router stopped retrying permanently dead
  accounts — the specific bug that made rotation appear not to work.
- Eliminated a class of silent hangs (a provider accepting a request and never
  answering) with a per-provider upstream timeout and fall-through; identified
  the cause as **retired model names** (`gemini-2.5-flash` refused; the
  `-latest` alias answered in ~2.7 s).
- Built a **traceback auto-fixer** that captures a failing command, resolves
  `file:line` context from the traceback, and applies a fix **only when the
  patch matches the target file exactly once** (backs up first, refuses
  ambiguous patches) — designed so it can never silently corrupt a file.
- Rebuilt a **broken agent with durable state**: SQLite-backed conversation
  history, key/value memory, and a tool-run audit, plus keyless web search,
  replacing a dead API bridge whose auth token did not exist.
- Made rotation **survive the caller's shell** via an on-demand `systemd --user`
  unit (deliberately *not* enabled, so nothing auto-starts at boot).
- **Verified every change**: compile checks, shell parse checks, live
  end-to-end calls against the running gateway, and deterministic state
  round-trips.

### Skills

`Python (stdlib-only)` · `HTTP service design` · `OpenAI-compatible API` ·
`rate-limit & key rotation` · `SQLite` · `systemd user units` · `Bash` ·
`root-cause analysis` · `CLI/UX design` · `technical writing`

---

# 2. rag_seal_sim — injection-resistant RAG (security research)

**One line:** Designed and benchmarked an HNSW retrieval architecture that
treats retrieved documents as untrusted evidence instead of executable
instructions, cutting indirect-prompt-injection success from **100% to 0%** at
**+0.22 ms/query** overhead.

*Long form: `prototypes/rag_seal_sim/PORTFOLIO.md` and `WHITEPAPER.md`.*

### Bullets

- Designed and implemented a **9-module, ~2,700-LOC Python system** (HNSW
  retrieval, sealed evidence nodes, policy gate, pluggable inference chain)
  with a **fully reproducible offline benchmark** — no API keys or network
  required.
- Reduced measured indirect-prompt-injection success from **100% (8/8) to 0%
  (0/8)** across an 8-category attack corpus, **including 2 payloads the input
  scanner never detected** — the defense holds at the output gate rather than
  depending on input detection.
- Demonstrated **defense-in-depth against an untrusted model**: the provider
  was compromised on 8/8 sealed queries and a provider-independent policy gate
  contained all 8 before user exposure.
- Quantified the security boundary at **+0.222 ms/query** (0.236 ms sealed vs
  0.025 ms concat end-to-end) — negligible beside real generation latency.
- Benchmarked retrieval at **0.014 ms/query (~71,000 q/s, 88.3% recall@5)**
  against exact-cosine ground truth, with a pure-Python fallback for
  environments where the native HNSW extension will not compile.
- Verified a **0% false-positive block rate** on benign queries with clean
  retrieval, and **re-ran the benchmark to confirm reproducibility** — the
  security result reproduced exactly, and the re-run caught and corrected a
  documentation/artifact numeric drift.

### Skills

`RAG / retrieval systems` · `HNSW / ANN indexing` · `LLM security` ·
`indirect prompt injection` · `threat modeling` · `benchmark design` ·
`measurement methodology` · `performance profiling` · `technical writing`

---

## Combined skills line

`Python` · `LLM application security` · `RAG & vector search` · `API design &
integration` · `rate limiting / key rotation` · `SQLite` · `systemd` · `Linux
CLI tooling` · `debugging & root-cause analysis` · `benchmarking & honest
measurement` · `technical writing`

## 30-second pitch

I build AI infrastructure and then measure it honestly. My security project
(`rag_seal_sim`) reduced indirect prompt-injection success from 100% to 0% and
I published the limitations alongside the result. My toolchain project replaced
five broken, independently-configured AI CLIs with one rotating gateway, one
config, and a traceback fixer that refuses to edit a file when it isn't certain.

## Using these

- Lead with whichever matches the role: **toolchain** for platform/infra/tooling
  roles, **rag_seal_sim** for security/ML roles.
- Keep the limits paragraphs from `PORTFOLIO.md`. The credibility is in naming
  what the work does *not* do.
- Every claim above maps to a file or a command in this repo. If a claim can't
  be traced, delete it rather than soften it.
