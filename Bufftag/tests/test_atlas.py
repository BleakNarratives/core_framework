"""Offline tests for explicit FKA/AKA movement routing."""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import os
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

from Bufftag import atlas, route_run


class AtlasCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.atlas_path = self.root / ".bufftag" / "moves.jsonl"
        self.modules_to_remove: list[str] = []

    def tearDown(self):
        while self.modules_to_remove:
            sys.modules.pop(self.modules_to_remove.pop(), None)
        while str(self.root) in sys.path:
            sys.path.remove(str(self.root))
        self.temp.cleanup()

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def record(self, secret=None, **overrides):
        values = {
            "workspace": self.root,
            "atlas_path": self.atlas_path,
            "old_path": "old/location.py",
            "new_path": "canonical/location.py",
            "actor": " Buffy",
            "reason": "consolidation",
            "aka": ["legacy/location.py"],
            "evidence": ["decision:test"],
        }
        values.update(overrides)
        return atlas.record_route(secret=secret, **values)


class MovementLedgerTests(AtlasCase):
    def test_signed_route_records_fka_aka_reason_evidence_and_move_hashes(self):
        old = self.write("old/location.py", "VALUE = 'old'\n")
        new = self.write("canonical/location.py", "VALUE = 'new'\n")
        secret = b"movement-test-key"
        record = self.record(
            secret=secret,
            old_module="legacy_location",
            new_module="canonical_location",
        )
        self.assertEqual(record["old_sha256"], atlas._file_hash(old))
        self.assertEqual(record["new_sha256"], atlas._file_hash(new))
        self.assertEqual(record["aka"], ["legacy/location.py"])
        self.assertEqual(record["signature"]["mode"], "hmac-sha256")

        by_path, by_module = atlas.active_routes(self.atlas_path, secret)
        self.assertEqual(by_path["old/location.py"].new_path, "canonical/location.py")
        self.assertEqual(by_alias := by_path["legacy/location.py"], by_path["old/location.py"])
        self.assertEqual(by_alias.new_path, "canonical/location.py")
        self.assertEqual(by_module["legacy_location"].new_module, "canonical_location")
        report = atlas.verify_atlas(
            workspace=self.root, atlas_path=self.atlas_path, secret=secret
        )
        self.assertTrue(report.ok, report.as_dict())

    def test_signed_atlas_fails_closed_without_key(self):
        self.write("canonical/location.py", "VALUE = 1\n")
        self.record(secret=b"private-key")
        with self.assertRaisesRegex(atlas.AtlasError, "signature key unavailable"):
            atlas.active_routes(self.atlas_path, None)

    def test_tampered_route_breaks_record_identity_and_chain(self):
        self.write("canonical/location.py", "VALUE = 1\n")
        self.record()
        record = json.loads(self.atlas_path.read_text(encoding="utf-8"))
        record["new_path"] = "somewhere/else.py"
        self.atlas_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(atlas.AtlasError, "failed integrity"):
            atlas.active_routes(self.atlas_path, None)

    def test_conflicting_active_alias_is_refused_at_record_time(self):
        self.write("canonical/location.py", "VALUE = 1\n")
        self.write("other/location.py", "VALUE = 2\n")
        self.record()
        with self.assertRaisesRegex(atlas.AtlasError, "already maps elsewhere"):
            self.record(
                old_path="second.py",
                new_path="other/location.py",
                aka=["legacy/location.py"],
            )

    def test_retraction_removes_only_the_explicit_route(self):
        self.write("canonical/location.py", "VALUE = 1\n")
        route = self.record()
        retraction = atlas.retract_route(
            atlas_path=self.atlas_path,
            route_id=route["record_id"],
            actor="operator",
            reason="route no longer valid",
        )
        by_path, by_module = atlas.active_routes(self.atlas_path, None)
        self.assertEqual(by_path, {})
        self.assertEqual(by_module, {})
        self.assertEqual(retraction["action"], "retract")

    def test_later_canonical_edits_warn_but_do_not_break_route(self):
        target = self.write("canonical/location.py", "VALUE = 1\n")
        self.record()
        target.write_text("VALUE = 2\n", encoding="utf-8")
        report = atlas.verify_atlas(
            workspace=self.root, atlas_path=self.atlas_path, secret=None
        )
        self.assertTrue(report.ok)
        self.assertIn("route_content_changed", {finding.code for finding in report.findings})

    def test_escape_and_invalid_timestamp_are_refused(self):
        self.write("canonical/location.py", "VALUE = 1\n")
        with self.assertRaisesRegex(atlas.AtlasError, "relative"):
            self.record(new_path="../outside.py")
        with self.assertRaisesRegex(atlas.AtlasError, "timezone"):
            self.record(created_at="2026-09-25T12:00:00")


