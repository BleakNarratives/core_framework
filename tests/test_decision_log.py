"""One log, two writers: pipe verdicts and Cutting Room floors.

The pipe kept `verdicts.jsonl` and Cutting Room kept its own floor file. Both
records answer the same question -- "has this decision already been made against this
evidence?" -- and two places answering one question is how the second place goes
stale without anyone noticing which one is right.

They now share one append-only log per ledger root, and each reader claims only the
entries it recognises. These tests pin the parts that would fail silently:

  * a floor decision must never read as an answered question, because then the pipe
    would report research as done that it never did;
  * a verdict must never read as an inherited cut, because then a floor would come
    back with work still standing in it;
  * both writers must resolve to one path, which is the whole claim.

Cutting Room's own suite runs from `projects/cuttingroom`; this module reaches into
it the way the herald wrapper reaches into `projects/herald`, so there is one source
of truth for the language and this file only tests the seam between them.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUTTINGROOM = ROOT / "projects" / "cuttingroom"


def load_cuttingroom():
    """Load the language from its file, without touching `sys.path`.

    Inserting `projects/cuttingroom` into `sys.path` made `projects/cuttingroom/tests`
    shadow the repository's own `tests` package, and an unrelated module that does
    `from tests.fixtures import ...` stopped importing. It only failed when this file
    happened to be collected first, which is the worst way for a test to break
    something.    `registry.py` loads `scripts/check_provenance.py` by path for a
    related reason, so this is the established way to reach outside the package.

    The module is registered under a name nothing else will claim, because
    `dataclasses` resolves string annotations through `sys.modules` and raises
    without it. Unregistering on failure keeps a broken load from leaving a
    half-initialised module behind for the next test.
    """
    path = CUTTINGROOM / "cuttingroom.py"
    if not path.is_file():
        raise ImportError(f"cuttingroom moved; expected {path}")
    spec = importlib.util.spec_from_file_location("cuttingroom_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


cuttingroom = load_cuttingroom()
from src.foxwood_research import ledger as foxwood_ledger  # noqa: E402
from src.foxwood_research.pipe import (  # noqa: E402
    PipeRun,
    load_verdicts,
    record_verdict,
    resolved_keys,
    verdict_key,
)

PROGRAM = """\
bulk cast.hero
bulk act3.letter
carve cast.hero because the letter is the play
floor act3.letter because it is the spine
"""


class DecisionLogWiringTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "ledger"
        self.root.mkdir()
        self.program = Path(self.tmp.name) / "play.cr"
        self.program.write_text(PROGRAM, encoding="utf-8")

    # -- the two writers, neither of which calls a model --------------------

    def verdict(self):
        """Write exactly what a real run writes, without asking a model anything."""
        run = PipeRun(query="what is supported?", seed=3, lens="synthesize",
                      model="openai/gpt-oss-120b", verdict="accepted",
                      source_ids=("src-abc",), source_hashes=("deadbeef",),
                      findings=(), frame_ids=("frame-1",))
        record_verdict(self.root, run)
        return run

    def cut(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cuttingroom.main([str(self.program), "--ledger", str(self.root),
                                     *extra])
        return code, out.getvalue(), err.getvalue()

    def log_entries(self):
        path = foxwood_ledger.decision_log_path(self.root)
        return [json.loads(line) for line in path.read_text().splitlines()
                if line.strip()]

    # -- the seams ----------------------------------------------------------

    def test_the_cutting_room_module_this_module_reaches_into_is_where_it_expects(self):
        self.assertTrue((CUTTINGROOM / "cuttingroom.py").is_file(),
                        f"cuttingroom moved; expected {CUTTINGROOM}")
        self.assertEqual(Path(cuttingroom.__file__).resolve(),
                         (CUTTINGROOM / "cuttingroom.py").resolve())

    def test_both_writers_resolve_to_one_file(self):
        self.verdict()
        self.cut()
        self.assertTrue(foxwood_ledger.decision_log_path(self.root).is_file())
        kinds = {entry.get("kind") for entry in self.log_entries()}
        self.assertEqual(kinds, {foxwood_ledger.KIND_VERDICT,
                                 foxwood_ledger.KIND_DECISION})

    def test_the_pipe_reads_its_verdicts_and_not_the_floors(self):
        run = self.verdict()
        self.cut()
        verdicts = load_verdicts(self.root)
        key = verdict_key(run.lens, run.source_ids)
        self.assertEqual(list(verdicts), [key])
        self.assertEqual(resolved_keys(verdicts), {key})

    def test_a_floor_decision_cannot_make_the_pipe_skip_a_question(self):
        self.cut()
        self.assertEqual(load_verdicts(self.root), {})
        self.assertEqual(resolved_keys(load_verdicts(self.root)), set())

    def test_cutting_room_reads_its_floors_and_not_the_verdicts(self):
        self.verdict()
        self.cut()
        entries = cuttingroom.load_floor(foxwood_ledger.decision_log_path(self.root))
        self.assertTrue(entries)
        self.assertTrue(all(cuttingroom._owns_floor(entry) for entry in entries))
        self.assertTrue(all("verdict" not in entry for entry in entries))
        # Somebody else's verdict is not this module's stale work, and not a
        # previous program's decisions either.
        decided, prior, stale = cuttingroom.inheritance(
            entries, entries[0]["bulk"], entries[0]["program"])
        self.assertTrue(decided)
        self.assertEqual((prior, stale), ([], []))

    def test_a_verdict_does_not_stop_cutting_room_from_inheriting_its_own_floor(self):
        self.verdict()
        self.assertEqual(self.cut()[0], 0)
        code, out, _ = self.cut()
        self.assertEqual(code, 0)
        self.assertIn("inherited", out)
        self.assertIn("replayed from the floor", out)

    def test_a_floor_written_first_does_not_stop_the_pipe_reading_verdicts(self):
        self.cut()
        run = self.verdict()
        self.assertIn(verdict_key(run.lens, run.source_ids), load_verdicts(self.root))

    def test_a_readable_verdict_survives_an_unreadable_line_between_floors(self):
        self.cut()
        path = foxwood_ledger.decision_log_path(self.root)
        with path.open("a", encoding="utf-8") as handle:
            handle.write("this line is not json\n")
        run = self.verdict()
        self.assertIn(verdict_key(run.lens, run.source_ids), load_verdicts(self.root))
        self.assertTrue(cuttingroom.load_floor(path))


if __name__ == "__main__":
    unittest.main()
