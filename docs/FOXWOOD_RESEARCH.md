# Foxwood Research Ledger

Foxwood Research Ledger is a clean-room, provenance-first research collector. It
is intentionally not a copy or wrapper of the foreign `ScholarScout/` checkout.
It does not import that repository, its prompts, its skills, its fetchers, or its
branding.

## Core contract

- Sources are stored with a stable ID, URL, publisher, retrieval timestamp,
  SHA-256 content hash, excerpt, and license note.
- Claims cannot be recorded without one or more source IDs already present in the
  ledger.
- Markdown exports print claim citations and source hashes together.
- Known foreign workspace paths, including `ScholarScout/` and
  `ScholarScoutSwarm/`, are rejected before ingestion. This is two locks: the
  module's built-in list, which is code and cannot be edited away, and the
  `PROVENANCE.md` registry, which is data and can be extended without a code
  change. Neither substitutes for the other.
- Network input is bounded, stripped to inert text, and never executed.
- Private and local network URLs are rejected.

## Minimal usage

Search public metadata without a key:

```bash
python -m src.foxwood_research search "graph neural networks" --provider both --limit 5
```

The default store is `foxwood_data/ledger`; use `--store /path/to/ledger` to
choose another directory. The first adapters are OpenAlex and Crossref, and
network responses are mocked in the test suite.

Python usage:

```python
from pathlib import Path
from src.foxwood_research import ResearchLedger

ledger = ResearchLedger(Path("foxwood_data/ledger"))
source = ledger.fetch_source(
    title="A public source",
    url="https://example.org/article",
    publisher="Example",
    license_note="review before redistribution",
)
claim = ledger.add_claim(
    text="A statement supported by the source.",
    source_ids=[source.source_id],
    confidence="medium",
)
packet = ledger.packet("my research question", [claim])
print(packet.to_markdown(ledger))
```

Public metadata discovery feeds the trustworthy evidence and attribution spine.
Every layer added after it must consume `SourceRecord` and emit registered
`Claim` objects rather than bypassing the ledger, and `pipe.py` below is the
worked example of that rule.

## The pipe: evidence in, gated non-static claims out

`synthesize` asks one fixed question of one model at temperature 0, so
near-identical evidence comes back as near-identical prose. The guard rails were
right and the output was static. `pipe.py` keeps the rails and varies the
question.

```bash
# see exactly what will be asked, calling no model
python -m src.foxwood_research pipe "what changed in this area?" \
    --source-id src-abc123 --seed 7 --dry-run

# ask, audit, and persist
python -m src.foxwood_research pipe "what changed in this area?" \
    --source-id src-abc123 --seed 7 --model openai/gpt-oss-120b \
    --output packets/area.md
```

Five stages run in a fixed order:

1. **Admit.** Every source re-enters through the `PROVENANCE.md` registry gate,
   including sources stored before the gate existed.
2. **Frame.** A seeded lens builds the prompt. Five lenses ship:
   `synthesize`, `counterfactual`, `adversarial`, `rank`, `refine`.
3. **Ask.** One model front end goes through `bin/ai`, so key rotation, cooldown
   and quarantine behave the same as everywhere else in this repository. Run on
   the gateway's rotating pool deliberately (`--model` omitted) and the run is
   recorded as `auto (unpinned)`, because pool selection is not reproducibility.
4. **Audit.** The MOLT Oracle scans the proposed text before anything is
   persisted. `prompt_injection` and `xss_injection` block; findings about code or
   keys are recorded on the claim instead, because a research corpus legitimately
   quotes `subprocess.run` and a gate that refuses that is a gate operators route
   around.
5. **Record.** Accepted claims go to the ledger; every other outcome goes to the
   ledger's one append-only decision log, because a refusal is a finding and not
   copy.

That log is `verdicts.jsonl`, and the name is kept from the first thing that wrote
here rather than changed to something honest like `decisions.jsonl`, because
renaming a log is a way to lose the log. It is now **shared**: the pipe writes
verdicts, and Cutting Room (`projects/cuttingroom --ledger ROOT`) writes floors into
the same file, so the decisions taken against one body of evidence persist in one
place instead of two. Each reader claims only the entries it recognises -- the pipe
claims entries carrying a `verdict`, Cutting Room claims entries naming a work and a
program -- and both decide that *structurally*, never by checking `kind`, because a
filter keyed on a discriminator introduced later would ignore every line written
before it existed. `kind` is for a human reading the file.

The shared path is defined once, in `ledger.py`'s `decision_log_path`, so two writers
cannot disagree about where "the same place" is.

A seed is how a plan is *chosen*, never part of what a question *is*. That
distinction is now enforced: a question's identity is `(lens plan, evidence)` and
nothing else. Two seeds that select the same lens ask the identical question and
share one identity, so the verdict ledger reports work as done rather than as
undone. Replay uses `(seed, lens, model, source hashes)`; `--redo` is how you ask
an answered question again on purpose, exactly as in `herald`.

### Proving it is not static

The `diversity` subcommand is a gate, not a report. It builds the frames for a
range of seeds, calls no model, and exits non-zero the moment the framing goes
static:

```bash
python -m src.foxwood_research --store DIR diversity --source-id src-abc123
python -m src.foxwood_research --store DIR diversity --source-id src-abc123 --markdown
```

It checks that the same seed replays exactly, that a lens's prompt does not depend
on the seed, that the five lenses produce five different prompts, that a lens
carries one frame ID across seeds and no two lenses share one, that consecutive
seeds actually reach every lens, and that every frame fits its bound.

No model is called, and that is deliberate. A model call is not reproducible --
`bin/ai` without a pinned `--model` rotates gateway pools, so the same prompt
returns different text on different calls -- and an eval built on one measures pool
selection rather than this code. Framing is what the pipe guarantees, so framing is
what gets measured.

**Two real defects came out of writing that probe**, which is the argument for
having it. The first version of the seed function hashed the seed and took a
modulus: reproducible, and also uneven, reaching four of five lenses over seeds
0..11 so that `refine` was simply unreachable in that range. It is now an arithmetic
walk whose step is coprime with the lens count, so any five consecutive seeds reach
every lens exactly once. The second was the identity bug described above.

### Herald reads the ledger

`projects/herald/outreach_agent.py` can cite this ledger, so a draft points at
something real instead of gesturing at "code you can read":

```bash
cd projects/herald
python outreach_agent.py --about-file ABOUT.md \
    --evidence-ledger ~/foxwood_data/ledger --dry-run
python outreach_agent.py --about-file ABOUT.md \
    --evidence-ledger ~/foxwood_data/ledger --evidence-claim claim-abc123
```

Two rules govern that path. `ABOUT.md` stays the only place a claim about the
operator may come from; the ledger lines only say what the existing claims rest on,
and the model is told in the prompt never to imply those artifacts live inside the
prospect's system. And every source is admitted through the `PROVENANCE.md`
registry gate before it can reach a prompt, which is how the last bullet of
`ABOUT_EVIDENCE.md` stops being a wish.

A ledger that was asked for and cannot be read fails the run with exit 2. It does
not quietly become "no evidence available" while the drafts go out weaker than the
operator believes.

Before public release, run the repository provenance checker against the output
and review every source license manually.
