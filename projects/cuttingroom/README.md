# Cutting Room

A language that only subtracts.

Every other language starts from nothing and builds. This one starts from everything.
The work arrives complete and overfull — the shape a first draft actually has — and a
program is a list of removals. What survives is the work. What was removed, with its
reason, is **the floor**.

```bash
python cuttingroom.py examples/the_play.cr --floor /tmp/floor.jsonl --seed 4
```

```
cuttingroom 0.1 — seed 4, 2 still standing, 4 cut this run
residue:
  cast.hero
  act3.letter
the floor:
  kept    act3.letter — because she reads it twice and it is the only time she does
  cut     act1.opening — because the play starts at the ballroom
  swept   act1 → left standing inside it: nothing — because act one is one joke told twice
  cut     cast.brother — because the play works without him
  drew    act2.ballroom of act2.ballroom, cast.hero — because only one of them can
          carry the last scene (seed 4)
  filed   "the brother's letter" — because cutting him left a letter with no sender
floor assertion: holds — it is the spine, and everything above was arranged around it
```

## The ops

| Op | What it does |
|---|---|
| `bulk <path>...` | Declare something that exists. Containers are implied by dots. No reason needed: existence is given. |
| `keep <path> because <why>` | Lock one thing so no later op can take it. |
| `carve <path> because <why>` | Remove one named thing and everything under it. |
| `sweep <path> because <why>` | Empty a node; the node itself stands if anything kept survives inside. |
| `sweep * because <why>` | Take everything. |
| `draw <a> <b> ... because <why>` | Cut exactly one of several equally defensible things. The seed picks; the seed is recorded. |
| `file "<text>" because <why>` | Put a note on the floor. Not an edit — a record, so nobody goes looking for a letter with no sender. |
| `floor <path>... [because <why>]` | Assert what must remain. If it isn't in the residue, the run fails. |

`#` is a **full-line** comment. It is not stripped inline, because `file "..."`
carries prose and prose about a play contains the word the usual rule would eat.

## The four rules that are the language

**1. Every cut needs `because`. It is grammar, not style.**
`carve act2 because it repeats act1` parses. `carve act2` does not. The removal is the
easy half and the sentence is the half that is thankless to write, so the language
refuses to let you skip it. A program of bare cuts would produce the same residue and
nobody could tell whether the cutter knew why.

**2. A refusal is a finding, not a fatal.**
Cutting something already gone, or something somebody kept, is recorded and execution
continues. Only two things stop a run: a malformed instruction, and a floor you cut
away — the two cases where carrying on would produce a confident wrong answer instead
of a stop.

**3. Carve is one thing. Sweep is a set.**
`carve` will not accept a wildcard; `sweep act1` takes what lives under `act1`. `*` is
the whole pattern or it is nothing — there is no `act1.*`, because `sweep act1` already
comes to exactly that, and two operators that mean one thing are two programs nobody
can tell apart.

**4. The residue is only what somebody would have to defend.**
Containers are namespaces, not content. `act2` is a way of naming `act2.ballroom`, so
it is never in the residue on its own account. The named things that survive are the
work.

## The floor persists, in one of two places

`--floor FILE` is a private log and needs nothing but this checkout. `--ledger ROOT`
writes the floor into a **Foxwood ledger's** decision log instead, alongside that
ledger's verdicts, so the cuts and the research decisions taken against the same work
persist in one place instead of two:

```bash
python cuttingroom.py examples/the_play.cr --ledger foxwood_data --seed 4
```

The log is shared and each reader claims only what it recognises: this language
claims entries that name a work and a program, the pipe claims entries carrying a
verdict. Neither needs to know the other exists. Giving both `--floor` and `--ledger`
is refused rather than resolved by precedence — picking one silently would decide for
you where your decisions went.

The path is defined once, by `ledger.decision_log_path`, so the two writers cannot
disagree about where "the same place" is. Cutting Room still runs on a checkout with
no Foxwood at all: the import is lazy and only the `--ledger` path pays for it.

Either way, the log holds everything that is *not* the work: cuts, keeps, filed
notes, refusals. Reach for it the next day:

```
cuttingroom 0.1 — seed 4, 2 still standing, 0 cut this run
  4 cut(s) replayed from the floor — applied so the residue is right, not decided again
  inherited 6 decision(s) already on the floor for this program and this bulk
```

Inherited decisions are **replayed, not skipped**. Skipping them would leave the work
untouched and report the entire original bulk as the residue — the most confident
possible wrong answer. Replay applies the *recorded outcome*, which is also the only
way a `draw` survives a second run: the seed that picked is on the floor, so nobody has
to guess it again.

The log is keyed on the **bulk** and on the **program**, so:

- same program, same work → every decision inherited, nothing decided twice;
- a *different* program over the same work → the earlier decisions are shown as
  context and **not** applied, because they describe a program that is not this one;
- a log from different work → said out loud, not used.

`--redo` decides again rather than inheriting, which is what you want when the coin
should be re-flipped: `--seed 9 --redo`.

Program identity is its instructions, not its whitespace or comments — reformatting a
program, or explaining it better, must not throw away the floor. Changing what it
*decides* must.

Exits: `0` the floor holds · `1` you cut the thing that made it fly, or the program cut
nothing · `2` the program is malformed, missing, or asked for two logs at once.

## Tests

```bash
cd projects/cuttingroom && python -m unittest discover -s tests -t . -v
```

## What it is for

Nothing. That is the honest answer and also why it works as a two-chair exercise: there
is no deliverable to argue about, so the only thing on the table is whether a reason
holds. One person and one model, a persistent floor, deciding what has to hit the
ground for the thing to fly — and a log that makes the next session start from what was
already decided instead of from nothing.
