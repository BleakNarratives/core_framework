"""Cutting Room's rules, pinned.

Every test here is a claim the language makes about itself: a cut without a reason
does not parse, a refusal is not a fatal, carve is one thing and sweep is a set, a
floor you cut away fails the run, and a floor on disk keeps a second session from
redoing the thankless half.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cuttingroom as cr  # noqa: E402


def residue_of(output: str) -> list[str]:
    """Pull the residue block out of a printed report, for comparing two runs."""
    lines = output.splitlines()
    start = lines.index("residue:") + 1
    end = lines.index("the floor:")
    return [line.strip() for line in lines[start:end]]


def run(text: str, seed: int = 0, decided=None):
    """Parse and execute a program the same way `main` does."""
    room = cr.Room(seed=seed)
    instructions = cr.parse(text)
    for instruction in instructions:
        if instruction.op == "bulk":
            room.bulk(instruction)
    was_there, refusals = cr.execute(instructions, room, decided=decided)
    return room, was_there, refusals


PLAY = """\
# what the play currently is, before anyone has been honest about it
bulk cast.hero
bulk cast.brother
bulk act1.opening
bulk act1.dinner
bulk act2.ballroom
bulk act3.letter

keep act3.letter because she reads it twice and it is the only time she does
carve act1.opening because the play starts at the ballroom
sweep act1 because act one is one joke told twice
carve cast.brother because the play works without him
draw cast.hero act2.ballroom because only one of them can carry the last scene
file "the brother's letter" because cutting him left a letter with no sender
floor act3.letter because it is the spine
"""


class TestGrammar(unittest.TestCase):
    def test_a_cut_without_a_reason_does_not_parse(self):
        with self.assertRaises(cr.CuttingRoomError) as caught:
            cr.parse("bulk act2.ballroom\ncarve act2.ballroom")
        self.assertIn("line 2", str(caught.exception))
        self.assertIn("needs a reason", str(caught.exception))

    def test_a_reason_with_nothing_after_it_does_not_parse(self):
        with self.assertRaises(cr.CuttingRoomError) as caught:
            cr.parse("carve act2 because   ")
        self.assertIn("needs a reason", str(caught.exception))

    def test_bulk_needs_no_reason_because_existence_is_given(self):
        self.assertEqual(len(cr.parse("bulk act2.ballroom")), 1)

    def test_floor_needs_no_reason_but_accepts_one(self):
        self.assertEqual(cr.parse("floor act3").pop().why, "")
        self.assertEqual(cr.parse("floor act3 because it is the spine").pop().why,
                         "it is the spine")

    def test_carve_will_not_accept_a_wildcard(self):
        with self.assertRaises(cr.CuttingRoomError) as caught:
            cr.parse("carve act1.* because it drags")
        self.assertIn("one named thing", str(caught.exception))
        self.assertIn("sweep", str(caught.exception))

    def test_the_same_rule_guards_keep_and_floor(self):
        for line in ("keep act1.* because it matters",
                     "floor act1.* because it is the spine"):
            with self.subTest(line=line), self.assertRaises(cr.CuttingRoomError):
                cr.parse(line)

    def test_the_only_pattern_is_a_bare_star(self):
        # `sweep act1` already comes to exactly what `sweep act1.*` would mean, so
        # the dotted form is refused rather than quietly behaving the same way.
        with self.assertRaises(cr.CuttingRoomError) as caught:
            cr.parse("sweep act1.* because it drags")
        self.assertIn("the whole pattern", str(caught.exception))
        self.assertIn("sweep act1", str(caught.exception))
        self.assertEqual(cr.parse("sweep * because none of it is worth an hour")
                         .pop().targets, ("*",))

    def test_a_star_is_not_a_thing_to_name_for_the_cutting_ops(self):
        for line in ("bulk *", "draw * act2 because one of them must go"):
            with self.subTest(line=line), self.assertRaises(cr.CuttingRoomError):
                cr.parse(line)

    def test_an_unreadable_line_names_itself_and_the_ops(self):
        with self.assertRaises(cr.CuttingRoomError) as caught:
            cr.parse("bulk act1.opening\npolish act1 because it is dull")
        message = str(caught.exception)
        self.assertIn("line 2", message)
        self.assertIn("polish act1", message)
        self.assertIn("carve", message)

    def test_a_bad_line_stops_the_program_rather_than_being_skipped(self):
        with self.assertRaises(cr.CuttingRoomError):
            cr.parse("carve act1 because it drags\nnonsense here\ncarve act2 because it drags")

    def test_blank_lines_and_comment_lines_are_ignored(self):
        parsed = cr.parse("# why\n\n   \nbulk act1\n")
        self.assertEqual([str(i) for i in parsed], ["bulk act1"])
        self.assertEqual(parsed[0].line, 4)

    def test_a_hash_inside_filed_prose_survives(self):
        # The usual inline-comment rule would eat this. It is prose about a play.
        instruction = cr.parse('file "act 2 # the joke again" because it repeats')[0]
        self.assertEqual(instruction.text, "act 2 # the joke again")

    def test_an_op_with_no_target_is_rejected(self):
        with self.assertRaises(cr.CuttingRoomError):
            cr.parse("floor")


class TestProgramIdentity(unittest.TestCase):
    def test_comments_and_spacing_do_not_change_a_program(self):
        plain = "carve act1 because it drags"
        annotated = "# the opening is slow\ncarve   act1   because it drags\n"
        self.assertEqual(cr.program_id(plain), cr.program_id(annotated))

    def test_changing_a_reason_changes_the_program(self):
        self.assertNotEqual(cr.program_id("carve act1 because it drags"),
                            cr.program_id("carve act1 because it repeats act two"))

    def test_changing_what_is_cut_changes_the_program(self):
        self.assertNotEqual(cr.program_id("carve act1 because it drags"),
                            cr.program_id("carve act2 because it drags"))

    def test_an_instruction_key_is_one_function(self):
        # The key a decision is recorded under and the key it is inherited by are
        # produced by the same property, so they cannot drift apart.
        instruction = cr.parse("carve act1 because it drags")[0]
        self.assertEqual(instruction.key, cr.parse("carve act1 because it drags")[0].key)
        self.assertNotEqual(instruction.key,
                            cr.parse("sweep act1 because it drags")[0].key)


class TestBulk(unittest.TestCase):
    def test_bulk_creates_containers_implicitly(self):
        room = cr.Room()
        room.bulk(cr.parse("bulk act2.ballroom")[0])
        self.assertIn("act2", room.present)
        self.assertIn("act2.ballroom", room.present)
        self.assertIn("act2.ballroom", room.declared)
        self.assertNotIn("act2", room.declared)

    def test_residue_prunes_a_container_left_with_nothing_in_it(self):
        room, _, _ = run("bulk act2.ballroom\ncarve act2.ballroom because it is dull")
        self.assertEqual(room.residue(), [])

    def test_an_explicitly_declared_thing_survives_its_children(self):
        room, _, _ = run("bulk act2\nbulk act2.ballroom\n"
                         "carve act2.ballroom because it is dull")
        self.assertEqual(room.residue(), ["act2"])

    def test_a_container_is_not_residue_on_its_own_account(self):
        # `act2` is a way of naming `act2.ballroom`, not a thing in the play.
        room, _, _ = run("bulk act2.ballroom\ncarve act2.mirror because it is a joke")
        self.assertEqual(room.residue(), ["act2.ballroom"])
        self.assertIn("act2", room.present)


class TestCarve(unittest.TestCase):
    def test_carving_a_node_takes_what_lives_under_it(self):
        room, _, _ = run("bulk act2.ballroom\nbulk act2.ballroom.mirror\n"
                         "carve act2 because act two is a joke told twice")
        self.assertEqual(room.residue(), [])

    def test_carving_something_absent_is_a_finding_not_a_failure(self):
        room, _, refusals = run(
            "bulk act1.opening\nbulk act3.letter\n"
            "carve act2.ballroom because it is dull\n"
            "carve act1.opening because it drags")
        self.assertEqual(len(refusals), 1)
        self.assertIn("already gone", room.entries[0]["because"])
        # The run continued: the second cut still happened.
        self.assertEqual(room.residue(), ["act3.letter"])

    def test_carving_a_kept_thing_is_refused_with_its_reason(self):
        room, _, refusals = run("bulk act3.letter\n"
                                "keep act3.letter because she reads it twice\n"
                                "carve act3.letter because act three is slow")
        self.assertEqual(room.residue(), ["act3.letter"])
        self.assertEqual(room.entries[-1]["op"], "refused")
        self.assertIn("she reads it twice", room.entries[-1]["because"])
        self.assertEqual([i.op for i in refusals], ["carve"])

    def test_carving_around_a_kept_thing_is_also_refused(self):
        # You cannot take the container out from under something somebody kept.
        room, _, refusals = run("bulk act3.letter\n"
                                "keep act3.letter because it is the spine\n"
                                "carve act3 because act three is slow")
        self.assertEqual(room.residue(), ["act3.letter"])
        self.assertEqual(len(refusals), 1)

    def test_a_refusal_lands_on_the_floor(self):
        room, _, _ = run("carve act2 because it is dull")
        self.assertEqual(room.entries[0]["op"], "refused")
        self.assertEqual(room.entries[0]["asked"], "carve")


class TestKeep(unittest.TestCase):
    def test_keep_records_the_reason_it_locked(self):
        room, _, _ = run("bulk act3.letter\nkeep act3.letter because it is the spine")
        self.assertEqual(room.locks["act3.letter"], "it is the spine")
        self.assertEqual(room.entries[-1]["op"], "kept")

    def test_keeping_what_is_not_there_is_refused(self):
        room, _, _ = run("keep act3.letter because it is the spine")
        self.assertIn("nothing by that name", room.entries[0]["because"])

    def test_keeping_twice_is_refused_the_second_time(self):
        room, _, _ = run("bulk act3.letter\n"
                         "keep act3.letter because it is the spine\n"
                         "keep act3.letter because I am nervous")
        self.assertIn("already kept", room.entries[-1]["because"])
        self.assertEqual(room.locks["act3.letter"], "it is the spine")


class TestSweep(unittest.TestCase):
    def test_sweep_takes_the_contents_and_leaves_the_node(self):
        room, _, _ = run("bulk act1.dinner\nbulk act1.opening\n"
                         "sweep act1 because act one is one joke told twice")
        # act1 was implicit and is now empty, so it goes too -- but the *declared*
        # things under it were what the sweep took.
        self.assertEqual(room.residue(), [])
        self.assertEqual(sorted(room.entries[-1]["took"]), ["act1.dinner",
                                                            "act1.opening"])

    def test_sweep_spares_a_kept_child_and_says_so(self):
        room, _, _ = run("bulk act1.opening\nbulk act1.dinner\n"
                         "keep act1.opening because the play needs one beginning\n"
                         "sweep act1 because act one is one joke told twice")
        self.assertEqual(room.residue(), ["act1.opening"])
        self.assertEqual(room.entries[-1]["skipped"], ["act1.opening (the play needs "
                                                       "one beginning)"])
        self.assertEqual(room.entries[-1]["took"], ["act1.dinner"])

    def test_a_sweep_that_would_take_only_kept_things_is_refused(self):
        room, _, refusals = run("bulk act1.opening\n"
                                "keep act1.opening because it is the beginning\n"
                                "sweep act1 because act one drags")
        self.assertEqual(len(refusals), 1)
        self.assertIn("everything under it is kept", room.entries[-1]["because"])
        self.assertEqual(room.residue(), ["act1.opening"])

    def test_sweeping_nothing_is_refused(self):
        room, _, _ = run("bulk act1.opening\nsweep act2 because it is dull")
        self.assertIn("nothing lives under it", room.entries[-1]["because"])

    def test_sweep_star_empties_the_work(self):
        room, _, _ = run("bulk act1.opening\nbulk act3.letter\nbulk cast.hero\n"
                         "sweep * because nothing here is worth an hour")
        self.assertEqual(room.residue(), [])

    def test_sweeping_a_node_takes_everything_under_it(self):
        room, _, _ = run("bulk act2.ballroom\nbulk act2.ballroom.mirror\n"
                         "sweep act2 because the whole act is the joke")
        self.assertEqual(room.residue(), [])
        # Every path the sweep actually removed is written down, not just the one it
        # was pointed at, so a later session can replay the exact same removals.
        self.assertEqual(room.entries[-1]["took"],
                         ["act2.ballroom", "act2.ballroom.mirror"])


class TestDraw(unittest.TestCase):
    CHOICE = "bulk cast.hero\nbulk act2.ballroom\ndraw cast.hero act2.ballroom because only one can carry the last scene"

    def test_the_same_seed_makes_the_same_cut_twice(self):
        first, _, _ = run(self.CHOICE, seed=7)
        second, _, _ = run(self.CHOICE, seed=7)
        self.assertEqual(first.residue(), second.residue())

    def test_different_seeds_make_different_cuts(self):
        picks = {tuple(run(self.CHOICE, seed=seed)[0].residue()) for seed in range(12)}
        self.assertGreater(len(picks), 1)
        self.assertTrue(all(len(residue) == 1 for residue in picks))

    def test_the_choice_and_the_seed_are_written_down(self):
        room, _, _ = run(self.CHOICE, seed=3)
        entry = room.entries[-1]
        self.assertEqual(entry["op"], "drew")
        self.assertEqual(entry["seed"], 3)
        self.assertEqual(entry["from_"], ["act2.ballroom", "cast.hero"])

    def test_draw_will_not_take_something_that_is_kept(self):
        room, _, _ = run("bulk cast.hero\nbulk act2.ballroom\n"
                         "keep act2.ballroom because the waltz is the play\n"
                         "draw cast.hero act2.ballroom because only one can carry it",
                         seed=5)
        self.assertEqual(room.residue(), ["act2.ballroom"])

    def test_draw_with_nothing_left_to_choose_from_is_refused(self):
        room, _, refusals = run("draw cast.hero act2.ballroom because only one can carry it")
        self.assertEqual(len(refusals), 1)
        self.assertIn("nothing to draw from", room.entries[-1]["because"])


class TestFile(unittest.TestCase):
    def test_filing_puts_a_note_on_the_floor_without_touching_the_work(self):
        room, _, _ = run('bulk act3.letter\ncarve nothing.content because it is empty\n'
                         'file "the brother\'s letter" because cutting him left a '
                         'letter with no sender')
        self.assertEqual(room.residue(), ["act3.letter"])
        self.assertEqual(room.notes, [{"text": "the brother's letter",
                                       "why": "cutting him left a letter with no sender"}])
        self.assertEqual(room.entries[-1]["op"], "filed")

    def test_a_filed_note_is_not_a_cut(self):
        room, _, _ = run('file "an idea nobody needs" because it is one')
        self.assertEqual(room.cuts, 0)


class TestFloorAssertion(unittest.TestCase):
    def test_a_floor_that_holds_reports_no_violations(self):
        room, _, _ = run(PLAY)
        self.assertEqual(room.floor_violations(), [])
        self.assertEqual(room.floor_why, "it is the spine")

    def test_a_floor_you_cut_away_names_what_was_lost(self):
        room, _, _ = run("bulk act3.letter\ncarve act3.letter because act three is slow\n"
                         "floor act3.letter because it is the spine")
        self.assertEqual(room.floor_violations(), ["act3.letter"])


class TestTheWholePlay(unittest.TestCase):
    def test_the_residue_is_only_what_somebody_would_have_to_explain(self):
        room, _, _ = run(PLAY, seed=1)
        residue = room.residue()
        self.assertIn("act3.letter", residue)          # kept
        self.assertNotIn("cast.brother", residue)      # carved
        self.assertNotIn("act1.dinner", residue)       # swept
        self.assertNotIn("act1.opening", residue)      # carved first
        self.assertNotIn("act1", residue)              # pruned with its contents
        # The draw means exactly one of these two is still standing.
        self.assertEqual(len({"cast.hero", "act2.ballroom"} & set(residue)), 1)

    def test_the_run_is_reproducible(self):
        self.assertEqual(run(PLAY, seed=1)[0].residue(), run(PLAY, seed=1)[0].residue())

    def test_a_program_that_cuts_nothing_has_not_started(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = Path(tmp) / "clockwork.cr"
            handle.write_text("bulk act3.letter\n"
                              "keep act3.letter because it is the spine\n"
                              "floor act3.letter\n")
            self.assertEqual(cr.main([str(handle)]), 1)


class TestTheFloorOnDisk(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "floor.jsonl"
        self.program = Path(self.tmp.name) / "play.cr"
        self.program.write_text(PLAY)

    def main(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cr.main([str(self.program), "--floor", str(self.log), *extra])
        return code, out.getvalue(), err.getvalue()

    def test_a_second_run_inherits_instead_of_redoing_the_work(self):
        first, _, _ = self.main("--seed", "4")
        second, out, _ = self.main("--seed", "4")
        self.assertEqual(first, 0)
        self.assertEqual(second, 0)
        self.assertIn("inherited", out)
        self.assertNotIn("a program that cuts nothing", (out + _))

    def test_inheriting_reproduces_the_same_residue(self):
        _, first, _ = self.main("--seed", "4")
        _, second, _ = self.main("--seed", "4")
        self.assertEqual(residue_of(first), residue_of(second))
        self.assertEqual(residue_of(first), run(PLAY, seed=4)[0].residue())

    def test_a_replayed_cut_is_not_reported_as_decided_again(self):
        self.main("--seed", "4")
        _, out, _ = self.main("--seed", "4")
        self.assertIn("0 cut this run", out)
        self.assertIn("replayed from the floor", out)

    def test_redo_decides_again_rather_than_inheriting(self):
        self.main("--seed", "4")
        _, out, _ = self.main("--seed", "4", "--redo")
        self.assertNotIn("inherited", out)

    def test_the_log_records_the_bulk_and_the_program(self):
        self.main("--seed", "4")
        entries = cr.load_floor(self.log)
        self.assertTrue(entries)
        self.assertTrue(all(entry["bulk"] and entry["program"] for entry in entries))

    def test_the_log_does_not_grow_with_duplicate_decisions(self):
        self.main("--seed", "4")
        first = len(cr.load_floor(self.log))
        self.main("--seed", "4")
        self.assertEqual(len(cr.load_floor(self.log)), first)

    def test_a_different_program_over_the_same_work_is_shown_as_context(self):
        self.main("--seed", "4")
        self.program.write_text(PLAY + "\ncarve act2.ballroom because it is a dance\n")
        code, out, _ = self.main("--seed", "4")
        self.assertEqual(code, 0)
        self.assertIn("a previous program left", out)

    def test_a_log_from_other_work_says_so_instead_of_being_applied(self):
        self.main("--seed", "4")
        elsewhere = Path(self.tmp.name) / "other.cr"
        elsewhere.write_text("bulk kitchen.sink\nbulk kitchen.counter\n"
                             "carve kitchen.counter because it is dirty\n"
                             "floor kitchen.sink because it is the only sink\n")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cr.main([str(elsewhere), "--floor", str(self.log)])
        self.assertEqual(code, 0)
        self.assertIn("not applicable here", out.getvalue())

    def test_an_unreadable_log_line_is_skipped_not_fatal(self):
        self.log.write_text('{"op": "cut", "key": "abc", "bulk": "x", "program": "y"}\n'
                            'not json at all\n')
        self.assertEqual(len(cr.load_floor(self.log)), 1)


class TestTheSharedLedger(unittest.TestCase):
    """`--ledger` puts the floor in a Foxwood ledger instead of a private file.

    Cutting Room still runs on a checkout with no Foxwood at all; only this path
    imports it, and only when it is asked for.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "ledger"
        self.root.mkdir()
        self.program = Path(self.tmp.name) / "play.cr"
        self.program.write_text(PLAY, encoding="utf-8")
        self.ledger = cr._import_ledger()
        self.log = self.ledger.decision_log_path(self.root)

    def main(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cr.main([str(self.program), "--ledger", str(self.root), *extra])
        return code, out.getvalue(), err.getvalue()

    def test_the_shared_log_is_one_named_place(self):
        code, out, _ = self.main("--seed", "4")
        self.assertEqual(code, 0)
        self.assertTrue(self.log.is_file())
        self.assertIn("shared with the Foxwood ledger", out)
        self.assertEqual(self.log.name, self.ledger.DECISION_LOG_FILENAME)

    def test_floor_entries_are_stamped_with_the_writer(self):
        self.main("--seed", "4")
        import json as _json
        entries = [_json.loads(line) for line in self.log.read_text().splitlines()
                   if line.strip()]
        self.assertTrue(entries)
        self.assertEqual({e["kind"] for e in entries}, {self.ledger.KIND_DECISION})

    def test_a_verdict_in_the_log_is_not_a_floor_decision(self):
        # Somebody else's decision, in the same file, must not be read as this
        # language's history.
        import json as _json
        self.log.write_text(_json.dumps(
            {"kind": "verdict", "key": "synthesize:abc", "verdict": "accepted",
             "at": "2026-01-01T00:00:00+00:00", "why": ""}) + "\n")
        self.assertEqual(cr.load_floor(self.log), [])
        code, out, _ = self.main("--seed", "4")
        self.assertEqual(code, 0)
        self.assertNotIn("not applicable here", out)

    def test_a_run_finds_its_own_decisions_through_the_shared_log(self):
        self.main("--seed", "4")
        code, out, _ = self.main("--seed", "4")
        self.assertEqual(code, 0)
        self.assertIn("inherited", out)

    def test_a_private_log_and_the_shared_one_are_never_both_used(self):
        # Picking one silently would decide for the operator where their decisions
        # were recorded.
        code, _, err = self.main("--floor", str(Path(self.tmp.name) / "private.jsonl"))
        self.assertEqual(code, 2)
        self.assertIn("give one, not both", err)


class TestVerifyingTheBecause(unittest.TestCase):
    """`because <why> citing src-a` is checked against the ledger BEFORE the cut.

    What this gate proves: the evidence exists and was recorded with a hash and a
    licence before the decision was taken. What it does NOT prove: that the reason is
    correct. `because it is dull citing src-abc` verifies the moment src-abc exists.
    Several tests below exist to pin that limit rather than let it be read as more.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "ledger"
        self.ledger_module = cr._import_ledger()
        self.ledger = self.ledger_module.ResearchLedger(self.root)
        self.source = self.ledger.add_source(
            title="A public record", url="https://example.test/record",
            publisher="Example", excerpt="A bounded excerpt.")
        self.program = Path(self.tmp.name) / "play.cr"

    def run_program(self, text, *extra, ledger=True):
        self.program.write_text(text, encoding="utf-8")
        argv = [str(self.program)]
        if ledger:
            argv += ["--ledger", str(self.root)]
        argv += list(extra)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cr.main(argv)
        return code, out.getvalue(), err.getvalue()

    # -- grammar -------------------------------------------------------------

    def test_a_reason_can_cite_evidence(self):
        instruction = cr.parse("carve act2 because it repeats act1 citing src-a src-b")[0]
        self.assertEqual(instruction.why, "it repeats act1")
        self.assertEqual(instruction.proof, ("src-a", "src-b"))
        self.assertEqual(str(instruction),
                         "carve act2 because it repeats act1 citing src-a src-b")

    def test_a_prose_reason_needs_no_citation(self):
        instruction = cr.parse("carve act2 because it repeats act1")[0]
        self.assertEqual((instruction.why, instruction.proof),
                         ("it repeats act1", ()))

    def test_citing_with_nothing_named_is_refused(self):
        with self.assertRaises(cr.CuttingRoomError) as caught:
            cr.parse("carve act2 because it drags citing")
        self.assertIn("line 1", str(caught.exception))
        self.assertIn("citation that names nothing", str(caught.exception))

    def test_a_prose_reason_containing_the_word_citing_is_split(self):
        # Documented, not accidental: `citing` is the one reserved word in a reason.
        instruction = cr.parse("carve act2 because it was citing the critics")[0]
        self.assertEqual(instruction.why, "it was")
        # Whatever words follow the reserved word are read as source ids, because that
        # is what follows it everywhere else. The fix is to not write it in prose.
        self.assertEqual(instruction.proof, ("the", "critics"))

    # -- identity ------------------------------------------------------------

    def test_a_citation_is_part_of_the_decision_identity(self):
        plain = cr.parse("carve act2 because it drags")[0]
        cited = cr.parse("carve act2 because it drags citing src-a")[0]
        self.assertNotEqual(plain.key, cited.key)
        self.assertNotEqual(cr.program_id("carve act2 because it drags"),
                            cr.program_id("carve act2 because it drags citing src-a"))

    def test_a_prose_only_key_is_the_value_it_was_before_citations_existed(self):
        # This is the compatibility contract: the citation is appended to the identity
        # only when there is one, so a floor written by an earlier version still
        # inherits instead of silently looking like a different program.
        instruction = cr.parse("carve act2 because it drags")[0]
        expected = cr._sha("\x1f".join(("carve", "", "act2", "it drags")))
        self.assertEqual(instruction.key, expected)

    # -- the gate ------------------------------------------------------------

    def test_the_verifier_checks_existence_not_correctness(self):
        verify = cr.make_verifier(self.ledger, require_verified=False)
        dull_but_cited = cr.parse(
            f"carve act2 because it is dull citing {self.source.source_id}")[0]
        self.assertIsNone(verify(dull_but_cited))

    def test_the_verifier_names_what_is_missing(self):
        verify = cr.make_verifier(self.ledger, require_verified=False)
        self.assertIn("src-nope",
                      verify(cr.parse("carve act2 because x citing src-nope")[0]))
        self.assertIsNone(verify(cr.parse("carve act2 because x")[0]))

    def test_requiring_verified_also_refuses_a_reason_that_cites_nothing(self):
        strict = cr.make_verifier(self.ledger, require_verified=True)
        self.assertIn("no evidence cited",
                      strict(cr.parse("carve act2 because x")[0]))

    def test_a_cited_cut_is_recorded_as_verified(self):
        code, out, _ = self.run_program(
            f"bulk act1.opening\nbulk act3.letter\n"
            f"carve act1.opening because it drags citing {self.source.source_id}\n"
            f"floor act3.letter because it is the spine\n")
        self.assertEqual(code, 0)
        self.assertIn(f"[cited: {self.source.source_id}]", out)
        self.assertIn("1 backed by evidence in the ledger, 0 asserted", out)

    def test_an_inherited_decision_is_re_checked_when_the_rule_tightens(self):
        # A floor written without citations must not become permanently exempt the
        # moment --require-verified is switched on. The gate runs before the replay,
        # so an earlier decision is re-examined by the rule in force now -- the
        # zero-trust rule, and the reason it is ordered this way rather than for
        # tidiness.
        program = ("bulk act1.opening\nbulk act3.letter\n"
                   "carve act1.opening because it is dull\n"
                   "floor act3.letter because it is the spine\n")
        self.assertEqual(self.run_program(program)[0], 0)
        inherited_code, out, _ = self.run_program(program)
        self.assertEqual(inherited_code, 0)
        self.assertIn("inherited", out)
        strict, _, err = self.run_program(program, "--require-verified")
        self.assertEqual(strict, 1)
        self.assertIn("could not be checked against the ledger", err)

    def test_a_citation_to_something_that_does_not_exist_refuses_the_cut(self):
        program = ("bulk act3.letter\nbulk act1.opening\n"
                   "carve act3.letter because act three is slow citing src-nope\n"
                   "carve act1.opening because the play starts later\n"
                   "floor act3.letter because it is the spine\n")
        code, out, _ = self.run_program(program)
        self.assertEqual(code, 0)
        self.assertIn("nothing in the ledger is named src-nope", out)
        # The safety property: the unverifiable cut did not happen, so the thing it
        # tried to remove is still standing. The rest of the program still ran.
        residue = residue_of(out)
        self.assertIn("act3.letter", residue)
        self.assertNotIn("act1.opening", residue)

    def test_requiring_verified_fails_the_run_when_a_reason_cannot_be_checked(self):
        program = ("bulk act1.opening\nbulk act3.letter\n"
                   "carve act1.opening because it is dull\n"
                   "floor act3.letter because it is the spine\n")
        relaxed, out, _ = self.run_program(program)
        self.assertEqual(relaxed, 0)
        self.assertIn("0 backed by evidence in the ledger, 1 asserted", out)
        strict, _, err = self.run_program(program, "--require-verified")
        self.assertEqual(strict, 1)
        self.assertIn("could not be checked against the ledger", err)

    def test_a_citation_without_a_ledger_is_refused_at_the_door(self):
        code, _, err = self.run_program(
            f"bulk act3.letter\nkeep act3.letter because x "
            f"citing {self.source.source_id}\n", ledger=False)
        self.assertEqual(code, 2)
        self.assertIn("--ledger was not given", err)

    def test_a_recorded_claim_can_be_cited_as_well_as_a_source(self):
        claim = self.ledger.add_claim(text="Latency fell.",
                                      source_ids=(self.source.source_id,))
        code, out, _ = self.run_program(
            f"bulk act1.opening\nbulk act3.letter\n"
            f"carve act1.opening because the research says so citing {claim.claim_id}\n"
            f"floor act3.letter because it is the spine\n")
        self.assertEqual(code, 0)
        self.assertIn(claim.claim_id, out)

    def test_json_reports_cited_and_unverifiable_counts(self):
        program = (f"bulk act1.opening\nbulk act2.ballroom\nbulk act3.letter\n"
                   f"carve act1.opening because it drags citing {self.source.source_id}\n"
                   f"carve act2.ballroom because it is a dance citing src-nope\n"
                   f"floor act3.letter\n")
        code, out, _ = self.run_program(program, "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["cited"], 1)
        self.assertEqual(payload["unverifiable"], 1)
        self.assertEqual(payload["residue"], ["act2.ballroom", "act3.letter"])


class TestCommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, text):
        path = self.root / name
        path.write_text(text)
        return path

    def main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cr.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_a_working_program_exits_zero(self):
        code, out, _ = self.main([str(self.write("play.cr", PLAY))])
        self.assertEqual(code, 0)
        self.assertIn("residue:", out)
        self.assertIn("the floor:", out)

    def test_a_floor_you_cut_away_exits_one_and_says_what_was_lost(self):
        program = self.write("bad.cr", "bulk act3.letter\n"
                                       "carve act3.letter because it is slow\n"
                                       "floor act3.letter because it is the spine\n")
        code, _, err = self.main([str(program)])
        self.assertEqual(code, 1)
        self.assertIn("you cut the thing that made it fly", err)
        self.assertIn("act3.letter", err)

    def test_a_malformed_program_exits_two(self):
        code, _, err = self.main([str(self.write("bad.cr", "carve act1"))])
        self.assertEqual(code, 2)
        self.assertIn("needs a reason", err)

    def test_a_missing_program_exits_two(self):
        code, _, err = self.main([str(self.root / "nothing.cr")])
        self.assertEqual(code, 2)
        self.assertIn("no program at", err)

    def test_json_output_is_json(self):
        code, out, _ = self.main([str(self.write("play.cr", PLAY)), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["program"], cr.program_id(PLAY))
        self.assertTrue(payload["floor_holds"])
        self.assertEqual(payload["residue"], run(PLAY, seed=0)[0].residue())

    def test_the_refused_are_reported_without_stopping_the_run(self):
        program = self.write("play.cr", PLAY + "\ncarve cast.brother because again\n")
        code, out, _ = self.main([str(program)])
        self.assertEqual(code, 0)
        self.assertIn("refused 1 instruction(s)", out)


if __name__ == "__main__":
    unittest.main()
