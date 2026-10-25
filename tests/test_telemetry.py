"""Tests for bin/telemetry.py -- the hook that makes tool use measurable.

The failure mode being guarded against is a metric that looks like evidence but
is not: an atexit hook that changes a tool's exit code, a row that silently
loses a column, or a write that "succeeds" while the log is unwritable.
"""
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

BIN = Path.home() / "bin"
sys.path.insert(0, str(BIN))
import telemetry  # noqa: E402


class RowFormat(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.real = telemetry.LOG
        telemetry.LOG = Path(self.tmp.name) / "events.tsv"

    def tearDown(self):
        telemetry.LOG = self.real
        self.tmp.cleanup()

    def test_row_has_exactly_the_declared_columns(self):
        self.assertTrue(telemetry.write_row("verify_keys", 0, 1.5, "argv --apply",
                                            available=True))
        row = telemetry.LOG.read_text().strip().split("\t")
        self.assertEqual(len(row), len(telemetry.COLUMNS))
        self.assertEqual(row[1], "verify_keys")
        self.assertEqual(row[2], "0")
        self.assertEqual(row[4], "1")

    def test_bus_unavailable_is_recorded_as_zero(self):
        telemetry.write_row("x", 1, 0, "", available=False)
        self.assertEqual(telemetry.LOG.read_text().strip().split("\t")[4], "0")

    def test_tabs_and_newlines_cannot_forge_columns(self):
        telemetry.write_row("bad\ttool\nrow", 0, 0, "a\tb\nc", available=True)
        lines = telemetry.LOG.read_text().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(len(lines[0].split("\t")), len(telemetry.COLUMNS))

    def test_detail_is_truncated(self):
        telemetry.write_row("x", 0, 0, "y" * 5000, available=True)
        field = telemetry.LOG.read_text().splitlines()[0].split("\t")[5]
        self.assertLessEqual(len(field), 200)

    def test_override_may_be_a_string(self):
        telemetry.LOG = str(telemetry.LOG)
        self.assertTrue(telemetry.write_row("x", 0, 0, "", available=True))

    def test_unwritable_log_returns_false_and_does_not_raise(self):
        blocker = Path(self.tmp.name) / "blocker"
        blocker.write_text("not a directory")
        telemetry.LOG = blocker / "events.tsv"
        self.assertFalse(telemetry.write_row("x", 0, 0, "", available=True))

    def test_no_key_material_is_ever_logged(self):
        telemetry.write_row("x", 0, 0, "ok", available=True)
        self.assertNotIn("sk-", telemetry.LOG.read_text())


class ExitCodeCapture(unittest.TestCase):
    """install() must record the real status, not a hopeful zero."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "events.tsv"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, body: str, expect_rc: int | None = None) -> list[str]:
        script = textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(BIN)!r})
            import telemetry
            telemetry.LOG = {str(self.log)!r}
            telemetry.install("probe-tool")
            {body}
        """)
        proc = subprocess.run([sys.executable, "-c", script],
                              capture_output=True, text=True, timeout=60)
        if expect_rc is not None:
            self.assertEqual(proc.returncode, expect_rc, proc.stderr)
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_explicit_exit_status_is_recorded(self):
        rows = self._run("sys.exit(3)", expect_rc=3)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].split("\t")[2], "3")

    def test_clean_exit_is_recorded_as_zero(self):
        rows = self._run("pass")
        self.assertEqual(rows[0].split("\t")[2], "0")

    def test_an_uncaught_exception_is_recorded_as_failure(self):
        rows = self._run("raise ValueError('boom')", expect_rc=1)
        cols = rows[0].split("\t")
        self.assertEqual(cols[2], "1")
        self.assertIn("ValueError", cols[5])
        self.assertIn("boom", cols[5])

    def test_install_does_not_change_stdout(self):
        rows = self._run("print('hello')")
        self.assertEqual(len(rows), 1)

    def test_installing_twice_does_not_double_log(self):
        rows = self._run("telemetry.install('probe-tool')")
        self.assertEqual(len(rows), 1)


class Toolrun(unittest.TestCase):
    """The wrapper path: coverage for commands that cannot import anything."""

    def test_toolrun_records_the_wrapped_status(self):
        env_log = Path(tempfile.mkdtemp()) / "events.tsv"
        script = textwrap.dedent(f"""
            import sys, runpy
            sys.path.insert(0, {str(BIN)!r})
            import telemetry
            telemetry.LOG = {str(env_log)!r}
            telemetry.main(["--log", "--tool", "wrapped", "--rc", "7"])
        """)
        subprocess.run([sys.executable, "-c", script], check=True, timeout=60)
        cols = env_log.read_text().splitlines()[0].split("\t")
        self.assertEqual(cols[1], "wrapped")
        self.assertEqual(cols[2], "7")


if __name__ == "__main__":
    unittest.main()