class RollbackAnchorTests(AtlasCase):
    def setUp(self):
        super().setUp()
        self.anchor_path = self.root / "separate" / "movement-head.json"
        self.secret = b"external-head-key"

    def test_signed_external_head_authenticates_checkpoint(self):
        self.write("canonical/location.py", "VALUE = 1\n")
        self.record(secret=self.secret)
        anchor = atlas.create_anchor(
            atlas_path=self.atlas_path,
            anchor_path=self.anchor_path,
            actor="operator",
            reason="approved baseline",
            secret=self.secret,
            created_at="2026-09-25T12:00:00+00:00",
        )
        self.assertEqual(anchor["signature"]["mode"], "hmac-sha256")
        self.assertEqual(anchor["ledger_records"], 1)
        findings = atlas.verify_anchor(
            atlas_path=self.atlas_path,
            anchor_path=self.anchor_path,
            secret=self.secret,
        )
        self.assertFalse([finding for finding in findings if finding.severity == "error"])

    def test_external_head_allows_valid_ledger_advance(self):
        self.write("canonical/location.py", "VALUE = 1\n")
        self.record(secret=self.secret)
        atlas.create_anchor(
            atlas_path=self.atlas_path,
            anchor_path=self.anchor_path,
            actor="operator",
            reason="approved baseline",
            secret=self.secret,
        )
        self.write("other/location.py", "VALUE = 2\n")
        self.record(
            secret=self.secret,
            old_path="old/other.py",
            new_path="other/location.py",
            aka=[],
        )
        findings = atlas.verify_anchor(
            atlas_path=self.atlas_path,
            anchor_path=self.anchor_path,
            secret=self.secret,
        )
        self.assertIn("anchor_behind", {finding.code for finding in findings})
        self.assertFalse([finding for finding in findings if finding.severity == "error"])

    def test_external_head_detects_valid_prefix_rollback(self):
        self.write("canonical/location.py", "VALUE = 1\n")
        self.record(secret=self.secret)
        anchored_line = self.atlas_path.read_text(encoding="utf-8")
        atlas.create_anchor(
            atlas_path=self.atlas_path,
            anchor_path=self.anchor_path,
            actor="operator",
            reason="approved baseline",
            secret=self.secret,
        )
        self.write("other/location.py", "VALUE = 2\n")
        self.record(
            secret=self.secret,
            old_path="old/other.py",
            new_path="other/location.py",
            aka=[],
        )
        self.atlas_path.write_text("", encoding="utf-8")
        findings = atlas.verify_anchor(
            atlas_path=self.atlas_path,
            anchor_path=self.anchor_path,
            secret=self.secret,
        )
        self.assertIn("movement_rollback", {finding.code for finding in findings})
        self.atlas_path.write_text(anchored_line, encoding="utf-8")

    def test_tampered_or_unsigned_external_head_fails_closed(self):
        self.write("canonical/location.py", "VALUE = 1\n")
        self.record(secret=self.secret)
        atlas.create_anchor(
            atlas_path=self.atlas_path,
            anchor_path=self.anchor_path,
            actor="operator",
            reason="approved baseline",
            secret=self.secret,
        )
        anchor = json.loads(self.anchor_path.read_text(encoding="utf-8"))
        anchor["ledger_head"] = "0" * 64
        self.anchor_path.write_text(json.dumps(anchor) + "\n", encoding="utf-8")
        findings = atlas.verify_anchor(
            atlas_path=self.atlas_path,
            anchor_path=self.anchor_path,
            secret=self.secret,
        )
        self.assertIn("anchor_invalid", {finding.code for finding in findings})

        anchor["signature"] = {"mode": "unsigned"}
        self.anchor_path.write_text(json.dumps(anchor) + "\n", encoding="utf-8")
        findings = atlas.verify_anchor(
            atlas_path=self.atlas_path,
            anchor_path=self.anchor_path,
            secret=self.secret,
        )
        self.assertIn("unsigned anchor", " ".join(finding.message for finding in findings))

    def test_signed_external_head_attests_an_existing_unsigned_prefix(self):
        self.write("canonical/location.py", "VALUE = 1\n")
        self.record()  # Historical unsigned route.
        anchor = atlas.create_anchor(
            atlas_path=self.atlas_path,
            anchor_path=self.anchor_path,
            actor="operator",
            reason="operator-attested historical prefix",
            secret=self.secret,
        )
        self.assertEqual(anchor["ledger_records"], 1)
        with self.assertRaisesRegex(atlas.AtlasError, "unsigned record"):
            atlas.active_routes(self.atlas_path, self.secret)
        by_path, _ = atlas.active_routes(
            self.atlas_path,
            self.secret,
            allow_unsigned_existing=True,
        )
        self.assertIn("old/location.py", by_path)
        report = atlas.verify_atlas(
            workspace=self.root,
            atlas_path=self.atlas_path,
            secret=self.secret,
            anchor_path=self.anchor_path,
            allow_unsigned_existing=True,
        )
        self.assertTrue(report.ok, report.as_dict())

    def test_anchor_creation_requires_key_and_nonempty_valid_ledger(self):
        with self.assertRaisesRegex(atlas.AtlasError, "empty movement atlas"):
            atlas.create_anchor(
                atlas_path=self.atlas_path,
                anchor_path=self.anchor_path,
                actor="operator",
                reason="baseline",
                secret=self.secret,
            )
        self.write("canonical/location.py", "VALUE = 1\n")
        self.record(secret=self.secret)
        with self.assertRaisesRegex(atlas.AtlasError, "require an HMAC key"):
            atlas.create_anchor(
                atlas_path=self.atlas_path,
                anchor_path=self.anchor_path,
                actor="operator",
                reason="baseline",
                secret=b"",
            )


