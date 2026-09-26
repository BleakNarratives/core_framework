"""
Vendored-copy parity.

`src/skill/_vendor/verified_cache.py` is a verbatim copy of the standalone
`verified-cache` package. A vendored copy is the obvious place for silent
divergence: someone fixes the library, forgets the copy, and the running system
keeps using code that no longer exists anywhere else.

This test makes that failure loud. It is the same idea as the drift guard,
applied to the one duplication that actually matters in this tree -- and it
dogfoods the packaged tool's premise, which is that invariants should be
enforced rather than remembered.

The canonical source lives outside the repository (it is a separate, publishable
repo). So when it is absent -- a clean clone, another machine -- the test
SKIPS rather than fails. The vendored copy is what ships; the upstream is a
development convenience.
"""
from __future__ import annotations

import hashlib
import os
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = REPO_ROOT / "src" / "skill" / "_vendor"

# module filename -> candidate locations for its canonical source, most
# specific first. Both packages follow the same vendoring rule, so the parity
# rule is written once and applied twice.
UPSTREAM_CANDIDATES = {
    "verified_cache.py": [
        REPO_ROOT / "verified-cache" / "verified_cache.py",
        Path.home() / "verified-cache" / "verified_cache.py",
    ],
    "driftguard.py": [
        REPO_ROOT / "drift-guard" / "driftguard.py",
        Path.home() / "drift-guard" / "driftguard.py",
    ],
}

SKIP_REASON = "canonical source not present in this checkout"


def _find_upstream(name):
    for p in UPSTREAM_CANDIDATES[name]:
        if p.exists():
            return p
    return None


UPSTREAM = {name: _find_upstream(name) for name in UPSTREAM_CANDIDATES}


class TestVendoredCopyExists(unittest.TestCase):
    """These run everywhere. The vendored copy ships, so it must always be here."""

    def test_vendored_modules_are_present(self):
        for name in UPSTREAM_CANDIDATES:
            p = VENDOR_DIR / name
            self.assertTrue(
                p.exists(),
                f"vendored module missing: {p}. The runtime and test suite import "
                f"it directly, so its absence breaks real code paths.",
            )

    def test_vendored_modules_are_importable(self):
        from src.skill._vendor.verified_cache import SidecarStore, Verification
        from src.skill._vendor.driftguard import run
        self.assertTrue(callable(SidecarStore))
        self.assertTrue(callable(Verification))
        self.assertTrue(callable(run))

    def test_scout_actually_uses_it(self):
        """Guards against the vendored copy being present but unused."""
        from src.skill import scout
        self.assertTrue(hasattr(scout, "SidecarStore"))


class TestParityWithUpstream(unittest.TestCase):
    """Skipped per-module: the upstream repos are development conveniences and
    are absent from a clean clone, but the vendored copy is what ships."""

    def _parity(self, name):
        up = UPSTREAM[name]
        if up is None:
            self.skipTest(f"{name}: {SKIP_REASON}")
        vend = VENDOR_DIR / name
        self.assertEqual(
            vend.read_bytes(), up.read_bytes(),
            f"vendored {name} has drifted from {up}. Either re-copy it "
            f"(`cp {up} {vend}`) or make the change upstream first. A vendored "
            f"fork nobody remembers is just a second source of truth.",
        )

    def test_verified_cache_is_byte_identical(self):
        self._parity("verified_cache.py")

    def test_driftguard_is_byte_identical(self):
        self._parity("driftguard.py")

    def test_digests_match_for_clear_error_messages(self):
        for name, up in UPSTREAM.items():
            if up is None:
                continue
            with self.subTest(module=name):
                v = hashlib.sha256((VENDOR_DIR / name).read_bytes()).hexdigest()
                u = hashlib.sha256(up.read_bytes()).hexdigest()
                self.assertEqual(v, u, f"{name}: vendored sha256={v[:12]} upstream sha256={u[:12]}")


if __name__ == "__main__":
    unittest.main()
