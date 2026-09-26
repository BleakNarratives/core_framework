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
VENDORED = REPO_ROOT / "src" / "skill" / "_vendor" / "verified_cache.py"

# Candidate locations for the canonical source, most specific first.
UPSTREAM_CANDIDATES = [
    REPO_ROOT / "verified-cache" / "verified_cache.py",
    Path.home() / "verified-cache" / "verified_cache.py",
]

SKIP_REASON = "canonical verified-cache source not present in this checkout"


def _find_upstream():
    for p in UPSTREAM_CANDIDATES:
        if p.exists():
            return p
    return None


UPSTREAM = _find_upstream()


class TestVendoredCopyExists(unittest.TestCase):
    """These run everywhere. The vendored copy ships, so it must always be here."""

    def test_vendored_module_is_present(self):
        self.assertTrue(
            VENDORED.exists(),
            f"vendored module missing: {VENDORED}. The runtime imports it directly, "
            f"so its absence breaks every scout sidecar operation.",
        )

    def test_vendored_module_is_importable(self):
        from src.skill._vendor.verified_cache import SidecarStore, Verification
        self.assertTrue(callable(SidecarStore))
        self.assertTrue(callable(Verification))

    def test_scout_actually_uses_it(self):
        """Guards against the vendored copy being present but unused."""
        from src.skill import scout
        self.assertTrue(hasattr(scout, "SidecarStore"))


@unittest.skipIf(UPSTREAM is None, SKIP_REASON)
class TestParityWithUpstream(unittest.TestCase):
    def test_vendored_copy_is_byte_identical(self):
        self.assertEqual(
            VENDORED.read_bytes(),
            UPSTREAM.read_bytes(),
            f"vendored copy has drifted from {UPSTREAM}. Either re-copy it "
            f"(`cp {UPSTREAM} {VENDORED}`) or make the change upstream first. "
            f"A vendored fork that nobody remembers is just a second source of truth.",
        )

    def test_digest_matches_for_a_clear_error_message(self):
        """Independent confirmation, so a failure names both digests."""
        v = hashlib.sha256(VENDORED.read_bytes()).hexdigest()
        u = hashlib.sha256(UPSTREAM.read_bytes()).hexdigest()
        self.assertEqual(v, u, f"vendored sha256={v[:12]} upstream sha256={u[:12]}")


if __name__ == "__main__":
    unittest.main()