class WorkspaceIntegrationTests(unittest.TestCase):
    """Exercise the concept against the repository's observed broken import edge."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.atlas_path = Path(self.temp.name) / "moves.jsonl"
        self.root = Path(__file__).resolve().parents[2]
        self.redirects: list[tuple[str, str, str]] = []

    def tearDown(self):
        for name in ("pheromone_store", "projects.agents.scouts.scout_clout"):
            sys.modules.pop(name, None)
        self.temp.cleanup()

    def test_workspace_scout_uses_canonical_import_without_runtime_redirect(self):
        module = importlib.import_module("projects.agents.scouts.scout_clout")
        self.assertTrue(hasattr(module, "PheromoneStore"))
        self.assertEqual(self.redirects, [])


class RuntimeRoutingTests(AtlasCase):
    def setUp(self):
        super().setUp()
        sys.path.insert(0, str(self.root))
        self.redirects: list[tuple[str, str, str]] = []

    def handler(self, old, route, kind):
        self.redirects.append((old, route.new_path, kind))

    def test_missing_old_import_resolves_only_through_explicit_module_route(self):
        self.write("canonical_mod.py", "VALUE = 42\n")
        self.record(
            old_path="old/canonical_mod.py",
            new_path="canonical_mod.py",
            aka=[],
            old_module="legacy_mod",
            new_module="canonical_mod",
        )
        self.modules_to_remove.extend(["legacy_mod", "canonical_mod"])
        with route_run.RoutingSession(
            atlas_path=self.atlas_path,
            workspace=self.root,
            on_redirect=self.handler,
        ):
            module = importlib.import_module("legacy_mod")
            self.assertEqual(module.VALUE, 42)
        self.assertEqual(self.redirects, [("legacy_mod", "canonical_mod.py", "import")])

    def test_same_module_name_routes_to_canonical_file(self):
        self.write("moved_mod.py", "VALUE = 'canonical'\n")
        self.record(
            old_path="old/moved_mod.py",
            new_path="moved_mod.py",
            aka=[],
            old_module="moved_mod",
            new_module="moved_mod",
        )
        self.modules_to_remove.append("moved_mod")
        with route_run.RoutingSession(
            atlas_path=self.atlas_path,
            workspace=self.root,
            on_redirect=self.handler,
        ):
            module = importlib.import_module("moved_mod")
            self.assertEqual(module.__file__, str(self.root / "moved_mod.py"))
            self.assertEqual(module.VALUE, "canonical")

    def test_unknown_import_is_not_guessed(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("module_with_no_route")

    def test_route_run_executes_canonical_script_and_restores_process_state(self):
        self.write(
            "canonical/tool.py",
            "import sys\nVALUE = '7'\nprint('VALUE=' + VALUE)\nprint('ARGS=' + ','.join(sys.argv[1:]))\n",
        )
        self.record(
            old_path="old/tool.py",
            new_path="canonical/tool.py",
            aka=["old-alias/tool.py"],
        )
        previous_hook = sys.excepthook
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            route_run.route_run(
                atlas_path=self.atlas_path,
                workspace=self.root,
                old_script="old-alias/tool.py",
                arguments=["alpha", "beta"],
                on_redirect=self.handler,
            )
        self.assertIn("VALUE=7", output.getvalue())
        self.assertIn("ARGS=alpha,beta", output.getvalue())
        self.assertEqual(self.redirects[0][2], "script")
        self.assertIs(sys.excepthook, previous_hook)
        self.assertFalse(any(
            isinstance(finder, route_run.AtlasImportFinder) for finder in sys.meta_path
        ))

    def test_traceback_display_preserves_old_path_and_annotates_new_address(self):
        target = self.write("canonical/location.py", "raise RuntimeError('boom')\n")
        self.record()
        by_path, _ = atlas.active_routes(self.atlas_path, None)
        old_absolute = self.root / "old" / "location.py"
        text = f'Traceback (most recent call last):\n  File "{old_absolute}", line 1, in old\n'
        rendered = route_run.annotate_traceback_text(text, self.root, by_path)
        self.assertIn(f'File "{old_absolute}" → "canonical/location.py"', rendered)
        self.assertIn(str(old_absolute), rendered)
        self.assertEqual(str(target), str(self.root / "canonical/location.py"))

    def test_default_redirect_handler_emits_a_warning(self):
        self.write("canonical/location.py", "VALUE = 1\n")
        route_record = self.record()
        route = atlas.active_routes(self.atlas_path, None)[0]["old/location.py"]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            route_run.default_redirect_handler("old/location.py", route, "script")
        self.assertEqual(len(caught), 1)
        self.assertIn(route_record["record_id"], str(caught[0].message))

    def test_runtime_refuses_ledger_rolled_back_below_external_head(self):
        secret = b"runtime-anchor-key"
        anchor_path = self.root / "external" / "head.json"
        self.write("canonical/location.py", "VALUE = 1\n")
        self.record(secret=secret)
        atlas.create_anchor(
            atlas_path=self.atlas_path,
            anchor_path=anchor_path,
            actor="operator",
            reason="approved runtime baseline",
            secret=secret,
        )
        self.atlas_path.write_text("", encoding="utf-8")
        with self.assertRaisesRegex(atlas.AtlasError, "external movement head rejected"):
            route_run.RoutingSession(
                atlas_path=self.atlas_path,
                workspace=self.root,
                secret=secret,
                anchor_path=anchor_path,
            )


if __name__ == "__main__":
    unittest.main()
