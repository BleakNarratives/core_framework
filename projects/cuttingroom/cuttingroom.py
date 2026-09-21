"""cuttingroom — a language that only subtracts.

THE PREMISE, WHICH IS THE JOKE AND ALSO THE POINT
  Every other language starts from nothing and builds. This one starts from
  everything. The work is assumed complete on the first line -- bloated, overfull,
  the shape a first draft actually has -- and a Cutting Room program is a list of
  removals. What survives is the work. What was removed, with its reason, is the
  floor.

WHY EVERY CUT NEEDS `because`, AND WHY THAT IS GRAMMAR AND NOT STYLE
  `carve act2 because it repeats act1` parses. `carve act2` does not. The removal is
  the easy half and the sentence is the half that is thankless to write, so the
  language refuses to let you skip it. A program of bare cuts would produce the same
  residue and nobody could tell whether the cutter knew why.

WHY REFUSALS ARE NOT ERRORS
  Cutting something already gone, or something somebody kept, is recorded and
  execution continues. A refusal is a finding: it says this program's model of the
  work disagreed with the work. A language that halts on the first one teaches you
  to write programs that never discover anything. Only two things are fatal -- a
  malformed instruction, and a floor you cut away -- because those are the two where
  carrying on would produce a confident wrong answer instead of a stop.

CARVE IS ONE THING. SWEEP IS A SET.
  `carve` takes a single named thing and will not accept a wildcard; `sweep act1`
  empties act1 and leaves the node standing. That rule is enforced, not suggested: a
  cut you cannot name is a cut you are not making, and `carve *` is how a program
  removes everything and calls it editing.

  `*` is the whole pattern or it is nothing. There is no `act1.*`, because
  `sweep act1` already comes to exactly that -- an operator that means what another
  operator means is a way to have two programs that nobody can tell apart. `sweep *`
  survives because it is the one thing no named sweep can say: none of this is worth
  an hour.

THE FLOOR IS BOTH THE THING AND THE RECORD
  `floor act3.letter because she reads it twice` asserts what must remain. `--floor
  FILE` is where decisions land, and it holds everything that is *not* the work: the
  cuts, the keeps, the filed notes, the refusals. Two senses of one word, and both
  are the same idea seen from either side of the line.

  The log is keyed on the bulk and on the program, so a second session running the
  same program inherits its decisions instead of redoing thankless work, a session
  running a *different* program is shown the earlier reasoning as context, and a log
  from different work says so out loud instead of being applied to work it never
  described. Every decision is keyed by one function, `Instruction.key`, so a
  decision recorded and a decision inherited cannot disagree about what they are.

ONE PLACE, NOT TWO
  `--floor FILE` keeps a private log and needs nothing but this checkout. `--ledger
  ROOT` writes the floor into a Foxwood ledger's decision log instead, alongside that
  ledger's verdicts, so the cuts and the research decisions against the same work
  persist in one place. Cutting Room still runs on a checkout where Foxwood is absent,
  so the import is lazy and only the `--ledger` path pays for it.

  The shared log is read structurally in both directions: this module claims entries
  that name a work and a program, and the pipe claims entries that carry a verdict.
  Neither needs to know the other exists, which is the only way a shared file stays
  shareable.

WHAT IT IS FOR
  Nothing. Which is the honest answer and also why it works as a teambuilding
  exercise: there is no deliverable to argue about, so the only thing on the table is
  whether a reason holds. Two people and a persistent log, deciding what has to hit
  the floor for the thing to fly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1"
HERE = Path(__file__).resolve().parent


class CuttingRoomError(Exception):
    """A malformed program, or a floor that cannot hold."""


# ── grammar ──────────────────────────────────────────────────────────────────

# Full-line comments only. `#` is not stripped inline, because `file "..."` carries
# prose and prose about a play contains the word the usual comment rule would eat.
COMMENT_RE = re.compile(r"^\s*(?:#|$)")

# A reason may cite evidence in the shared ledger. `citing` was chosen over
# `proven by` on purpose: this checks that the evidence EXISTS, never that the
# reason is CORRECT, and a keyword that promised proof would be the same
# overstatement the rest of this file refuses to make. It is also far less likely to
# appear inside an ordinary sentence, so a prose reason cannot be split in half by
# accident.
_HOW = (r"because\s+(?P<why>\S.*?)"
        r"(?:\s+citing\s+(?P<proof>\S+(?:\s+\S+)*))?$")
BULK_RE = re.compile(r"^bulk\s+(?P<paths>\S+(?:\s+\S+)*)$")
KEEP_RE = re.compile(rf"^keep\s+(?P<path>\S+)\s+{_HOW}")
CARVE_RE = re.compile(rf"^carve\s+(?P<path>\S+)\s+{_HOW}")
SWEEP_RE = re.compile(rf"^sweep\s+(?P<path>\S+)\s+{_HOW}")
DRAW_RE = re.compile(rf"^draw\s+(?P<paths>\S+(?:\s+\S+)*)\s+{_HOW}")
FILE_RE = re.compile(rf'^file\s+"(?P<text>[^"]*)"\s+{_HOW}')
# `paths` is lazy and the reason is optional, because a greedy target swallows the
# `because` clause and turns a floor assertion into a list of words.
FLOOR_RE = re.compile(
    r"^floor\s+(?P<paths>\S.*?)(?:\s+because\s+(?P<why>\S.*))?$")

OPS = (("bulk", BULK_RE), ("keep", KEEP_RE), ("carve", CARVE_RE), ("sweep", SWEEP_RE),
       ("draw", DRAW_RE), ("file", FILE_RE), ("floor", FLOOR_RE))

# The ops that must carry a reason. `bulk` is existence and needs none. `floor` is
# the assertion the program exists to make, and a bare floor is a legitimate one.
NEEDS_A_REASON = ("keep", "carve", "sweep", "draw", "file")

# Ops whose target must be one nameable thing rather than a pattern.
ONE_THING_ONLY = ("keep", "carve", "floor")

# Ops that take something out of the work.
CUTTING_OPS = ("carve", "sweep", "draw")

# Ops whose reason can be cited. `floor` is left out: it asserts what must remain,
# and an assertion checked against evidence is a claim, which this language does not
# have to be -- the ledger does.
VERIFIABLE_OPS = NEEDS_A_REASON


@dataclass(frozen=True)
class Instruction:
    op: str
    targets: tuple[str, ...]
    why: str
    line: int
    text: str = ""
    proof: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        """Identity of the decision, independent of where it sits in the program.

        One function, used both to record a decision and to recognise one that was
        already made. If these were computed in two places they would drift, and the
        drift would look like a program that quietly stopped inheriting.

        A citation is part of the identity -- deciding the same thing against
        different evidence is a different decision -- but it is appended only when
        there is one, so a prose-only program keeps the keys it had before citations
        existed and a floor written earlier still inherits.
        """
        parts = [self.op, self.text, *self.targets, self.why]
        if self.proof:
            parts.extend(self.proof)
        return _sha("\x1f".join(parts))

    @property
    def cuts(self) -> bool:
        return self.op in CUTTING_OPS

    def __str__(self) -> str:
        if self.op == "file":
            base = f'file "{self.text}" because {self.why}'
        else:
            reason = f" because {self.why}" if self.why else ""
            base = f"{self.op} {' '.join(self.targets)}{reason}"
        return base + (f" citing {' '.join(self.proof)}" if self.proof else "")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def parse(text: str) -> list[Instruction]:
    """Program text -> instructions. Raises on the first line it cannot read.

    Stops at the first malformed line rather than skipping it. A skipped line is a
    cut that did not happen, in a language whose entire output is the set of cuts
    that happened -- so the failure is loud, and it names the line.
    """
    instructions: list[Instruction] = []
    for number, raw in enumerate((text or "").splitlines(), start=1):
        if COMMENT_RE.match(raw):
            continue
        line = raw.strip()
        for op, pattern in OPS:
            match = pattern.match(line)
            if not match:
                continue
            groups = match.groupdict()
            why = (groups.get("why") or "").strip()
            proof = tuple((groups.get("proof") or "").split())
            # The citation clause is optional, so a reason ending in the bare word
            # `citing` still matches with no proof group and would otherwise read as
            # prose. It is the one reserved word: it must name something.
            if not proof and why.split()[-1:] == ["citing"]:
                raise CuttingRoomError(
                    f"line {number}: `citing` needs at least one source id — a "
                    f"citation that names nothing is not a citation. Write "
                    f"`because <why> citing src-abc123`.")
            if op in NEEDS_A_REASON and not why:
                raise CuttingRoomError(
                    f"line {number}: `{op}` needs a reason — `because <why>` with "
                    f"something after it. The cut is the easy half.")
            targets = tuple((groups.get("paths") or groups.get("path") or "").split())
            if not targets and op != "file":
                raise CuttingRoomError(f"line {number}: `{op}` names nothing to act on")
            for target in targets:
                if "*" not in target or (op == "sweep" and target == "*"):
                    continue
                named = target.split("*", 1)[0].rstrip(".") or "a name"
                if op in ONE_THING_ONLY or op in ("bulk", "draw"):
                    raise CuttingRoomError(
                        f"line {number}: `{op}` takes one named thing, not `{target}`. "
                        f"A cut you cannot name is a cut you are not making; use "
                        f"`sweep` if you mean everything under it.")
                raise CuttingRoomError(
                    f"line {number}: `*` is the whole pattern, not part of one "
                    f"(`{target}`). `sweep {named}` already takes everything under "
                    f"{named}, and `sweep *` takes the lot.")
            instructions.append(Instruction(op=op, targets=targets, why=why,
                                            line=number,
                                            text=groups.get("text") or "",
                                            proof=proof))
            break
        else:
            # A line that starts with a real op but did not match is almost always a
            # missing reason, and "cannot read" would send the writer looking for the
            # wrong mistake.
            word = line.split()[0] if line.split() else ""
            if " citing " in f" {line} ":
                raise CuttingRoomError(
                    f"line {number}: `citing` needs at least one source id — a "
                    f"citation with nothing named is not a citation. Write "
                    f"`because <why> citing src-abc123`.")
            if word in NEEDS_A_REASON:
                if word == "file" and '"' not in line:
                    raise CuttingRoomError(
                        f"line {number}: `file` files a phrase, so it needs quotes: "
                        f'`file "<text>" because <why>`.')
                raise CuttingRoomError(
                    f"line {number}: `{word}` needs a reason — `because <why>` with "
                    f"something after it. The cut is the easy half.")
            raise CuttingRoomError(
                f"line {number}: cannot read `{line}`. Ops are "
                f"{', '.join(op for op, _ in OPS)}.")
    return instructions


def program_id(text: str) -> str:
    """Identity of a program: its instructions, not its whitespace or comments.

    Reformatting a program, or explaining it better in a comment, must not throw away
    the floor. Changing what it decides must. Same reasoning as the pipe's frame
    identity, which keys on the lens plan and the evidence and deliberately not on the
    seed that selected them.
    """
    return _sha("\n".join(str(i) for i in parse(text)))


# ── the room ─────────────────────────────────────────────────────────────────

@dataclass
class Room:
    """The work, and the record of everything taken out of it."""

    seed: int = 0
    present: dict[str, None] = field(default_factory=dict)   # declared order
    locks: dict[str, str] = field(default_factory=dict)      # path -> because
    declared: set[str] = field(default_factory=set)
    notes: list[dict] = field(default_factory=list)
    entries: list[dict] = field(default_factory=list)
    cuts: int = 0        # decided this run
    replayed: int = 0    # already on the floor, applied but not decided again
    unverifiable: list[str] = field(default_factory=list)   # instruction keys refused
                                                            # for a reason that could
                                                            # not be checked
    floor_paths: list[str] = field(default_factory=list)
    floor_why: str = ""

    # -- reading the work ---------------------------------------------------

    def subtree(self, path: str) -> list[str]:
        """`path` and everything under it, in declared order."""
        return [p for p in self.present if p == path or p.startswith(path + ".")]

    def descendants(self, path: str) -> list[str]:
        return [p for p in self.present if p.startswith(path + ".")]

    def resolve(self, pattern: str) -> list[str]:
        """A `sweep` target -> what it comes to. `*` is everything there is."""
        return list(self.present) if pattern == "*" else self.descendants(pattern)

    def locked_within(self, path: str) -> str:
        """The reason a kept thing lives inside `path`, or "" when nothing is kept."""
        for kept in self.locks:
            if kept == path or kept.startswith(path + ".") or path.startswith(kept + "."):
                return kept
        return ""

    def residue(self) -> list[str]:
        """The named things that survive, in declared order.

        Containers are namespaces, not content -- `act2` is a way of naming
        `act2.ballroom`, so it is never in the residue on its own account. That is
        where the bulk actually goes, and why the residue reads like a list of things
        somebody would have to defend out loud.
        """
        return [path for path in self.present if path in self.declared]

    # -- writing the floor --------------------------------------------------

    def _record(self, op: str, key: str, targets, why: str, **extra) -> None:
        self.entries.append({
            "op": op, "key": key, "targets": list(targets), "why": why,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **extra})

    def refuse(self, instruction: Instruction, because: str) -> None:
        """A finding, not a fatal. Recorded so the next session sees it too."""
        self._record("refused", instruction.key, instruction.targets, instruction.why,
                     asked=instruction.op, because=because)

    def _take(self, path: str) -> None:
        for gone in self.subtree(path):
            self.present.pop(gone, None)
        self.locks.pop(path, None)

    # -- the ops ------------------------------------------------------------

    def bulk(self, instruction: Instruction) -> None:
        for path in instruction.targets:
            parts = path.split(".")
            for index in range(1, len(parts)):
                self.present.setdefault(".".join(parts[:index]), None)
            self.present.setdefault(path, None)
            self.declared.add(path)

    def keep(self, instruction: Instruction) -> None:
        path = instruction.targets[0]
        if path not in self.present:
            self.refuse(instruction, "nothing by that name is in the work")
            return
        if path in self.locks:
            self.refuse(instruction, f"already kept because {self.locks[path]}")
            return
        self.locks[path] = instruction.why
        self._record("kept", instruction.key, [path], instruction.why)

    def carve(self, instruction: Instruction) -> None:
        path = instruction.targets[0]
        if path not in self.present:
            self.refuse(instruction, "already gone")
            return
        held = self.locked_within(path)
        if held:
            self.refuse(instruction, f"`{held}` is kept because {self.locks[held]}")
            return
        self._take(path)
        self.cuts += 1
        self._record("cut", instruction.key, [path], instruction.why)

    def sweep(self, instruction: Instruction) -> None:
        """Take the contents, leave the node. Kept things inside survive it."""
        pattern = instruction.targets[0]
        targets = self.resolve(pattern)
        if not targets:
            self.refuse(instruction, "nothing lives under it")
            return
        taken, skipped = [], []
        for path in targets:
            held = self.locked_within(path)
            if held:
                skipped.append(f"{path} ({self.locks[held]})")
                continue
            self._take(path)
            taken.append(path)
        if not taken:
            self.refuse(instruction,
                        "everything under it is kept: " + "; ".join(skipped))
            return
        self.cuts += len(taken)
        self._record("swept", instruction.key, [pattern], instruction.why,
                     took=taken, skipped=skipped)

    def draw(self, instruction: Instruction) -> None:
        """Cut exactly one of several equally defensible things, reproducibly.

        The seed picks and the seed is written down. Two identical runs make the same
        cut; two runs at different seeds make different ones. This is the one place
        the language is not deterministic, and it is not a coin flip -- it is a
        decision that was already a coin flip, made the same way twice.
        """
        names = list(instruction.targets)
        candidates = [n for n in names
                      if n in self.present and not self.locked_within(n)]
        if not candidates:
            self.refuse(instruction,
                        "none of them is present and unkept, so there is nothing to "
                        "draw from")
            return
        pick = candidates[
            int(_sha(f"{self.seed}|{instruction.why}|{'|'.join(sorted(candidates))}"),
                16) % len(candidates)]
        self._take(pick)
        self.cuts += 1
        self._record("drew", instruction.key, [pick], instruction.why,
                     seed=self.seed, from_=sorted(candidates))

    def file(self, instruction: Instruction) -> None:
        """Put something on the floor: a decision that needs no edit, only a record."""
        self.notes.append({"text": instruction.text, "why": instruction.why})
        self._record("filed", instruction.key, [instruction.text], instruction.why)

    def replay(self, entry: dict) -> None:
        """Apply a decision that is already on the floor, without re-deciding it.

        Replaying is not the same as skipping, and getting that wrong is how the
        residue comes back wrong: a run that skipped its inherited cuts would report
        the whole untouched bulk as the work. The recorded outcome is applied instead
        of re-derived, which is also the only way a `draw` survives a second run --
        the seed that picked is on the floor, so nobody has to guess it again.
        """
        # Counted separately from `cuts`: a replayed cut is work somebody already
        # did, and a report that adds the two together tells the next session it
        # decided things it only inherited.
        op = entry.get("op")
        if op in ("cut", "drew"):
            path = entry["targets"][0]
            if path in self.present:
                self._take(path)
                self.replayed += 1
        elif op == "swept":
            for path in entry.get("took", []):
                if path in self.present:
                    self._take(path)
                    self.replayed += 1
        elif op == "kept":
            self.locks[entry["targets"][0]] = entry["why"]
        elif op == "filed":
            self.notes.append({"text": entry["targets"][0], "why": entry["why"]})
        # A refusal changed nothing the first time, so it changes nothing now.

    def floor(self, instruction: Instruction) -> None:
        self.floor_paths = list(instruction.targets)
        self.floor_why = instruction.why

    def floor_violations(self) -> list[str]:
        residue = set(self.residue())
        return [path for path in self.floor_paths if path not in residue]


def execute(instructions, room: Room, *, decided: dict | None = None,
            verifier=None) -> tuple[list[Instruction], list[Instruction]]:
    """Run the program. Returns (instructions inherited, instructions refused).

    An instruction whose decision is already on the floor for this bulk and this
    program is replayed rather than decided again. It does not need deciding again:
    the work is the same, the instruction is the same, and the answer was recorded.
    That is the whole of what a persistent floor buys -- the thankless part is not
    done twice.

    `verifier` is checked BEFORE the op runs, not after. A cut whose reason cannot be
    checked does not happen: recording the decision and then reporting that its
    evidence was missing would leave the work already changed on the strength of a
    citation that never resolved. The refusal is recorded and the run continues, so
    one unverifiable cut does not hide the rest of the program.

    The verifier runs before the *replay* check too, and that ordering is the whole of
    the zero-trust rule: a decision inherited from an earlier session is re-checked
    against the rule running now. Otherwise switching `--require-verified` on would
    quietly exempt exactly the decisions most likely to predate the rule -- the floor
    would look clean while nothing about it had been re-examined. An inherited
    decision whose citation no longer resolves is refused on this run, the run fails
    loudly, and nobody is handed a residue that a stricter rule would not have
    produced.
    """
    decided = decided or {}
    was_there, refusals = [], []
    for instruction in instructions:
        if verifier is not None and instruction.op in VERIFIABLE_OPS:
            problem = verifier(instruction)
            if problem:
                room.refuse(instruction, problem)
                room.unverifiable.append(instruction.key)
                refusals.append(instruction)
                continue
        replayable = decided.get(instruction.key)
        if replayable is not None:
            was_there.append(instruction)
            room.replay(replayable)
            continue
        before = len(room.entries)
        handler = getattr(room, instruction.op)
        handler(instruction)
        if any(entry["op"] == "refused" for entry in room.entries[before:]):
            refusals.append(instruction)
    return was_there, refusals


# ── the floor, on disk ───────────────────────────────────────────────────────

def _owns_floor(entry: dict) -> bool:
    """A floor entry is one that names a work and the program that decided about it.

    Structural, and deliberately not a check on `kind`. The shared log is written by
    two writers who each ignore what they do not recognise, and a filter keyed on a
    discriminator introduced later would ignore every entry written before it -- the
    same class of mistake as a lock nobody turned.
    """
    return "op" in entry and "bulk" in entry and "program" in entry


def load_floor(path: Path) -> list[dict]:
    """Read the floor, keeping only this module's own decisions.

    An unreadable line is skipped, never fatal. A log is a record of work already
    done, and failing to parse one must not stop the next person from working. What
    it must not do is pretend the decisions were read, so the caller counts what it
    got and reports it.
    """
    path = Path(path)
    if not path.is_file():
        return []
    entries = []
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and _owns_floor(entry):
            entries.append(entry)
    return entries


def find_repo_root() -> Path | None:
    """Walk up to the repository root: PROVENANCE.md plus src/foxwood_research.

    Both are required, not either. PROVENANCE.md alone is the classification registry
    and lives at the root; src/foxwood_research alone could be a vendored copy.
    Needing both is what makes this the root rather than a directory that happens to
    look like one. The same rule herald uses, for the same reason.
    """
    for parent in (HERE, *HERE.parents):
        if (parent / "PROVENANCE.md").is_file() \
                and (parent / "src" / "foxwood_research").is_dir():
            return parent
    return None


def _import_ledger():
    """Import the Foxwood ledger lazily, only on the path that asked for it.

    Cutting Room has to run on a checkout where Foxwood is absent -- it is a project
    in this repository, not a dependency of it -- so this lives here rather than at
    module scope. No import, no cost, and no new way for the language to fail to
    start.
    """
    root = find_repo_root()
    if root is None:
        raise RuntimeError(
            f"no repository root found above {HERE} (looking for PROVENANCE.md and "
            f"src/foxwood_research); --ledger needs both")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from src.foxwood_research import ledger as ledger_module
    except Exception as exc:
        raise RuntimeError(f"Foxwood is not importable from {root}: {exc}") from exc
    return ledger_module


def _ledger_has(ledger, name: str) -> bool:
    """Is `name` a source or a claim already recorded in this ledger?"""
    for lookup in (ledger.get_source, ledger.get_claim):
        try:
            lookup(name)
            return True
        except Exception:
            continue
    return False


def make_verifier(ledger, require_verified: bool):
    """Check a decision's citation against the ledger: a problem, or None.

    WHAT THIS PROVES, AND WHAT IT DOES NOT. It proves the evidence exists and was
    recorded -- with a hash and a licence -- before the decision was taken. It does
    not prove the reason is correct: `because it is dull citing src-abc` verifies the
    moment src-abc exists, and nothing here can read the cut and disagree. This is a
    citation gate, not a truth gate, exactly as the research pipe's is. Calling it
    proof would be the overstatement this file keeps refusing to make.

    `require_verified` closes the remaining door: with it on, a reason that cites
    nothing at all is refused too, so a program cannot satisfy the gate by saying less.
    """
    def verify(instruction: Instruction) -> str | None:
        if not instruction.proof:
            if not require_verified:
                return None
            return ("no evidence cited, and this run requires every reason to cite "
                    "something")
        missing = [name for name in instruction.proof if not _ledger_has(ledger, name)]
        if missing:
            return (f"nothing in the ledger is named {', '.join(missing)}; a citation "
                    f"to evidence that does not exist is not a citation")
        return None
    return verify


def save_floor(path: Path, entries) -> None:
    """Append, each line self-describing. Never rewrite: the floor is a history."""
    if not entries:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")


def inheritance(entries, bulk_id: str, prog_id: str):
    """(decisions to replay, a previous program's decisions, other work).

    The later entry wins for a repeated key: a `--redo` run appends its new decision,
    and the floor is a history, so the most recent reading of the same instruction is
    the one that holds.
    """
    decided = {}
    for entry in entries:
        if entry.get("bulk") == bulk_id and entry.get("program") == prog_id \
                and entry.get("key"):
            decided[entry["key"]] = entry
    prior = [entry for entry in entries
             if entry.get("bulk") == bulk_id and entry.get("program") != prog_id]
    stale = [entry for entry in entries if entry.get("bulk") != bulk_id]
    return decided, prior, stale


# ── cli ──────────────────────────────────────────────────────────────────────

def report(room: Room, inherited, prior, stale, seed) -> str:
    lines = [f"cuttingroom {VERSION} — seed {seed}, {len(room.residue())} still "
             f"standing, {room.cuts} cut this run"]
    if room.replayed:
        lines.append(f"  {room.replayed} cut(s) replayed from the floor — applied so "
                     f"the residue is right, not decided again")
    if inherited:
        lines.append(f"  inherited {len(inherited)} decision(s) already on the floor "
                     f"for this program and this bulk")
    if prior:
        lines.append(f"  a previous program left {len(prior)} decision(s) for this "
                     f"bulk; shown as the floor, not applied")
    if stale:
        lines.append(f"  the floor holds {len(stale)} decision(s) for other work; not "
                     f"applicable here and not used")
    lines.append("residue:")
    for path in room.residue():
        lines.append(f"  {path}")
    if not room.residue():
        lines.append("  (nothing — everything named was cut)")
    lines.append("the floor:")
    for instruction in inherited:
        lines.append(f"  (already) {instruction}")
    if not room.entries and not inherited:
        lines.append("  (empty)")
    for entry in room.entries:
        op = entry["op"]
        target = ", ".join(str(t) for t in entry["targets"])
        # cited / asserted, said on the line itself. A reader scanning the floor should
        # not have to cross-reference the program to learn which cuts had evidence.
        suffix = (f"  [cited: {', '.join(entry['proof'])}]"
                  if entry.get("proof") else "  [asserted, nothing cited]")
        if op == "filed":
            line = f'  filed   "{target}" — because {entry["why"]}'
        elif op == "refused":
            line = (f'  refused {entry["asked"]} {target} — because '
                    f'{entry["because"]} (asked because {entry["why"]})')
            suffix = ""
        elif op == "drew":
            line = (f'  drew    {target} of {", ".join(entry["from_"])} — '
                    f'because {entry["why"]} (seed {entry["seed"]})')
        elif op == "swept":
            line = (f'  swept   {target} → left standing inside it: '
                    f'{", ".join(entry["skipped"]) or "nothing"} — because '
                    f'{entry["why"]}')
        else:
            line = f'  {op:<7} {target} — because {entry["why"]}'
        lines.append(line + suffix)
    if room.floor_paths:
        holds = not room.floor_violations()
        lines.append(f"floor assertion: {'holds' if holds else 'does NOT hold'} — "
                     f"{room.floor_why or 'no reason given'}")
    cited = sum(1 for entry in room.entries if entry.get("proof"))
    settled = sum(1 for entry in room.entries if entry["op"] != "refused")
    if settled:
        lines.append(f"reasons: {cited} backed by evidence in the ledger, "
                     f"{settled - cited} asserted with nothing cited")
    if room.unverifiable:
        lines.append(f"refused on evidence: {len(room.unverifiable)} decision(s) "
                     f"could not have their reason checked")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cuttingroom",
        description="A language that only subtracts: bulk everything in, cut what has "
                    "to hit the floor.")
    parser.add_argument("program", help="the program to run")
    parser.add_argument("--floor", default=None, metavar="FILE",
                        help="append decisions here, and inherit the ones this bulk "
                             "and this program already decided")
    parser.add_argument("--ledger", default=None, metavar="ROOT",
                        help="write the floor into this Foxwood ledger's one decision "
                             "log instead of a private file, so cuts and verdicts "
                             "against the same work persist in one place")
    parser.add_argument("--require-verified", action="store_true",
                        help="refuse any decision whose reason does not cite evidence "
                             "in the ledger, and exit non-zero if anything was "
                             "refused for that")
    parser.add_argument("--seed", type=int, default=0,
                        help="seed for `draw` (default 0; the choice is recorded)")
    parser.add_argument("--redo", action="store_true",
                        help="ignore the floor's inherited decisions and decide again")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    # Two logs to choose between, never both. Picking one silently would decide for
    # the operator which record their decisions went into.
    if args.floor and args.ledger:
        print("cuttingroom: --floor names a private log and --ledger names the "
              "shared one; give one, not both", file=sys.stderr)
        return 2

    path = Path(args.program).expanduser()
    if not path.is_file():
        print(f"cuttingroom: no program at {path}", file=sys.stderr)
        return 2
    text = path.read_text(errors="replace")
    try:
        instructions = parse(text)
        prog_id = program_id(text)
    except CuttingRoomError as exc:
        print(f"cuttingroom: {exc}", file=sys.stderr)
        return 2

    room = Room(seed=args.seed)
    # The bulk declares existence, and its identity has to be known before the rest
    # runs so the floor can be matched to it -- so the tree is built first and the
    # remaining instructions run over it. Re-running `bulk` in `execute` is
    # idempotent, which keeps `execute` a complete interpreter of any program.
    for instruction in instructions:
        if instruction.op == "bulk":
            room.bulk(instruction)
    bulk_id = _sha("|".join(sorted(room.declared)))

    shared = None
    if args.ledger:
        try:
            shared = _import_ledger()
        except RuntimeError as exc:
            print(f"cuttingroom: {exc}", file=sys.stderr)
            return 2
        log = shared.decision_log_path(args.ledger)
    else:
        log = Path(args.floor).expanduser() if args.floor else None
    # A citation needs somewhere to be checked. Refusing here rather than inside the
    # verifier keeps the failure where the operator is looking -- "no ledger given",
    # not a mysterious "nothing is named src-abc".
    verifier = None
    if any(instruction.proof for instruction in instructions) or args.require_verified:
        if shared is None:
            print("cuttingroom: a reason can only be checked against a ledger, and "
                  "--ledger was not given", file=sys.stderr)
            return 2
        try:
            evidence = shared.ResearchLedger(args.ledger)
        except Exception as exc:
            print(f"cuttingroom: the ledger at {args.ledger} could not be read: {exc}",
                  file=sys.stderr)
            return 2
        verifier = make_verifier(evidence, args.require_verified)

    entries = [] if args.redo or log is None else (
        shared.read_decisions(log, _owns_floor) if shared else load_floor(log))
    decided, prior, stale = inheritance(entries, bulk_id, prog_id)
    was_there, refusals = execute(instructions, room, decided=decided,
                                  verifier=verifier)
    # An op that ran got past the verifier, so its citation resolved. Recording that
    # on the decision is what makes a later reader able to tell a cited cut from an
    # asserted one without re-reading the program.
    cited = {i.key: i.proof for i in instructions if i.proof}
    for entry in room.entries:
        if entry["op"] != "refused" and entry["key"] in cited:
            entry["proof"] = list(cited[entry["key"]])
            entry["verified"] = True

    for entry in room.entries:
        entry["bulk"] = bulk_id
        entry["program"] = prog_id
    if log:
        # `--redo` means the new decision is the one that holds, so the duplicates it
        # deliberately produces are written rather than filtered away.
        already = set() if args.redo else {entry.get("key") for entry in entries}
        written = [entry for entry in room.entries if entry["key"] not in already]
        if shared:
            # `kind` names the writer, and it only earns its place in a file that has
            # more than one writer. A private log keeps the older, plainer shape.
            for entry in written:
                entry["kind"] = shared.KIND_DECISION
            shared.append_decisions(log, written)
        else:
            save_floor(log, written)

    rank = len(room.residue())
    effective_cuts = room.cuts + room.replayed
    if args.json:
        print(json.dumps({
            "version": VERSION, "seed": args.seed, "bulk": bulk_id,
            "program": prog_id, "residue": room.residue(),
            "cuts": effective_cuts, "cuts_this_run": room.cuts,
            "replayed": room.replayed,
            "inherited": [str(i) for i in was_there],
            "prior": len(prior), "stale": len(stale),
            "refused": [str(i) for i in refusals],
            "floor": room.floor_paths, "floor_why": room.floor_why,
            "floor_holds": not room.floor_violations(),
            "entries": room.entries,
            "standing": rank,
            "log": str(log) if log else None,
            "shared": bool(shared),
            "cited": sum(1 for entry in room.entries if entry.get("proof")),
            "unverifiable": len(room.unverifiable),
        }, indent=2, sort_keys=True))
    else:
        print(report(room, was_there, prior, stale, args.seed))
        if log:
            print(f"floor log: {log}"
                  + (" (shared with the Foxwood ledger)" if shared else ""))
        if refusals:
            print(f"refused {len(refusals)} instruction(s); they are on the floor and "
                  f"the run continued")

    violations = room.floor_violations()
    if violations:
        print(f"\nyou cut the thing that made it fly: {', '.join(violations)}",
              file=sys.stderr)
        return 1
    if args.require_verified and room.unverifiable:
        print(f"\n{len(room.unverifiable)} decision(s) refused: their reason could not "
              f"be checked against the ledger", file=sys.stderr)
        return 1
    if not effective_cuts:
        print("\na program that cuts nothing has not started", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
