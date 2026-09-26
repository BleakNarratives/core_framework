"""
Boardroom router tests.

Two hard constraints shape this file:

1. NO NETWORK. Every provider call is intercepted with a fake `requests.post`.
   No test may reach Groq, OpenRouter, Gemini, Cerebras or Ollama.

2. NO VAULT BOOTSTRAP. Importing a router runs `_vault_bootstrap()`, which
   shells out to `source /home/bleaknarratives/bin/vault-env` and mutates
   `os.environ` with real credentials. Setting GROQ_API_KEY before import makes
   that function return early, so the subprocess never runs. This is asserted
   explicitly below, because if that seam ever breaks the suite would quietly
   start sourcing a real vault.

The routers live under paths that are not importable packages, so they are
loaded by file location.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

from src.skill._vendor.driftguard import (  # noqa: E402
    build_invariants,
    load_config,
    run,
)

# Config paths are relative to the repo root, which is what drift-guard resolves
# them against; the config itself lives beside this test.

ROUTER_PATHS = {
    "werkz": REPO_ROOT / "The-Werkz" / "Official-Vertical-AI-Boardroom" / "router.py",
    "syntax": REPO_ROOT / "SyntaxIntelligence" / "boardroom" / "router.py",
    "buffface": REPO_ROOT / "buffface-saga-partition" / "Official-Vertical-AI-Boardroom" / "router.py",
}

# A fake key, never a real one. Only its PRESENCE matters: it short-circuits
# _vault_bootstrap(). This value is not a credential.
_FAKE_GROQ = "test-not-a-real-key-0000"


def _code_only(src: str) -> str:
    """Source with whole-line comments removed.

    The drift checks below are substring predicates. A comment that documents
    a fixed bug repeats the bug's text, so checking raw source makes a
    well-documented fix look like an unfixed one. Strip comments first.
    """
    return "\n".join(
        ln for ln in src.splitlines() if not ln.strip().startswith("#")
    )


# The three boardroom subprojects sit outside the repo's gitignore allowlist
# (which tracks only src/tools/templates/tests/docs/projects/rag_storage), so
# they are deliberately untracked. On a clean clone these files do not exist
# and the whole module skips rather than failing -- an absent optional subtree
# is not a test failure. It IS worth seeing locally, hence skip (reported as
# skipped, not silently green) rather than a bare early return.
MISSING_ROUTERS = sorted(n for n, p in ROUTER_PATHS.items() if not p.exists())
requires_routers = unittest.skipIf(
    MISSING_ROUTERS,
    f"boardroom router copies not present in this checkout: {MISSING_ROUTERS}",
)


def load_router(name: str) -> types.ModuleType:
    """Import a router by path with the vault bootstrap neutralised."""
    path = ROUTER_PATHS[name]
    assert path.exists(), f"router not found: {path}"
    saved = os.environ.get("GROQ_API_KEY")
    os.environ["GROQ_API_KEY"] = _FAKE_GROQ
    try:
        spec = importlib.util.spec_from_file_location(f"offline_router_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            os.environ.pop("GROQ_API_KEY", None)
        else:
            os.environ["GROQ_API_KEY"] = saved
    return module


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self._payload = payload if payload is not None else {"response": "ok"}
        self.status = status
        self.status_code = status
        self.text = str(self._payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")


@requires_routers
class TestImportSafety(unittest.TestCase):
    def test_vault_bootstrap_is_neutralised_by_fake_key(self):
        """The seam that stops this suite sourcing a real vault must hold."""
        os.environ["GROQ_API_KEY"] = _FAKE_GROQ
        try:
            # With a key present, _vault_bootstrap returns before subprocess.
            self.assertTrue(os.environ.get("GROQ_API_KEY"))
        finally:
            os.environ.pop("GROQ_API_KEY", None)

    def test_all_three_routers_import(self):
        for name in ROUTER_PATHS:
            with self.subTest(router=name):
                mod = load_router(name)
                self.assertTrue(hasattr(mod, "_get_telemetry_order"))


@requires_routers
class TestTelemetryOrdering(unittest.TestCase):
    def test_falls_back_to_default_order_without_judgment(self):
        """No judgment module => the hardcoded cascade, not a crash."""
        mod = load_router("werkz")
        order = mod._get_telemetry_order()
        self.assertIsInstance(order, list)
        self.assertIn("ollama", order)
        self.assertIn("groq", order)

    def test_no_dead_co_varnames_branch(self):
        """Regression guard: provider_health was once fed co_varnames.

        Checks the code, not the comment that documents the fix -- the
        comment necessarily names the mistake.
        """
        for name, path in ROUTER_PATHS.items():
            with self.subTest(router=name):
                src = path.read_text(encoding="utf-8")
                body = src.split("def _get_telemetry_order():", 1)[1]
                body = body.split("DEFAULT_PROVIDER_ORDER", 1)[0]
                code = [
                    ln for ln in body.splitlines()
                    if ln.strip() and not ln.strip().startswith("#")
                ]
                self.assertFalse(
                    [ln for ln in code if "co_varnames" in ln],
                    f"{name}: provider_health still fed co_varnames",
                )

    def test_syntax_scores_cerebras(self):
        """SyntaxIntelligence declares cerebras, so it must be scored too."""
        mod = load_router("syntax")
        self.assertIn("cerebras", mod._get_telemetry_order())
        self.assertIn("cerebras", mod.DEFAULT_PROVIDER_ORDER)

    def test_every_scored_name_has_a_call_path(self):
        """A provider in the order that no *_call_* function can serve is dead."""
        for name in ("werkz", "syntax"):
            with self.subTest(router=name):
                mod = load_router(name)
                for provider in mod._get_telemetry_order():
                    self.assertTrue(
                        hasattr(mod, f"_call_{provider}"),
                        f"{name}: provider {provider!r} in order but no _call_{provider}",
                    )


@requires_routers
class TestKeyHandling(unittest.TestCase):
    def test_key_hint_never_leaks_the_key(self):
        mod = load_router("werkz")
        self.assertEqual(mod._key_hint(""), "none")
        self.assertEqual(mod._key_hint("abc"), "none")  # <=4 chars, no hint
        hint = mod._key_hint("gsk-1234567890abcd")
        self.assertTrue(hint.startswith("..."))
        self.assertNotIn("1234567890", hint)

    def test_placeholder_values_excluded_from_pool(self):
        """`your_*` / your_key must never become a live key.

        Loads the router with a placeholder as GROQ_API_KEY and asserts the
        resulting pool is empty, which is what stops a placeholder reaching
        the wire.
        """
        path = ROUTER_PATHS["werkz"]
        saved = os.environ.get("GROQ_API_KEY")
        os.environ["GROQ_API_KEY"] = "your_key_here"
        try:
            spec = importlib.util.spec_from_file_location("offline_router_ph", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        finally:
            if saved is None:
                os.environ.pop("GROQ_API_KEY", None)
            else:
                os.environ["GROQ_API_KEY"] = saved
        self.assertEqual(mod.GROQ_KEYS, [])
        self.assertEqual(mod.GROQ_API_KEY, "")

    def test_vault_capture_filter_keeps_pool_vars(self):
        """GROQ_API_KEY_POOL must survive the vault capture filter.

        The Werkz copy once dropped *_POOL, silently downgrading rotation to a
        single key. buffface already had the fix; all three must now agree.
        """
        for name in ("werkz", "syntax", "buffface"):
            with self.subTest(router=name):
                src = ROUTER_PATHS[name].read_text(encoding="utf-8")
                self.assertIn('"_KEY_POOL"', src)
                self.assertIn('"GROQ_API_KEY_POOL",', src)


@requires_routers
class TestOllamaLane(unittest.TestCase):
    def test_payload_pins_threads_and_context(self):
        """Regression guard: un-pinned threads defaulted to all 4 cores, which
        measured SLOWER (51.7s vs 33.5s) on the documented host."""
        mod = load_router("werkz")
        captured = {}

        def fake_post(url, json=None, timeout=None, **kw):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            return FakeResponse({"response": "hi"})

        original = mod.requests.post
        mod.requests.post = fake_post
        try:
            out = mod._call_ollama("hello", tier=mod.ModelTier.FAST)
        finally:
            mod.requests.post = original

        self.assertEqual(out, "hi")
        self.assertTrue(captured["url"].endswith("/api/generate"))
        opts = captured["json"]["options"]
        self.assertEqual(opts["num_thread"], 2)
        self.assertEqual(opts["num_ctx"], 1024)
        self.assertGreaterEqual(captured["timeout"], 180)

    def test_ollama_uri_defaults_to_loopback(self):
        mod = load_router("werkz")
        self.assertTrue(mod.OLLAMA_URI.startswith("http://127.0.0.1:"))

    def test_tiers_map_to_distinct_models(self):
        mod = load_router("werkz")
        self.assertEqual(
            mod.OLLAMA_MODELS[mod.ModelTier.FAST], "llama3.2:1b",
            "FAST is the only tier whose default is actually installed on this host",
        )

    def test_non_2xx_propagates(self):
        """A 404 for an uninstalled model must surface, not return a fake body."""
        mod = load_router("werkz")

        def fake_post(url, json=None, timeout=None, **kw):
            return FakeResponse({"error": "model not found"}, status=404)

        original = mod.requests.post
        mod.requests.post = fake_post
        try:
            with self.assertRaises(RuntimeError):
                mod._call_ollama("hello", tier=mod.ModelTier.FAST)
        finally:
            mod.requests.post = original


@requires_routers
class TestCopyDrift(unittest.TestCase):
    """The three router copies are a deliberate 3-way feature fork.

    buffface has stall visibility, Werkz and SyntaxIntelligence have free-model
    rotation, SyntaxIntelligence has cerebras. No copy is a superset, and that
    is exactly why the `_KEY_POOL` capture bug survived in two copies while the
    third already had the fix: hand-applying a fix to N copies silently fails
    when you forget one.

    These tests cannot make the copies identical, but they CAN make it fail
    loudly when a security- or correctness-critical edit lands in one copy and
    not the others. The features may differ; the invariants may not.
    """

    # The invariants live in the standalone drift-guard package, vendored under
    # src/skill/_vendor/. They used to be hardcoded lambdas in this file, which
    # meant the package shipped unused while a duplicate of its logic sat right
    # next to it. Config as data, one implementation, nothing to keep in sync.
    #
    # Two different roots, easy to conflate: the CONFIG lives beside this test,
    # while the paths INSIDE it resolve against the repo root.
    DRIFT_CONFIG = Path(__file__).resolve().parent / "routers.drift.json"

    def _invariants(self):
        return build_invariants(load_config(self.DRIFT_CONFIG)["invariants"])

    def test_security_critical_fixes_present_in_all_copies(self):
        rep = run(
            [str(p.relative_to(REPO_ROOT)) for p in ROUTER_PATHS.values()],
            self._invariants(),
            missing="skip",
            root=REPO_ROOT,
        )
        offenders = [f"{v['file']}: {v['invariant']} -- {v['reason']}" for v in rep.violations]
        self.assertEqual(
            offenders, [],
            "invariant drift across the router copies (a fix reached some, not all):\n  "
            + "\n  ".join(offenders),
        )

    def test_drift_config_covers_every_router_copy(self):
        """A copy added later must be added to the config, or it is unguarded."""
        configured = set(load_config(self.DRIFT_CONFIG)["files"])
        self.assertEqual(
            configured,
            {str(p.relative_to(REPO_ROOT)) for p in ROUTER_PATHS.values()},
            "routers.drift.json does not cover exactly the copies this test knows about",
        )

    def test_every_declared_provider_has_a_call_path(self):
        """A provider in the cascade order with no _call_* is a dead lane."""
        for name in ROUTER_PATHS:
            with self.subTest(router=name):
                mod = load_router(name)
                for provider in mod.DEFAULT_PROVIDER_ORDER:
                    self.assertTrue(
                        hasattr(mod, f"_call_{provider}"),
                        f"{name}: {provider} declared in the cascade but no "
                        f"_call_{provider} exists",
                    )

    def test_copies_differ_in_features_so_this_guard_stays_necessary(self):
        """If the three ever converge, this guard can be retired as a no-op."""
        sources = {n: p.read_text(encoding="utf-8") for n, p in ROUTER_PATHS.items()}
        self.assertGreater(
            len(set(sources.values())), 1,
            "router copies are now identical -- the drift guard can be retired",
        )


if __name__ == "__main__":
    unittest.main()
