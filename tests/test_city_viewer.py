"""
Contract test: the Code City viewer consumes exactly what the scanner emits.

The viewer is HTML/Canvas and this environment has no browser, so its drawing
cannot be verified here. What CAN be verified -- and is the part that actually
breaks in practice -- is the data contract: if the scanner renames a field or
drops one, the viewer renders an empty city and reports nothing wrong.

So the viewer is parsed for the keys it reads, the scanner is run for real on a
temp tree, and the two are asserted to agree. A missing field is a hard failure
with both key sets in the message.
"""
from __future__ import annotations

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEWER = REPO_ROOT / "Code-City-Apocalypse" / "Code_City" / "viewer.html"
SCANNER = REPO_ROOT / "Code-City-Apocalypse" / "Code_City" / "repo_scanner.py"

requires_assets = unittest.skipIf(
    not (VIEWER.exists() and SCANNER.exists()),
    "Code City assets not present in this checkout",
)


def _load_scanner():
    spec = importlib.util.spec_from_file_location("contract_scanner", SCANNER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@requires_assets
class TestViewerScannerContract(unittest.TestCase):
    """The scanner produces X; the viewer must read X."""

    def setUp(self):
        self.rs = _load_scanner()
        self.html = VIEWER.read_text(encoding="utf-8")
        tmp = Path(tempfile.mkdtemp())
        (tmp / "clean.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        (tmp / "smelly.py").write_text(
            "\n".join("    " * 10 + f"x{i} = {i}  # TODO" for i in range(40)),
            encoding="utf-8",
        )
        self.city = self.rs.scan_repo(tmp)

    def _viewer_building_keys(self):
        # Property reads off building objects in the viewer's script.
        # The negative lookahead excludes method calls: `f.text()` is the JS
        # File API in the drop handler, not a building property, and counting it
        # produced a false "field the scanner never emits".
        pat = r"\bf\.(\w++)(?!\s*\()"
        return set(re.findall(pat, self.html)) | set(re.findall(r"\bb\.f\.(\w+)", self.html))

    def test_every_building_key_the_viewer_reads_is_emitted(self):
        emitted = set(self.city["buildings"][0].keys())
        read = self._viewer_building_keys()
        missing = read - emitted
        self.assertEqual(
            missing, set(),
            f"viewer reads building keys the scanner never emits: {sorted(missing)}. "
            f"Emitted: {sorted(emitted)}",
        )

    def test_viewer_reads_the_key_metrics(self):
        """Guard against someone simplifying the viewer into a blank canvas."""
        read = self._viewer_building_keys()
        for key in ("path", "language", "height", "flaw_score", "code_lines", "todos"):
            self.assertIn(key, read, f"viewer no longer reads {key!r}")

    def test_totals_keys_the_hud_reads_are_emitted(self):
        hud = self.html.split('id="s-files"')[0] + self.html.split("</div>")[0]
        read = set(re.findall(r"totals\)\.(\w+)", self.html)) | set(
            re.findall(r"t\.(\w+)\s*=", self.html))
        emitted = set(self.city["totals"].keys())
        self.assertEqual(read - emitted, set(),
                         f"hud reads totals keys the scanner never emits: {read - emitted}")

    def test_viewer_handles_the_real_payload_shape(self):
        """Sanity: the two buildings we built exercise every branch it draws."""
        langs = {b["language"] for b in self.city["buildings"]}
        self.assertIn("python", langs)
        self.assertTrue(any(b["flaw_score"] > 0 for b in self.city["buildings"]),
                        "fixture should include a flawed building")
        self.assertTrue(any(b["flaw_score"] == 0 for b in self.city["buildings"]),
                        "fixture should include a clean building")

    def test_viewer_is_self_contained(self):
        """No CDN, no build step, no network: it has to work from a file://."""
        html = VIEWER.read_text(encoding="utf-8")
        for bad in ("http://", "https://cdn", "unpkg", "jsdelivr", "cdnjs"):
            self.assertNotIn(bad, html, f"viewer references an external URL: {bad}")
        # The one fetch is same-origin and guarded; assert it is the only one.
        self.assertEqual(len(re.findall(r"\bfetch\(", html)), 1)


if __name__ == "__main__":
    unittest.main()
