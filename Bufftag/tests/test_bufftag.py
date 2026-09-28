"""Offline tests and legacy-stack characterization probes.

The LegacyCharacterizationTests document behavior that is currently unsafe. If
one starts failing, the old implementation changed and the audit entry in
BUNNYSPACE.md must be re-checked rather than silently reinterpreted.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Bufftag import bufftag


def _load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _metadata(**overrides: str) -> dict[str, str]:
    metadata = {
        "origin": "test-device",
        "pillar": "test",
        "deps": "none",
        "role": "deterministic test fixture",
        "author": "Buffy",
        "recorded_at": "2026-09-25T12:00:00+00:00",
    }
    metadata.update(overrides)
    return metadata


class TagParsingTests(unittest.TestCase):
    def test_complete_top_level_header_parses(self):
        text = "#!/usr/bin/env python3\n" + bufftag.render_header(_metadata()) + "\nprint('ok')\n"
        header = bufftag.parse_header(text, ".py")
        self.assertIsNotNone(header)
        self.assertEqual(header.metadata, _metadata())
        self.assertEqual(header.start_line, 1)

    def test_docstring_decoy_is_not_a_header(self):
        decoy = bufftag.render_header(_metadata()).replace("# ", "", 1)
        text = '"""A file that merely discusses provenance.\n' + decoy + '"""\n'
        self.assertIsNone(bufftag.parse_header(text, ".py"))

    def test_prose_marker_is_not_a_header(self):
        text = "# This comment mentions [DNA_TAG] and [/DNA_TAG].\nprint('ok')\n"
        self.assertIsNone(bufftag.parse_header(text, ".py"))

    def test_duplicate_field_is_rejected(self):
        fields = bufftag.render_header(_metadata())
        fields = fields.replace(
            "# role: deterministic test fixture\n",
            "# role: deterministic test fixture\n# role: second claim\n",
        )
        with self.assertRaisesRegex(bufftag.HeaderError, "duplicate field"):
            bufftag.parse_header("#!/bin/sh\n" + fields, ".sh")

    def test_unknown_field_is_rejected(self):
        fields = bufftag.render_header(_metadata()).replace(
            "# [/BUFFTAG]\n", "# injected: claim\n# [/BUFFTAG]\n"
        )
        with self.assertRaisesRegex(bufftag.HeaderError, "extra="):
            bufftag.parse_header(fields, ".py")

    def test_timezone_naive_timestamp_is_rejected(self):
        with self.assertRaisesRegex(bufftag.HeaderError, "timezone"):
            bufftag.parse_header(bufftag.render_header(_metadata(recorded_at="2026-09-25")), ".py")

    def test_control_characters_cannot_cross_the_header_boundary(self):
        with self.assertRaisesRegex(bufftag.HeaderError, "control character"):
            bufftag.render_header(_metadata(role="safe\n# [/BUFFTAG]"))

    def test_markdown_uses_comments_after_frontmatter(self):
        original = "---\ntitle: Example\n---\n# Example\n"
        header = bufftag.render_header(_metadata(), suffix=".md")
        stamped = "---\ntitle: Example\n---\n" + header + "\n# Example\n"
        parsed = bufftag.parse_header(stamped, ".md")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.start_line, 3)
        self.assertNotIn("# [BUFFTAG", stamped)
        self.assertEqual(stamped.splitlines()[0], "---")


class SafeStampTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.receipts = self.root / ".bufftag" / "receipts.jsonl"

    def tearDown(self):
        self.temp.cleanup()

    def test_stamp_preserves_shebang_and_encoding_and_content_hash(self):
        path = self.root / "sample.py"
        original = "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\nprint('hello')\n"
        path.write_text(original, encoding="utf-8")
        result = bufftag.stamp(
            root=self.root,
            file_path=path,
            metadata=_metadata(),
            receipts_path=self.receipts,
            secret=None,
        )
        stamped = path.read_text(encoding="utf-8")
        lines = stamped.splitlines()
        self.assertEqual(lines[0], "#!/usr/bin/env python3")
        self.assertEqual(lines[1], "# -*- coding: utf-8 -*-")
        self.assertEqual(lines[2], bufftag.HEADER_START)
        self.assertEqual(result["sha256"], bufftag.content_sha256(stamped))
        self.assertEqual(bufftag._content_without_header(stamped, bufftag.parse_header(stamped, ".py")), original)
        compile(stamped, str(path), "exec")

    def test_stamp_refuses_a_symlink_target(self):
        outside = Path(self.temp.name).parent / f"bufftag-outside-{os.getpid()}.py"
        outside.write_text("print('outside')\n", encoding="utf-8")
        link = self.root / "link.py"
        link.symlink_to(outside)
        try:
            with self.assertRaisesRegex(bufftag.BufftagError, "symlink"):
                bufftag.stamp(
                    root=self.root,
                    file_path=link,
                    metadata=_metadata(),
                    receipts_path=self.receipts,
                    secret=None,
                )
            self.assertEqual(outside.read_text(encoding="utf-8"), "print('outside')\n")
        finally:
            outside.unlink(missing_ok=True)

    def test_stamp_refuses_paths_outside_the_root(self):
        with tempfile.TemporaryDirectory() as outside:
            path = Path(outside) / "outside.py"
            path.write_text("print('outside')\n", encoding="utf-8")
            with self.assertRaisesRegex(bufftag.BufftagError, "escapes root"):
                bufftag.stamp(
                    root=self.root,
                    file_path=path,
                    metadata=_metadata(),
                    receipts_path=self.receipts,
                    secret=None,
                )

    def test_legacy_tag_is_preserved_but_not_trusted(self):
        path = self.root / "legacy.py"
        original = "# [DNA_TAG]\n# ORIGIN: made-up\n# [/DNA_TAG]\nprint('legacy')\n"
        path.write_text(original, encoding="utf-8")
        bufftag.stamp(
            root=self.root,
            file_path=path,
            metadata=_metadata(),
            receipts_path=self.receipts,
            secret=None,
        )
        stamped = path.read_text(encoding="utf-8")
        self.assertIn("# ORIGIN: made-up", stamped)
        report = bufftag.verify(root=self.root, receipts_path=self.receipts, secret=None)
        self.assertIn("legacy_dna_tag", {finding.code for finding in report.findings})


class ReceiptIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.receipts = self.root / ".bufftag" / "receipts.jsonl"

    def tearDown(self):
        self.temp.cleanup()

    def _stamp(self, name: str, text: str, secret: bytes | None = None) -> dict:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return bufftag.stamp(
            root=self.root,
            file_path=path,
            metadata=_metadata(),
            receipts_path=self.receipts,
            secret=secret,
        )

    def test_signed_receipt_chain_verifies_and_detects_content_drift(self):
        secret = b"test-only-hmac-key"
        self._stamp("one.py", "print('one')\n", secret)
        self._stamp("nested/two.py", "print('two')\n", secret)
        report = bufftag.verify(root=self.root, receipts_path=self.receipts, secret=secret)
        self.assertTrue(report.ok, report.as_dict())
        self.assertEqual(report.receipt_count, 2)

        changed = self.root / "one.py"
        changed.write_text(
            changed.read_text(encoding="utf-8").replace("print('one')", "print('changed')"),
            encoding="utf-8",
        )
        report = bufftag.verify(root=self.root, receipts_path=self.receipts, secret=secret)
        self.assertFalse(report.ok)
        self.assertIn("content_drift", {finding.code for finding in report.findings})

        changed.write_text("print('changed')\n", encoding="utf-8")
        report = bufftag.verify(root=self.root, receipts_path=self.receipts, secret=secret)
        self.assertIn("header_removed", {finding.code for finding in report.findings})

    def test_unsigned_receipts_are_valid_but_explicitly_unsigned(self):
        result = self._stamp("one.py", "print('one')\n")
        self.assertEqual(result["receipt"]["signature"], {"mode": "unsigned"})
        report = bufftag.verify(root=self.root, receipts_path=self.receipts, secret=None)
        self.assertTrue(report.ok, report.as_dict())

    def test_signed_log_without_key_fails_closed(self):
        self._stamp("one.py", "print('one')\n", b"secret")
        report = bufftag.verify(root=self.root, receipts_path=self.receipts, secret=None)
        self.assertFalse(report.ok)
        self.assertIn("signature key unavailable", {f.message for f in report.findings})

    def test_receipt_tampering_breaks_identity_and_chain(self):
        self._stamp("one.py", "print('one')\n")
        record = json.loads(self.receipts.read_text(encoding="utf-8"))
        record["metadata"]["author"] = "someone-else"
        self.receipts.write_text(json.dumps(record) + "\n", encoding="utf-8")
        report = bufftag.verify(root=self.root, receipts_path=self.receipts, secret=None)
        self.assertFalse(report.ok)
        codes = {finding.code for finding in report.findings}
        self.assertIn("receipt_invalid", codes)
        self.assertIn("metadata_drift", codes)

    def test_appending_to_a_tampered_log_is_refused(self):
        self._stamp("one.py", "print('one')\n")
        record = json.loads(self.receipts.read_text(encoding="utf-8"))
        record["sha256"] = "0" * 64
        self.receipts.write_text(json.dumps(record) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(bufftag.BufftagError, "receipt log is invalid"):
            self._stamp("two.py", "print('two')\n")

    def test_missing_receipt_is_never_treated_as_clean(self):
        path = self.root / "one.py"
        path.write_text(bufftag.render_header(_metadata()) + "\nprint('one')\n", encoding="utf-8")
        report = bufftag.verify(root=self.root, receipts_path=self.receipts, secret=None)
        self.assertFalse(report.ok)
        self.assertIn("receipt_missing", {finding.code for finding in report.findings})


class ScopeAndProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.receipts = self.root / ".bufftag" / "receipts.jsonl"

    def tearDown(self):
        self.temp.cleanup()

    def test_scan_is_recursive_and_never_follows_symlinks(self):
        nested = self.root / "a" / "b"
        nested.mkdir(parents=True)
        outside = Path(self.temp.name).parent / f"bufftag-outside-{os.getpid()}.py"
        outside.write_text("print('outside')\n", encoding="utf-8")
        (nested / "link.py").symlink_to(outside)
        try:
            report = bufftag.verify(root=self.root, receipts_path=self.receipts, secret=None)
            self.assertIn("a/b/link.py", {f.path for f in report.findings})
            self.assertIn("symlink_skipped", {f.code for f in report.findings})
        finally:
            outside.unlink(missing_ok=True)

    def test_require_complete_promotes_untagged_files_to_errors(self):
        (self.root / "plain.py").write_text("print('plain')\n", encoding="utf-8")
        normal = bufftag.verify(root=self.root, receipts_path=self.receipts, secret=None)
        strict = bufftag.verify(
            root=self.root,
            receipts_path=self.receipts,
            secret=None,
            require_complete=True,
        )
        self.assertTrue(normal.ok)
        self.assertFalse(strict.ok)

    def test_proposal_never_invents_origin_or_author(self):
        path = self.root / "sample.py"
        path.write_text('"""Does a bounded thing."""\nimport os\nfrom pathlib import Path\n', encoding="utf-8")
        result = bufftag.propose(self.root, path)
        self.assertEqual(result["metadata"]["origin"], "unverified")
        self.assertEqual(result["metadata"]["author"], "unverified")
        self.assertEqual(result["metadata"]["role"], "Does a bounded thing.")
        self.assertEqual(result["metadata"]["deps"], "os,pathlib")

    def test_watch_once_is_a_deterministic_single_pass(self):
        (self.root / "plain.py").write_text("print('plain')\n", encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = bufftag.main([
                "watch", str(self.root), "--once", "--json",
                "--receipts", str(self.receipts),
            ])
        self.assertEqual(status, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["files_scanned"], 1)
        self.assertIn("untagged", {finding["code"] for finding in payload["findings"]})


class LegacyCharacterizationTests(unittest.TestCase):
    """Safe probes of current legacy behavior; no legacy main() is executed."""

    @classmethod
    def setUpClass(cls):
        cls.dna_tag = _load_module("legacy_dna_tag", "tools/provenance/dna_tag_v1.py")
        cls.dna_parser = _load_module(
            "legacy_dna_parser", "RootBase/dna_backtagger/dna_parser.py"
        )
        cls.caps_stego = _load_module(
            "legacy_caps_stego", "tools/provenance/caps_stego.py"
        )
        cls.pheromone_store = _load_module(
            "legacy_pheromone_store", "tools/provenance/pheromone_store.py"
        )
        cls.BULL = _load_module("legacy_BULL", "BULL.py")

    def test_legacy_parser_accepts_a_docstring_decoy(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "decoy.py"
            path.write_text(
                '"""Documentation.\n# [DNA_TAG]\nORIGIN: forged\nPILLAR: fake\n'
                '# [/DNA_TAG]\n"""\nprint("hello")\n',
                encoding="utf-8",
            )
            metadata = self.dna_parser.extract_dna_header(path)
            self.assertEqual(metadata["ORIGIN"], "forged")

    def test_legacy_stamp_breaks_shebang_placement(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tool.py"
            path.write_text("#!/usr/bin/env python3\nprint('hello')\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.dna_tag.stamp_file(path, "device", {
                    "pillar": "test", "role": "test", "deps": "none",
                    "author": "test", "session": "2026-09-25", "tier": "3",
                })
            self.assertFalse(path.read_text(encoding="utf-8").startswith("#!"))

    def test_checked_in_ecosystem_map_contains_literal_placeholders(self):
        path = ROOT / "RootBase" / "dna_backtagger" / "dna_ecosystem_map.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        placeholders = {
            metadata.get("ORIGIN")
            for record in records
            for metadata in [record.get("metadata", {})]
        }
        self.assertIn("{origin}", placeholders)

    def test_bull_reports_clean_while_omitting_an_unmapped_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            nested = root / "unmapped" / "deep"
            nested.mkdir(parents=True)
            (nested / "orphan.py").write_text("print('orphan')\n", encoding="utf-8")
            output = io.StringIO()
            with patch.object(self.BULL, "HOME", root), contextlib.redirect_stdout(output):
                status = self.BULL.cmd_check()
            self.assertEqual(status, 0)
            self.assertIn("Clean", output.getvalue())

    def test_bull_claims_an_hop_log_but_writes_none(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "OutClaw"
            project.mkdir()
            target = project / "sample.py"
            target.write_text(
                "# [DNA_TAG]\n# ORIGIN: test\n# PILLAR: wrong\n"
                "# DEPS: none\n# ROLE: test\n# AUTHOR: test\n"
                "# SESSION: 2026-09-25\n# TIER: 3\n# [/DNA_TAG]\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with patch.object(self.BULL, "HOME", root), contextlib.redirect_stdout(output):
                status = self.BULL.cmd_fix(go=True)
            self.assertEqual(status, 0)
            self.assertIn("HOP_LOG: fix logged", output.getvalue())
            self.assertFalse(any("HOP_LOG" in path.name for path in root.rglob("*")))

    def test_pheromone_release_race_can_release_a_new_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            store_path = Path(temp) / "pheromones.jsonl"
            target = Path(temp) / "task.py"
            normalized = str(target.resolve())
            old = {
                "id": "old", "type": "TASK_CLAIM", "source": "old-agent",
                "path": normalized,
                "timestamp": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat(),
                "strength": 1.0, "decay_rate": 2.0, "payload": {},
            }
            store_path.write_text(json.dumps(old) + "\n", encoding="utf-8")

            store = self.pheromone_store.PheromoneStore(str(store_path))
            injected = False

            def racing_emit(type_, source, path="", strength=1.0, decay_rate=0.0, payload=None):
                nonlocal injected
                if type_ == "TASK_RELEASE" and not injected:
                    injected = True
                    self.pheromone_store.PheromoneStore.emit(
                        store, "TASK_CLAIM", source="new-agent", path=path
                    )
                return self.pheromone_store.PheromoneStore.emit(
                    store, type_, source, path, strength, decay_rate, payload
                )

            with patch.object(store, "emit", side_effect=racing_emit):
                released = self.pheromone_store.release_task(store, "old-agent", str(target))
            self.assertTrue(released)
            self.assertEqual(store.latest_task_event(str(target))["type"], "TASK_RELEASE")
            self.assertEqual(store.latest_task_event(str(target))["source"], "old-agent")

    def test_pheromone_emit_accepts_schema_violating_strength(self):
        with tempfile.TemporaryDirectory() as temp:
            store = self.pheromone_store.PheromoneStore(str(Path(temp) / "pheromones.jsonl"))
            event = store.emit("CONTRIBUTION", source="agent", strength=99.0, decay_rate=-7.0)
            self.assertEqual(event["strength"], 99.0)
            self.assertEqual(event["decay_rate"], -7.0)

    def test_caps_codec_has_no_integrity_failure_signal(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cover.txt"
            original = "tools/provenance/dna_tag.py"
            encoded = self.caps_stego.encode(original)
            carrier = next(index for index, char in enumerate(encoded) if char.isalpha())
            encoded = encoded[:carrier] + encoded[carrier].swapcase() + encoded[carrier + 1:]
            path.write_text(encoded, encoding="utf-8")
            self.assertNotEqual(self.caps_stego.decode_file(path), original)
            self.assertTrue(self.caps_stego.check(path)["ok"])


if __name__ == "__main__":
    unittest.main()
