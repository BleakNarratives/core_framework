# Cascade Arbitration

**Decide per request whether local inference is even eligible — in 20 seconds, instead of finding out with a 5-minute thrash.**

Small local models are everywhere now: Chromebooks, Mini PCs, edge boxes, air-gapped
machines, spare servers. Everyone hits the same wall and solves it the same way —
by trying, and waiting.

This measures your host and tells you what it can actually do, before you spend five
minutes discovering it can't.

---

## The problem

On a small host, a local model is **not a slower version of a cloud model. It is a
different tool.** Three things get conflated, and all three are wrong:

| The common question | Why it fails |
|---|---|
| "Is the local model up?" | Always yes. Useless. |
| "Is the local model smarter?" | No, and it was never the question. |
| "Is the local model good enough?" | Unanswerable without a latency budget. |

The question that *is* useful: **is this particular request one that a 4 tok/s model
can still do well?** Classification, routing, extraction, dedup and short summarization
— yes, and they are most of what an agent stack dispatches. Long-form generation,
multi-step reasoning, code authoring — no, because a slow wrong answer costs more
than a fast cloud one.

Nobody is arbitrating that today. LLM routers assume the tiers are the same *kind* of
thing and differ in quality, so they order by "best model first." That is backwards
for a 1B model on a 2.6GB box.

## The two things this gets right

**1. Resident bytes, not disk bytes.**

```
llama3.2:1b   1.3 GB on disk  →  505 MB resident
gemma:2b      1.7 GB on disk  →  ~1.6 GB resident
```

A model that cannot stay resident is not slow, it is **ineligible**. It will thrash to
disk and the host will fall over. The resident figure is what decides, and it is not
the number on the download page. If the size is unmeasured, this fails closed.

**2. Failure measured, not discovered.**

```
$ python3 bench.py
{ "local_usable": false,
  "probe": { "gen_tok_per_s": 10.84, "load_s": 16.55,
             "resident_mb": 1317 },
  "profile": { "available_ram_mb": 275, "cpu_cores": 4, "has_gpu": false } }
```

`1317MB resident > 275MB available` → the local tier is off, in 20 seconds. Without
this, the same fact is discovered by watching the box page out ~109GB, hit load average
13 on 4 cores, and wedge a process in uninterruptible `D` state. That is not a
hypothetical; that is the measurement that produced this package.

## Try it

```bash
python3 bench.py                  # measure THIS host, emit a profile
python3 demo.py                   # see the decisions it implies
python3 demo.py --host-gpu        # the same workload on a big GPU box
python3 -m unittest test_cascade -v   # 21 tests, all offline
```

No dependencies beyond the standard library. `bench.py` optionally probes a local
Ollama over loopback and degrades silently if it isn't running.

## The decisions

```
  task                                   tier    why
  --------------------------------------------------------------------------
  tag this document's language           local   shape 'classify' is local-eligible
  pick the next tool to call             local   shape 'route' is local-eligible
  pull name/email/org from a lead        local   shape 'extract' is local-eligible
  are these two issues duplicates?       local   shape 'dedup' is local-eligible
  3-sentence summary                     local   shape 'summarize_short' is local-eligible
  write a 900-word article               CLOUD   shape 'generate' is not local-eligible
  debug this stack trace                 CLOUD   shape 'reason' is not local-eligible
  refactor this function                 CLOUD   shape 'code_write' is not local-eligible
  summarise a 100k-token corpus          CLOUD   input 100000 tok exceeds ceiling 2048
```

Every escalation carries its reason. A decision you cannot justify after the fact is
not one to act on.

## What it deliberately is not

- **Not a router.** It does not make HTTP calls or talk to Ollama. It is a pure
  function of `(request, host)`, so it is testable and reproducible.
- **Not an authority.** `CascadeDecision.eligible` is a *recommendation*. Nothing here
  grants or revokes privilege — if you have a permission system, that system still
  decides. A capability declaration is not permission.
- **Not a benchmark suite.** One model, one host, real numbers, and a way for you to
  generate your own.

## Who this is for

You have a box that's good enough for a small model and you keep re-discovering that it
isn't good enough for *some* things. This tells you which, in one run.

## Honest limits

- Token ceilings (256 output / 2048 input) are deliberately conservative defaults, not
  derived from first principles. Tune them per workload.
- Throughput on a shared box **decays as other work loads the machine** — the same
  model measured 4.12 tok/s early in a session and far less later. Profile right
  before you decide, not from a number you saved in March.
- "Local" here means small and on-device. Speculative decoding (2–3x on CPU with a
  small draft model) would raise the ceiling, but needs both models resident, which
  this exact arithmetic will tell you is out of reach on a small box.

## License

MIT.
