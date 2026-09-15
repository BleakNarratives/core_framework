# rag_seal_sim — Portfolio / Résumé Writeup

*Everything below is traceable to `results.json`. Numbers were re-verified
2026-09-15; the security result reproduced exactly.*

---

## One-line summary

Built and benchmarked an HNSW retrieval architecture that treats retrieved
documents as untrusted evidence instead of executable instructions, cutting
indirect-prompt-injection success from **100% to 0%** on a planted attack
corpus at **+0.22 ms/query** overhead.

## 60-second pitch

RAG systems retrieve chunks from a knowledge base and paste them into the
prompt. If anyone else can write to that knowledge base — a shared wiki, a
customer upload, a web crawl — those chunks are an injection channel, because
the model cannot tell retrieved text from its own instructions.

`rag_seal_sim` implements both a standard context-concatenation baseline and a
"logic-sealed node" architecture, and benchmarks them head to head. Retrieved
chunks are wrapped in a privilege boundary carrying provenance, a content
hash, and a closed operation set, so retrieved text is evidence and never
instruction. A provider-independent policy gate post-validates the answer,
which means the boundary holds **even when the model itself is fooled** — in
this simulation the weak provider produced compromised output on all 8 attack
queries and the gate blocked all 8 before anything reached the user.

The whole thing runs offline with no API keys, so the numbers are reproducible
by anyone in one command.

## Résumé bullets

- Designed and implemented a 9-module, ~2,700-LOC Python system (HNSW
  retrieval, sealed evidence nodes, policy gate, pluggable inference chain) with
  a fully reproducible offline benchmark — **no API keys or network required**.
- Reduced measured indirect-prompt-injection success from **100% (8/8) to 0%
  (0/8)** on a planted 8-category attack corpus, **including 2 payloads the
  input scanner failed to detect** — the defense holds at the output gate
  rather than depending on input detection.
- Demonstrated **defense-in-depth against an untrusted model**: the provider
  was compromised on 8/8 sealed queries and the provider-independent policy
  gate contained **8/8** before user exposure.
- Quantified the security boundary's cost at **+0.222 ms/query** (0.236 ms
  sealed vs 0.025 ms concat end-to-end) — negligible against real
  tens-to-hundreds-of-milliseconds generation latency.
- Benchmarked retrieval at **0.014 ms/query (~71,000 q/s) with 88.3% recall@5**
  against an exact-cosine ground truth, with a pure-Python fallback so the
  artifact runs where the native HNSW extension cannot compile.
- Verified **0% false-positive block rate** on benign queries with clean
  retrieval — the gate fires on policy-violating content, not on volume.

## Skills demonstrated

`Python` · `RAG / retrieval systems` · `HNSW / ANN indexing` · `LLM security` ·
`indirect prompt injection` · `threat modeling` · `benchmark design` ·
`measurement methodology` · `performance profiling` · `technical writing`

## Honest framing (keep this — it is the strongest part)

This is a **simulation of architectural containment**, not a production system
and not a complete solution to prompt injection. Specifically:

- Embeddings are deterministic hashed bag-of-words vectors, chosen for
  reproducibility, not retrieval quality. Recall numbers are a property of the
  index over that embedding.
- The rule-based provider is *deliberately* weak; its purpose is to model a
  model that follows instructions found in its context.
- The attack-success scorer and the policy gate overlap by construction, so
  the result measures **configured-policy containment**, not an independent
  adversarial proof. An independent evaluation would use held-out payloads and
  a separate judge.
- Untrusted-zone misclassification at ingestion, semantic misinformation, and
  deny-list evasion remain open problems.

Stating the limits precisely is why the claim is credible. Do not remove this
section to make the project sound bigger.

## Reproduce it

```bash
cd prototypes/rag_seal_sim
python3 rag_seal_sim.py status         # backend + provider availability
python3 rag_seal_sim.py attack-demo    # injection resistance (the headline)
python3 capture_results.py > results.json
```

`hnswlib` is optional; without it the pure-Python fallback runs and the
security result is unchanged.

## Where this fits

- **Best use:** portfolio credential and writing sample. It proves the ability
  to design a security boundary, measure it honestly, and write it up — which
  is what consulting clients and hiring managers actually buy.
- **Not:** a product or a revenue line. It has no users and no market on its
  own. Its value is that it makes the person who built it believable.
