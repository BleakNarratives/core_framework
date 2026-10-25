"""The BLOCKERS view: repeated failures, read from the telemetry log.

The failure mode this guards against is a view that reports calm when it has
measured nothing. An absent or unreadable log is "unmeasured", never "healthy",
and one failure is a bad day, not a blocker.
"""
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path.home() / "turd-merger-tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import grimoire_tui as tui  # noqa: E402

ROW = "{stamp}\t{tool}\t{rc}\t{dur}\t1\t{detail}"


def ev(tool, rc, stamp="2026-10-25T10:00:00+00:00", detail=""):
    return {"stamp": stamp, "tool": tool, "rc": str(rc), "dur": "0.1",
            "bus": "1", "detail": detail}


class Grouping(unittest.TestCase):
    def test_a_tool_that_failed_twice_is_a_blocker(self):
        rows = [ev("ingest_keys", 1), ev("ingest_keys", 2)]
        out = tui.find_blockers(rows)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["tool"], "ingest_keys")
        self.assertEqual(out[0]["failures"], 2)
        self.assertEqual(out[0]["runs"], 2)

    def test_one_failure_is_not_a_blocker(self):
        self.assertEqual(tui.find_blockers([ev("x", 1), ev("x", 0)]), [])

    def test_successes_are_not_counted_as_failures(self):
        out = tui.find_blockers([ev("x", 0), ev("x", 0), ev("x", 0)])
        self.assertEqual(out, [])

    def test_mixed_runs_report_the_real_ratio(self):
        out = tui.find_blockers([ev("x", 0), ev("x", 1), ev("x", "unknown"),
                                 ev("x", 0)])
        self.assertEqual(out[0]["failures"], 2)
        self.assertEqual(out[0]["runs"], 4)

    def test_last_rc_and_detail_come_from_the_most_recent_failure(self):
        rows = [ev("x", 1, "2026-10-25T09:00:00+00:00", "old reason"),
                ev("x", 1, "2026-10-25T11:00:00+00:00", "new reason")]
        out = tui.find_blockers(rows)[0]
        self.assertEqual(out["last"], "2026-10-25T11:00:00+00:00")
        self.assertEqual(out["detail"], "new reason")

    def test_sorted_by_failures_then_name(self):
        rows = [ev("a", 1), ev("a", 1), ev("b", 1), ev("b", 1), ev("b", 1)]
        self.assertEqual([b["tool"] for b in tui.find_blockers(rows)], ["b", "a"])

    def test_threshold_is_configurable(self):
        rows = [ev("x", 1)]
        self.assertEqual(tui.find_blockers(rows, min_failures=1)[0]["tool"], "x")

    def test_empty_log_is_no_blockers(self):
        self.assertEqual(tui.find_blockers([]), [])


class Parsing(unittest.TestCase):
    def test_rows_load_from_the_tsv(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "events.tsv"
            p.write_text(ROW.format(stamp="2026-10-25T10:00:00+00:00",
                                    tool="verify_keys", rc=1, dur="2.5",
                                    detail="argv --apply") + "\n")
            rows = tui.load_events(p)
        self.assertEqual(rows[0]["tool"], "verify_keys")
        self.assertEqual(rows[0]["detail"], "argv --apply")

    def test_missing_file_is_an_empty_log_not_a_crash(self):
        self.assertEqual(tui.load_events(Path("/nonexistent/events.tsv")), [])

    def test_a_truncated_row_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "events.tsv"
            p.write_text("only\ttwo\n" + ROW.format(stamp="t", tool="ok", rc=0,
                                                     dur="0", detail="") + "\n")
            rows = tui.load_events(p)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tool"], "ok")

    def test_blocker_row_is_readable_at_a_glance(self):
        text, _ = tui.blocker_row({"tool": "git-ship", "failures": 3,
                                   "last_rc": "1"})
        self.assertIn("3 fail", text)
        self.assertIn("git-ship", text)


if __name__ == "__main__":
    unittest.main()
